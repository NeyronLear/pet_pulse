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
def api():
    return ApiClient(Client())


@pytest.fixture
def owner():
    # без пароля: хеширование паролей в тестах только замедляет прогон
    return get_user_model().objects.create(username="owner")


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

    def test_create_pet_without_login_uses_demo_owner(self, api):
        response = api.post(MAIN, {"name": " Рекс ", "species": "Собака", "breed": "", "birth_date": None})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Рекс" and data["birth_date"] is None
        assert Pet.objects.get(pk=data["id"]).owner.username == "demo"

    def test_create_pet_reuses_demo_owner(self, api):
        api.post(MAIN, {"name": "А"})
        api.post(MAIN, {"name": "Б"})
        assert get_user_model().objects.filter(username="demo").count() == 1

    def test_create_pet_logged_in_uses_current_user(self, owner):
        client = Client()
        client.force_login(owner)
        response = ApiClient(client).post(MAIN, {"name": "Рекс"})
        assert response.status_code == 201
        assert Pet.objects.get(pk=response.json()["id"]).owner == owner

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

    def test_write_with_valid_token_passes(self, pet):
        client = Client(enforce_csrf_checks=True)
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
