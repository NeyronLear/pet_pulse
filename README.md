# PetPulse

Веб-приложение для владельцев домашних животных: карточки питомцев, медкарта, история здоровья и процедур, дневник питания и push-уведомления о грядущих делах. По сайту гуляет виртуальный питомец-тамагочи.

## Возможности

- **Аккаунт**: регистрация, вход по логину или почте, смена профиля и пароля.
- **Питомцы**: имя, вид, порода, дата рождения, фото (до 10 МБ), сводка – возраст, последний вес, ближайшее дело.
- **Медкарта**: вес, аллергии, хронические заболевания, заметки. Сохранённый в карте вес автоматически попадает замером на график динамики.
- **Динамика веса**: график динамики в медкарте, раскрывается в большое окно по клику. Замер за сегодня добавляется полем «Вес» в форме медкарты, замер за любую прошлую дату – кнопкой в той же форме.
- **История**: вакцинации, обработки от паразитов, визиты к ветеринару, измерения, препараты. У записи есть заключение врача, дата следующей процедуры и отметка «выполнено».
- **Питание**: корма, предпочтения питомца, переносимость, нежелательные реакции.
- **Уведомления**: веб-push по стандарту Web Push + VAPID. Подписка кнопкой в интерфейсе (нужны VAPID-ключи и HTTPS – например, на задеплоенном домене). Раз в день (cron на сервере, 06:00 UTC) команда `send_reminders` шлёт каждому пользователю сводку: что запланировано на сегодня и завтра и какие процедуры вернулись по расписанию.
- **PWA**: есть `manifest.json` и service worker (отдаётся как `/user/sw.js`), сайт можно установить как приложение.
- **Тамагочи**: собака или кот, который ходит по экрану. На пользователя один питомец. Имя и тип хранятся на сервере, положение на экране – в `localStorage`.
- **Вход для жюри**: вход без пароля по имени, аккаунт `judge-<имя>` получает права администратора. Отключается переменной `JUDGE_LOGIN_ENABLED=0`.
- **Дежурный админ**: деплой идемпотентно создаёт суперюзера из секретов `SUPERUSER_USERNAME` / `SUPERUSER_EMAIL` / `SUPERUSER_PASSWORD` (скрипт `scripts/ensure_superuser.py`) – он может входить в `/admin/` по логину и паролю. Жюри пользуются judge-login, пароль им не нужен.

## Стек

