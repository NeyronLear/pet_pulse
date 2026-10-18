"use strict";

// ---------- Утилиты ----------

const $ = (selector) => document.querySelector(selector);

const HTML_ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);

// Готовый безопасный HTML: в шаблон вставляется как есть, без экранирования.
class SafeHtml {
  constructor(value) {
    this.value = value;
  }
  toString() {
    return this.value;
  }
}

// Шаблон html`<b>${text}</b>`: подстановки экранируются автоматически,
// кроме результатов другого html`` (их можно вкладывать и передавать массивами).
// Переносы строк между тегами вырезаются, поэтому отступы в шаблонах не влияют на вёрстку.
function html(strings, ...values) {
  const toHtml = (value) => {
    if (value instanceof SafeHtml) return value.value;
    if (Array.isArray(value)) return value.map(toHtml).join("");
    if (value == null || value === false) return "";
    return esc(value);
  };
  let result = strings[0];
  values.forEach((value, i) => {
    result += toHtml(value) + strings[i + 1];
  });
  return new SafeHtml(result.replace(/>\s*\n\s*</g, "><").trim());
}

const pad = (number) => String(number).padStart(2, "0");
const toDateKey = (date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const todayKey = () => toDateKey(new Date());
const formatDate = (dateKey) =>
  new Date(`${dateKey}T12:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });

// id могут быть числами (из БД) или строками (из data-атрибутов и <select>),
// поэтому сравниваем их как строки.
const sameId = (a, b) => String(a) === String(b);
const findById = (items, id) => items.find((item) => sameId(item.id, id));

const initial = (name) => Array.from(name)[0] ?? "";
const plainOptions = (...values) => values.map((value) => [value, value]);
const byDateTime = (a, b) =>
  `${a.date}${a.time || ""}`.localeCompare(`${b.date}${b.time || ""}`);

// ---------- Данные ----------

// Ключи state совпадают с моделями Django: pets — Pet, history — History,
// food — Food, medCards — MedCard.
const emptyState = () => ({ pets: [], history: [], food: [], medCards: [] });

// History хранит и напоминания, и записи здоровья: невыполненные записи
// показываются как напоминания, выполненные — на странице «Здоровье».
// Поэтому events и health отдельно не хранятся, а считаются из history.
const state = {
  ...emptyState(),
  get events() {
    return this.history.filter((record) => !record.done);
  },
  get health() {
    return this.history.filter((record) => record.done);
  },
};

// ---------- Обращения к серверу ----------

// Маршруты из main_api/urls.py подключены в backend/urls.py под префиксом user/.
const API_ROOT = "/user";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Django проверяет CSRF у POST/PUT/DELETE. Токен лежит в cookie csrftoken,
// а сама cookie появляется, если страницу отдаёт вьюха с @ensure_csrf_cookie.
const csrfToken = () =>
  document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1] ?? "";

async function request(method, path, body) {
  const response = await fetch(API_ROOT + path, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body !== undefined && { "Content-Type": "application/json" }),
      ...(method !== "GET" && { "X-CSRFToken": csrfToken() }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    // Ошибки вьюх приходят как {"detail": "..."} — этот текст можно показать пользователю.
    const error = await response.json().catch(() => null);
    throw new ApiError(
      error?.detail || `${method} ${path}: ${response.status}`,
      response.status,
    );
  }
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

// Как каждый ресурс интерфейса связан с моделью и маршрутом Django:
//   path       — маршрут из urls.py (без завершающего «/», как в path("history/<int:pet_id>"))
//   fromServer — JSON модели → запись интерфейса
//   toServer   — запись интерфейса → JSON модели
// В интерфейсе пустое значение — "", в БД у необязательных дат, времени и веса — null,
// поэтому конвертируем в обе стороны. Поля, которых нет в форме (vet_conclusion, next_date,
// preference, reaction), пропускаем через интерфейс как есть, чтобы update их не затирал.
const RESOURCES = {
  pets: {
    path: () => "/",
    fromServer: (row) => ({
      id: row.id,
      name: row.name,
      species: row.species,
      breed: row.breed,
      birth: row.birth_date ?? "",
    }),
    toServer: (pet) => ({
      id: pet.id,
      name: pet.name,
      species: pet.species,
      breed: pet.breed,
      birth_date: pet.birth || null,
    }),
  },
  history: {
    path: (petId) => `/history/${petId}`,
    fromServer: (row) => ({
      id: row.id,
      pet: row.pet,
      type: row.type,
      title: row.title,
      date: row.date,
      time: (row.time ?? "").slice(0, 5), // Django отдаёт "10:00:00", интерфейсу нужно "10:00"
      note: row.note,
      vet_conclusion: row.vet_conclusion,
      next_date: row.next_date,
      done: row.done,
    }),
    toServer: (record) => ({
      id: record.id,
      pet: Number(record.pet),
      type: record.type,
      title: record.title,
      date: record.date,
      time: record.time || null,
      note: record.note,
      vet_conclusion: record.vet_conclusion,
      next_date: record.next_date ?? null,
      done: record.done,
    }),
  },
  food: {
    path: (petId) => `/food/${petId}`,
    fromServer: (row) => ({
      id: row.id,
      pet: row.pet,
      title: row.name, // в модели Food поле называется name
      date: row.date,
      status: row.status,
      note: row.note,
      preference: row.preference,
      reaction: row.reaction,
    }),
    toServer: (item) => ({
      id: item.id,
      pet: Number(item.pet),
      name: item.title,
      date: item.date,
      status: item.status,
      note: item.note,
      preference: item.preference,
      reaction: item.reaction,
    }),
  },
  medCards: {
    path: (petId) => `/med_card/${petId}`,
    fromServer: (row) => ({
      id: row.id,
      pet: row.pet,
      weight: row.weight ?? "",
      allergies: row.allergies,
      chronic_conditions: row.chronic_conditions,
      notes: row.notes,
    }),
    toServer: (card) => ({
      id: card.id,
      pet: Number(card.pet),
      weight: card.weight === "" ? null : card.weight,
      allergies: card.allergies,
      chronic_conditions: card.chronic_conditions,
      notes: card.notes,
    }),
  },
};

// У питомца может ещё не быть медкарты: это не ошибка.
const ignoreNotFound = (error) => {
  if (error.status === 404) return null;
  throw error;
};

// Слой данных: единственное место, которое общается с сервером.
// Остальной код работает только с записями интерфейса (state).
const api = {
  // Питомцы приходят с «главной» (GET /user/), остальное запрашивается по каждому питомцу.
  async load() {
    const pets = (await request("GET", RESOURCES.pets.path())).map(
      RESOURCES.pets.fromServer,
    );
    const perPet = await Promise.all(
      pets.map(async ({ id }) => {
        const [history, food, medCard] = await Promise.all([
          request("GET", RESOURCES.history.path(id)),
          request("GET", RESOURCES.food.path(id)),
          request("GET", RESOURCES.medCards.path(id)).catch(ignoreNotFound),
        ]);
        return {
          history: history.map(RESOURCES.history.fromServer),
          food: food.map(RESOURCES.food.fromServer),
          medCards: medCard?.id == null ? [] : [RESOURCES.medCards.fromServer(medCard)],
        };
      }),
    );
    return {
      pets,
      history: perPet.flatMap((part) => part.history),
      food: perPet.flatMap((part) => part.food),
      medCards: perPet.flatMap((part) => part.medCards),
    };
  },
  // Нет id — создаём (POST), есть — обновляем (PUT, id уходит в теле запроса).
  // Сервер должен вернуть сохранённую запись вместе с id.
  async save(bucket, item) {
    const resource = RESOURCES[bucket];
    const saved = await request(
      item.id == null ? "POST" : "PUT",
      resource.path(item.pet),
      resource.toServer(item),
    );
    return resource.fromServer(saved);
  },
  // id удаляемой записи уходит в query-параметре: DELETE /user/history/<pet_id>?id=<id>
  async remove(bucket, item) {
    const path = RESOURCES[bucket].path(item.pet);
    await request("DELETE", `${path}?id=${encodeURIComponent(item.id)}`);
  },
};

// Вход и регистрация: сервер сам ставит cookie сессии и возвращает пользователя.
const auth = {
  me: () => request("GET", "/auth/me"),
  updateMe: (body) => request("PUT", "/auth/me", body),
  changePassword: (body) => request("POST", "/auth/password", body),
  login: (body) => request("POST", "/auth/login", body),
  register: (body) => request("POST", "/auth/register", body),
  logout: () => request("POST", "/auth/logout"),
};

async function saveItem(bucket, item) {
  const saved = await api.save(bucket, item);
  const index = state[bucket].findIndex((x) => sameId(x.id, saved.id));
  if (index < 0) state[bucket].push(saved);
  else state[bucket][index] = saved;
  return saved;
}

async function removeItem(bucket, id) {
  const item = findById(state[bucket], id);
  if (!item) return;
  await api.remove(bucket, item);
  state[bucket] = state[bucket].filter((x) => !sameId(x.id, id));
}

const petName = (id) => findById(state.pets, id)?.name ?? "Питомец не найден";

// Состояние интерфейса, которое не нужно хранить в базе.
const ui = { day: todayKey(), foodFilter: "Все", editing: null, user: null };

let toastTimer;
function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 3500);
}

// ---------- Общие блоки страниц ----------

function pageHeading({ title, note, kind, button }) {
  return html`
    <div class="heading">
      <div>
        <h1>${title}</h1>
        <p class="muted">${note}</p>
      </div>
      <button class="button" data-action="add" data-kind="${kind}">+ ${button}</button>
    </div>`;
}

function eventRow(item) {
  const isMedicine = item.type === "Препарат";
  return html`
    <div class="event ${item.done && "done"}">
      <span class="symbol ${isMedicine && "yellow"}" aria-hidden="true">${isMedicine ? "◒" : "+"}</span>
      <div class="event-body">
        <strong>${item.title}</strong>
        <small>${petName(item.pet)} · ${item.type}</small>
      </div>
      <small>${item.time || "Весь день"}</small>
      <button class="check" data-action="toggle-done" data-id="${item.id}"
        aria-label="${item.done ? "Отменить выполнение" : "Отметить выполненным"}">${item.done ? "✓" : ""}</button>
    </div>`;
}

function eventList(items) {
  return items.length
    ? items.map(eventRow)
    : html`<div class="empty">На этот день ничего не запланировано.<br>Можно просто побыть рядом.</div>`;
}

// ---------- Страница «Главная» ----------

function homeView() {
  return html`
    ${pageHeading({
      title: "Хороший день для заботы",
      note: "Всё важное о ваших любимцах под рукой.",
      kind: "event",
      button: "Добавить напоминание",
    })}
    <div class="dashboard">
      ${weekCard()}
      <div class="right">
        ${homePetsCard()}
        <div class="tip">
          <strong>Немного внимания каждый день</strong>
          <p>Наблюдайте за привычками питомца. Небольшие изменения помогут вовремя заметить важное.</p>
        </div>
      </div>
    </div>
    <div class="lower">
      <section class="card">
        <div class="section-head">
          <h2>Здоровье</h2>
          <a class="link" href="#health">История →</a>
        </div>
        <div class="metric">${state.health.length}</div>
        <p class="muted">записей в карте здоровья</p>
      </section>
      <section class="card">
        <div class="section-head">
          <h2>Питание</h2>
          <a href="#food" class="link">Дневник →</a>
        </div>
        <div class="metric">${state.food.filter((item) => item.status === "Подошло").length} / ${state.food.length}</div>
        <p class="muted">кормов с хорошей переносимостью</p>
      </section>
    </div>`;
}

function weekCard() {
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() + offset);
    return { date, key: toDateKey(date) };
  });
  const dayLabel =
    ui.day === todayKey() ? "СЕГОДНЯ" : formatDate(ui.day).toUpperCase();

  return html`
    <section class="card">
      <div class="section-head">
        <h2>Ближайшая неделя</h2>
        <span class="muted">${formatDate(days[0].key)} — ${formatDate(days[6].key)}</span>
      </div>
      <div class="week">${days.map(dayButton)}</div>
      <p class="day-label">${dayLabel}</p>
      ${eventList(state.events.filter((item) => item.date === ui.day))}
      <a href="#reminders" class="link">Все напоминания →</a>
    </section>`;
}

function dayButton({ date, key }) {
  const isActive = key === ui.day;
  const hasOpenEvents = state.events.some(
    (item) => item.date === key && !item.done,
  );
  return html`
    <button class="day ${isActive && "active"}" data-action="select-day" data-day="${key}" aria-pressed="${String(isActive)}">
      <span>${date.toLocaleDateString("ru-RU", { weekday: "short" })}</span>
      <b>${date.getDate()}</b>
      <i class="${hasOpenEvents ? "" : "hidden"}"></i>
    </button>`;
}

function homePetsCard() {
  return html`
    <section class="card">
      <div class="section-head">
        <h2>Мои питомцы</h2>
        <button class="button light" data-action="add" data-kind="pet">+ Добавить</button>
      </div>
      ${
        state.pets.length
          ? state.pets.map(miniPet)
          : html`<p class="empty">Добавьте первого питомца</p>`
      }
    </section>`;
}

function miniPet(pet) {
  return html`
    <a class="mini-pet" href="#pets">
      <span class="avatar">${initial(pet.name)}</span>
      <div>
        <strong>${pet.name}</strong>
        <p>${pet.species} · ${pet.breed || "Порода не указана"}</p>
      </div>
    </a>`;
}

// ---------- Страница «Мои питомцы» ----------

function petsView() {
  return html`
    ${pageHeading({
      title: "Те, о ком мы заботимся",
      note: "Маленькие личности с большой историей.",
      kind: "pet",
      button: "Добавить питомца",
    })}
    <div class="pet-grid">
      ${
        state.pets.length
          ? state.pets.map(petCard)
          : html`<div class="card empty">Здесь появятся ваши питомцы.</div>`
      }
    </div>`;
}

function petCard(pet) {
  const healthRecords = state.health.filter((record) =>
    sameId(record.pet, pet.id),
  );
  return html`
    <article class="card pet-card">
      <div class="avatar">${initial(pet.name)}</div>
      <h2>${pet.name}</h2>
      <p class="muted">${pet.species} · ${pet.breed || "Без указанной породы"}</p>
      <dl>
        <dt>День рождения</dt>
        <dd>${pet.birth ? formatDate(pet.birth) : "Не указан"}</dd>
        <dt>Записей здоровья</dt>
        <dd>${healthRecords.length}</dd>
      </dl>
      <button class="button light full" data-action="edit" data-kind="pet" data-id="${pet.id}">Изменить карточку</button>
    </article>`;
}

// ---------- Страница «Здоровье» ----------

function healthView() {
  const records = [...state.health].sort((a, b) => b.date.localeCompare(a.date));
  return html`
    ${pageHeading({
      title: "Здоровье в деталях",
      note: "История заботы, которую легко восстановить.",
      kind: "health",
      button: "Добавить запись",
    })}
    <div class="notice">Личная карта наблюдений не заменяет консультацию ветеринара.</div>
    ${
      state.pets.length
        ? html`
            <p class="day-label">МЕДКАРТЫ</p>
            <div class="pet-grid">${state.pets.map(medCard)}</div>
            <p class="day-label">ИСТОРИЯ</p>`
        : ""
    }
    ${
      records.length
        ? records.map(healthRecord)
        : html`<div class="card empty">Пока нет записей здоровья.</div>`
    }`;
}

// Медкарта питомца: в БД она одна на питомца (OneToOne) и может быть ещё не создана.
function medCard(pet) {
  const card = state.medCards.find((item) => sameId(item.pet, pet.id));
  const weight =
    card?.weight === "" || card?.weight == null
      ? "не указан"
      : `${Number(card.weight).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг`;
  return html`
    <article class="card record">
      <span class="eyebrow">МЕДКАРТА</span>
      <h2>${pet.name}</h2>
      ${
        card
          ? html`
              <p>Вес: ${weight}</p>
              <p>Аллергии: ${card.allergies || "не указаны"}</p>
              <p>Хронические заболевания: ${card.chronic_conditions || "не указаны"}</p>
              <p>Заметки: ${card.notes || "нет"}</p>`
          : html`<p>Медкарта ещё не заполнена.</p>`
      }
      <div class="actions">
        <button class="button" data-action="edit" data-kind="medcard" data-id="${pet.id}">${card ? "Изменить" : "Заполнить"}</button>
      </div>
    </article>`;
}

function healthRecord(record) {
  return html`
    <article class="card record">
      <div class="section-head">
        <span class="eyebrow">${petName(record.pet)} · ${record.type}</span>
        <span class="muted">${formatDate(record.date)}</span>
      </div>
      <h2>${record.title}</h2>
      <p>${record.note}</p>
      <div class="actions">
        <button class="button-danger" data-action="delete" data-bucket="history" data-id="${record.id}">Удалить запись</button>
      </div>
    </article>`;
}

// ---------- Страница «Питание» ----------

const FOOD_FILTERS = ["Все", "Подошло", "Не подошло", "Наблюдать"];

function foodView() {
  const items = state.food.filter(
    (item) => ui.foodFilter === "Все" || item.status === ui.foodFilter,
  );
  const emptyText = state.food.length
    ? "Нет записей с выбранной оценкой."
    : "Пока нет записей о питании.";
  return html`
    ${pageHeading({
      title: "Подходит именно им",
      note: "Корма, предпочтения и ваши наблюдения.",
      kind: "food",
      button: "Добавить корм",
    })}
    <div class="filters">${FOOD_FILTERS.map(foodFilterButton)}</div>
    <div class="food-grid">
      ${
        items.length
          ? items.map(foodCard)
          : html`<div class="card empty">${emptyText}</div>`
      }
    </div>`;
}

function foodFilterButton(value) {
  return html`<button class="filter ${ui.foodFilter === value && "active"}" data-action="filter-food" data-filter="${value}">${value}</button>`;
}

function foodCard(item) {
  return html`
    <article class="card record">
      <span class="eyebrow">${petName(item.pet)}</span>
      <h2>${item.title}</h2>
      <p>${item.note}</p>
      <div class="section-head">
        <span class="badge ${item.status !== "Подошло" && "warn"}">${item.status}</span>
        <button class="button-danger" data-action="delete" data-bucket="food" data-id="${item.id}">Удалить</button>
      </div>
    </article>`;
}

// ---------- Страница «Напоминания» ----------

function remindersView() {
  const items = [...state.events].sort(byDateTime);
  return html`
    ${pageHeading({
      title: "Важное не потеряется",
      note: "Процедуры и маленькие дела на каждый день.",
      kind: "event",
      button: "Добавить напоминание",
    })}
      ${
        items.length
          ? items.map(reminderItem)
          : html`<div class="empty">Пока нет напоминаний</div>`
      }
    </section>`;
}

function reminderItem(item) {
  const isOverdue = item.date < todayKey() && !item.done;
  return html`
    <div class="reminder">
      <p class="day-label">${formatDate(item.date)}${isOverdue && " · ПРОСРОЧЕНО"}</p>
      ${eventRow(item)}
      <div class="actions">
        <button class="button" data-action="export" data-id="${item.id}">В календарь</button>
        <button class="button-danger" data-action="delete" data-bucket="history" data-id="${item.id}">Удалить</button>
      </div>
    </div>`;
}

// ---------- Страница «Профиль» ----------

const fullName = (user) => [user.first_name, user.last_name].filter(Boolean).join(" ");

function profileView() {
  const user = ui.user;
  const stats = [
    ["Питомцев", state.pets.length],
    ["Записей здоровья", state.health.length],
    ["Напоминаний", state.events.length],
    ["Записей о питании", state.food.length],
  ];
  return html`
    ${pageHeading({
      title: "Мой профиль",
      note: "Ваши данные и настройки входа.",
      kind: "profile",
      button: "Редактировать профиль",
    })}
    <div class="profile">
      <section class="card profile-card">
        <div class="avatar">${initial(fullName(user) || user.username).toUpperCase()}</div>
        <h2>${fullName(user) || user.username}</h2>
        <p class="muted">@${user.username}</p>
        <dl>
          <dt>Почта</dt>
          <dd>${user.email}</dd>
          <dt>Телефон</dt>
          <dd>${user.phone || "Не указан"}</dd>
          <dt>С нами с</dt>
          <dd>${new Date(`${user.date_joined}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}</dd>
        </dl>
      </section>
      <div class="profile-side">
        <section class="card">
          <div class="section-head">
            <h2>Забота в цифрах</h2>
          </div>
          <div class="profile-stats">
            ${stats.map(([label, value]) => html`
              <div>
                <div class="metric">${value}</div>
                <p class="muted">${label}</p>
              </div>`)}
          </div>
        </section>
        <section class="card">
          <div class="section-head">
            <h2>Безопасность</h2>
          </div>
          <p class="muted">Используйте надёжный пароль, который не совпадает с логином и почтой.</p>
          <div class="actions">
            <button class="button light" data-action="add" data-kind="password">Сменить пароль</button>
            <button class="button-danger" data-action="logout">Выйти из аккаунта</button>
          </div>
        </section>
      </div>
    </div>`;
}

// ---------- Страницы и навигация ----------

// title показывается во вкладке браузера: «<title> · PetPulse».
const PAGES = {
  home: { title: "Главная", view: homeView },
  pets: { title: "Мои питомцы", view: petsView },
  health: { title: "Здоровье", view: healthView },
  food: { title: "Питание", view: foodView },
  reminders: { title: "Напоминания", view: remindersView },
  profile: { title: "Профиль", view: profileView },
};

// location.hash начинается с «#», поэтому первый символ отбрасываем.
function currentPage() {
  const name = location.hash.slice(1);
  return Object.hasOwn(PAGES, name) ? name : "home";
}

function render() {
  const page = currentPage();
  document.title = `${PAGES[page].title} · PetPulse`;
  document
    .querySelectorAll("nav a")
    .forEach((link) => link.classList.toggle("active", link.hash === `#${page}`));
  $("#main").innerHTML = PAGES[page].view().toString();
}

// ---------- Форма добавления и редактирования ----------

// attrs — дополнительные атрибуты input готовым html``, например step и min для числа.
function inputField(
  name,
  label,
  { type = "text", value = "", required = false, maxlength = 100, attrs = "" } = {},
) {
  return html`
    <div class="field">
      <label for="field-${name}">${label}${required && " *"}</label>
      <input id="field-${name}" name="${name}" type="${type}" value="${value}" maxlength="${maxlength}" ${attrs} ${required && "required"}>
    </div>`;
}

function selectField(name, label, options, selected) {
  return html`
    <div class="field">
      <label for="field-${name}">${label}</label>
      <select name="${name}" id="field-${name}">
        ${options.map(([value, text]) => html`<option value="${value}" ${value === selected && "selected"}>${text}</option>`)}
      </select>
    </div>`;
}

const petField = () =>
  selectField("pet", "Питомец", state.pets.map((pet) => [pet.id, pet.name]));
const titleField = (label = "Название") =>
  inputField("title", label, { required: true });
const dateField = () =>
  inputField("date", "Дата", { type: "date", value: todayKey(), required: true });
const textareaField = (name, label, value = "") => html`
  <div class="field">
    <label for="field-${name}">${label}</label>
    <textarea id="field-${name}" name="${name}" maxlength="2000">${value}</textarea>
  </div>`;
const noteField = () => textareaField("note", "Наблюдения и заметки");

// Варианты поля «Тип» — это History.TYPE_CHOICES из models.py, значение уходит в БД как есть.
const HISTORY_TYPES = [
  ["Вакцинация", "Вакцинация"],
  ["Обработка", "Обработка от паразитов"],
  ["Визит к ветеринару", "Визит к ветеринару"],
  ["Измерение", "Измерение"],
  ["Препарат", "Препарат"],
  ["Другое", "Другое"],
];

// Описание каждой формы:
//   bucket   — ключ state (он же ресурс в RESOURCES), куда сохраняем
//   defaults — поля, которых нет в форме, но нужны новой записи (получает id из openEditor)
//   find     — как искать редактируемую запись, если не по её id
//   save     — своё сохранение вместо saveItem (для форм, не связанных с питомцами)
//   noPet    — форму можно открыть, даже если питомцев ещё нет
//   check    — проверка значений до отправки, возвращает текст ошибки
//   title, fields — заголовок и набор полей; item — редактируемая запись, если она есть
const EDITORS = {
  pet: {
    bucket: "pets",
    noPet: true,
    title: (item) => (item ? "Карточка питомца" : "Знакомимся с питомцем"),
    fields: (item = {}) => [
      inputField("name", "Имя", { value: item.name, required: true }),
      selectField(
        "species",
        "Вид",
        [
          ["Кот", "Кот"],
          ["Собака", "Собака"],
          ["Другое", "Другой питомец"],
        ],
        item.species,
      ),
      inputField("breed", "Порода", { value: item.breed }),
      inputField("birth", "Дата рождения", { type: "date", value: item.birth }),
    ],
  },
  // Напоминание и запись здоровья — одна модель History, разница в поле done:
  // напоминание ещё не выполнено, запись здоровья — уже выполнена.
  event: {
    bucket: "history",
    defaults: () => ({ done: false }),
    title: () => "Новое напоминание",
    fields: () => [
      petField(),
      titleField(),
      dateField(),
      inputField("time", "Время (необязательно)", { type: "time" }),
      selectField("type", "Тип", HISTORY_TYPES),
    ],
  },
  health: {
    bucket: "history",
    defaults: () => ({ done: true }),
    title: () => "Запись о здоровье",
    fields: () => [
      petField(),
      titleField(),
      dateField(),
      selectField("type", "Тип записи", HISTORY_TYPES),
      noteField(),
    ],
  },
  food: {
    bucket: "food",
    title: () => "Новый корм",
    fields: () => [
      petField(),
      titleField("Название корма"),
      dateField(),
      selectField("status", "Переносимость", plainOptions("Наблюдать", "Подошло", "Не подошло")),
      noteField(),
    ],
  },
  // У питомца одна медкарта, поэтому для неё id в openEditor — это id питомца.
  medcard: {
    bucket: "medCards",
    find: (petId) => state.medCards.find((card) => sameId(card.pet, petId)),
    defaults: (petId) => ({ pet: petId }),
    title: () => "Медицинская карта",
    fields: (card = {}) => [
      inputField("weight", "Вес, кг", {
        type: "number",
        value: card.weight,
        attrs: html`step="0.01" min="0" max="9999.99"`,
      }),
      textareaField("allergies", "Аллергии", card.allergies),
      textareaField("chronic_conditions", "Хронические заболевания", card.chronic_conditions),
      textareaField("notes", "Заметки", card.notes),
    ],
  },
  profile: {
    noPet: true,
    find: () => ui.user,
    save: async (values) => showAccount(await auth.updateMe(values)),
    title: () => "Редактирование профиля",
    fields: (user) => [
      inputField("username", "Логин", { value: user.username, required: true, maxlength: 150 }),
      inputField("email", "Почта", { type: "email", value: user.email, required: true, maxlength: 254 }),
      inputField("phone", "Телефон", { type: "tel", value: user.phone, maxlength: 20 }),
      inputField("first_name", "Имя", { value: user.first_name, maxlength: 150 }),
      inputField("last_name", "Фамилия", { value: user.last_name, maxlength: 150 }),
    ],
  },
  password: {
    noPet: true,
    save: ({ old_password, new_password }) =>
      auth.changePassword({ old_password, new_password }),
    check: ({ new_password, new_password2 }) =>
      new_password === new_password2 ? "" : "Пароли не совпадают.",
    title: () => "Смена пароля",
    fields: () => [
      inputField("old_password", "Текущий пароль", { type: "password", required: true, maxlength: 128 }),
      inputField("new_password", "Новый пароль", { type: "password", required: true, maxlength: 128, attrs: html`minlength="8"` }),
      inputField("new_password2", "Повторите новый пароль", { type: "password", required: true, maxlength: 128, attrs: html`minlength="8"` }),
    ],
  },
};

// Запись, которую редактирует форма; у новой записи её нет.
function findEditing(kind, id) {
  const editor = EDITORS[kind];
  // у форм со своим save редактируемый объект не зависит от id (профиль — всегда текущий пользователь)
  if (editor.save) return editor.find?.();
  if (id == null) return undefined;
  return editor.find ? editor.find(id) : findById(state[editor.bucket], id);
}

function openEditor(kind, id) {
  const editor = EDITORS[kind];
  if (!editor.noPet && !state.pets.length) {
    toast("Сначала добавьте питомца");
    return;
  }
  const item = findEditing(kind, id);

  ui.editing = { kind, id };
  $("#dialog-title").textContent = editor.title(item);
  $("#fields").innerHTML = html`${editor.fields(item)}`.toString();
  $("#error").textContent = "";
  $("#editor").showModal();
  $("#fields input")?.focus();
}

// required пропускает пробелы, поэтому пустые после trim() проверяем отдельно.
const hasBlankRequired = (form) =>
  [...form.elements].some((element) => element.required && !element.value.trim());

$("#form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  // пароли не обрезаем: пробелы по краям — тоже часть пароля
  const values = Object.fromEntries(
    [...new FormData(form)].map(([key, value]) => [
      key,
      form.elements[key].type === "password" ? value : value.trim(),
    ]),
  );

  if (!form.checkValidity() || hasBlankRequired(form)) {
    $("#error").textContent = "Заполните обязательные поля и проверьте значения.";
    form.reportValidity();
    return;
  }
  if (values.birth > todayKey()) {
    $("#error").textContent = "Дата рождения не может быть в будущем.";
    return;
  }

  const { kind, id } = ui.editing;
  const editor = EDITORS[kind];
  const problem = editor.check?.(values);
  if (problem) {
    $("#error").textContent = problem;
    return;
  }
  const existing = findEditing(kind, id);
  try {
    if (editor.save) await editor.save(values);
    else await saveItem(editor.bucket, { ...editor.defaults?.(id), ...existing, ...values });
  } catch (error) {
    console.error(error);
    if (isUnauthorized(error)) {
      $("#editor").close();
      return;
    }
    // 400 — понятная пользователю причина от сервера (например, почта занята)
    $("#error").textContent =
      error.status === 400 ? error.message : "Не удалось сохранить. Попробуйте ещё раз.";
    return;
  }
  $("#editor").close();
  render();
  toast("Сохранено");
});

// «×» и «Отмена» просто закрывают окно, ничего не сохраняя.
["#close", "#cancel"].forEach((selector) =>
  $(selector).addEventListener("click", () => $("#editor").close()),
);

// ---------- Действия по клику ----------

// Сколько строка с отмеченным напоминанием остаётся на экране, пока играет анимация.
const DONE_ANIMATION_MS = 500;
const FADE_OUT_MS = 400; // должно совпадать с transition у .leaving в styles.css
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Плавно скрывает элемент: растворяет и схлопывает по высоте.
// max-height нужно задать числом заранее, иначе переход от auto не анимируется.
function fadeOut(element) {
  element.style.maxHeight = `${element.offsetHeight}px`;
  element.getBoundingClientRect(); // фиксируем стартовое состояние перед сменой класса
  element.classList.add("leaving");
  return delay(FADE_OUT_MS);
}

// Кнопка в разметке: data-action="<имя>" и параметры в data-* (приходят в dataset),
// вторым аргументом приходит сама кнопка.
const actions = {
  add: ({ kind }) => openEditor(kind),
  edit: ({ kind, id }) => openEditor(kind, id),
  "select-day": ({ day }) => {
    ui.day = day;
    render();
  },
  "filter-food": ({ filter }) => {
    ui.foodFilter = filter;
    render();
  },
  "toggle-done": async ({ id }, button) => {
    const item = findById(state.history, id);
    if (!item) return;
    // Выполненная запись пропадает из списка напоминаний при перерисовке,
    // поэтому сначала показываем анимацию отметки и только потом рендерим.
    const row = button.closest(".event");
    if (!item.done) {
      row?.classList.add("done");
      button.setAttribute("aria-pressed", "true");
    }
    button.disabled = true;
    try {
      const [saved] = await Promise.all([
        saveItem("history", { ...item, done: !item.done }),
        item.done ? null : delay(DONE_ANIMATION_MS),
      ]);
      if (saved.done && row) await fadeOut(row.closest(".reminder") ?? row);
      render();
      if (saved.done) toast("Выполнено. Запись перенесена в «Здоровье»");
    } catch (error) {
      row?.classList.toggle("done", item.done);
      button.removeAttribute("aria-pressed");
      button.disabled = false;
      throw error;
    }
  },
  delete: async ({ bucket, id }) => {
    if (!confirm("Удалить запись?")) return;
    await removeItem(bucket, id);
    render();
  },
  export: ({ id }) => exportCalendar(id),
  "auth-mode": ({ mode }) => setAuthMode(mode),
  logout: async () => {
    await auth.logout();
    showAuth();
  },
};

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  try {
    await actions[target.dataset.action]?.(target.dataset, target);
  } catch (error) {
    console.error(error);
    if (!isUnauthorized(error)) toast("Не удалось выполнить действие. Попробуйте ещё раз.");
  }
});

// ---------- Экспорт в календарь (.ics) ----------

const escapeIcsText = (text) =>
  String(text)
    .replace(/\\/g, "\\\\")
    .replace(/\r?\n/g, "\\n")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,");

function buildIcs(item) {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
  const start = item.date.replace(/-/g, "");
  const startLine = item.time
    ? `DTSTART:${start}T${item.time.replace(":", "")}00`
    : `DTSTART;VALUE=DATE:${start}`;

  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//PetCare//Local Frontend//RU",
    "BEGIN:VEVENT",
    `UID:${escapeIcsText(item.id)}@petcare.local`,
    `DTSTAMP:${stamp}`,
    startLine,
    `SUMMARY:${escapeIcsText(item.title)}`,
    `DESCRIPTION:${escapeIcsText(petName(item.pet))}`,
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");
}

function exportCalendar(id) {
  const item = findById(state.events, id);
  if (!item) return;
  const url = URL.createObjectURL(
    new Blob([buildIcs(item)], { type: "text/calendar;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "petcare-event.ics";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Файл календаря подготовлен. Импорт выполните в вашем календаре.");
}

// ---------- Вход, регистрация и выход ----------

// Пока пользователь не вошёл, вместо приложения показывается #auth
// (body.logged-out прячет боковую панель и рабочую область).
function showAuth() {
  ui.user = null;
  Object.assign(state, emptyState());
  if ($("#editor").open) $("#editor").close();
  document.body.classList.add("logged-out");
  $("#auth").hidden = false;
  setAuthMode("login");
}

// Сессия могла закончиться посреди работы: любой 401 возвращает на экран входа.
function isUnauthorized(error) {
  if (error.status !== 401) return false;
  showAuth();
  toast("Сессия закончилась. Войдите снова.");
  return true;
}

function setAuthMode(mode) {
  document.querySelectorAll("[data-action='auth-mode']").forEach((tab) => {
    const isActive = tab.dataset.mode === mode;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-pressed", String(isActive));
  });
  document.querySelectorAll(".auth-form").forEach((form) => {
    form.hidden = form.dataset.mode !== mode;
    form.reset();
    form.querySelector(".error").textContent = "";
  });
  $(`.auth-form[data-mode="${mode}"] input`).focus();
}

// Блок пользователя в боковой панели.
function showAccount(user) {
  ui.user = user;
  const name = fullName(user) || user.username;
  $("#account-initial").textContent = initial(name).toUpperCase();
  $("#account-name").textContent = name;
  $("#account-email").textContent = user.email;
}

async function startApp(user) {
  showAccount(user);
  $("#auth").hidden = true;
  document.body.classList.remove("logged-out");
  try {
    Object.assign(state, await api.load());
  } catch (error) {
    console.error(error);
    if (isUnauthorized(error)) return;
    toast("Не удалось загрузить данные.");
  }
  render();
}

// Обе формы устроены одинаково: проверяем поля, отправляем, при успехе входим в приложение.
// check возвращает текст ошибки, если значения не подходят ещё до запроса.
function handleAuthForm(form, { send, check = () => "" }) {
  const errorBox = form.querySelector(".error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const problem =
      !form.checkValidity() || hasBlankRequired(form)
        ? "Заполните обязательные поля и проверьте значения."
        : check(values);
    if (problem) {
      errorBox.textContent = problem;
      form.reportValidity();
      return;
    }

    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      await startApp(await send(values));
    } catch (error) {
      console.error(error);
      // 400 — понятная пользователю причина от сервера, остальное — сбой
      errorBox.textContent =
        error.status === 400 ? error.message : "Сервер недоступен. Попробуйте позже.";
    } finally {
      submit.disabled = false;
    }
  });
}

handleAuthForm($("#login-form"), {
  send: ({ login, password }) => auth.login({ login: login.trim(), password }),
});

handleAuthForm($("#register-form"), {
  check: ({ password, password2 }) =>
    password === password2 ? "" : "Пароли не совпадают.",
  send: ({ username, email, phone, password }) =>
    auth.register({
      username: username.trim(),
      email: email.trim(),
      phone: phone.trim(),
      password,
    }),
});

// ---------- Запуск ----------

async function init() {
  $("#today").textContent = new Date().toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  try {
    await startApp(await auth.me());
  } catch (error) {
    if (error.status !== 401) console.error(error);
    showAuth();
  }
}

window.addEventListener("hashchange", render);
init();
