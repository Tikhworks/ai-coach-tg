# main.py

import asyncio
import logging
import os
import sys
import json
import sqlite3
from datetime import date, timedelta
from cryptography.fernet import Fernet
from urllib.parse import urlencode

# --- Необходимые библиотеки ---
# pip install aiogram google-generativeai stravalib cryptography aiohttp
# Примечание: garminconnect больше не используется

import requests
import google.generativeai as genai
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from stravalib.client import Client
# Garmin SDK предназначен для декодирования файлов, а не для API. Мы используем OAuth.

# ==============================================================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==============================================================================

# --- Ключи и токены (ВАЖНО: ЗАПОЛНИТЕ ЭТИ ПОЛЯ) ---
TELEGRAM_BOT_TOKEN = "8062193958:AAGjIUkYG_YCjsWrfgs6TDzK3SU7_e8QnZI"
GEMINI_API_KEY = "AIzaSyDMsXs9h8jAyo7GRIMxoLv0_p2peb3cUXw"
ENCRYPTION_KEY = b'jgKPVRDS3T_n80PN-ldK8zwoSytl7cZYbO3DpW48hdg='

# --- Настройки OAuth и веб-сервера (ВАЖНО: ЗАПОЛНИТЕ ЭТИ ПОЛЯ) ---
# URL, по которому доступен ваш бот. Если запускаете локально, используйте ngrok.
BASE_URL = "http://your_public_ip_or_domain:8080" 

STRAVA_CLIENT_ID = "166736"
STRAVA_CLIENT_SECRET = "65614e2855a564d6612c520cf102c860819c0d11"

GARMIN_CLIENT_ID = "YOUR_GARMIN_CLIENT_ID"
GARMIN_CLIENT_SECRET = "YOUR_GARMIN_CLIENT_SECRET"

SUUNTO_CLIENT_ID = "YOUR_SUUNTO_CLIENT_ID"
SUUNTO_CLIENT_SECRET = "YOUR_SUUNTO_CLIENT_SECRET"

# --- Общие настройки ---
DB_FILE = 'ai_coach.db'
POLL_INTERVAL_SECONDS = 3600

# --- Настройка логирования и клиентов API ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')
cipher_suite = Fernet(ENCRYPTION_KEY)
try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Ошибка конфигурации Gemini: {e}")

# ==============================================================================
# 2. СЛОЙ БАЗЫ ДАННЫХ
# ==============================================================================
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS credentials (id INTEGER PRIMARY KEY, user_id INTEGER, service TEXT, creds_json TEXT, UNIQUE(user_id, service))')
        cursor.execute('CREATE TABLE IF NOT EXISTS processed_workouts (workout_id TEXT PRIMARY KEY, user_id INTEGER, analysis_text TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS friends (id INTEGER PRIMARY KEY, user_id_1 INTEGER, user_id_2 INTEGER, status TEXT, UNIQUE(user_id_1, user_id_2))')
        conn.commit()
        logging.info("База данных инициализирована.")

def encrypt_creds(creds: dict) -> str:
    return cipher_suite.encrypt(json.dumps(creds).encode('utf-8')).decode('utf-8')

def decrypt_creds(encrypted_creds: str) -> dict:
    return json.loads(cipher_suite.decrypt(encrypted_creds.encode('utf-8')))

