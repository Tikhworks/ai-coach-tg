import requests

# --- Настройки ---
# Ваш токен доступа, полученный после авторизации пользователя
ACCESS_TOKEN = "YOUR_SUUNTO_ACCESS_TOKEN" 
# Ваш ключ подписки на API Suunto (указан в вашем приложении на сайте Suunto)
API_KEY = "YOUR_SUUNTO_API_KEY"

# --- Параметры запроса ---
api_url = "https://cloudapi.suunto.com/v2/workouts"

# Заголовки, необходимые для аутентификации
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Ocp-Apim-Subscription-Key": API_KEY
}

try:
    print("Запрос последних тренировок из Suunto Cloud API...")
    
    # --- Выполнение запроса ---
    response = requests.get(api_url, headers=headers)

    # Проверка статуса ответа
    response.raise_for_status() 

    # --- Обработка данных ---
    workouts = response.json()

    if not workouts:
        print("Тренировки не найдены.")
    else:
        print("Последние 5 тренировок:")
        # Suunto API возвращает массив объектов. Берем первые 5.
        for workout in workouts[:5]:
            # Дистанция в метрах, переводим в км
            distance_km = round(workout.get('totalDistance', 0) / 1000, 2)
            # Длительность в секундах
            duration_sec = workout.get('totalDuration', 0)
            
            print(
                f"  - ID тренировки: {workout.get('workoutKey')}\n"
                f"    Дата: {workout.get('startTime')}\n"
                f"    Активность: {workout.get('activityName', 'N/A')}\n"
                f"    Дистанция: {distance_km} км\n"
                f"    Длительность: {round(duration_sec / 60)} мин\n"
            )

except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        print("Ошибка 401: Несанкционированный доступ. Проверьте ваш токен доступа и API-ключ.")
    else:
        print(f"HTTP ошибка: {e}")
except Exception as e:
    print(f"Произошла непредвиденная ошибка: {e}")