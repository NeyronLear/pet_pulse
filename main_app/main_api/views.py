"""Обработка запросов"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import View

from .models import Food, History, MedCard, Pet, PushSubscription, Tamagochi, WeightEntry
from .push import push_enabled


def test(request: HttpRequest) -> HttpResponse:
    """Тестовая функция для CI/CD"""
    return HttpResponse(status=200)


# ---------- Общие утилиты ----------

def _wants_json(request: HttpRequest) -> bool:
    """fetch() из script.js всегда шлёт Accept: application/json,
    обычная навигация браузера — нет."""
    return "application/json" in request.headers.get("Accept", "")


def _body(request: HttpRequest) -> dict:
    """Разбирает JSON-тело запроса. Пустое тело — это пустой словарь,
    JSON не-объект ([], 1, "строка") — ValueError."""
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("invalid json body") from error
    if not isinstance(data, dict):
        raise ValueError("json body is not an object")
    return data


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


def unauthorized() -> JsonResponse:
    """app.js на любой 401 показывает экран входа."""
    return JsonResponse({"detail": "Требуется вход."}, status=401)


class LoginRequiredJsonMixin:
    """Пускает в API только вошедших пользователей, остальным — 401 в JSON
    (стандартный LoginRequiredMixin делает редирект, а fetch'у нужен код)."""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return unauthorized()
        return super().dispatch(request, *args, **kwargs)


def _pet(request: HttpRequest, pet_id: int) -> Pet:
    """Питомец текущего пользователя; чужой или несуществующий — 404."""
    return get_object_or_404(Pet, pk=pet_id, owner=request.user)


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
        "photo": pet.photo.url if pet.photo else None,
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


def tamagochi_to_json(pet: Tamagochi) -> dict:
    return {
        "id": pet.id,
        "name": pet.name,
        "type": pet.type,
    }


def weight_to_json(entry: WeightEntry) -> dict:
    return {
        "id": entry.id,
        "pet": entry.pet_id,
        "weight": str(entry.weight),
        "date": _iso(entry.date),
    }


# ---------- Главная страница + список питомцев (RESOURCES.pets.path === "/") ----------

@method_decorator(ensure_csrf_cookie, name="get")
class MainView(View):
    """GET отдаёт index.html обычному браузеру и список питомцев — fetch'у.
    POST/PUT — создание/обновление питомца (Pet). Страница открыта всем,
    API — только после входа."""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        is_page = request.method == "GET" and not _wants_json(request)
        if not is_page and not request.user.is_authenticated:
            return unauthorized()
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest):
        if _wants_json(request):
            pets = Pet.objects.filter(owner=request.user).order_by("id")
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
                owner=request.user,
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

        pet = get_object_or_404(Pet, pk=data.get("id"), owner=request.user)
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


# ---------- Фото питомца (/pet_photo/<pet_id>) ----------

PHOTO_MAX_SIZE = 5 * 1024 * 1024


class PetPhotoForm(forms.Form):
    """ImageField через Pillow проверяет, что файл — действительно картинка."""
    photo = forms.ImageField(
        error_messages={
            "required": "Выберите фото.",
            "invalid_image": "Файл не похож на изображение.",
        },
    )

    def clean_photo(self):
        photo = self.cleaned_data["photo"]
        if photo.size > PHOTO_MAX_SIZE:
            raise ValidationError("Фото должно быть не больше 5 МБ.")
        return photo


