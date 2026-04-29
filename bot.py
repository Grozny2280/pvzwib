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
