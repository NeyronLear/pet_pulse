# PetPulse

Веб-приложение для владельцев домашних животных: карточки питомцев, медкарта, история здоровья и процедур, дневник питания. По сайту гуляет виртуальный питомец-тамагочи.

## Возможности

- **Аккаунт**: регистрация, вход по логину или почте, смена профиля и пароля.
- **Питомцы**: имя, вид, порода, дата рождения, фото (до 10 МБ), сводка — возраст, последний вес, ближайшее дело.
- **Медкарта**: вес, аллергии, хронические заболевания, заметки. Сохранённый в карте вес автоматически попадает замером на график динамики.
- **Динамика веса**: замеры веса питомца на вертикальном графике прямо в медкарте (замеры добавляются формой «Замер веса»).
- **История**: вакцинации, обработки от паразитов, визиты к ветеринару, измерения, препараты. У записи есть заключение врача, дата следующей процедуры и отметка «выполнено».
- **Питание**: корма, предпочтения питомца, переносимость, нежелательные реакции.
- **Тамагочи**: собака или кот, который ходит по экрану. На пользователя один питомец. Имя и тип хранятся на сервере, положение на экране — в `localStorage`.
- **Вход для жюри**: вход без пароля по имени, аккаунт `judge-<имя>` получает права администратора. Отключается переменной `JUDGE_LOGIN_ENABLED=0`.
- **Дежурный админ**: CI при каждом деплое идемпотентно создаёт суперюзера из секретов `SUPERUSER_USERNAME` / `SUPERUSER_EMAIL` / `SUPERUSER_PASSWORD` (скрипт `scripts/ensure_superuser.py`) — он может входить в `/admin/` по логину и паролю. Жюри пользуются judge-login, пароль им не нужен.

## Стек

- Backend: Python 3.12, Django 6.1, SQLite, Pillow
- Frontend: чистый JavaScript (без сборки), Web Components (`<pet-widget>`)
- Тесты: pytest + pytest-django, `node:test`
- Деплой: Docker, docker compose, GitLab CI (Kaniko → Spirit Registry → ВМ по SSH)

## Структура

```
.
├── Dockerfile, docker-compose.yml, .gitlab-ci.yml
├── requirements/           # prod.txt / test.txt / dev.txt
└── main_app/
    ├── manage.py
    ├── backend/            # настройки и корневые URL
    ├── main_api/           # модели, вьюхи, URL, шаблон, тесты
    ├── static/
    │   ├── css/styles.css
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

Приложение откроется на http://127.0.0.1:8000/ (редирект на `/user/`), админка — на http://127.0.0.1:8000/admin/.

### Через Docker

```bash
cp .env.example .env
docker build -t pet_pulse_1337:local .
docker compose up
```

При старте контейнер сам применяет миграции и слушает порт `8000`. Healthcheck проверяет `/user/test`.

## Переменные окружения

| Переменная            | По умолчанию          | Описание                                          |
|-----------------------|-----------------------|---------------------------------------------------|
| `SECRET_KEY`          | `fake`                | Секретный ключ Django                             |
| `ALLOWED_HOSTS`       | `localhost,127.0.0.1` | Разрешённые хосты, через запятую                  |
| `JUDGE_LOGIN_ENABLED` | `1`                   | `0` — выключить вход для жюри                     |

> `DEBUG` сейчас жёстко задан как `True` в `backend/settings.py`, переменная `DEBUG` из `.env` не читается. Загруженные фото Django отдаёт сам только при включённом `DEBUG`.

## API

Все адреса начинаются с `/user/`. Тело запросов и ответов — JSON (кроме загрузки фото, там `multipart/form-data`). Для всего, кроме страницы и входа/регистрации, нужна сессия, иначе ответ `401`. Запросы, меняющие данные, требуют CSRF-токен: кука `csrftoken` выставляется при открытии главной страницы.

| Метод                   | Путь                     | Описание                                            |
|-------------------------|--------------------------|-----------------------------------------------------|
| GET                     | `/user/`                 | HTML-страница; с `Accept: application/json` — список питомцев |
| POST / PUT              | `/user/`                 | Создать / обновить питомца                          |
| POST / DELETE           | `/user/pet_photo/<id>`   | Загрузить / удалить фото питомца                    |
| GET / POST / PUT / DELETE | `/user/med_card/<id>`  | Медкарта питомца                                    |
| GET / POST / PUT / DELETE | `/user/weight/<id>`    | Замеры веса питомца (график динамики)               |
| GET / POST / PUT / DELETE | `/user/history/<id>`   | Записи истории питомца                              |
| GET / POST / PUT / DELETE | `/user/food/<id>`      | Записи о питании питомца                            |
| GET / POST / PUT / DELETE | `/user/tamagochi`      | Тамагочи текущего пользователя                      |
| POST                    | `/user/auth/register`    | Регистрация                                         |
| POST                    | `/user/auth/login`       | Вход                                                |
| POST                    | `/user/auth/judge`       | Вход для жюри                                       |
| POST                    | `/user/auth/logout`      | Выход                                               |
| GET / PUT               | `/user/auth/me`          | Профиль текущего пользователя                       |
| POST                    | `/user/auth/password`    | Смена пароля                                        |
| GET                     | `/user/test`             | Проверка, что сервер жив                            |

## Тесты

```bash
cd main_app

# backend
pytest

# frontend (нужен Node.js 18+)
node --test js_tests/*.test.mjs
```

## Деплой

Пайплайн в `.gitlab-ci.yml` запускается на ветке `master`:

1. `build:image` собирает образ через Kaniko и пушит его в `registry.spirit.t-education.com`.
2. `setup:vm` ставит на ВМ Spirit CLI (`dp`), если его там нет.
3. `deploy:vm` копирует на ВМ `docker-compose.yml` и `.env`, скачивает новый образ и перезапускает контейнер, затем создаёт/обновляет суперюзера (`docker compose exec -T ... python manage.py shell < ensure_superuser.py`, секреты `SUPERUSER_USERNAME`, `SUPERUSER_EMAIL`, `SUPERUSER_PASSWORD`).

Загруженные фото хранятся в volume `media` (путь в контейнере `/app/main_app/media`) и переживают перезапуски и перевыпуски контейнера.

CI-переменные задаются в Spirit (Код → Репозитории → CI-переменные):

- `DEPLOY_HOST` — адрес ВМ; `DEPLOY_USER` — пользователь (по умолчанию `root`)
- `DEPLOY_KEY` — приватный SSH-ключ (тип File)
- `SPIRIT_DOCKER_SA_KEY` — ключ сервис-аккаунта registry
- `APP_ENV_FILE` — содержимое `.env` для продакшена (тип File)
