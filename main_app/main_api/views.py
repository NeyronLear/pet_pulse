"""Обработка запросов"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import View

from .models import Food, History, MedCard, Pet


def test(request: HttpRequest) -> HttpResponse:
    """Тестовая функция для CI/CD"""
    return HttpResponse(status=200)


# ---------- Общие утилиты ----------

def _wants_json(request: HttpRequest) -> bool:
    """fetch() из script.js всегда шлёт Accept: application/json,
    обычная навигация браузера — нет."""
    return "application/json" in request.headers.get("Accept", "")


def _body(request: HttpRequest) -> dict:
    """Разбирает JSON-тело запроса. Пустое тело — это пустой словарь."""
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("invalid json body") from error


def bad_request(message: str) -> JsonResponse:
    return JsonResponse({"detail": message}, status=400)


def _date(value):
    """Пустое значение — None; неверный формат или несуществующая дата — ValueError."""
    if not value:
        return None
    parsed = parse_date(value)  # сам бросает ValueError для 2026-02-30
    if parsed is None:
        raise ValueError("bad date")
    return parsed


def _time(value):
    """Пустое значение — None; неверный формат — ValueError."""
    if not value:
        return None
    parsed = parse_time(value)
    if parsed is None:
        raise ValueError("bad time")
    return parsed


def _owner(request: HttpRequest):
    """Pet.owner обязателен, а регистрации пока нет: берём текущего пользователя
    или общего пользователя demo."""
    if request.user.is_authenticated:
        return request.user
    user, _ = get_user_model().objects.get_or_create(username="demo")
    return user


def _negative_weight(weight) -> bool:
    """Модель не запрещает отрицательный вес, поэтому проверяем здесь.
    Нечисловое значение отсеет full_clean()."""
    try:
        return weight not in ("", None) and Decimal(str(weight)) < 0
    except InvalidOperation:
        return False


def _save(instance):
    """Проверяет модель (choices, длины, формат веса) и сохраняет.
    Возвращает ответ 400, если данные не прошли проверку, иначе None."""
    try:
        instance.full_clean()
    except ValidationError as error:
        return bad_request("; ".join(error.messages))
    instance.save()
    return None


# ---------- Сериализация моделей в JSON, который ждёт script.js ----------

def _iso(value):
    return value.isoformat() if value is not None else None


def pet_to_json(pet: Pet) -> dict:
    return {
        "id": pet.id,
        "name": pet.name,
        "species": pet.species,
        "breed": pet.breed,
        "birth_date": _iso(pet.birth_date),
    }


def history_to_json(record: History) -> dict:
    return {
        "id": record.id,
        "pet": record.pet_id,
        "type": record.type,
        "title": record.title,
        "date": _iso(record.date),
        "time": record.time.strftime("%H:%M:%S") if record.time else None,
        "note": record.note,
        "vet_conclusion": record.vet_conclusion,
        "next_date": _iso(record.next_date),
        "done": record.done,
    }


def food_to_json(item: Food) -> dict:
    return {
        "id": item.id,
        "pet": item.pet_id,
        "name": item.name,
        "date": _iso(item.date),
        "status": item.status,
        "note": item.note,
        "preference": item.preference,
        "reaction": item.reaction,
    }


def medcard_to_json(card: MedCard) -> dict:
    return {
        "id": card.id,
        "pet": card.pet_id,
        "weight": str(card.weight) if card.weight is not None else None,
        "allergies": card.allergies,
        "chronic_conditions": card.chronic_conditions,
        "notes": card.notes,
    }


# ---------- Главная страница + список питомцев (RESOURCES.pets.path === "/") ----------

@method_decorator(ensure_csrf_cookie, name="get")
class MainView(View):
    """GET отдаёт index.html обычному браузеру и список питомцев — fetch'у.
    POST/PUT — создание/обновление питомца (Pet)."""

    def get(self, request: HttpRequest):
        if _wants_json(request):
            pets = Pet.objects.all().order_by("id")
            return JsonResponse([pet_to_json(pet) for pet in pets], safe=False)
        return render(request, "main_api/index.html")

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        name = (data.get("name") or "").strip()
        if not name:
            return bad_request("Имя питомца обязательно.")

        try:
            pet = Pet(
                owner=_owner(request),
                name=name,
                species=data.get("species") or "Кот",
                breed=data.get("breed") or "",
                birth_date=_date(data.get("birth_date")),
            )
        except ValueError:
            return bad_request("Неверный формат даты.")
        return _save(pet) or JsonResponse(pet_to_json(pet), status=201)

    def put(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        pet = get_object_or_404(Pet, pk=data.get("id"))
        name = (data.get("name") or "").strip()
        if not name:
            return bad_request("Имя питомца обязательно.")

        pet.name = name
        pet.species = data.get("species") or "Кот"
        pet.breed = data.get("breed") or ""
        try:
            pet.birth_date = _date(data.get("birth_date"))
        except ValueError:
            return bad_request("Неверный формат даты.")
        return _save(pet) or JsonResponse(pet_to_json(pet))


# ---------- История / напоминания (RESOURCES.history.path === "/history/<pet_id>") ----------

class HistoryView(View):
    """CRUD записей History одного питомца.
    done=False — напоминание, done=True — запись здоровья (см. state в script.js)."""

    def get(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        records = History.objects.filter(pet_id=pet_id).order_by("date", "time")
        return JsonResponse([history_to_json(record) for record in records], safe=False)

    def post(self, request: HttpRequest, pet_id: int):
        pet = get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        title = (data.get("title") or "").strip()
        if not title or not data.get("date"):
            return bad_request("Название и дата обязательны.")

        try:
            record = History(
                pet=pet,
                type=data.get("type") or "Другое",
                title=title,
                date=_date(data.get("date")),
                time=_time(data.get("time")),
                note=data.get("note") or "",
                vet_conclusion=data.get("vet_conclusion") or "",
                next_date=_date(data.get("next_date")),
                done=bool(data.get("done", False)),
            )
        except ValueError:
            return bad_request("Неверный формат даты или времени.")
        return _save(record) or JsonResponse(history_to_json(record), status=201)

    def put(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        record = get_object_or_404(History, pk=data.get("id"), pet_id=pet_id)

        title = (data.get("title") or "").strip()
        if not title or not data.get("date"):
            return bad_request("Название и дата обязательны.")

        try:
            record.date = _date(data.get("date"))
            record.time = _time(data.get("time"))
            record.next_date = _date(data.get("next_date"))
        except ValueError:
            return bad_request("Неверный формат даты или времени.")
        record.type = data.get("type") or record.type
        record.title = title
        record.note = data.get("note") or ""
        record.vet_conclusion = data.get("vet_conclusion") or record.vet_conclusion
        record.done = bool(data.get("done", record.done))
        return _save(record) or JsonResponse(history_to_json(record))

    def delete(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        record_id = request.GET.get("id")
        if not record_id or not record_id.isdigit():
            return bad_request("Не передан id записи.")
        record = get_object_or_404(History, pk=record_id, pet_id=pet_id)
        record.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Медкарта (RESOURCES.medCards.path === "/med_card/<pet_id>") ----------

class MedcardView(View):
    """У питомца не более одной медкарты (OneToOne). Отсутствие карты — это 404,
    script.js ловит такую ошибку через ignoreNotFound и не считает её сбоем."""

    def get(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        try:
            card = MedCard.objects.get(pet_id=pet_id)
        except MedCard.DoesNotExist:
            return JsonResponse({"detail": "Медкарта не найдена."}, status=404)
        return JsonResponse(medcard_to_json(card))

    def post(self, request: HttpRequest, pet_id: int):
        pet = get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        if MedCard.objects.filter(pet_id=pet_id).exists():
            return bad_request("Медкарта уже существует, используйте обновление.")

        weight = data.get("weight")
        if _negative_weight(weight):
            return bad_request("Вес не может быть отрицательным.")
        card = MedCard(
            pet=pet,
            weight=weight if weight not in ("", None) else None,
            allergies=data.get("allergies") or "",
            chronic_conditions=data.get("chronic_conditions") or "",
            notes=data.get("notes") or "",
        )
        return _save(card) or JsonResponse(medcard_to_json(card), status=201)

    def put(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        card = get_object_or_404(MedCard, pk=data.get("id"), pet_id=pet_id)
        weight = data.get("weight")
        if _negative_weight(weight):
            return bad_request("Вес не может быть отрицательным.")
        card.weight =weight if weight not in ("", None) else None
        card.allergies = data.get("allergies") or ""
        card.chronic_conditions = data.get("chronic_conditions") or ""
        card.notes = data.get("notes") or ""
        try:
            card.full_clean()
        except ValidationError as error:
            return bad_request("; ".join(error.messages))
        card.save()
        return JsonResponse(medcard_to_json(card))

    def delete(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        card_id = request.GET.get("id")
        if not card_id or not card_id.isdigit():
            return bad_request("Не передан id записи.")
        card = get_object_or_404(MedCard, pk=card_id, pet_id=pet_id)
        card.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Питание (RESOURCES.food.path === "/food/<pet_id>") ----------

class FoodView(View):
    """CRUD записей Food одного питомца."""

    def get(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        items = Food.objects.filter(pet_id=pet_id).order_by("date")
        return JsonResponse([food_to_json(item) for item in items], safe=False)

    def post(self, request: HttpRequest, pet_id: int):
        pet = get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        name = (data.get("name") or "").strip()
        if not name or not data.get("date"):
            return bad_request("Название и дата обязательны.")

        try:
            item = Food(
                pet=pet,
                name=name,
                date=_date(data.get("date")),
                status=data.get("status") or "Наблюдать",
                note=data.get("note") or "",
                preference=data.get("preference") or "",
                reaction=data.get("reaction") or "",
            )
        except ValueError:
            return bad_request("Неверный формат даты.")
        return _save(item) or JsonResponse(food_to_json(item), status=201)

    def put(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        item = get_object_or_404(Food, pk=data.get("id"), pet_id=pet_id)

        name = (data.get("name") or "").strip()
        if not name or not data.get("date"):
            return bad_request("Название и дата обязательны.")

        try:
            item.date = _date(data.get("date"))
        except ValueError:
            return bad_request("Неверный формат даты.")
        item.name = name
        item.status = data.get("status") or item.status
        item.note = data.get("note") or ""
        item.preference = data.get("preference") or item.preference
        item.reaction = data.get("reaction") or item.reaction
        return _save(item) or JsonResponse(food_to_json(item))

    def delete(self, request: HttpRequest, pet_id: int):
        get_object_or_404(Pet, pk=pet_id)
        item_id = request.GET.get("id")
        if not item_id or not item_id.isdigit():
            return bad_request("Не передан id записи.")
        item = get_object_or_404(Food, pk=item_id, pet_id=pet_id)
        item.delete()
        return JsonResponse(None, safe=False, status=204)
