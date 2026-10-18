"""Тесты API (main_api/views.py).

Запуск из папки main_app:  pytest
Тесты повторяют запросы, которые строит static/js/app.js: JSON в теле,
Accept: application/json, id записи в теле PUT и в ?id= у DELETE.
"""

import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from main_api.models import Food, History, MedCard, Pet

pytestmark = pytest.mark.django_db

MAIN = "/user/"


# ---------- Вспомогательные классы и фикстуры ----------

class ApiClient:
    """Говорит с API так же, как app.js."""

    def __init__(self, client: Client):
        self.client = client

    def get(self, url):
        return self.client.get(url, HTTP_ACCEPT="application/json")

    def send(self, method, url, body=None):
        kwargs = {"HTTP_ACCEPT": "application/json"}
        if body is not None:
            kwargs["data"] = body if isinstance(body, (str, bytes)) else json.dumps(body)
            kwargs["content_type"] = "application/json"
        return getattr(self.client, method)(url, **kwargs)

    def post(self, url, body=None):
        return self.send("post", url, body)

    def put(self, url, body=None):
        return self.send("put", url, body)

    def delete(self, url):
        return self.send("delete", url)


@pytest.fixture
def owner():
    # без пароля: хеширование паролей в тестах только замедляет прогон
    return get_user_model().objects.create(username="owner", email="owner@example.com")


def logged_in(user) -> ApiClient:
    client = Client()
    client.force_login(user)
    return ApiClient(client)


@pytest.fixture
def api(owner):
    """Клиент, вошедший как владелец питомцев из фикстур."""
    return logged_in(owner)


@pytest.fixture
def anon():
    return ApiClient(Client())


@pytest.fixture
def stranger():
    return get_user_model().objects.create(username="stranger", email="stranger@example.com")


@pytest.fixture
def pet(owner):
    return Pet.objects.create(
        owner=owner, name="Барсик", species="Кот", breed="Британский",
        birth_date=date(2022, 4, 12),
    )


@pytest.fixture
def other_pet(owner):
    return Pet.objects.create(owner=owner, name="Мия", species="Собака")


@pytest.fixture
def record(pet):
    return History.objects.create(
        pet=pet, type="Вакцинация", title="Плановая вакцинация",
        date=date(2026, 10, 17), vet_conclusion="Здоров", next_date=date(2027, 10, 17),
    )


@pytest.fixture
def food(pet):
    return Food.objects.create(pet=pet, name="Royal Canin", date=date(2026, 10, 17))


@pytest.fixture
def card(pet):
    return MedCard.objects.create(pet=pet, weight="4.80", allergies="Курица")


def history_url(pet_id):
    return reverse("history_point", args=[pet_id])


def food_url(pet_id):
    return reverse("food_point", args=[pet_id])


def card_url(pet_id):
    return reverse("med_card_point", args=[pet_id])


def history_body(pet, **overrides):
    body = {
        "pet": pet.id, "type": "Обработка", "title": "Таблетка",
        "date": "2026-10-17", "time": "09:30", "next_date": None, "done": False,
    }
    return {**body, **overrides}


def food_body(pet, **overrides):
    body = {"pet": pet.id, "name": "Monge", "date": "2026-10-17", "status": "Не подошло", "note": "x"}
    return {**body, **overrides}


# ---------- Маршруты ----------

def test_routes_are_mounted_under_user_prefix(pet):
    assert reverse("main") == MAIN
    assert history_url(pet.id) == f"/user/history/{pet.id}"
    assert food_url(pet.id) == f"/user/food/{pet.id}"
    assert card_url(pet.id) == f"/user/med_card/{pet.id}"


def test_healthcheck(client):
    assert client.get(reverse("test")).status_code == 200


# ---------- Главная страница и питомцы ----------

