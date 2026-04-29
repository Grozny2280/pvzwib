import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import pytz
import re

from aiogram import Bot, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

from config import ADMIN_IDS, SUPERADMIN_IDS, PVZ_ADDRESS, GROUP_CHAT_ID, TIMEZONE
import database as db

# Состояния пользователей
user_states: Dict[int, str] = {}
user_data: Dict[int, Dict] = {}

# Константы состояний
STATE_REGISTER_FIO = "register_fio"
STATE_REGISTER_WB_ID = "register_wb_id"
STATE_WAITING_SHIFT_PHOTO = "waiting_shift_photo"
STATE_WAITING_BREAK_PHOTO = "waiting_break_photo"
STATE_EDIT_EMPLOYEE_NAME = "edit_employee_name"
STATE_EDIT_EMPLOYEE_WB = "edit_employee_wb"
STATE_EDIT_SHIFT_OPEN = "edit_shift_open"
STATE_EDIT_SHIFT_CLOSE = "edit_shift_close"

TZ = pytz.timezone(TIMEZONE)
_last_notification = {}


def now_msk() -> datetime:
    return datetime.now(TZ)


def fmt_datetime(dt_str: str) -> str:
    """Форматирование даты и времени"""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return dt_str


def fmt_duration(minutes: int) -> str:
    """Форматирование длительности"""
    if minutes is None:
        return "0ч 0м"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}ч {mins}м"


async def notify_admins(bot: Bot, message: str, photo_id: str = None, notification_key: str = None):
    """Уведомление всех администраторов"""
    if notification_key:
        current_time = datetime.now().timestamp()
        if notification_key in _last_notification:
            if current_time - _last_notification[notification_key] < 2:
                return
        _last_notification[notification_key] = current_time
    
    all_admin_ids = list(set(ADMIN_IDS + SUPERADMIN_IDS))
    
    for admin_id in all_admin_ids:
        try:
            if photo_id:
                await bot.send_photo(admin_id, photo_id, caption=message)
            else:
                await bot.send_message(admin_id, message)
        except Exception:
            pass
    
    if GROUP_CHAT_ID:
        try:
            if photo_id:
                await bot.send_photo(GROUP_CHAT_ID, photo_id, caption=message)
            else:
                await bot.send_message(GROUP_CHAT_ID, message)
        except Exception:
            pass


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