def get_user_credentials(user_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT service, creds_json FROM credentials WHERE user_id = ?", (user_id,)).fetchall()

def save_user_credentials(user_id, service, creds):
    encrypted_creds = encrypt_creds(creds)
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO credentials (user_id, service, creds_json) VALUES (?, ?, ?)", (user_id, service, encrypted_creds))
        conn.commit()

def delete_user_credentials(user_id, service):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM credentials WHERE user_id = ? AND service = ?", (user_id, service))
        conn.commit()

def is_workout_processed(workout_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT 1 FROM processed_workouts WHERE workout_id = ?", (workout_id,)).fetchone() is not None

def save_processed_workout(workout_id, user_id, analysis_text):
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO processed_workouts (workout_id, user_id, analysis_text) VALUES (?, ?, ?)", (workout_id, user_id, analysis_text))
        conn.commit()

def add_friend_request(user_id_1, user_id_2):
    with get_db_connection() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE telegram_id = ?", (user_id_2,)).fetchone(): return "not_found"
        existing = conn.execute("SELECT * FROM friends WHERE (user_id_1 = ? AND user_id_2 = ?) OR (user_id_1 = ? AND user_id_2 = ?)", (user_id_1, user_id_2, user_id_2, user_id_1)).fetchone()
        if existing: return "already_exists"
        conn.execute("INSERT INTO friends (user_id_1, user_id_2, status) VALUES (?, ?, 'pending')", (user_id_1, user_id_2))
        conn.commit()
        return "ok"

def get_user_friends(user_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT u.telegram_id, u.full_name FROM friends f JOIN users u ON u.telegram_id = CASE WHEN f.user_id_1 = ? THEN f.user_id_2 ELSE f.user_id_1 END WHERE (f.user_id_1 = ? OR f.user_id_2 = ?) AND f.status = 'accepted'", (user_id, user_id, user_id)).fetchall()

def get_friend_requests(user_id):
    with get_db_connection() as conn:
        incoming = conn.execute("SELECT u.telegram_id, u.full_name FROM friends f JOIN users u ON u.telegram_id = f.user_id_1 WHERE f.user_id_2 = ? AND f.status = 'pending'", (user_id,)).fetchall()
        outgoing = conn.execute("SELECT u.telegram_id, u.full_name FROM friends f JOIN users u ON u.telegram_id = f.user_id_2 WHERE f.user_id_1 = ? AND f.status = 'pending'", (user_id,)).fetchall()
        return {"incoming": incoming, "outgoing": outgoing}

def update_friend_request(user_id_1, user_id_2, new_status):
    with get_db_connection() as conn:
        if new_status == 'accepted':
            conn.execute("UPDATE friends SET status = ? WHERE user_id_1 = ? AND user_id_2 = ?", (new_status, user_id_1, user_id_2))
        else: # 'declined' or 'cancelled'
            conn.execute("DELETE FROM friends WHERE (user_id_1 = ? AND user_id_2 = ?) OR (user_id_1 = ? AND user_id_2 = ?)", (user_id_1, user_id_2, user_id_2, user_id_1))
        conn.commit()

# ==============================================================================
# 3. СЛОЙ СЕРВИСОВ
# ==============================================================================
def get_strava_data(creds: dict):
    workouts = []
    try:
        client = Client(access_token=creds['access_token'])
        activities = client.get_activities(limit=5)
        for activity_summary in activities:
            detailed_activity = client.get_activity(activity_summary.id, include_all_efforts=True)
            workouts.append({"id": f"strava_{detailed_activity.id}", "service": "Strava", "data": detailed_activity.to_dict()})
    except Exception as e:
        logging.error(f"Ошибка получения данных Strava: {e}")
    return workouts

def get_garmin_data(creds: dict):
    logging.warning("Функция get_garmin_data является заглушкой. Для работы с Garmin Health API требуется корпоративный аккаунт.")
    return []

def get_suunto_data(creds: dict):
    workouts = []
    try:
        headers = {"Authorization": f"Bearer {creds['access_token']}", "Ocp-Apim-Subscription-Key": SUUNTO_CLIENT_SECRET}
        response = requests.get("https://cloudapi.suunto.com/v2/workouts", headers=headers)
        response.raise_for_status()
        for activity in response.json().get('payload', []):
            workouts.append({"id": f"suunto_{activity.get('workoutKey')}", "service": "Suunto", "data": activity})
    except Exception as e:
        logging.error(f"Ошибка получения данных Suunto: {e}")
    return workouts

SERVICE_MAP = {'strava': get_strava_data, 'garmin': get_garmin_data, 'suunto': get_suunto_data}

# ==============================================================================
# 4. СЛОЙ АНАЛИЗА
# ==============================================================================
async def analyze_workout_with_gemini(workout_info: dict) -> str:
    service = workout_info['service']
    data = workout_info['data']
    base_prompt = "Ты — элитный ИИ-тренер по фитнесу. Проанализируй данные о недавней тренировке спортсмена. Будь кратким, но дай глубокий анализ и 1-2 действенных совета на следующую тренировку. Обращайся к спортсмену на 'ты'."
    details = ""
    if service == 'Strava':
        details = f"""- Тип: {data.get('sport_type')}, Дистанция: {data.get('distance', 0) / 1000:.2f} км, Время: {int(data.get('moving_time', 0) / 60)} мин, Набор высоты: {data.get('total_elevation_gain')} м, Сред. мощность: {data.get('average_watts')} Вт, Сред. пульс: {data.get('average_heartrate')} уд/мин. Особое внимание удели мощности, пульсовым зонам и результатам на сегментах."""
    elif service == 'Suunto':
        details = f"""- Тип: {data.get('activityName')}, Дистанция: {data.get('totalDistance', 0) / 1000:.2f} км, Длительность: {int(data.get('totalDuration', 0) / 60)} мин, Набор высоты: {data.get('totalAscent')} м, Сред. пульс: {data.get('hrdata', {}).get('avg')} уд/мин, PTE: {data.get('extensions', [{}])[0].get('pte')}, EPOC: {data.get('extensions', [{}])[0].get('peakEpoc')}. Особое внимание удели показателям PTE и EPOC."""
    
    full_prompt = f"{base_prompt}\n\nДАННЫЕ ТРЕНИРОВКИ:\n{details}"
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = await model.generate_content_async(full_prompt)
        return response.text
    except Exception as e:
        logging.error(f"Ошибка анализа в Gemini: {e}")
        return "Не удалось проанализировать тренировку."

# ==============================================================================
# 5. ВЕБ-СЕРВЕР ДЛЯ OAUTH
# ==============================================================================
async def handle_oauth_callback(request):
    service = request.match_info.get('service', 'unknown')
    try:
        code = request.query['code']
        user_id = int(request.query['state'])
        token_data = {}
        if service == 'strava':
            response = requests.post("https://www.strava.com/oauth/token", data={'client_id': STRAVA_CLIENT_ID, 'client_secret': STRAVA_CLIENT_SECRET, 'code': code, 'grant_type': 'authorization_code'})
            response.raise_for_status()
            token_data = response.json()
        # Добавить логику для Garmin и Suunto
        
        save_user_credentials(user_id, service, token_data)
        bot = request.app['bot']
        await bot.send_message(user_id, f"✅ Успешно подключено к {service.capitalize()}!")
        return web.Response(text=f"Авторизация для {service.capitalize()} прошла успешно! Можете вернуться в Telegram.")
    except Exception as e:
        logging.error(f"Ошибка в OAuth callback для {service}: {e}")
        return web.Response(text="Произошла ошибка авторизации.", status=500)

async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/oauth/callback', handle_oauth_callback) # Общий callback
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info(f"Веб-сервер для OAuth запущен на порту 8080")

# ==============================================================================
# 6. ЛОГИКА БОТА
# ==============================================================================
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class FriendStates(StatesGroup):
    adding_friend = State()

# --- Клавиатуры ---
main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ Управление сервисами", callback_data="manage_services")], [InlineKeyboardButton(text="👥 Мои друзья", callback_data="friends_menu")], [InlineKeyboardButton(text="🔄 Проверить вручную", callback_data="fetch_manual")]])

def services_menu_keyboard(user_id):
    creds = get_user_credentials(user_id)
    buttons = [[InlineKeyboardButton(text="➕ Добавить сервис", callback_data="add_service")]]
    for cred in creds:
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить {cred['service'].capitalize()}", callback_data=f"delete_service_{cred['service']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def friends_menu_keyboard(requests_count):
    text = f"📨 Заявки ({requests_count})" if requests_count > 0 else "📨 Заявки в друзья"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤝 Список друзей", callback_data="list_friends")], [InlineKeyboardButton(text=text, callback_data="friend_requests")], [InlineKeyboardButton(text="➕ Добавить друга", callback_data="add_friend")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main_menu")]])

