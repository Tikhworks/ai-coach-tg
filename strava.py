import time
from stravalib.client import Client

# --- Настройки ---
# Вставьте ваш токен доступа, полученный после авторизации пользователя
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN" 

# --- Инициализация клиента ---
client = Client(access_token=ACCESS_TOKEN)

try:
    # --- Получение информации о спортсмене ---
    athlete = client.get_athlete()
    print(f"Подключен аккаунт спортсмена: {athlete.firstname} {athlete.lastname}")
    print("-" * 20)

    # --- Получение последних 5 тренировок ---
    activities = client.get_activities(limit=5)

    if not list(activities):
        print("Тренировки не найдены.")
    else:
        print("Последние 5 тренировок:")
        for activity in activities:
            # Преобразование времени в читаемый формат
            activity_date = activity.start_date_local.strftime("%d-%m-%Y %H:%M")
            # Преобразование дистанции в км
            distance_km = round(activity.distance.to("km").magnitude, 2)

            print(
                f"  - Название: {activity.name}\n"
                f"    Дата: {activity_date}\n"
                f"    Тип: {activity.type}\n"
                f"    Дистанция: {distance_km} км\n"
            )

except Exception as e:
    print(f"Произошла ошибка: {e}")
    print("Возможно, ваш токен доступа истек или недействителен.")