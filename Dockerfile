# Жёстко фиксируем Python 3.12
FROM python:3.12-slim-bookworm

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем всё, включая numpy и numba
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir numpy==1.26.4 && \
    pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Запускаем через gunicorn (flask приложение)
CMD gunicorn eth_super_analyzer:app