class TestMain:
    def test_browser_gets_html_and_csrf_cookie(self, client):
        response = client.get(MAIN, HTTP_ACCEPT="text/html")
        assert response.status_code == 200
        assert b"<html" in response.content
        assert "csrftoken" in response.cookies

    def test_fetch_gets_json_list(self, api, pet, other_pet):
        response = api.get(MAIN)
        assert response.status_code == 200
        assert [p["name"] for p in response.json()] == ["Барсик", "Мия"]

    def test_pet_json_shape(self, api, pet):
        assert api.get(MAIN).json()[0] == {
            "id": pet.id, "name": "Барсик", "species": "Кот",
            "breed": "Британский", "birth_date": "2022-04-12",
        }

    def test_empty_list(self, api):
        assert api.get(MAIN).json() == []

    def test_create_pet_uses_current_user(self, api, owner):
        response = api.post(MAIN, {"name": " Рекс ", "species": "Собака", "breed": "", "birth_date": None})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Рекс" and data["birth_date"] is None
        assert Pet.objects.get(pk=data["id"]).owner == owner

    def test_create_pet_defaults_species(self, api):
        assert api.post(MAIN, {"name": "Рекс"}).json()["species"] == "Кот"

    @pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}])
    def test_create_pet_requires_name(self, api, body):
        assert api.post(MAIN, body).status_code == 400
        assert Pet.objects.count() == 0

    @pytest.mark.parametrize("birth", ["2026-02-30", "вчера", "12.04.2022"])
    def test_create_pet_rejects_bad_date(self, api, birth):
        assert api.post(MAIN, {"name": "Рекс", "birth_date": birth}).status_code == 400

    def test_create_pet_rejects_invalid_json(self, api):
        assert api.post(MAIN, "{not json").status_code == 400

    def test_create_pet_rejects_too_long_name(self, api):
        assert api.post(MAIN, {"name": "я" * 101}).status_code == 400

    def test_update_pet(self, api, pet):
        response = api.put(MAIN, {"id": pet.id, "name": "Барсик", "species": "Кот", "breed": "Шотландский", "birth_date": None})
        assert response.status_code == 200
        pet.refresh_from_db()
        assert pet.breed == "Шотландский" and pet.birth_date is None
        assert Pet.objects.count() == 1

    def test_update_pet_not_found(self, api):
        assert api.put(MAIN, {"id": 9999, "name": "X"}).status_code == 404

    def test_update_pet_requires_name(self, api, pet):
        assert api.put(MAIN, {"id": pet.id, "name": ""}).status_code == 400
        pet.refresh_from_db()
        assert pet.name == "Барсик"

    def test_update_pet_bad_date_keeps_data(self, api, pet):
        assert api.put(MAIN, {"id": pet.id, "name": "Новое", "birth_date": "2026-13-45"}).status_code == 400
        pet.refresh_from_db()
        assert pet.name == "Барсик"


# ---------- История и напоминания ----------

class TestHistory:
    def test_list_ordered_by_date_and_time(self, api, pet):
        History.objects.create(pet=pet, title="поздно", date=date(2026, 1, 2))
        History.objects.create(pet=pet, title="рано", date=date(2026, 1, 1))
        titles = [r["title"] for r in api.get(history_url(pet.id)).json()]
        assert titles == ["рано", "поздно"]

    def test_list_only_own_pet(self, api, pet, other_pet, record):
        History.objects.create(pet=other_pet, title="чужая", date=date(2026, 1, 1))
        data = api.get(history_url(pet.id)).json()
        assert [r["id"] for r in data] == [record.id]

    def test_json_shape(self, api, pet, record):
        assert api.get(history_url(pet.id)).json()[0] == {
            "id": record.id, "pet": pet.id, "type": "Вакцинация",
            "title": "Плановая вакцинация", "date": "2026-10-17", "time": None,
            "note": "", "vet_conclusion": "Здоров", "next_date": "2027-10-17", "done": False,
        }

    def test_unknown_pet_is_404(self, api):
        url = history_url(9999)
        assert api.get(url).status_code == 404
        assert api.post(url, {}).status_code == 404
        assert api.put(url, {}).status_code == 404
        assert api.delete(url).status_code == 404

    def test_create(self, api, pet):
        response = api.post(history_url(pet.id), history_body(pet))
        assert response.status_code == 201
        data = response.json()
        assert data["time"] == "09:30:00" and data["pet"] == pet.id and data["done"] is False
        assert History.objects.get(pk=data["id"]).type == "Обработка"

    def test_create_uses_pet_from_url_not_body(self, api, pet, other_pet):
        response = api.post(history_url(pet.id), history_body(other_pet))
        assert response.json()["pet"] == pet.id

    def test_create_defaults(self, api, pet):
        response = api.post(history_url(pet.id), {"title": "Без типа", "date": "2026-10-17"})
        assert response.status_code == 201
        assert response.json()["type"] == "Другое" and response.json()["done"] is False

    def test_create_health_record_done(self, api, pet):
        assert api.post(history_url(pet.id), history_body(pet, done=True)).json()["done"] is True

    @pytest.mark.parametrize("overrides", [
        {"title": ""}, {"title": "  "}, {"date": ""}, {"date": None},
        {"date": "2026-02-30"}, {"date": "завтра"},
        {"time": "25:99"}, {"time": "утром"},
        {"next_date": "2026-02-30"},
        {"type": "Процедура"},
    ])
    def test_create_rejects_invalid(self, api, pet, overrides):
        response = api.post(history_url(pet.id), history_body(pet, **overrides))
        assert response.status_code == 400
        assert History.objects.count() == 0

    def test_create_rejects_invalid_json(self, api, pet):
        assert api.post(history_url(pet.id), "{").status_code == 400

    def test_every_type_from_model_choices_is_accepted(self, api, pet):
        for value, _ in History.TYPE_CHOICES:
            response = api.post(history_url(pet.id), history_body(pet, type=value))
            assert response.status_code == 201, value

    def test_toggle_done_keeps_hidden_fields(self, api, pet, record):
        body = {
            "id": record.id, "pet": pet.id, "type": "Вакцинация", "title": "Плановая вакцинация",
            "date": "2026-10-17", "time": "", "note": "", "vet_conclusion": "Здоров",
            "next_date": "2027-10-17", "done": True,
        }
        assert api.put(history_url(pet.id), body).status_code == 200
        record.refresh_from_db()
        assert record.done is True
        assert record.vet_conclusion == "Здоров" and record.next_date == date(2027, 10, 17)

    def test_update_keeps_vet_conclusion_when_empty(self, api, pet, record):
        api.put(history_url(pet.id), {"id": record.id, "title": "Т", "date": "2026-10-17", "vet_conclusion": ""})
        record.refresh_from_db()
        assert record.vet_conclusion == "Здоров"

    def test_update_changes_fields(self, api, pet, record):
        response = api.put(history_url(pet.id), {
            "id": record.id, "type": "Измерение", "title": "Вес", "date": "2026-11-01",
            "time": "08:15", "note": "4,9 кг", "done": True,
        })
        assert response.status_code == 200
        record.refresh_from_db()
        assert (record.type, record.title, record.note) == ("Измерение", "Вес", "4,9 кг")
        assert record.time.strftime("%H:%M") == "08:15"

    def test_update_clears_time(self, api, pet):
        record = History.objects.create(pet=pet, title="Т", date=date(2026, 1, 1), time="10:00")
        api.put(history_url(pet.id), {"id": record.id, "title": "Т", "date": "2026-01-01", "time": ""})
        record.refresh_from_db()
        assert record.time is None

    def test_update_foreign_record_is_404(self, api, other_pet, record):
        body = {"id": record.id, "title": "Т", "date": "2026-10-17"}
        assert api.put(history_url(other_pet.id), body).status_code == 404

    def test_update_unknown_record_is_404(self, api, pet):
        body = {"id": 9999, "title": "Т", "date": "2026-10-17"}
        assert api.put(history_url(pet.id), body).status_code == 404

    @pytest.mark.parametrize("overrides", [
        {"title": ""}, {"date": ""}, {"date": "2026-02-30"}, {"time": "99:99"}, {"type": "Процедура"},
    ])
    def test_update_rejects_invalid_and_does_not_change(self, api, pet, record, overrides):
        body = {"id": record.id, "title": "Новое", "date": "2026-10-17", **overrides}
        assert api.put(history_url(pet.id), body).status_code == 400
        record.refresh_from_db()
        assert record.title == "Плановая вакцинация"

    def test_delete(self, api, pet, record):
        assert api.delete(f"{history_url(pet.id)}?id={record.id}").status_code == 204
        assert not History.objects.filter(pk=record.id).exists()

    def test_delete_requires_id(self, api, pet, record):
        assert api.delete(history_url(pet.id)).status_code == 400
        assert History.objects.filter(pk=record.id).exists()

    def test_delete_foreign_record_is_404(self, api, other_pet, record):
        assert api.delete(f"{history_url(other_pet.id)}?id={record.id}").status_code == 404
        assert History.objects.filter(pk=record.id).exists()

    def test_delete_unknown_record_is_404(self, api, pet):
        assert api.delete(f"{history_url(pet.id)}?id=9999").status_code == 404

    def test_delete_with_garbage_id_is_not_500(self, api, pet):
        assert api.delete(f"{history_url(pet.id)}?id=abc").status_code in (400, 404)


