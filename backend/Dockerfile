FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# DejaVu - шрифт с кириллицей для PDF-отчётов и диаграмм: своих кириллических
# шрифтов у reportlab нет, без этого пакета отчёт выйдет без русских букв.
RUN apt-get update \
    && apt-get install --no-install-recommends -y fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Если рядом лежит снимок версий (make lock), ставим строго по нему -
# сборка тогда повторяется один в один. Иначе берём диапазоны из
# requirements.txt. Звёздочка нужна, чтобы COPY не падал без lock-файла.
COPY requirements.txt requirements.lock* ./
RUN if [ -f requirements.lock ]; then \
        pip install --no-cache-dir -r requirements.lock; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
