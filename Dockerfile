FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/ ./requirements/

RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

EXPOSE 8000

WORKDIR /app/main_app

RUN python3 manage.py collectstatic --noinput

CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]