- Backend: Python 3.12, Django 6.1, SQLite, Pillow, gunicorn
- Push: pywebpush (Web Push + VAPID)
- Frontend: чистый JavaScript (без сборки), Web Components (`<pet-widget>`), PWA (`manifest.json`, service worker)
- Прокси: nginx (статика и медиа, HTTPS + Let's Encrypt, редирект HTTP → HTTPS)
- Тесты: pytest + pytest-django, `node:test`
- Деплой: Docker, docker compose, GitHub Actions (тесты → образ в GHCR → ВМ по SSH)

## Структура

```
.
├── .github/
│   └── workflows/ci.yml    # CI/CD: тесты, сборка, деплой
├── Dockerfile, docker-compose.yml
├── nginx/
│   └── default.conf.template
├── scripts/                # ensure_superuser.py, setup_ssl.sh (certbot)
├── requirements/           # prod.txt / test.txt / dev.txt
└── main_app/
    ├── manage.py
    ├── backend/            # настройки и корневые URL
    ├── main_api/
    │   ├── push.py         # отправка web push (Web Push + VAPID)
    │   ├── models, views, urls, tests
    │   ├── management/commands/
    │   │   ├── generate_vapid_keys.py   # генерация ключей для .env
    │   │   └── send_reminders.py        # ежедневные push-напоминания
    │   └── templates/      # страница (index.html) и service worker (sw.js)
    ├── static/
    │   ├── manifest.json   # PWA-манифест
    │   ├── css/styles.css
    │   ├── img/logo.jpeg
    │   └── js/
    │       ├── app.js         # основное SPA
    │       ├── pet-widget.js  # веб-компонент тамагочи
    │       └── pet-app.js     # связка виджета с сервером
    └── js_tests/           # тесты фронтенда
```

## Локальный запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt

cp .env.example .env        # при необходимости поменяйте значения

cd main_app
python manage.py migrate
python manage.py createsuperuser   # по желанию, для /admin/
python manage.py runserver
```

Приложение откроется на http://127.0.0.1:8000/ (редирект на `/user/`), админка – на http://127.0.0.1:8000/admin/.

Push-уведомления локально по HTTP браузеры не дают: чтобы включить ключи, выполните `python manage.py generate_vapid_keys` и впишите строки `VAPID_*` в `.env` (работать они будут на HTTPS-домене).

### Через Docker

```bash
cp .env.example .env
docker build -t pet_pulse_1337:local .
docker compose up
```

При старте контейнер сам применяет миграции, собирает статику и запускает gunicorn на порту `8000`. Healthcheck проверяет `/user/test`. База и медиа живут в named volume (`db`, `media`).

Настроенный как в проде, compose также поднимает nginx на `80`/`443` (прокси на Django, выполняет `default.conf.template`). HTTPS-серверу nginx нужны сертификаты Let's Encrypt (`scripts/setup_ssl.sh` на сервере), без них сайт через compose не откроется – для локальной проверки пользуйтесь `runserver`.

## Переменные окружения

| Переменная            | По умолчанию          | Описание                                          |
|-----------------------|-----------------------|---------------------------------------------------|
| `SECRET_KEY`          | `fake`                | Секретный ключ Django                             |
| `DEBUG`               | `true`                | В проде обязательно выключить (`env_file` в compose это делает) |
| `ALLOWED_HOSTS`       | `localhost,127.0.0.1` | Разрешённые хосты, через запятую                  |
| `FQDN` / `DOMAIN`     | –                     | Домен продакшена: включает HTTPS-режим (Secure-флаги кук, `CSRF_TRUSTED_ORIGINS`) и используется nginx/SSL |
| `JUDGE_LOGIN_ENABLED` | `1`                   | `0` – выключить вход для жюри                     |
| `VAPID_PUBLIC_KEY`    | пусто                 | Публичный VAPID-ключ (`generate_vapid_keys`); пусто – push выключен |
| `VAPID_PRIVATE_KEY`   | пусто                 | Приватный VAPID-ключ                              |
| `VAPID_SUBJECT`       | `mailto:admin@example.com` | Контакт для push-сервисов браузеров          |

> Загруженные фото в проде отдаёт nginx (`/media/`), при локальном запуске с включённым `DEBUG` – сам Django.

## API

Все адреса начинаются с `/user/`. Тело запросов и ответов – JSON (кроме загрузки фото, там `multipart/form-data`). Для всего, кроме страницы и входа/регистрации, нужна сессия, иначе ответ `401`. Запросы, меняющие данные, требуют CSRF-токен: кука `csrftoken` выставляется при открытии главной страницы.

| Метод                    | Путь                       | Описание                                            |
|--------------------------|----------------------------|-----------------------------------------------------|
| GET                      | `/user/`                   | HTML-страница; с `Accept: application/json` – список питомцев |
| POST / PUT               | `/user/`                   | Создать / обновить питомца                          |
| POST / DELETE            | `/user/pet_photo/<id>`     | Загрузить / удалить фото питомца                    |
| GET / POST / PUT / DELETE| `/user/med_card/<id>`      | Медкарта питомца                                    |
| GET / POST / PUT / DELETE| `/user/weight/<id>`        | Замеры веса питомца (график динамики)               |
| GET / POST / PUT / DELETE| `/user/history/<id>`       | Записи истории питомца                              |
| GET / POST / PUT / DELETE| `/user/food/<id>`          | Записи о питании питомца                            |
| GET / POST / PUT / DELETE| `/user/tamagochi`          | Тамагочи текущего пользователя                      |
| GET                      | `/user/push/key`           | Публичный VAPID-ключ (пусто – push выключен)        |
| POST / DELETE            | `/user/push/subscribe`     | Подписаться / отписаться на push (DELETE – по endpoint) |
| GET                      | `/user/sw.js`              | Service worker для push-уведомлений                 |
| POST                     | `/user/auth/register`      | Регистрация                                         |
| POST                     | `/user/auth/login`         | Вход                                                |
| POST                     | `/user/auth/judge`         | Вход для жюри                                       |
| POST                     | `/user/auth/logout`        | Выход                                               |
| GET / PUT                | `/user/auth/me`            | Профиль текущего пользователя                       |
| POST                     | `/user/auth/password`      | Смена пароля                                        |
| GET                      | `/user/test`               | Проверка, что сервер жив                            |

## Тесты

```bash
cd main_app

# backend
pytest

# frontend (нужен Node.js 18+)
node --test js_tests/*.test.mjs
```

## Деплой

Пайплайн в `.github/workflows/ci.yml`:

1. `test-and-lint` – pytest на всех пушах и PR.
2. `build-and-verify` – сборка Docker-образа; при пуше в `develop`/`main` он пушится в `ghcr.io` (`:latest`), на PR только проверяется сборкой.
3. `deploy` – на	push в `main`, по SSH на ВМ:
   - копирует `docker-compose.yml`, `nginx/`, `scripts/setup_ssl.sh` и `ensure_superuser.py` в `~/app`;
   - дописывает `DOMAIN`/`FQDN` в `.env` на сервере и запускает `setup_ssl.sh` – выпускает сертификат Let's Encrypt (certbot standalone, если его ещё нет);
   - `docker compose pull && docker compose up -d --remove-orphans`;
   - создаёт/обновляет суперюзера (`docker compose exec -T ... python manage.py shell < ensure_superuser.py`, секреты `SUPERUSER_USERNAME`, `SUPERUSER_EMAIL`, `SUPERUSER_PASSWORD`);
   - восстанавливает cron-задачу: каждый день в 06:00 UTC – `python manage.py send_reminders` (push-напоминания пользователям).

CI-секреты задаются в настройках репозитория GitHub (Settings → Secrets and variables → Actions):

- `SERVER_IP`, `SERVER_USER`, `SSH_PRIVATE_KEY` – доступ к ВМ по SSH
- `DOMAIN`, `LE_EMAIL` – домен и почта для Let's Encrypt
- `SUPERUSER_USERNAME`, `SUPERUSER_EMAIL`, `SUPERUSER_PASSWORD` – дежурный админ

`GITHUB_TOKEN` для пуша в GHCR выдаётся автоматически.

## О проекте

Сайт был написан в рамках [Хакатона PROD](https://prodcontest.com/hackathon) в Санкт-Петербурге (2026 г.) за 3 дня и 3 бессонные ночи.

В разработке участвовали: Потапов Егор, Черанев Александр, Данилов Ярослав и еще Егор и Александр из нашей команды – спасибо за идеи, дизайн, тамагочи.