class PetPhotoView(LoginRequiredJsonMixin, View):
    """POST (multipart/form-data, поле photo) ставит или заменяет фото, DELETE убирает его.
    Оба отвечают питомцем целиком, как MainView."""

    def post(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
        form = PetPhotoForm(files=request.FILES)
        if not form.is_valid():
            return bad_request("; ".join(form.errors["photo"]))
        # старый файл удаляем, чтобы в media не копились фото, на которые никто не ссылается
        pet.photo.delete(save=False)
        pet.photo = form.cleaned_data["photo"]
        pet.save(update_fields=["photo", "updated_at"])
        return JsonResponse(pet_to_json(pet))

    def delete(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
        pet.photo.delete(save=False)
        pet.photo = None
        pet.save(update_fields=["photo", "updated_at"])
        return JsonResponse(pet_to_json(pet))


# ---------- Регистрация, вход и выход (/auth/...) ----------

def user_to_json(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": _iso(user.date_joined.date()),
        "is_staff": user.is_staff,
    }


class RegisterView(View):
    """Создаёт пользователя и сразу выполняет вход."""

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not username or not email or not password:
            return bad_request("Логин, почта и пароль обязательны.")

        user = get_user_model()(
            username=username,
            email=email,
            phone=(data.get("phone") or "").strip(),
        )
        try:
            # user передаём, чтобы пароль не был похож на логин или почту
            validate_password(password, user)
        except ValidationError as error:
            return bad_request(" ".join(error.messages))
        user.set_password(password)

        error = _save(user)
        if error:
            return error
        login(request, user)
        return JsonResponse(user_to_json(user), status=201)


class LoginView(View):
    """Вход по логину или почте."""

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        identifier = (data.get("login") or "").strip()
        password = data.get("password") or ""
        if "@" in identifier:
            found = get_user_model().objects.filter(email__iexact=identifier).first()
            identifier = found.username if found else ""

        # authenticate сам не пускает неактивных пользователей
        user = authenticate(request, username=identifier, password=password)
        if user is None:
            return bad_request("Неверный логин или пароль.")
        login(request, user)
        return JsonResponse(user_to_json(user))


class JudgeLoginView(View):
    """Вход жюри без пароля: у каждого судьи свой аккаунт judge-<имя> с правами
    администратора, повторный вход с тем же именем — в тот же аккаунт.
    Выключается JUDGE_LOGIN_ENABLED=0."""

    def post(self, request: HttpRequest):
        if not settings.JUDGE_LOGIN_ENABLED:
            return JsonResponse({"detail": "Вход для жюри отключён."}, status=403)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        name = (data.get("name") or "").strip()
        slug = slugify(name, allow_unicode=True)
        if not slug or len(name) > 50:
            return bad_request("Введите имя (до 50 символов).")

        user, created = get_user_model().objects.get_or_create(
            username=f"judge-{slug}",
            defaults={"email": f"judge-{slug}@petpulse.local", "first_name": name},
        )
        if created:
            # у аккаунтов жюри нет пароля — по нему их и отличаем
            user.set_unusable_password()
        elif user.has_usable_password():
            # обычный пользователь с таким логином не должен стать админом
            return bad_request("Это имя занято, введите другое.")
        user.is_active = user.is_staff = user.is_superuser = True
        user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return JsonResponse(user_to_json(user))


class LogoutView(View):
    """Выход. Только POST, чтобы выйти нельзя было простой ссылкой."""

    def post(self, request: HttpRequest):
        logout(request)
        return HttpResponse(status=204)


class MeView(LoginRequiredJsonMixin, View):
    """Текущий пользователь — app.js по нему решает, показывать ли экран входа.
    PUT — редактирование профиля (логин, почта, телефон, имя, фамилия)."""

    def get(self, request: HttpRequest):
        return JsonResponse(user_to_json(request.user))

    def put(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        if not username or not email:
            return bad_request("Логин и почта обязательны.")

        # меняем копию: если данные не пройдут проверку, request.user останется прежним
        user = get_user_model().objects.get(pk=request.user.pk)
        user.username = username
        user.email = email
        user.phone = (data.get("phone") or "").strip()
        user.first_name = (data.get("first_name") or "").strip()
        user.last_name = (data.get("last_name") or "").strip()
        try:
            # пароль не редактируется здесь, а у пользователей из createsuperuser/тестов он может быть пустым
            user.full_clean(exclude=["password"])
        except ValidationError as error:
            return bad_request("; ".join(error.messages))
        user.save()
        return JsonResponse(user_to_json(user))


class PasswordView(LoginRequiredJsonMixin, View):
    """Смена пароля: нужен текущий пароль. Сессия после смены сохраняется."""

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        user = request.user
        old_password = data.get("old_password") or ""
        new_password = data.get("new_password") or ""
        if not user.check_password(old_password):
            return bad_request("Текущий пароль указан неверно.")
        if not new_password:
            return bad_request("Новый пароль обязателен.")
        try:
            validate_password(new_password, user)
        except ValidationError as error:
            return bad_request(" ".join(error.messages))
        user.set_password(new_password)
        user.save()
        # иначе Django разлогинит пользователя: хеш сессии зависит от пароля
        update_session_auth_hash(request, user)
        return HttpResponse(status=204)


# ---------- История / напоминания (RESOURCES.history.path === "/history/<pet_id>") ----------

class HistoryView(LoginRequiredJsonMixin, View):
    """CRUD записей History одного питомца.
    done=False — напоминание, done=True — запись здоровья (см. state в script.js)."""

    def get(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        records = History.objects.filter(pet_id=pet_id).order_by("date", "time")
        return JsonResponse([history_to_json(record) for record in records], safe=False)

    def post(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
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
        _pet(request, pet_id)
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
        _pet(request, pet_id)
        record_id = request.GET.get("id")
        if not record_id or not record_id.isdigit():
            return bad_request("Не передан id записи.")
        record = get_object_or_404(History, pk=record_id, pet_id=pet_id)
        record.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Медкарта (RESOURCES.medCards.path === "/med_card/<pet_id>") ----------

class MedcardView(LoginRequiredJsonMixin, View):
    """У питомца не более одной медкарты (OneToOne). Отсутствие карты — это 404,
    script.js ловит такую ошибку через ignoreNotFound и не считает её сбоем."""

    def get(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        try:
            card = MedCard.objects.get(pet_id=pet_id)
        except MedCard.DoesNotExist:
            return JsonResponse({"detail": "Медкарта не найдена."}, status=404)
        return JsonResponse(medcard_to_json(card))

    def post(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
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
        error = _save(card)
        if error:
            return error
        _remember_weight(pet, weight if weight not in ("", None) else None)
        return JsonResponse(medcard_to_json(card), status=201)

    def put(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
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
        _remember_weight(card.pet, weight if weight not in ("", None) else None)
        return JsonResponse(medcard_to_json(card))

    def delete(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        card_id = request.GET.get("id")
        if not card_id or not card_id.isdigit():
            return bad_request("Не передан id записи.")
        card = get_object_or_404(MedCard, pk=card_id, pet_id=pet_id)
        card.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Замеры веса (RESOURCES.weights.path === "/weight/<pet_id>") ----------

def _remember_weight(pet: Pet, weight):
    """Сохранённый в медкарте вес — это замер на день сохранения:
    он же попадает в график динамики веса (один замер на дату)."""
    if weight in ("", None):
        return
    WeightEntry.objects.update_or_create(
        pet=pet, date=date.today(), defaults={"weight": weight},
    )


class WeightView(LoginRequiredJsonMixin, View):
    """CRUD замеров веса одного питомца — данные для графика динамики."""

    def get(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        entries = WeightEntry.objects.filter(pet_id=pet_id).order_by("date", "id")
        return JsonResponse([weight_to_json(entry) for entry in entries], safe=False)

    def post(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        if not data.get("weight") or not data.get("date"):
            return bad_request("Дата и вес обязательны.")
        if _negative_weight(data.get("weight")):
            return bad_request("Вес не может быть отрицательным.")

        try:
            # число из JSON (4.95) у Decimal даёт длинный хвост, поэтому вес — всегда строка
            entry = WeightEntry(pet=pet, weight=str(data.get("weight")), date=_date(data.get("date")))
        except ValueError:
            return bad_request("Неверный формат даты.")
        return _save(entry) or JsonResponse(weight_to_json(entry), status=201)

    def put(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        entry = get_object_or_404(WeightEntry, pk=data.get("id"), pet_id=pet_id)
        if not data.get("weight"):
            return bad_request("Вес обязателен.")
        if _negative_weight(data.get("weight")):
            return bad_request("Вес не может быть отрицательным.")
        entry.weight = str(data.get("weight"))
        try:
            entry.date = _date(data.get("date"))
        except ValueError:
            return bad_request("Неверный формат даты.")
        return _save(entry) or JsonResponse(weight_to_json(entry))

    def delete(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        entry_id = request.GET.get("id")
        if not entry_id or not entry_id.isdigit():
            return bad_request("Не передан id записи.")
        entry = get_object_or_404(WeightEntry, pk=entry_id, pet_id=pet_id)
        entry.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Питание (RESOURCES.food.path === "/food/<pet_id>") ----------

class FoodView(LoginRequiredJsonMixin, View):
    """CRUD записей Food одного питомца."""

    def get(self, request: HttpRequest, pet_id: int):
        _pet(request, pet_id)
        items = Food.objects.filter(pet_id=pet_id).order_by("date")
        return JsonResponse([food_to_json(item) for item in items], safe=False)

    def post(self, request: HttpRequest, pet_id: int):
        pet = _pet(request, pet_id)
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
        _pet(request, pet_id)
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
        _pet(request, pet_id)
        item_id = request.GET.get("id")
        if not item_id or not item_id.isdigit():
            return bad_request("Не передан id записи.")
        item = get_object_or_404(Food, pk=item_id, pet_id=pet_id)
        item.delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Тамагочи (tamagochi.path === "/tamagochi") ----------

class TamagochiView(LoginRequiredJsonMixin, View):
    """У пользователя не более одного тамагочи (OneToOne), поэтому id не нужен.
    Отсутствие тамагочи — это 404, как у медкарты."""

    def get(self, request: HttpRequest):
        try:
            pet = Tamagochi.objects.get(owner=request.user)
        except Tamagochi.DoesNotExist:
            return JsonResponse({"detail": "Тамагочи не найден."}, status=404)
        return JsonResponse(tamagochi_to_json(pet))

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        if Tamagochi.objects.filter(owner=request.user).exists():
            return bad_request("Тамагочи уже существует, используйте обновление.")

        name = (data.get("name") or "").strip()
        if not name:
            return bad_request("Имя тамагочи обязательно.")
        pet = Tamagochi(owner=request.user, name=name, type=data.get("type") or "dog")
        return _save(pet) or JsonResponse(tamagochi_to_json(pet), status=201)

    def put(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        pet = get_object_or_404(Tamagochi, owner=request.user)
        name = (data.get("name") or "").strip()
        if not name:
            return bad_request("Имя тамагочи обязательно.")
        pet.name = name
        pet.type = data.get("type") or pet.type
        return _save(pet) or JsonResponse(tamagochi_to_json(pet))

    def delete(self, request: HttpRequest):
        get_object_or_404(Tamagochi, owner=request.user).delete()
        return JsonResponse(None, safe=False, status=204)


# ---------- Push-уведомления (/push/...) ----------

def service_worker(request: HttpRequest) -> HttpResponse:
    """Service worker должен лежать не глубже страниц, которыми управляет:
    из /static/js/ он не увидел бы /user/. Поэтому отдаём его по адресу /user/sw.js."""
    response = render(request, "main_api/sw.js", content_type="application/javascript")
    # браузер должен сразу видеть новую версию воркера
    response["Cache-Control"] = "no-cache"
    return response


class PushKeyView(LoginRequiredJsonMixin, View):
    """Публичный VAPID-ключ для pushManager.subscribe(). Пустой ключ — push выключен."""

    def get(self, request: HttpRequest):
        key = settings.VAPID_PUBLIC_KEY if push_enabled() else ""
        return JsonResponse({"public_key": key})


class PushSubscribeView(LoginRequiredJsonMixin, View):
    """POST — сохранить подписку браузера (JSON из PushSubscription.toJSON()),
    DELETE — удалить её по endpoint (при отписке и выходе из аккаунта)."""

    def post(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")

        endpoint = data.get("endpoint") or ""
        keys = data.get("keys") or {}
        if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
            return bad_request("Неполные данные подписки.")

        # endpoint уникален: если в этом браузере раньше входил другой
        # пользователь, подписка переходит к текущему
        subscription = PushSubscription.objects.filter(endpoint=endpoint).first()
        created = subscription is None
        if created:
            subscription = PushSubscription(endpoint=endpoint)
        subscription.user = request.user
        subscription.p256dh = keys["p256dh"]
        subscription.auth = keys["auth"]
        return _save(subscription) or HttpResponse(status=201 if created else 204)

    def delete(self, request: HttpRequest):
        try:
            data = _body(request)
        except ValueError:
            return bad_request("Некорректный JSON.")
        PushSubscription.objects.filter(
            user=request.user, endpoint=data.get("endpoint") or ""
        ).delete()
        return HttpResponse(status=204)
