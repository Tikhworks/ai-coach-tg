import sqlite3
import json

# В реальном проекте ключи шифрования нужно хранить безопасно,
# а не в коде. Например, в переменных окружения.
# Для простоты примера оставляем его здесь.
# pip install cryptography
from cryptography.fernet import Fernet
ENCRYPTION_KEY = Fernet.generate_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def init_db():
    """Инициализирует базу данных и создает таблицы, если их нет."""
    conn = sqlite3.connect('ai_coach.db')
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT
        )
    ''')

    # Таблица для хранения учетных данных от сервисов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT, -- 'strava', 'garmin', 'suunto'
            credentials_json TEXT, -- Зашифрованный JSON с токенами/паролями
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    ''')

    # Таблица для хранения обработанных тренировок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_workouts (
            workout_id TEXT PRIMARY KEY,
            user_id INTEGER,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для дружеских связей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id_1 INTEGER,
            user_id_2 INTEGER,
            status TEXT, -- 'pending', 'accepted'
            FOREIGN KEY(user_id_1) REFERENCES users(telegram_id),
            FOREIGN KEY(user_id_2) REFERENCES users(telegram_id)
        )
    ''')

    conn.commit()
    conn.close()

def encrypt_creds(creds: dict) -> str:
    """Шифрует словарь с учетными данными в строку."""
    creds_bytes = json.dumps(creds).encode('utf-8')
    encrypted_creds = cipher_suite.encrypt(creds_bytes)
    return encrypted_creds.decode('utf-8')

def decrypt_creds(encrypted_creds: str) -> dict:
    """Расшифровывает строку в словарь с учетными данными."""
    decrypted_bytes = cipher_suite.decrypt(encrypted_creds.encode('utf-8'))
    return json.loads(decrypted_bytes.decode('utf-8'))

# ... (здесь будут функции для добавления/получения пользователей, учетных данных и т.д.) ...

if __name__ == '__main__':
    init_db()
    print("База данных 'ai_coach.db' инициализирована.")
    print(f"ВАЖНО: Сохраните ваш ключ шифрования в безопасном месте: {ENCRYPTION_KEY.decode()}")