# --- Обработчики ---
@dp.message(CommandStart())
async def command_start(message: Message):
    user_id, full_name, username = message.from_user.id, message.from_user.full_name, message.from_user.username
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, full_name, username) VALUES (?, ?, ?)", (user_id, full_name, username))
        conn.execute("UPDATE users SET full_name = ?, username = ? WHERE telegram_id = ?", (full_name, username, user_id))
        conn.commit()
    await message.answer(f"Привет, {full_name}! Что хочешь сделать?", reply_markup=main_menu_keyboard)

@dp.message(Command("myid"))
async def show_my_id(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n\nЭтот ID нужен, чтобы другие пользователи могли добавить вас в друзья.")

@dp.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню.", reply_markup=main_menu_keyboard)
    await callback.answer()

@dp.callback_query(F.data == "manage_services")
async def manage_services_callback(callback: CallbackQuery):
    await callback.message.edit_text("Здесь вы можете подключить или удалить свои фитнес-сервисы.", reply_markup=services_menu_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "add_service")
async def add_service_callback(callback: CallbackQuery):
    strava_params = {'client_id': STRAVA_CLIENT_ID, 'redirect_uri': f"{BASE_URL}/oauth/callback?service=strava", 'response_type': 'code', 'scope': 'read,activity:read_all', 'state': callback.from_user.id}
    strava_url = f"https://www.strava.com/oauth/authorize?{urlencode(strava_params)}"
    # Аналогично для Garmin и Suunto
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Подключить Strava", url=strava_url)], [InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_services")]])
    await callback.message.edit_text("Нажмите на кнопку, чтобы авторизоваться в нужном сервисе:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_service_"))