# ---------- Питание ----------

class TestFood:
    def test_list_and_shape(self, api, pet, food):
        assert api.get(food_url(pet.id)).json() == [{
            "id": food.id, "pet": pet.id, "name": "Royal Canin", "date": "2026-10-17",
            "status": "Наблюдать", "note": "", "preference": "", "reaction": "",
        }]

    def test_list_only_own_pet(self, api, pet, other_pet, food):
        Food.objects.create(pet=other_pet, name="чужой", date=date(2026, 1, 1))
        assert [f["id"] for f in api.get(food_url(pet.id)).json()] == [food.id]

    def test_list_ordered_by_date(self, api, pet):
        Food.objects.create(pet=pet, name="поздно", date=date(2026, 2, 1))
        Food.objects.create(pet=pet, name="рано", date=date(2026, 1, 1))
        assert [f["name"] for f in api.get(food_url(pet.id)).json()] == ["рано", "поздно"]

    def test_unknown_pet_is_404(self, api):
        assert api.get(food_url(9999)).status_code == 404
        assert api.post(food_url(9999), {}).status_code == 404

    def test_create(self, api, pet):
        response = api.post(food_url(pet.id), food_body(pet))
        assert response.status_code == 201
        assert response.json()["name"] == "Monge" and response.json()["status"] == "Не подошло"

    def test_create_default_status(self, api, pet):
        body = food_body(pet)
        del body["status"]
        assert api.post(food_url(pet.id), body).json()["status"] == "Наблюдать"

    def test_create_requires_name_not_title(self, api, pet):
        """В интерфейсе поле называется title, но на сервер оно уходит как name."""
        assert api.post(food_url(pet.id), {"title": "Monge", "date": "2026-10-17"}).status_code == 400

    @pytest.mark.parametrize("overrides", [
        {"name": ""}, {"name": " "}, {"date": ""}, {"date": "2026-02-30"},
        {"status": "Плохо"}, {"preference": "Ничего"},
    ])
    def test_create_rejects_invalid(self, api, pet, overrides):
        assert api.post(food_url(pet.id), food_body(pet, **overrides)).status_code == 400
        assert Food.objects.count() == 0

    def test_update(self, api, pet, food):
        assert api.put(food_url(pet.id), food_body(pet, id=food.id, note="y")).status_code == 200
        food.refresh_from_db()
        assert (food.name, food.note, food.status) == ("Monge", "y", "Не подошло")

    def test_update_rejects_invalid(self, api, pet, food):
        assert api.put(food_url(pet.id), food_body(pet, id=food.id, status="Плохо")).status_code == 400
        food.refresh_from_db()
        assert food.name == "Royal Canin"

    def test_update_foreign_or_unknown_is_404(self, api, other_pet, food):
        assert api.put(food_url(other_pet.id), food_body(other_pet, id=food.id)).status_code == 404
        assert api.put(food_url(other_pet.id), food_body(other_pet, id=9999)).status_code == 404

    def test_delete(self, api, pet, food):
        assert api.delete(f"{food_url(pet.id)}?id={food.id}").status_code == 204
        assert Food.objects.count() == 0

    def test_delete_requires_id(self, api, pet, food):
        assert api.delete(food_url(pet.id)).status_code == 400

    def test_delete_foreign_is_404(self, api, other_pet, food):
        assert api.delete(f"{food_url(other_pet.id)}?id={food.id}").status_code == 404
        assert Food.objects.count() == 1