async def get_main_keyboard(telegram_id: int, bot: Bot = None) -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    is_superadmin = telegram_id in SUPERADMIN_IDS
    is_admin = telegram_id in ADMIN_IDS or is_superadmin
    is_approved_employee = await db.is_approved(telegram_id)
    
    keyboard = []
    
    if is_approved_employee:
        active_shift = await db.get_active_shift(telegram_id)
        active_break = await db.get_active_break(telegram_id)
        
        if active_shift:
            if active_break:
                keyboard.append([KeyboardButton(text="✅ Завершить перерыв")])
                keyboard.append([KeyboardButton(text="❌ Закрыть смену")])
            else:
                keyboard.append([KeyboardButton(text="☕ Начать перерыв")])
                keyboard.append([KeyboardButton(text="❌ Закрыть смену")])
        else:
            keyboard.append([KeyboardButton(text="✅ Открыть смену")])
        
        keyboard.append([KeyboardButton(text="📈 Моя статистика")])
    
    if is_admin and is_approved_employee:
        if keyboard:
            keyboard.append([KeyboardButton(text="─" * 20)])
    
    if is_admin:
        keyboard.append([KeyboardButton(text="📊 Статистика сотрудника")])
        keyboard.append([KeyboardButton(text="👥 Активные смены")])
        keyboard.append([KeyboardButton(text="📋 Все сотрудники")])
        
        if is_superadmin:
            keyboard.append([KeyboardButton(text="⚙️ Суперадмин панель")])
    
    if not keyboard:
        keyboard = [[KeyboardButton(text="⏳ Ожидание подтверждения")]]
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_superadmin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура суперадмина"""
    keyboard = [
        [KeyboardButton(text="👥 Все сотрудники (включая неодобренных)")],
        [KeyboardButton(text="✅ Одобрить сотрудников")],
        [KeyboardButton(text="✏️ Редактировать сотрудника")],
        [KeyboardButton(text="📅 Редактировать смену")],
        [KeyboardButton(text="📊 Недельный отчёт")],
        [KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


async def update_user_keyboard(message: Message, bot: Bot):
    """Обновление клавиатуры"""
    telegram_id = message.from_user.id
    keyboard = await get_main_keyboard(telegram_id, bot)
    await message.answer("🔄 Меню обновлено", reply_markup=keyboard)


# ============= ОСНОВНЫЕ ОБРАБОТЧИКИ =============

async def handle_start(message: Message, bot: Bot):
    """Обработчик команды /start"""
    telegram_id = message.from_user.id
    is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
    
    if not await db.is_employee_exists(telegram_id):
        user_states[telegram_id] = STATE_REGISTER_FIO
        await message.answer(
            "👋 Добро пожаловать в систему учёта рабочего времени ПВЗ!\n\n"
            "Для начала работы необходимо пройти регистрацию.\n\n"
            "Введите ваше ФИО (полностью):",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    if not await db.is_approved(telegram_id):
        if is_admin:
            await db.approve_employee(telegram_id)
            await message.answer("✅ Ваша учётная запись администратора автоматически подтверждена!")
        else:
            await message.answer(
                "⏳ Ваша регистрация ожидает подтверждения администратором.\n"
                "Пожалуйста, ожидайте. Вам придёт уведомление после подтверждения."
            )
            return
    
    employee = await db.get_employee(telegram_id)
    active_shift = await db.get_active_shift(telegram_id)
    active_break = await db.get_active_break(telegram_id)
    
    keyboard = await get_main_keyboard(telegram_id, bot)
    
    status_text = f"✅ Добро пожаловать, {employee['full_name']}!\n"
    
    if telegram_id in SUPERADMIN_IDS:
        status_text += f"👑 Роль: Суперадминистратор\n"
    elif telegram_id in ADMIN_IDS:
        status_text += f"👤 Роль: Администратор\n"
    else:
        status_text += f"👤 Роль: Сотрудник\n"
    
    if active_shift:
        opened_at = fmt_datetime(active_shift["opened_at"])
        status_text += f"\n🟢 Смена открыта с {opened_at}"
        if active_break:
            status_text += f"\n🔴 Вы на перерыве с {fmt_datetime(active_break['started_at'])}"
    else:
        status_text += f"\n⚪ Смена закрыта"
    
    await message.answer(status_text, reply_markup=keyboard)


async def handle_cancel(message: Message):
    """Отмена текущей операции"""
    telegram_id = message.from_user.id
    
    if telegram_id in user_states:
        state = user_states[telegram_id]
        if state.startswith("register"):
            del user_states[telegram_id]
            if telegram_id in user_data:
                del user_data[telegram_id]
            await message.answer(
                "❌ Регистрация отменена.\n"
                "Для начала новой регистрации используйте команду /start",
                reply_markup=types.ReplyKeyboardRemove()
            )
        else:
            del user_states[telegram_id]
            if telegram_id in user_data:
                del user_data[telegram_id]
            keyboard = await get_main_keyboard(telegram_id, message.bot)
            await message.answer("❌ Действие отменено.", reply_markup=keyboard)
    else:
        await message.answer("Нет активных операций для отмены.")


async def handle_register(message: Message, bot: Bot):
    """Обработка регистрации"""
    telegram_id = message.from_user.id
    
    if telegram_id not in user_states:
        return False
    
    state = user_states[telegram_id]
    
    if telegram_id not in user_data:
        user_data[telegram_id] = {}
    
    try:
        if state == STATE_REGISTER_FIO:
            full_name = message.text.strip()
            
            if len(full_name.split()) < 2:
                await message.answer(
                    "❌ Пожалуйста, введите полное ФИО (минимум Имя и Фамилию).\n\n"
                    "Пример: Иванов Иван Иванович"
                )
                return True
            
            user_data[telegram_id]["full_name"] = full_name
            user_states[telegram_id] = STATE_REGISTER_WB_ID
            
            await message.answer(
                f"✅ ФИО сохранено: {full_name}\n\n"
                "Теперь введите ваш ID сотрудника Wildberries:"
            )
            return True
        
        elif state == STATE_REGISTER_WB_ID:
            wb_id = message.text.strip()
            
            if not wb_id or len(wb_id) > 100:
                await message.answer(
                    "❌ Пожалуйста, введите корректный ID сотрудника WB.\n\n"
                    "ID должен быть не пустым и не длиннее 100 символов."
                )
                return True
            
            full_name = user_data[telegram_id].get("full_name")
            
            if not full_name:
                user_states[telegram_id] = STATE_REGISTER_FIO
                await message.answer(
                    "❌ Ошибка: данные потеряны. Пожалуйста, начните регистрацию заново.\n\n"
                    "Введите ваше ФИО:"
                )
                return True
            
            success = await db.register_employee(telegram_id, full_name, wb_id)
            
            if success:
                is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
                
                if is_admin:
                    await db.approve_employee(telegram_id)
                    await message.answer(
                        "✅ Регистрация успешно завершена!\n\n"
                        "Вы авторизованы как АДМИНИСТРАТОР, учётная запись автоматически подтверждена.\n"
                        "Теперь вы можете начать работу, используя кнопки меню.",
                        reply_markup=await get_main_keyboard(telegram_id, bot)
                    )
                else:
                    await message.answer(
                        "✅ Регистрация успешно завершена!\n\n"
                        "Ваша заявка отправлена администратору на подтверждение.\n"
                        "После подтверждения вы сможете начать работу.\n\n"
                        "Ожидайте уведомления.",
                        reply_markup=types.ReplyKeyboardRemove()
                    )
                    
                    for superadmin_id in SUPERADMIN_IDS:
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{telegram_id}")]
                        ])
                        try:
                            await bot.send_message(
                                superadmin_id,
                                f"🆕 НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ!\n\n"
                                f"👤 ФИО: {full_name}\n"
                                f"🆔 WB ID: {wb_id}\n"
                                f"📱 Telegram ID: {telegram_id}\n"
                                f"👤 Username: @{message.from_user.username if message.from_user.username else 'не указан'}",
                                reply_markup=keyboard
                            )
                        except Exception:
                            pass
            else:
                await message.answer(
                    "❌ Ошибка регистрации!\n\n"
                    "Возможные причины:\n"
                    "• Вы уже зарегистрированы (используйте /start для входа)\n"
                    "• Техническая ошибка базы данных\n\n"
                    "Если проблема повторяется, обратитесь к администратору."
                )
            
            del user_states[telegram_id]
            del user_data[telegram_id]
            return True
    
    except Exception as e:
        print(f"Ошибка при регистрации {telegram_id}: {e}")
        await message.answer(
            "❌ Произошла техническая ошибка при регистрации.\n"
            "Пожалуйста, попробуйте позже или обратитесь к администратору."
        )
        if telegram_id in user_states:
            del user_states[telegram_id]
        if telegram_id in user_data:
            del user_data[telegram_id]
        return True
    
    return False


async def handle_open_shift(message: Message, bot: Bot):
    """Открытие смены"""
    telegram_id = message.from_user.id
    
    if not await db.is_approved(telegram_id):
        await message.answer("❌ Ваша учетная запись не подтверждена.")
        return
    
    if await db.get_active_shift(telegram_id):
        await message.answer("❌ У вас уже открыта смена! Сначала закройте её.")
        return
    
    await message.answer(
        f"📸 Пожалуйста, отправьте фото ПВЗ ({PVZ_ADDRESS})\n"
        "Фото необходимо для подтверждения начала смены.",
        reply_markup=get_cancel_keyboard()
    )
    user_states[telegram_id] = STATE_WAITING_SHIFT_PHOTO


async def handle_shift_photo(message: Message, bot: Bot):
    """Обработка фото для открытия смены"""
    telegram_id = message.from_user.id
    
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото.")
        return
    
    photo_id = message.photo[-1].file_id
    shift_id = await db.open_shift(telegram_id, photo_id)
    
    if shift_id:
        open_time = now_msk()
        await message.answer(
            f"✅ Смена открыта!\n"
            f"Время начала: {fmt_datetime(open_time.isoformat())}\n"
            f"ПВЗ: {PVZ_ADDRESS}"
        )
        
        employee = await db.get_employee(telegram_id)
        is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
        
        if not is_admin:
            await notify_admins(
                bot, 
                f"🟢 СОТРУДНИК ОТКРЫЛ СМЕНУ\n"
                f"👤 {employee['full_name']}\n"
                f"🆔 WB ID: {employee['wb_employee_id']}\n"
                f"🕐 Время: {fmt_datetime(open_time.isoformat())}\n"
                f"📍 {PVZ_ADDRESS}",
                photo_id,
                f"shift_open_{telegram_id}"
            )
        elif GROUP_CHAT_ID:
            await bot.send_message(
                GROUP_CHAT_ID,
                f"🟢 АДМИНИСТРАТОР {employee['full_name']} открыл смену\n"
                f"🕐 Время: {fmt_datetime(open_time.isoformat())}"
            )
        
        await update_user_keyboard(message, bot)
    else:
        await message.answer("❌ Ошибка открытия смены.")
    
    if telegram_id in user_states:
        del user_states[telegram_id]


async def handle_close_shift(message: Message, bot: Bot):
    """Закрытие смены"""
    telegram_id = message.from_user.id
    
    if not await db.is_approved(telegram_id):
        await message.answer("❌ Ваша учетная запись не подтверждена.")
        return
    
    if not await db.get_active_shift(telegram_id):
        await message.answer("❌ У вас нет открытой смены.")
        return
    
    if await db.get_active_break(telegram_id):
        await message.answer("❌ Вы находитесь на перерыве. Сначала завершите перерыв.")
        return
    
    duration = await db.close_shift(telegram_id)
    if duration:
        close_time = now_msk()
        await message.answer(
            f"✅ Смена закрыта!\n"
            f"Время закрытия: {fmt_datetime(close_time.isoformat())}\n"
            f"Длительность: {fmt_duration(duration)}"
        )
        
        employee = await db.get_employee(telegram_id)
        is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
        
        if not is_admin:
            await notify_admins(
                bot,
                f"🔴 СОТРУДНИК ЗАКРЫЛ СМЕНУ\n"
                f"👤 {employee['full_name']}\n"
                f"🆔 WB ID: {employee['wb_employee_id']}\n"
                f"🕐 Время закрытия: {fmt_datetime(close_time.isoformat())}\n"
                f"⏱️ Длительность: {fmt_duration(duration)}",
                notification_key=f"shift_close_{telegram_id}"
            )
        elif GROUP_CHAT_ID:
            await bot.send_message(
                GROUP_CHAT_ID,
                f"🔴 АДМИНИСТРАТОР {employee['full_name']} закрыл смену\n"
                f"⏱️ Длительность: {fmt_duration(duration)}"
            )
        
        await update_user_keyboard(message, bot)
    else:
        await message.answer("❌ Ошибка закрытия смены.")


async def handle_break_start(message: Message, bot: Bot):
    """Начало перерыва"""
    telegram_id = message.from_user.id
    
    if not await db.is_approved(telegram_id):
        await message.answer("❌ Ваша учетная запись не подтверждена.")
        return
    
    if not await db.get_active_shift(telegram_id):
        await message.answer("❌ У вас нет открытой смены.")
        return
    
    if await db.get_active_break(telegram_id):
        await message.answer("❌ Вы уже на перерыве!")
        return
    
    await message.answer(
        "📸 Отправьте фото для подтверждения начала перерыва:",
        reply_markup=get_cancel_keyboard()
    )
    user_states[telegram_id] = STATE_WAITING_BREAK_PHOTO


async def handle_break_photo(message: Message, bot: Bot):
    """Обработка фото для начала перерыва"""
    telegram_id = message.from_user.id
    
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото.")
        return
    
    photo_id = message.photo[-1].file_id
    break_id = await db.start_break(telegram_id, photo_id)
    
    if break_id:
        break_start_time = now_msk()
        await message.answer(
            f"☕ Перерыв начался!\n"
            f"Время начала: {fmt_datetime(break_start_time.isoformat())}"
        )
        
        employee = await db.get_employee(telegram_id)
        is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
        
        if not is_admin:
            await notify_admins(
                bot,
                f"☕ СОТРУДНИК НАЧАЛ ПЕРЕРЫВ\n"
                f"👤 {employee['full_name']}\n"
                f"🆔 WB ID: {employee['wb_employee_id']}\n"
                f"🕐 Время: {fmt_datetime(break_start_time.isoformat())}",
                photo_id,
                f"break_start_{telegram_id}"
            )
        elif GROUP_CHAT_ID:
            await bot.send_message(
                GROUP_CHAT_ID,
                f"☕ АДМИНИСТРАТОР {employee['full_name']} начал перерыв\n"
                f"🕐 Время: {fmt_datetime(break_start_time.isoformat())}"
            )
        
        await update_user_keyboard(message, bot)
        asyncio.create_task(check_break_duration(telegram_id, bot, break_id, break_start_time))
    else:
        await message.answer("❌ Ошибка начала перерыва.")
    
    if telegram_id in user_states:
        del user_states[telegram_id]


async def check_break_duration(telegram_id: int, bot: Bot, break_id: int, break_start_time: datetime):
    """Проверка длительности перерыва"""
    await asyncio.sleep(15 * 60)
    
    break_obj = await db.get_active_break(telegram_id)
    if break_obj and break_obj["id"] == break_id:
        employee = await db.get_employee(telegram_id)
        current_duration = int((now_msk() - break_start_time).total_seconds() / 60)
        
        is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
        
        if not is_admin:
            await notify_admins(
                bot,
                f"⚠️ ВНИМАНИЕ! ПЕРЕРЫВ БОЛЕЕ 15 МИНУТ\n"
                f"👤 {employee['full_name']}\n"
                f"🆔 WB ID: {employee['wb_employee_id']}\n"
                f"🕐 Начало перерыва: {fmt_datetime(break_start_time.isoformat())}\n"
                f"⏱️ Длительность: {fmt_duration(current_duration)}"
            )
        elif GROUP_CHAT_ID:
            await bot.send_message(
                GROUP_CHAT_ID,
                f"⚠️ ВНИМАНИЕ! АДМИНИСТРАТОР {employee['full_name']} на перерыве более 15 минут!\n"
                f"⏱️ Длительность: {fmt_duration(current_duration)}"
            )


async def handle_break_end(message: Message, bot: Bot):
    """Завершение перерыва"""
    telegram_id = message.from_user.id
    
    if not await db.is_approved(telegram_id):
        await message.answer("❌ Ваша учетная запись не подтверждена.")
        return
    
    if not await db.get_active_break(telegram_id):
        await message.answer("❌ У вас нет активного перерыва.")
        return
    
    duration = await db.end_break(telegram_id)
    if duration is not None:
        end_time = now_msk()
        await message.answer(
            f"✅ Перерыв завершён!\n"
            f"Время завершения: {fmt_datetime(end_time.isoformat())}\n"
            f"Длительность: {fmt_duration(duration)}"
        )
        
        employee = await db.get_employee(telegram_id)
        is_admin = telegram_id in ADMIN_IDS or telegram_id in SUPERADMIN_IDS
        
        if not is_admin:
            await notify_admins(
                bot,
                f"✅ СОТРУДНИК ЗАВЕРШИЛ ПЕРЕРЫВ\n"
                f"👤 {employee['full_name']}\n"
                f"🆔 WB ID: {employee['wb_employee_id']}\n"
                f"⏱️ Длительность: {fmt_duration(duration)}",
                notification_key=f"break_end_{telegram_id}"
            )
        elif GROUP_CHAT_ID:
            await bot.send_message(
                GROUP_CHAT_ID,
                f"✅ АДМИНИСТРАТОР {employee['full_name']} завершил перерыв\n"
                f"⏱️ Длительность: {fmt_duration(duration)}"
            )
        
        await update_user_keyboard(message, bot)
    else:
        await message.answer("❌ Ошибка завершения перерыва.")


async def handle_my_stats(message: Message):
    """Просмотр своей статистики"""
    telegram_id = message.from_user.id
    
    if not await db.is_approved(telegram_id):
        await message.answer("❌ Ваша учетная запись не подтверждена.")
        return
    
    stats = await db.get_week_stats(telegram_id)
    employee = await db.get_employee(telegram_id)
    
    text = (
        f"📊 Статистика за неделю для {employee['full_name']}:\n\n"
        f"📅 Количество смен: {stats['shifts_count']}\n"
        f"⏱️ Отработанные часы: {stats['total_hours']} ч\n"
        f"☕ Количество перерывов: {stats['breaks_count']}\n"
        f"⏰ Время перерывов: {stats['total_breaks_hours']} ч"
    )
    await message.answer(text)


async def handle_active_shifts(message: Message):
    """Просмотр активных смен"""
    telegram_id = message.from_user.id
    
    if telegram_id not in ADMIN_IDS and telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    active_employees = await db.get_active_employees()
    
    if not active_employees:
        await message.answer("📭 Нет активных смен.")
        return
    
    text = "👥 Активные смены:\n\n"
    for emp in active_employees:
        status = "🔴 НА ПЕРЕРЫВЕ" if emp["on_break"] else "🟢 РАБОТАЕТ"
        is_admin = emp["telegram_id"] in ADMIN_IDS or emp["telegram_id"] in SUPERADMIN_IDS
        admin_mark = " [АДМИН]" if is_admin else ""
        
        text += (
            f"👤 {emp['full_name']}{admin_mark}\n"
            f"   {status}\n"
            f"   ⏱️ Работает: {fmt_duration(emp['duration_minutes'])}\n"
            f"   🕐 Начало: {fmt_datetime(emp['opened_at'])}\n"
        )
        if emp["break_started"]:
            break_duration = int((now_msk() - datetime.fromisoformat(emp["break_started"])).total_seconds() / 60)
            text += f"   ☕ Перерыв: {fmt_duration(break_duration)}\n"
        text += "\n"
    
    await message.answer(text)


async def handle_all_employees(message: Message):
    """Список всех сотрудников"""
    telegram_id = message.from_user.id
    
    if telegram_id not in ADMIN_IDS and telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    employees = await db.get_all_employees(include_unapproved=False)
    
    if not employees:
        await message.answer("📭 Нет зарегистрированных сотрудников.")
        return
    
    text = "📋 Список сотрудников:\n\n"
    for emp in employees:
        is_admin = emp['telegram_id'] in ADMIN_IDS or emp['telegram_id'] in SUPERADMIN_IDS
        admin_mark = " [АДМИН]" if is_admin else ""
        
        text += f"👤 {emp['full_name']}{admin_mark}\n"
        text += f"   ID: {emp['wb_employee_id']}\n"
        text += f"   Telegram: {emp['telegram_id']}\n"
        text += f"   Регистрация: {fmt_datetime(emp['registered_at'])}\n\n"
    
    await message.answer(text)


async def handle_admin_stats(message: Message):
    """Статистика сотрудника для админа"""
    telegram_id = message.from_user.id
    
    if telegram_id not in ADMIN_IDS and telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    employees = await db.get_all_employees(include_unapproved=True)
    
    if not employees:
        await message.answer("📭 Нет сотрудников.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{emp['full_name']} ({emp['wb_employee_id']}){' [АДМИН]' if emp['telegram_id'] in ADMIN_IDS or emp['telegram_id'] in SUPERADMIN_IDS else ''}", 
            callback_data=f"admin_stats_{emp['telegram_id']}"
        )]
        for emp in employees
    ])
    
    await message.answer("Выберите сотрудника:", reply_markup=keyboard)


async def handle_superadmin_panel(message: Message):
    """Суперадмин панель"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    await message.answer("⚙️ Суперадмин панель", reply_markup=get_superadmin_keyboard())


