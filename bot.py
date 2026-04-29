#!/usr/bin/env python3
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import init_db
import handlers

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Запуск бота"""
    logger.info("Инициализация базы данных...")
    await init_db()
    
    logger.info("Запуск бота...")
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрация обработчиков сообщений
    @dp.message(F.text == "/start")
    async def start_cmd(message: types.Message):
        await handlers.handle_start(message, bot)
    
    @dp.message(F.text == "/cancel")
    async def cancel_cmd(message: types.Message):
        await handlers.handle_cancel(message)
    
    @dp.message(F.text == "❌ Отмена")
    async def cancel_btn_cmd(message: types.Message):
        await handlers.handle_cancel(message)
    
    @dp.message(F.text == "✅ Открыть смену")
    async def open_shift_cmd(message: types.Message):
        await handlers.handle_open_shift(message, bot)
    
    @dp.message(F.text == "❌ Закрыть смену")
    async def close_shift_cmd(message: types.Message):
        await handlers.handle_close_shift(message, bot)
    
    @dp.message(F.text == "☕ Начать перерыв")
    async def break_start_cmd(message: types.Message):
        await handlers.handle_break_start(message, bot)
    
    @dp.message(F.text == "✅ Завершить перерыв")
    async def break_end_cmd(message: types.Message):
        await handlers.handle_break_end(message, bot)
    
    @dp.message(F.text == "📈 Моя статистика")
    async def my_stats_cmd(message: types.Message):
        await handlers.handle_my_stats(message)
    
    @dp.message(F.text == "👥 Активные смены")
    async def active_shifts_cmd(message: types.Message):
        await handlers.handle_active_shifts(message)
    
    @dp.message(F.text == "📋 Все сотрудники")
    async def all_employees_cmd(message: types.Message):
        await handlers.handle_all_employees(message)
    
    @dp.message(F.text == "📊 Статистика сотрудника")
    async def admin_stats_cmd(message: types.Message):
        await handlers.handle_admin_stats(message)
    
    @dp.message(F.text == "⚙️ Суперадмин панель")
    async def superadmin_panel_cmd(message: types.Message):
        await handlers.handle_superadmin_panel(message)
    
    @dp.message(F.text == "👥 Все сотрудники (включая неодобренных)")
    async def all_employees_unapproved_cmd(message: types.Message):
        await handlers.handle_all_employees_unapproved(message)
    
    @dp.message(F.text == "✅ Одобрить сотрудников")
    async def approve_employees_cmd(message: types.Message):
        await handlers.handle_approve_employees(message)
    
    @dp.message(F.text == "✏️ Редактировать сотрудника")
    async def edit_employee_cmd(message: types.Message):
        await handlers.handle_edit_employee(message)
    
    @dp.message(F.text == "📅 Редактировать смену")
    async def edit_shift_cmd(message: types.Message):
        await handlers.handle_edit_shift(message)
    
    @dp.message(F.text == "📊 Недельный отчёт")
    async def week_report_cmd(message: types.Message):
        await handlers.handle_week_report(message, bot)
    
    @dp.message(F.text == "◀️ Назад")
    async def back_cmd(message: types.Message):
        await handlers.handle_back(message, bot)
    
    # Обработка текстовых сообщений
    @dp.message(F.text)
    async def text_handler(message: types.Message):
        telegram_id = message.from_user.id
        
        # Проверяем регистрацию
        if telegram_id in handlers.user_states and handlers.user_states[telegram_id] in [
            handlers.STATE_REGISTER_FIO, 
            handlers.STATE_REGISTER_WB_ID
        ]:
            await handlers.handle_register(message, bot)
            return
        
        # Проверяем редактирование
        if await handlers.process_edit_input(message, bot):
            return
        
        # Если ничего не подошло
        if not await handlers.handle_register(message, bot):
            keyboard = await handlers.get_main_keyboard(telegram_id, bot)
            await message.answer("Используйте кнопки для навигации", reply_markup=keyboard)
    
    # Обработка фото
    @dp.message(F.photo)
    async def photo_handler(message: types.Message):
        telegram_id = message.from_user.id
        
        if telegram_id in handlers.user_states:
            state = handlers.user_states[telegram_id]
            if state == handlers.STATE_WAITING_SHIFT_PHOTO:
                await handlers.handle_shift_photo(message, bot)
            elif state == handlers.STATE_WAITING_BREAK_PHOTO:
                await handlers.handle_break_photo(message, bot)
            else:
                await message.answer("Фото не требуется в данный момент.")
        else:
            await message.answer("Фото не требуется в данный момент.")
    
    # Обработка инлайн callback'ов
    @dp.callback_query()
    async def callback_handler(callback: types.CallbackQuery):
        await handlers.handle_callback_query(callback, bot)
    
    logger.info("Бот запущен и готов к работе!")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
