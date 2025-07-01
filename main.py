# main.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# --- Импорт конфигурации и модулей ---
import config
# Важно: нужно немного доработать ваши файлы, чтобы они не запускались при импорте
# и возвращали данные, а не просто печатали их.
# Представим, что они доработаны и содержат функции:
# get_strava_data(), get_garmin_data(), get_suunto_data()
import strava
import garmin
import suunto

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- Инициализация бота и диспетчера ---
bot = Bot(token=config.TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# --- Клавиатуры ---
main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Strava 🏃", callback_data="fetch_strava")],
    [InlineKeyboardButton(text="Garmin ⌚️", callback_data="fetch_garmin")],
    [InlineKeyboardButton(text="Suunto 🧭", callback_data="fetch_suunto")]
])

# --- Обработчики команд и кнопок ---

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Этот обработчик будет вызван, когда пользователь нажмет `/start`
    """
    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Я твой ИИ-тренер. Я могу анализировать твои тренировки "
        "и давать рекомендации.\n\n"
        "С какого сервиса хочешь получить данные?",
        reply_markup=main_menu_keyboard
    )


@dp.callback_query(F.data.startswith("fetch_"))
async def process_fetch_callback(callback: CallbackQuery):
    """
    Обрабатывает нажатия на кнопки выбора сервиса.
    """
    service = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    await callback.message.answer(f"⏳ Начинаю запрос данных из {service.capitalize()}...")
    
    # Скрываем кнопки после нажатия
    await callback.message.edit_reply_markup(reply_markup=None)

    data = ""
    # В зависимости от выбора вызываем соответствующую функцию
    if service == "strava":
        # В реальном приложении токен нужно брать из БД для конкретного user_id
        data = strava.get_strava_data(config.STRAVA_ACCESS_TOKEN)
    elif service == "garmin":
        data = garmin.get_garmin_data(config.GARMIN_EMAIL, config.GARMIN_PASSWORD)
    elif service == "suunto":
        data = suunto.get_suunto_data(config.SUUNTO_ACCESS_TOKEN, config.SUUNTO_API_KEY)
    
    # Отправляем полученные данные пользователю
    await callback.message.answer(f"<b>Отчет из {service.capitalize()}:</b>\n<pre>{data}</pre>")
    
    # --- ЗАГЛУШКА ДЛЯ AI-АНАЛИЗА ---
    ai_recommendation = analyze_workout_with_ai(data)
    await callback.message.answer(f"<b>🤖 Рекомендации от ИИ:</b>\n{ai_recommendation}")
    
    # Предлагаем сделать новый запрос
    await callback.message.answer("Хотите запросить данные с другого сервиса?", reply_markup=main_menu_keyboard)
    
    await callback.answer()


def analyze_workout_with_ai(workout_data: str) -> str:
    """
    ЗАГЛУШКА: Функция для анализа данных с помощью ИИ.
    В будущем здесь будет логика обработки данных и вызов LLM.
    """
    if "ошибка" in workout_data.lower() or "не найдены" in workout_data.lower():
        return "Не удалось получить данные для анализа."
        
    # Простой анализ на основе ключевых слов для примера
    recommendation = (
        "Отличная работа! Похоже, это была интенсивная тренировка. "
        "Не забудь хорошо восстановиться. "
        "Рекомендую следующую тренировку сделать легкой, с пульсом в зоне 2."
    )
    return recommendation


async def main() -> None:
    """
    Основная функция для запуска бота.
    """
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())