async def handle_all_employees_unapproved(message: Message):
    """Все сотрудники включая неодобренных"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    employees = await db.get_all_employees(include_unapproved=True)
    
    if not employees:
        await message.answer("📭 Нет зарегистрированных сотрудников.")
        return
    
    text = "📋 Все сотрудники (включая неодобренных):\n\n"
    for emp in employees:
        status = "✅ Одобрен" if emp['approved'] else "⏳ Не одобрен"
        is_admin = emp['telegram_id'] in ADMIN_IDS or emp['telegram_id'] in SUPERADMIN_IDS
        admin_mark = " [АДМИН]" if is_admin else ""
        
        text += f"👤 {emp['full_name']}{admin_mark}\n"
        text += f"   ID: {emp['wb_employee_id']}\n"
        text += f"   Telegram: {emp['telegram_id']}\n"
        text += f"   Статус: {status}\n"
        text += f"   Регистрация: {fmt_datetime(emp['registered_at'])}\n\n"
    
    await message.answer(text)


async def handle_approve_employees(message: Message):
    """Одобрение сотрудников"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    unapproved = await db.get_unapproved_employees()
    unapproved = [emp for emp in unapproved if emp['telegram_id'] not in ADMIN_IDS and emp['telegram_id'] not in SUPERADMIN_IDS]
    
    if not unapproved:
        await message.answer("📭 Нет неодобренных сотрудников.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{emp['full_name']} ({emp['wb_employee_id']})", callback_data=f"approve_{emp['telegram_id']}")]
        for emp in unapproved
    ])
    
    await message.answer("Выберите сотрудника для одобрения:", reply_markup=keyboard)