async def delete_service_callback(callback: CallbackQuery):
    service_to_delete = callback.data.split("_")[2]
    delete_user_credentials(callback.from_user.id, service_to_delete)
    await callback.answer(f"Сервис {service_to_delete.capitalize()} удален.", show_alert=True)
    await callback.message.edit_text("Меню управления сервисами.", reply_markup=services_menu_keyboard(callback.from_user.id))

# --- Система друзей ---
@dp.callback_query(F.data == "friends_menu")
async def friends_menu_callback(callback: CallbackQuery):
    requests = get_friend_requests(callback.from_user.id)
    await callback.message.edit_text("Меню управления друзьями.", reply_markup=friends_menu_keyboard(len(requests['incoming'])))
    await callback.answer()

@dp.callback_query(F.data == "add_friend")
async def add_friend_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FriendStates.adding_friend)
    await callback.message.edit_text("Отправь мне Telegram ID пользователя, которого хочешь добавить.\n\n(ID можно узнать командой /myid)")
    await callback.answer()

@dp.message(FriendStates.adding_friend)
async def process_friend_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("ID должен быть числом. Попробуй еще раз.")
        return
    friend_id, user_id = int(message.text), message.from_user.id
    if friend_id == user_id:
        await message.answer("Нельзя добавить в друзья самого себя.")
        return
    result = add_friend_request(user_id, friend_id)
    if result == "ok":
        await message.answer("✅ Заявка в друзья отправлена!")
        try:
            requests = get_friend_requests(friend_id)
            await bot.send_message(friend_id, f"Пользователь {message.from_user.full_name} хочет добавить вас в друзья!", reply_markup=friends_menu_keyboard(len(requests['incoming'])))
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление о заявке пользователю {friend_id}: {e}")
    elif result == "not_found":
        await message.answer("❌ Пользователь с таким ID не найден в боте.")
    elif result == "already_exists":
        await message.answer("ℹ️ Вы уже друзья или заявка была отправлена ранее.")
    await state.clear()
    requests = get_friend_requests(user_id)
    await message.answer("Меню управления друзьями.", reply_markup=friends_menu_keyboard(len(requests['incoming'])))

@dp.callback_query(F.data == "friend_requests")
async def friend_requests_callback(callback: CallbackQuery):
    requests = get_friend_requests(callback.from_user.id)
    text = "<b>Входящие заявки:</b>\n"
    kb_buttons = []
    if not requests['incoming']: text += "Пусто\n"
    else:
        for req in requests['incoming']:
            text += f"- {req['full_name']} (ID: {req['telegram_id']})\n"
            kb_buttons.append([InlineKeyboardButton(text=f"✅ Принять {req['full_name']}", callback_data=f"friend_accept_{req['telegram_id']}"), InlineKeyboardButton(text=f"❌ Отклонить", callback_data=f"friend_decline_{req['telegram_id']}")])
    text += "\n<b>Исходящие заявки:</b>\n"
    if not requests['outgoing']: text += "Пусто"
    else:
        for req in requests['outgoing']: text += f"- {req['full_name']} (ID: {req['telegram_id']})\n"
    kb_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="friends_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("friend_accept_"))