# ---------- Медкарта ----------

class TestMedCard:
    def test_missing_card_is_404(self, api, pet):
        """app.js считает 404 нормой («карты ещё нет»), остальное — ошибкой."""
        assert api.get(card_url(pet.id)).status_code == 404

    def test_unknown_pet_is_404(self, api):
        assert api.get(card_url(9999)).status_code == 404

    def test_get(self, api, pet, card):
        assert api.get(card_url(pet.id)).json() == {
            "id": card.id, "pet": pet.id, "weight": "4.80", "allergies": "Курица",
            "chronic_conditions": "", "notes": "",
        }

    def test_create(self, api, pet):
        body = {"pet": pet.id, "weight": "3.5", "allergies": "Нет", "chronic_conditions": "", "notes": ""}
        assert api.post(card_url(pet.id), body).status_code == 201
        assert MedCard.objects.get(pet=pet).allergies == "Нет"

    def test_create_with_empty_weight(self, api, pet):
        response = api.post(card_url(pet.id), {"weight": ""})
        assert response.status_code == 201 and response.json()["weight"] is None

    def test_create_twice_is_400(self, api, pet, card):
        assert api.post(card_url(pet.id), {"weight": "3"}).status_code == 400
        assert MedCard.objects.count() == 1

    @pytest.mark.parametrize("weight", ["abc", "99999", "-1", "1.234"])
    def test_create_rejects_bad_weight(self, api, pet, weight):
        assert api.post(card_url(pet.id), {"weight": weight}).status_code == 400
        assert MedCard.objects.count() == 0

    def test_update(self, api, pet, card):
        body = {"id": card.id, "weight": None, "allergies": "Курица", "chronic_conditions": "", "notes": "н"}
        assert api.put(card_url(pet.id), body).status_code == 200
        card.refresh_from_db()
        assert card.weight is None and card.notes == "н"

    def test_update_rejects_bad_weight_and_keeps_data(self, api, pet, card):
        assert api.put(card_url(pet.id), {"id": card.id, "weight": "abc"}).status_code == 400
        card.refresh_from_db()
        assert str(card.weight) == "4.80"

    def test_update_foreign_or_unknown_is_404(self, api, other_pet, card):
        assert api.put(card_url(other_pet.id), {"id": card.id}).status_code == 404
        assert api.put(card_url(other_pet.id), {"id": 9999}).status_code == 404

    def test_delete(self, api, pet, card):
        assert api.delete(f"{card_url(pet.id)}?id={card.id}").status_code == 204
        assert MedCard.objects.count() == 0

    def test_delete_requires_id(self, api, pet, card):
        assert api.delete(card_url(pet.id)).status_code == 400

    def test_delete_foreign_is_404(self, api, other_pet, card):
        assert api.delete(f"{card_url(other_pet.id)}?id={card.id}").status_code == 404
        assert MedCard.objects.count() == 1


# ---------- Каскады ----------

def test_deleting_pet_removes_related_records(pet, record, food, card):
    pet.delete()
    assert not (History.objects.exists() or Food.objects.exists() or MedCard.objects.exists())


# ---------- CSRF и методы ----------