async def handle_edit_employee(message: Message):
    """Редактирование сотрудника"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    employees = await db.get_all_employees(include_unapproved=True)
    
    if not employees:
        await message.answer("📭 Нет сотрудников.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{emp['full_name']} ({emp['wb_employee_id']}){' [АДМИН]' if emp['telegram_id'] in ADMIN_IDS or emp['telegram_id'] in SUPERADMIN_IDS else ''}", 
            callback_data=f"edit_emp_{emp['telegram_id']}"
        )]
        for emp in employees
    ])
    
    await message.answer("Выберите сотрудника для редактирования:", reply_markup=keyboard)


async def handle_edit_shift(message: Message):
    """Редактирование смены"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    employees = await db.get_all_employees(include_unapproved=False)
    
    if not employees:
        await message.answer("📭 Нет сотрудников.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{emp['full_name']} ({emp['wb_employee_id']})", callback_data=f"edit_shift_list_{emp['telegram_id']}")]
        for emp in employees
    ])
    
    await message.answer("Выберите сотрудника, чью смену хотите отредактировать:", reply_markup=keyboard)


async def handle_week_report(message: Message, bot: Bot):
    """Недельный отчёт"""
    telegram_id = message.from_user.id
    
    if telegram_id not in SUPERADMIN_IDS:
        await message.answer("❌ Нет доступа.")
        return
    
    all_stats = await db.get_all_week_stats()
    
    if not all_stats:
        await message.answer("📭 Нет данных за неделю.")
        return
    
    text = "📊 НЕДЕЛЬНЫЙ ОТЧЁТ\n"
    text += f"📅 Период: последние 7 дней\n"
    text += f"{'='*40}\n\n"
    
    total_shifts = 0
    total_hours = 0
    
    for stat in all_stats:
        is_admin = stat['telegram_id'] in ADMIN_IDS or stat['telegram_id'] in SUPERADMIN_IDS
        admin_mark = " [АДМИН]" if is_admin else ""
        
        text += (
            f"👤 {stat['full_name']}{admin_mark} (ID: {stat['wb_employee_id']})\n"
            f"   📅 Смен: {stat['shifts_count']}\n"
            f"   ⏱️ Часов: {stat['total_hours']}\n"
            f"   ☕ Перерывов: {stat['breaks_count']}\n"
            f"   ⏰ Время перерывов: {stat['total_breaks_hours']} ч\n\n"
        )
        total_shifts += stat['shifts_count']
        total_hours += stat['total_hours']
    
    text += f"{'='*40}\n"
    text += f"📊 ИТОГО:\n"
    text += f"📅 Всего смен: {total_shifts}\n"
    text += f"⏱️ Всего часов: {round(total_hours, 2)}\n"
    
    await message.answer(text[:4000])
    
    for admin_id in SUPERADMIN_IDS:
        try:
            await bot.send_message(admin_id, text[:4000])
        except Exception:
            pass