async def accept_friend_callback(callback: CallbackQuery):
    friend_id, user_id = int(callback.data.split("_")[2]), callback.from_user.id
    update_friend_request(friend_id, user_id, 'accepted')
    await callback.answer("✅ Заявка принята!")
    await bot.send_message(friend_id, f"Пользователь {callback.from_user.full_name} принял вашу заявку в друзья!")
    await friend_requests_callback(callback)

@dp.callback_query(F.data.startswith("friend_decline_"))
async def decline_friend_callback(callback: CallbackQuery):
    friend_id, user_id = int(callback.data.split("_")[2]), callback.from_user.id
    update_friend_request(friend_id, user_id, 'declined')
    await callback.answer("❌ Заявка отклонена.")
    await friend_requests_callback(callback)

@dp.callback_query(F.data == "list_friends")
async def list_friends_callback(callback: CallbackQuery):
    friends = get_user_friends(callback.from_user.id)
    text = "<b>Список ваших друзей:</b>\n"
    kb_buttons = []
    if not friends: text += "У вас пока нет друзей."
    else:
        for friend in friends:
            text += f"- {friend['full_name']}\n"
            kb_buttons.append([InlineKeyboardButton(text=f"📊 Посмотреть активность {friend['full_name']}", callback_data=f"view_friend_{friend['telegram_id']}")])
    kb_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="friends_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("view_friend_"))
async def view_friend_activity_callback(callback: CallbackQuery):
    friend_id = int(callback.data.split("_")[2])
    with get_db_connection() as conn:
        last_workout = conn.execute("SELECT analysis_text FROM processed_workouts WHERE user_id = ? ORDER BY rowid DESC LIMIT 1", (friend_id,)).fetchone()
        friend = conn.execute("SELECT full_name FROM users WHERE telegram_id = ?", (friend_id,)).fetchone()
    if last_workout and last_workout['analysis_text']:
        await callback.answer()
        await callback.message.answer(f"<b>Последний анализ тренировки для {friend['full_name']}:</b>\n\n{last_workout['analysis_text']}")
    else:
        await callback.answer("У этого пользователя еще нет проанализированных тренировок.", show_alert=True)

@dp.callback_query(F.data == "fetch_manual")
async def fetch_manual_callback(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Начинаю проверку вручную...", reply_markup=None)
    await check_user_workouts(bot, callback.from_user.id)
    await callback.message.edit_text("✅ Проверка завершена!", reply_markup=main_menu_keyboard)
    await callback.answer("Проверка завершена")

# ==============================================================================
# 6. ФОНОВЫЙ ПЛАНИРОВЩИК
# ==============================================================================
async def check_user_workouts(bot: Bot, user_id: int):
    user_creds = get_user_credentials(user_id)
    if not user_creds: return

    all_workouts = []
    for service, encrypted_creds_json in user_creds:
        try:
            creds = decrypt_creds(encrypted_creds_json)
            if service in SERVICE_MAP:
                all_workouts.extend(SERVICE_MAP[service](creds))
        except Exception as e:
            logging.error(f"Ошибка получения данных для {service} у {user_id}: {e}")

    for workout in all_workouts:
        if not is_workout_processed(workout['id']):
            logging.info(f"Найдена новая тренировка для {user_id}: {workout['id']}")
            try:
                await bot.send_message(user_id, f"💪 Обнаружена новая тренировка: <b>{workout.get('data', {}).get('name', 'Без названия')}</b>! Анализирую...")
                analysis_text = await analyze_workout_with_gemini(workout)
                save_processed_workout(workout['id'], user_id, analysis_text)
                await bot.send_message(user_id, f"<b>🤖 Рекомендации от ИИ-тренера:</b>\n\n{analysis_text}")
            except Exception as e:
                logging.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

async def scheduler(bot: Bot):
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        logging.info("Запуск плановой проверки тренировок...")
        with get_db_connection() as conn:
            users = conn.execute("SELECT telegram_id FROM users").fetchall()
        for user in users:
            await check_user_workouts(bot, user['telegram_id'])
        
# ==============================================================================
# 7. ТОЧКА ВХОДА
# ==============================================================================
async def main():
    init_db()
    asyncio.create_task(start_web_server(bot))
    asyncio.create_task(scheduler(bot))
    logging.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