class TestSecurity:
    @pytest.fixture
    def strict(self):
        return ApiClient(Client(enforce_csrf_checks=True))

    @pytest.mark.parametrize("method", ["post", "put", "delete"])
    def test_writes_require_csrf_token(self, strict, pet, record, method):
        url = MAIN if method != "delete" else f"{history_url(pet.id)}?id={record.id}"
        body = {"name": "X", "id": pet.id} if method != "delete" else None
        assert strict.send(method, url, body).status_code == 403
        assert Pet.objects.count() == 1 and History.objects.count() == 1

    def test_write_with_valid_token_passes(self, owner):
        client = Client(enforce_csrf_checks=True)
        client.force_login(owner)
        client.get(MAIN, HTTP_ACCEPT="text/html")  # выдаёт csrftoken
        response = client.post(
            MAIN, data=json.dumps({"name": "Рекс"}), content_type="application/json",
            HTTP_ACCEPT="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        assert response.status_code == 201

    @pytest.mark.parametrize("url_name", ["history_point", "food_point", "med_card_point"])
    def test_unsupported_method_is_405(self, api, pet, url_name):
        assert api.send("patch", reverse(url_name, args=[pet.id]), {}).status_code == 405

    def test_main_does_not_support_delete(self, api):
        assert api.delete(MAIN).status_code == 405


# ---------- Доступ: без входа и к чужим данным ----------

class TestAccess:
    def test_page_is_open_without_login(self, anon):
        response = anon.client.get(MAIN, HTTP_ACCEPT="text/html")
        assert response.status_code == 200 and b"<html" in response.content

    @pytest.mark.parametrize("method", ["get", "post", "put"])
    def test_pets_api_requires_login(self, anon, pet, method):
        response = anon.get(MAIN) if method == "get" else anon.send(method, MAIN, {"id": pet.id, "name": "X"})
        assert response.status_code == 401
        pet.refresh_from_db()
        assert pet.name == "Барсик" and Pet.objects.count() == 1

    @pytest.mark.parametrize("url_name", ["history_point", "food_point", "med_card_point"])
    def test_pet_resources_require_login(self, anon, pet, url_name):
        assert anon.get(reverse(url_name, args=[pet.id])).status_code == 401

    def test_pet_list_shows_only_own_pets(self, pet, stranger):
        Pet.objects.create(owner=stranger, name="Чужой")
        assert [p["name"] for p in logged_in(stranger).get(MAIN).json()] == ["Чужой"]

    def test_cannot_update_foreign_pet(self, pet, stranger):
        response = logged_in(stranger).put(MAIN, {"id": pet.id, "name": "Украден"})
        assert response.status_code == 404
        pet.refresh_from_db()
        assert pet.name == "Барсик"

    @pytest.mark.parametrize("url_name", ["history_point", "food_point", "med_card_point"])
    def test_foreign_pet_resources_are_404(self, pet, record, food, card, stranger, url_name):
        client = logged_in(stranger)
        url = reverse(url_name, args=[pet.id])
        assert client.get(url).status_code == 404
        assert client.post(url, {"title": "x", "name": "x", "date": "2026-10-17"}).status_code == 404
        assert client.delete(f"{url}?id=1").status_code == 404
        assert History.objects.count() == Food.objects.count() == MedCard.objects.count() == 1


# ---------- Регистрация, вход и выход ----------

REGISTER = "/user/auth/register"
LOGIN = "/user/auth/login"
LOGOUT = "/user/auth/logout"
ME = "/user/auth/me"
PASSWORD_URL = "/user/auth/password"
PASSWORD = "Kot-Barsik-2026"


def register_body(**overrides):
    body = {"username": "anna", "email": "Anna@Example.com", "phone": "", "password": PASSWORD}
    return {**body, **overrides}


@pytest.fixture
def member():
    return get_user_model().objects.create_user(username="anna", email="anna@example.com", password=PASSWORD)


class TestAuth:
    def test_auth_routes(self):
        names = ("register", "login", "logout", "me", "password")
        assert [reverse(n) for n in names] == [REGISTER, LOGIN, LOGOUT, ME, PASSWORD_URL]

    def test_register_creates_user_and_logs_in(self, anon):
        response = anon.post(REGISTER, register_body(phone="+7 900 000-00-00"))
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "anna" and data["email"] == "anna@example.com"
        assert "password" not in data
        user = get_user_model().objects.get(username="anna")
        assert user.check_password(PASSWORD) and user.phone == "+7 900 000-00-00"
        assert anon.get(ME).json()["id"] == user.id

    def test_registered_user_owns_new_pets(self, anon):
        anon.post(REGISTER, register_body())
        pet_id = anon.post(MAIN, {"name": "Рекс"}).json()["id"]
        assert Pet.objects.get(pk=pet_id).owner.username == "anna"

    @pytest.mark.parametrize("overrides", [
        {"username": ""}, {"email": ""}, {"password": ""},
        {"email": "не-почта"},
        {"username": "с пробелом"},
        {"password": "12345678"},  # слишком простой
        {"password": "short"},
        {"password": "anna@example.com"},  # похож на почту
    ])
    def test_register_rejects_invalid(self, anon, overrides):
        response = anon.post(REGISTER, register_body(**overrides))
        assert response.status_code == 400 and response.json()["detail"]
        assert not get_user_model().objects.exists()

    def test_register_rejects_taken_username_and_email(self, anon, member):
        assert anon.post(REGISTER, register_body(email="new@example.com")).status_code == 400
        response = anon.post(REGISTER, register_body(username="other"))
        assert response.status_code == 400
        assert "почт" in response.json()["detail"]
        assert get_user_model().objects.count() == 1

    def test_register_rejects_invalid_json(self, anon):
        assert anon.post(REGISTER, "{not json").status_code == 400

    @pytest.mark.parametrize("login", ["anna", "anna@example.com", "ANNA@example.com"])
    def test_login_by_username_or_email(self, anon, member, login):
        response = anon.post(LOGIN, {"login": login, "password": PASSWORD})
        assert response.status_code == 200 and response.json()["username"] == "anna"
        assert anon.get(ME).status_code == 200

    @pytest.mark.parametrize("body", [
        {"login": "anna", "password": "wrong"},
        {"login": "nobody", "password": PASSWORD},
        {"login": "", "password": ""},
        {},
    ])
    def test_login_rejects_bad_credentials(self, anon, member, body):
        assert anon.post(LOGIN, body).status_code == 400
        assert anon.get(ME).status_code == 401

    def test_inactive_user_cannot_login(self, anon, member):
        member.is_active = False
        member.save()
        assert anon.post(LOGIN, {"login": "anna", "password": PASSWORD}).status_code == 400

    def test_logout(self, anon, member, pet):
        anon.post(LOGIN, {"login": "anna", "password": PASSWORD})
        assert anon.post(LOGOUT).status_code == 204
        assert anon.get(ME).status_code == 401
        assert anon.get(MAIN).status_code == 401

    def test_logout_without_login_is_ok(self, anon):
        assert anon.post(LOGOUT).status_code == 204

    def test_logout_requires_post(self, api):
        assert api.get(LOGOUT).status_code == 405
        assert api.get(ME).status_code == 200

    def test_me_requires_login(self, anon):
        assert anon.get(ME).status_code == 401

    def test_auth_writes_require_csrf(self, member):
        client = ApiClient(Client(enforce_csrf_checks=True))
        assert client.post(LOGIN, {"login": "anna", "password": PASSWORD}).status_code == 403
        assert client.post(REGISTER, register_body(username="new", email="n@example.com")).status_code == 403


# ---------- Профиль: редактирование и смена пароля ----------

def profile_body(**overrides):
    body = {
        "username": "anna",
        "email": "anna@example.com",
        "phone": "",
        "first_name": "",
        "last_name": "",
    }
    return {**body, **overrides}


class TestProfile:
    def test_me_json_shape(self, api, owner):
        data = api.get(ME).json()
        assert set(data) == {"id", "username", "email", "phone", "first_name", "last_name", "date_joined"}
        assert data["date_joined"] == owner.date_joined.date().isoformat()

    def test_update_profile(self, api, owner):
        body = profile_body(email=" Anna@Example.com ", phone="+7 900", first_name="Анна", last_name="Котова")
        response = api.put(ME, body)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "anna" and data["email"] == "anna@example.com"
        assert data["first_name"] == "Анна" and data["last_name"] == "Котова"
        owner.refresh_from_db()
        assert owner.username == "anna" and owner.phone == "+7 900"

    def test_update_keeps_session(self, api):
        api.put(ME, profile_body(username="renamed"))
        assert api.get(ME).json()["username"] == "renamed"

    @pytest.mark.parametrize("overrides", [
        {"username": ""}, {"email": ""}, {"username": "с пробелом"}, {"email": "не-почта"},
        {"phone": "1" * 21},
    ])
    def test_update_rejects_invalid(self, api, owner, overrides):
        response = api.put(ME, profile_body(**overrides))
        assert response.status_code == 400 and response.json()["detail"]
        owner.refresh_from_db()
        assert owner.username == "owner" and owner.email == "owner@example.com"

    def test_update_rejects_taken_username_and_email(self, api, owner, stranger):
        assert api.put(ME, profile_body(username="stranger")).status_code == 400
        response = api.put(ME, profile_body(email="stranger@example.com"))
        assert response.status_code == 400 and "почт" in response.json()["detail"]
        owner.refresh_from_db()
        assert owner.username == "owner"

    def test_update_own_email_unchanged_is_ok(self, api):
        assert api.put(ME, profile_body(username="owner", email="owner@example.com")).status_code == 200

    def test_update_rejects_invalid_json(self, api):
        assert api.put(ME, "{not json").status_code == 400

    def test_profile_requires_login(self, anon):
        assert anon.put(ME, profile_body()).status_code == 401
        assert anon.post(PASSWORD_URL, {}).status_code == 401

    def test_change_password(self, member):
        client = logged_in(member)
        response = client.post(PASSWORD_URL, {"old_password": PASSWORD, "new_password": "Pes-Reks-2027"})
        assert response.status_code == 204
        member.refresh_from_db()
        assert member.check_password("Pes-Reks-2027")
        assert client.get(ME).status_code == 200  # сессия не сбросилась

    @pytest.mark.parametrize("body", [
        {"old_password": "wrong", "new_password": "Pes-Reks-2027"},
        {"old_password": PASSWORD, "new_password": ""},
        {"old_password": PASSWORD, "new_password": "12345678"},
        {"old_password": PASSWORD, "new_password": "anna@example.com"},
        {},
    ])
    def test_change_password_rejects_invalid(self, member, body):
        response = logged_in(member).post(PASSWORD_URL, body)
        assert response.status_code == 400 and response.json()["detail"]
        member.refresh_from_db()
        assert member.check_password(PASSWORD)

    def test_profile_writes_require_csrf(self, member):
        client = Client(enforce_csrf_checks=True)
        client.force_login(member)
        client = ApiClient(client)
        assert client.put(ME, profile_body(username="x")).status_code == 403
        assert client.post(PASSWORD_URL, {"old_password": PASSWORD, "new_password": "Pes-Reks-2027"}).status_code == 403


# ---------- Контракт с app.js: полный круг запросов ----------

def test_full_cycle_like_the_frontend(api):
    """Создать питомца → напоминание → отметить выполненным → удалить."""
    pet_id = api.post(MAIN, {"name": "Рекс", "species": "Собака", "breed": "", "birth_date": None}).json()["id"]
    created = api.post(history_url(pet_id), history_body(Pet.objects.get(pk=pet_id))).json()
    assert created["done"] is False

    created.update(done=True, time="09:30")  # app.js отправляет время как HH:MM
    done = api.put(history_url(pet_id), created).json()
    assert done["done"] is True and done["time"] == "09:30:00"

    assert [r["done"] for r in api.get(history_url(pet_id)).json()] == [True]

    assert api.delete(f"{history_url(pet_id)}?id={created['id']}").status_code == 204
    assert api.get(history_url(pet_id)).json() == []


# ---------- Ветки, не покрытые выше ----------

def test_site_root_redirects_to_main(client):
    response = client.get("/")
    assert response.status_code == 302 and response.url == MAIN


class TestMainExtra:
    def test_update_pet_rejects_invalid_json(self, api, pet):
        assert api.put(MAIN, "{not json").status_code == 400

    def test_update_pet_without_id_is_404(self, api, pet):
        assert api.put(MAIN, {"name": "X"}).status_code == 404

    def test_update_pet_defaults_species_and_strips_name(self, api, pet):
        data = api.put(MAIN, {"id": pet.id, "name": "  Мурзик "}).json()
        assert data["name"] == "Мурзик" and data["species"] == "Кот" and data["breed"] == ""

    def test_update_pet_rejects_too_long_name(self, api, pet):
        assert api.put(MAIN, {"id": pet.id, "name": "я" * 101}).status_code == 400
        pet.refresh_from_db()
        assert pet.name == "Барсик"

    def test_create_pet_with_birth_date(self, api):
        assert api.post(MAIN, {"name": "Рекс", "birth_date": "2020-01-31"}).json()["birth_date"] == "2020-01-31"


class TestHistoryExtra:
    def test_update_rejects_invalid_json(self, api, pet, record):
        assert api.put(history_url(pet.id), "{").status_code == 400

    def test_update_without_id_is_404(self, api, pet, record):
        assert api.put(history_url(pet.id), {"title": "Т", "date": "2026-10-17"}).status_code == 404

    def test_update_keeps_type_and_done_when_not_sent(self, api, pet):
        record = History.objects.create(pet=pet, type="Препарат", title="Т", date=date(2026, 1, 1), done=True)
        api.put(history_url(pet.id), {"id": record.id, "title": "Т2", "date": "2026-01-01"})
        record.refresh_from_db()
        assert (record.type, record.done, record.title) == ("Препарат", True, "Т2")

    def test_update_clears_next_date(self, api, pet, record):
        api.put(history_url(pet.id), {"id": record.id, "title": "Т", "date": "2026-10-17", "next_date": ""})
        record.refresh_from_db()
        assert record.next_date is None

    def test_update_rejects_bad_next_date(self, api, pet, record):
        body = {"id": record.id, "title": "Т", "date": "2026-10-17", "next_date": "2026-02-30"}
        assert api.put(history_url(pet.id), body).status_code == 400

    def test_create_with_note_and_next_date(self, api, pet):
        data = api.post(history_url(pet.id), history_body(pet, note="н", next_date="2027-01-01")).json()
        assert data["note"] == "н" and data["next_date"] == "2027-01-01"

    def test_create_rejects_too_long_title(self, api, pet):
        assert api.post(history_url(pet.id), history_body(pet, title="я" * 201)).status_code == 400


class TestFoodExtra:
    def test_unknown_pet_put_and_delete_are_404(self, api):
        assert api.put(food_url(9999), {}).status_code == 404
        assert api.delete(f"{food_url(9999)}?id=1").status_code == 404

    def test_create_with_all_fields(self, api, pet):
        body = food_body(pet, preference="Понравилось", reaction="Зуд")
        data = api.post(food_url(pet.id), body).json()
        assert data["preference"] == "Понравилось" and data["reaction"] == "Зуд"

    def test_create_uses_pet_from_url_not_body(self, api, pet, other_pet):
        assert api.post(food_url(pet.id), food_body(other_pet)).json()["pet"] == pet.id

    def test_create_rejects_invalid_json(self, api, pet):
        assert api.post(food_url(pet.id), "{").status_code == 400

    def test_create_rejects_too_long_name(self, api, pet):
        assert api.post(food_url(pet.id), food_body(pet, name="я" * 201)).status_code == 400

    def test_update_rejects_invalid_json(self, api, pet, food):
        assert api.put(food_url(pet.id), "{").status_code == 400

    @pytest.mark.parametrize("overrides", [{"name": ""}, {"date": ""}, {"date": "2026-02-30"}])
    def test_update_rejects_invalid_and_does_not_change(self, api, pet, food, overrides):
        assert api.put(food_url(pet.id), food_body(pet, id=food.id, **overrides)).status_code == 400
        food.refresh_from_db()
        assert food.name == "Royal Canin"

    def test_update_keeps_status_preference_reaction_when_empty(self, api, pet):
        item = Food.objects.create(
            pet=pet, name="К", date=date(2026, 1, 1),
            status="Подошло", preference="Понравилось", reaction="Нет",
        )
        body = {"id": item.id, "name": "К", "date": "2026-01-01", "status": "", "preference": "", "reaction": ""}
        assert api.put(food_url(pet.id), body).status_code == 200
        item.refresh_from_db()
        assert (item.status, item.preference, item.reaction) == ("Подошло", "Понравилось", "Нет")

    def test_delete_unknown_or_garbage_id(self, api, pet, food):
        assert api.delete(f"{food_url(pet.id)}?id=9999").status_code == 404
        assert api.delete(f"{food_url(pet.id)}?id=abc").status_code == 400
        assert Food.objects.count() == 1


class TestMedCardExtra:
    def test_unknown_pet_write_is_404(self, api):
        assert api.post(card_url(9999), {}).status_code == 404
        assert api.put(card_url(9999), {}).status_code == 404
        assert api.delete(f"{card_url(9999)}?id=1").status_code == 404

    def test_create_with_numeric_weight(self, api, pet):
        assert api.post(card_url(pet.id), {"weight": 4.5}).json()["weight"] == "4.5"

    def test_create_with_empty_object(self, api, pet):
        data = api.post(card_url(pet.id), {}).json()
        assert data["weight"] is None and data["allergies"] == "" and data["pet"] == pet.id

    def test_create_rejects_invalid_json(self, api, pet):
        assert api.post(card_url(pet.id), "{").status_code == 400

    def test_update_rejects_invalid_json(self, api, pet, card):
        assert api.put(card_url(pet.id), "{").status_code == 400

    def test_update_rejects_negative_weight(self, api, pet, card):
        assert api.put(card_url(pet.id), {"id": card.id, "weight": "-0.5"}).status_code == 400
        card.refresh_from_db()
        assert str(card.weight) == "4.80"

    def test_update_clears_text_fields(self, api, pet, card):
        api.put(card_url(pet.id), {"id": card.id, "weight": "5"})
        card.refresh_from_db()
        assert card.allergies == "" and str(card.weight) == "5.00"

    def test_delete_unknown_or_garbage_id(self, api, pet, card):
        assert api.delete(f"{card_url(pet.id)}?id=9999").status_code == 404
        assert api.delete(f"{card_url(pet.id)}?id=abc").status_code == 400
        assert MedCard.objects.count() == 1

    def test_can_create_again_after_delete(self, api, pet, card):
        api.delete(f"{card_url(pet.id)}?id={card.id}")
        assert api.post(card_url(pet.id), {"weight": "3"}).status_code == 201


class TestAuthExtra:
    def test_login_rejects_invalid_json(self, anon):
        assert anon.post(LOGIN, "{not json").status_code == 400

    def test_login_by_unknown_email(self, anon, member):
        assert anon.post(LOGIN, {"login": "nobody@example.com", "password": PASSWORD}).status_code == 400

    def test_login_strips_login(self, anon, member):
        assert anon.post(LOGIN, {"login": "  anna ", "password": PASSWORD}).status_code == 200

    def test_register_strips_fields(self, anon):
        response = anon.post(REGISTER, register_body(username=" anna ", email=" Anna@Example.com ", phone=" 123 "))
        assert response.status_code == 201
        user = get_user_model().objects.get()
        assert (user.username, user.email, user.phone) == ("anna", "anna@example.com", "123")

    def test_register_rejects_password_like_username(self, anon):
        assert anon.post(REGISTER, register_body(username="barsik2026", password="barsik2026")).status_code == 400

    @pytest.mark.parametrize("url", [REGISTER, LOGIN])
    def test_auth_endpoints_require_post(self, anon, url):
        assert anon.get(url).status_code == 405

    def test_password_change_requires_post(self, api):
        assert api.get(PASSWORD_URL).status_code == 405

    def test_password_change_rejects_invalid_json(self, api):
        assert api.post(PASSWORD_URL, "{not json").status_code == 400

    def test_me_does_not_support_post(self, api):
        assert api.post(ME, {}).status_code == 405

    def test_failed_profile_update_does_not_touch_session_user(self, api):
        api.put(ME, profile_body(email="не-почта"))
        assert api.get(ME).json()["email"] == "owner@example.com"


@pytest.mark.parametrize("body", ["[]", "1", '"строка"', "null"])
@pytest.mark.parametrize("method, url_name", [
    ("post", "main"), ("put", "main"),
    ("post", "history_point"), ("put", "history_point"),
    ("post", "food_point"), ("put", "food_point"),
    ("post", "med_card_point"), ("put", "med_card_point"),
    ("post", "register"), ("post", "login"), ("put", "me"), ("post", "password"),
])
def test_non_object_json_is_400(api, pet, method, url_name, body):
    """JSON, который не является объектом, — это 400, а не 500."""
    args = [pet.id] if url_name.endswith("_point") else []
    assert api.send(method, reverse(url_name, args=args), body).status_code == 400