async def handle_back(message: Message, bot: Bot):
    """Возврат в главное меню"""
    keyboard = await get_main_keyboard(message.from_user.id, bot)
    await message.answer("Главное меню", reply_markup=keyboard)


# ============= INLINE CALLBACKS =============

async def handle_callback_query(callback: CallbackQuery, bot: Bot):
    """Обработка инлайн кнопок"""
    await callback.answer()
    data = callback.data
    
    if data.startswith("approve_"):
        emp_id = int(data.split("_")[1])
        
        await db.approve_employee(emp_id)
        await callback.message.edit_text(f"✅ Сотрудник одобрен!")
        
        try:
            employee = await db.get_employee(emp_id)
            await bot.send_message(
                emp_id, 
                f"✅ Ваша регистрация одобрена!\n"
                f"Добро пожаловать в команду, {employee['full_name']}!\n\n"
                f"Теперь вы можете открыть смену через главное меню."
            )
        except Exception:
            pass
        
        employee = await db.get_employee(emp_id)
        await notify_admins(bot, f"✅ Сотрудник {employee['full_name']} одобрен")
    
    elif data.startswith("admin_stats_"):
        emp_id = int(data.split("_")[2])
        stats = await db.get_week_stats(emp_id)
        employee = await db.get_employee(emp_id)
        
        text = (
            f"📊 Статистика для {employee['full_name']}:\n\n"
            f"📅 Количество смен: {stats['shifts_count']}\n"
            f"⏱️ Отработанные часы: {stats['total_hours']} ч\n"
            f"☕ Количество перерывов: {stats['breaks_count']}\n"
            f"⏰ Время перерывов: {stats['total_breaks_hours']} ч"
        )
        
        await callback.message.answer(text)
        await callback.message.delete()
    
    elif data.startswith("edit_emp_"):
        emp_id = int(data.split("_")[2])
        user_data[callback.from_user.id] = {"edit_employee_id": emp_id}
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data=f"edit_emp_name_{emp_id}")],
            [InlineKeyboardButton(text="✏️ Изменить WB ID", callback_data=f"edit_emp_wb_{emp_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ])
        
        await callback.message.edit_text("Что хотите изменить?", reply_markup=keyboard)
    
    elif data.startswith("edit_emp_name_"):
        emp_id = int(data.split("_")[3])
        user_states[callback.from_user.id] = STATE_EDIT_EMPLOYEE_NAME
        user_data[callback.from_user.id] = {"edit_employee_id": emp_id}
        
        await callback.message.edit_text("Введите новое ФИО:", reply_markup=get_cancel_keyboard())
    
    elif data.startswith("edit_emp_wb_"):
        emp_id = int(data.split("_")[3])
        user_states[callback.from_user.id] = STATE_EDIT_EMPLOYEE_WB
        user_data[callback.from_user.id] = {"edit_employee_id": emp_id}
        
        await callback.message.edit_text("Введите новый WB ID:", reply_markup=get_cancel_keyboard())
    
    elif data.startswith("edit_shift_list_"):
        emp_id = int(data.split("_")[3])
        shifts = await db.get_employee_shifts(emp_id)
        
        if not shifts:
            await callback.message.edit_text("У этого сотрудника нет смен.")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📅 {fmt_datetime(s['opened_at'])} - {fmt_datetime(s['closed_at']) if s['closed_at'] else 'активна'}",
                callback_data=f"edit_shift_{s['id']}"
            )]
            for s in shifts[:10]
        ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")])
        
        user_data[callback.from_user.id] = {"edit_shift_employee": emp_id}
        await callback.message.edit_text("Выберите смену для редактирования:", reply_markup=keyboard)
    
    elif data.startswith("edit_shift_"):
        shift_id = int(data.split("_")[2])
        if callback.from_user.id not in user_data:
            user_data[callback.from_user.id] = {}
        user_data[callback.from_user.id]["edit_shift_id"] = shift_id
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Изменить время начала", callback_data=f"edit_shift_open_{shift_id}")],
            [InlineKeyboardButton(text="⏰ Изменить время окончания", callback_data=f"edit_shift_close_{shift_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить смену", callback_data=f"delete_shift_{shift_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ])
        
        await callback.message.edit_text("Что хотите изменить?", reply_markup=keyboard)
    
    elif data.startswith("edit_shift_open_"):
        shift_id = int(data.split("_")[3])
        user_states[callback.from_user.id] = STATE_EDIT_SHIFT_OPEN
        user_data[callback.from_user.id]["edit_shift_id"] = shift_id
        
        await callback.message.edit_text(
            "Введите новое время начала смены:\n\n"
            "Формат: ГГГГ-ММ-ДД ЧЧ:ММ:СС\n"
            "Пример: 2025-01-15 09:00:00\n\n"
            "Или используйте относительное время:\n"
            "+2 часа, -30 минут",
            reply_markup=get_cancel_keyboard()
        )
    
    elif data.startswith("edit_shift_close_"):
        shift_id = int(data.split("_")[3])
        user_states[callback.from_user.id] = STATE_EDIT_SHIFT_CLOSE
        user_data[callback.from_user.id]["edit_shift_id"] = shift_id
        
        await callback.message.edit_text(
            "Введите новое время окончания смены:\n\n"
            "Формат: ГГГГ-ММ-ДД ЧЧ:ММ:СС\n"
            "Пример: 2025-01-15 18:00:00\n\n"
            "Или используйте относительное время:\n"
            "+2 часа, -30 минут",
            reply_markup=get_cancel_keyboard()
        )
    
    elif data.startswith("delete_shift_"):
        shift_id = int(data.split("_")[2])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{shift_id}")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="cancel_edit")]
        ])
        
        await callback.message.edit_text("Вы уверены, что хотите удалить эту смену?", reply_markup=keyboard)
    
    elif data.startswith("confirm_delete_"):
        shift_id = int(data.split("_")[2])
        await db.delete_shift(shift_id)
        await callback.message.edit_text("✅ Смена удалена!")
    
    elif data.startswith("cancel_edit"):
        if callback.from_user.id in user_states:
            del user_states[callback.from_user.id]
        if callback.from_user.id in user_data:
            del user_data[callback.from_user.id]
        await callback.message.delete()


# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============

async def process_edit_input(message: Message, bot: Bot):
    """Обработка ввода при редактировании"""
    telegram_id = message.from_user.id
    state = user_states.get(telegram_id)
    
    if state == STATE_EDIT_EMPLOYEE_NAME:
        emp_id = user_data[telegram_id]["edit_employee_id"]
        await db.update_employee(emp_id, full_name=message.text)
        await message.answer(f"✅ ФИО изменено на: {message.text}")
        del user_states[telegram_id]
        del user_data[telegram_id]
        keyboard = await get_main_keyboard(telegram_id, bot)
        await message.answer("Главное меню", reply_markup=keyboard)
        return True
    
    elif state == STATE_EDIT_EMPLOYEE_WB:
        emp_id = user_data[telegram_id]["edit_employee_id"]
        await db.update_employee(emp_id, wb_employee_id=message.text)
        await message.answer(f"✅ WB ID изменён на: {message.text}")
        del user_states[telegram_id]
        del user_data[telegram_id]
        keyboard = await get_main_keyboard(telegram_id, bot)
        await message.answer("Главное меню", reply_markup=keyboard)
        return True
    
    elif state in [STATE_EDIT_SHIFT_OPEN, STATE_EDIT_SHIFT_CLOSE]:
        shift_id = user_data[telegram_id]["edit_shift_id"]
        new_time = message.text.strip()
        
        try:
            if new_time.startswith("+"):
                hours = 0
                minutes = 0
                if 'час' in new_time or 'ч' in new_time:
                    hours_match = re.search(r'(\d+)\s*ч', new_time)
                    if hours_match:
                        hours = int(hours_match.group(1))
                if 'минут' in new_time or 'м' in new_time:
                    minutes_match = re.search(r'(\d+)\s*м', new_time)
                    if minutes_match:
                        minutes = int(minutes_match.group(1))
                new_dt = now_msk() + timedelta(hours=hours, minutes=minutes)
            elif new_time.startswith("-"):
                hours = 0
                minutes = 0
                if 'час' in new_time or 'ч' in new_time:
                    hours_match = re.search(r'(\d+)\s*ч', new_time)
                    if hours_match:
                        hours = int(hours_match.group(1))
                if 'минут' in new_time or 'м' in new_time:
                    minutes_match = re.search(r'(\d+)\s*м', new_time)
                    if minutes_match:
                        minutes = int(minutes_match.group(1))
                new_dt = now_msk() - timedelta(hours=hours, minutes=minutes)
            else:
                new_dt = datetime.strptime(new_time, "%Y-%m-%d %H:%M:%S")
                new_dt = TZ.localize(new_dt)
            
            if state == STATE_EDIT_SHIFT_OPEN:
                await db.update_shift(shift_id, new_open_time=new_dt.isoformat())
                await message.answer(f"✅ Время начала смены изменено на {fmt_datetime(new_dt.isoformat())}")
            else:
                await db.update_shift(shift_id, new_close_time=new_dt.isoformat())
                await message.answer(f"✅ Время окончания смены изменено на {fmt_datetime(new_dt.isoformat())}")
            
            del user_states[telegram_id]
            del user_data[telegram_id]
            keyboard = await get_main_keyboard(telegram_id, bot)
            await message.answer("Главное меню", reply_markup=keyboard)
            return True
            
        except Exception as e:
            await message.answer(f"❌ Ошибка формата времени. Используйте формат: ГГГГ-ММ-ДД ЧЧ:ММ:СС или относительное время (+2 часа, -30 минут)")
            return True
    
    return False
