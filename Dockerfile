FROM python:3.11-slim

WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/

# Создаём директорию для данных (будет монтироваться через volume)
RUN mkdir -p data

# Запускаем приложение
CMD ["python", "-m", "app.main"]

