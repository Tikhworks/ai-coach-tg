import logging
from datetime import date, timedelta
from garminconnect import Garmin

# --- Настройки ---
# Вставьте логин и пароль пользователя Garmin Connect
EMAIL = "your_garmin_email@example.com"
PASSWORD = "your_garmin_password"

# Включаем логирование для отладки (опционально)
# logging.basicConfig(level=logging.DEBUG)

def get_garmin_data():
    """
    Функция для входа в Garmin Connect и получения данных.
    """
    try:
        # --- Инициализация API ---
        # Укажите is_cn=True, если аккаунт на сервере в Китае
        api = Garmin(EMAIL, PASSWORD)
        
        # --- Вход в аккаунт ---
        api.login()
        print("Успешный вход в аккаунт Garmin Connect.")
        print("-" * 20)

        # --- Получение тренировок за последние 30 дней ---
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        print(f"Получение тренировок с {start_date.strftime('%d-%m-%Y')} по {end_date.strftime('%d-%m-%Y')}")
        
        activities = api.get_activities_by_date(
            start_date.isoformat(), end_date.isoformat()
        )

        if not activities:
            print("Тренировки за указанный период не найдены.")
        else:
            # Выводим информацию о 5 последних тренировках
            for activity in activities[:5]:
                distance_km = round(activity.get("distance", 0) / 1000, 2)
                print(
                    f"  - Название: {activity.get('activityName', 'Без названия')}\n"
                    f"    Дата: {activity.get('startTimeLocal', '')}\n"
                    f"    Тип: {activity.get('activityType', {}).get('typeKey', 'N/A')}\n"
                    f"    Дистанция: {distance_km} км\n"
                )

    except Exception as e:
        print(f"Произошла ошибка при работе с Garmin Connect: {e}")
        print("Проверьте логин/пароль или попробуйте позже. API могло измениться.")

# --- Запуск функции ---
get_garmin_data()