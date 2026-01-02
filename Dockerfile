FROM python:3.11-slim

WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/
COPY data/ ./data/

# Создаём директорию для данных
RUN mkdir -p data

# Запускаем приложение
CMD ["python", "-m", "app.main"]

