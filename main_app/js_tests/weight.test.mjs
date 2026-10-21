// Тесты фронтенда (static/js/app.js): сводка по питомцу и график веса.
// Запуск из папки main_app:  node --test js_tests/
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

import { loadApp, str } from "./harness.mjs";

// Ключ даты "ГГГГ-ММ-ДД" со сдвигом в днях от сегодня, как в app.js.
const dateKey = (shiftDays = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + shiftDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const pet = { id: 1, name: "Барсик", species: "Кот", breed: "", birth: "2010-01-01", photo: "" };
const grownPet = { ...pet, birth: "2010-01-01" };
const weightPoint = (id, weight, date) => ({ id, pet: 1, weight, date });
const reminder = (id, title, date) => ({
  id, pet: 1, type: "Вакцинация", title, date, time: "", note: "", done: false,
});

let app;

beforeEach(async () => {
  ({ app } = await loadApp());
});

describe("сводка по питомцу", () => {
  test("возраст словами", () => {
    assert.match(app.petAge(grownPet), /^\d+ (год|года|лет)( \d+ (месяц|месяца|месяцев))?$/);
  });

  test("родился сегодня — меньше месяца", () => {
    assert.equal(app.petAge({ ...pet, birth: dateKey() }), "меньше месяца");
  });

  test("без даты рождения и в будущем — пусто", () => {
    assert.equal(app.petAge({ ...pet, birth: "" }), "");
    assert.equal(app.petAge({ ...pet, birth: dateKey(1) }), "");
  });

  test("последний замер веса: последняя по дате точка, не последняя по id", () => {
    app.state.weights = [weightPoint(2, "4.80", "2026-10-01"), weightPoint(1, "3.90", "2026-11-01")];
    assert.equal(app.lastWeight(1).weight, "3.90");
    assert.equal(app.lastWeight("1").weight, "3.90");
    assert.equal(app.lastWeight(999), undefined);
  });

  test("ближайшее дело — незавершённое и не раньше сегодня", () => {
    app.state.history = [
      reminder(1, "Просрочено", "2026-01-01"),
      reminder(2, "Завтра", dateKey(1)),
    ];
    assert.equal(app.nextEventFor(1).title, "Завтра");
    assert.equal(app.nextEventFor(999), undefined);
  });

  test("карточка на главной показывает вес и ближайшее дело", () => {
    app.state.weights = [weightPoint(1, "4.80", "2026-10-01")];
    app.state.history = [reminder(1, "Прививка", dateKey(1))];
    const html = str(app.miniPet(pet));
    assert.match(html, /class="pet-note"/);
    assert.match(html, /4,8 кг/);
    assert.match(html, /Ближайшее: /);
  });

  test("карточка «Мои питомцы» показывает возраст и последний вес", () => {
    app.state.weights = [weightPoint(1, "4.80", "2026-10-01")];
    const html = str(app.petCard(pet));
    assert.match(html, /<dt>Возраст<\/dt><dd>[^<]+<\/dd>/);
    assert.match(html, /<dt>Последний вес<\/dt><dd>4,8 кг<\/dd>/);
  });

  test("без данных сводка не пустая и без сломанной разметки", () => {
    assert.match(str(app.miniPet({ ...pet, birth: "" })), /Данных пока нет/);
    assert.match(str(app.petCard(pet)), /не измерен/);
  });
});

describe("медкарта и замеры веса", () => {
  test("меньше двух замеров — подсказка без графика", () => {
    app.state.medCards = [{ id: 1, pet: 1, weight: "4.8", allergies: "", chronic_conditions: "", notes: "" }];
    app.state.weights = [weightPoint(1, "4.80", "2026-10-01")];
    const html = str(app.medCard(pet));
    assert.doesNotMatch(html, /<canvas/);
    assert.match(html, /хотя бы два замера/);
  });

  test("два замера — canvas графика с привязкой к питомцу", () => {
    const card = { id: 1, pet: 1, weight: "4.8", allergies: "", chronic_conditions: "", notes: "" };
    app.state.medCards = [card];
    app.state.weights = [
      weightPoint(1, "4.00", "2026-09-01"),
      weightPoint(2, "4.80", "2026-10-01"),
    ];
    const html = str(app.medCard(pet));
    assert.match(html, /<canvas class="weight-chart" data-pet="1"/);
    assert.match(html, /Последний замер: 4,8 кг/);
  });

  test("форма замера веса: вес обязателен, дата не в будущем", () => {
    const fields = app.EDITORS.weight.fields().map(str).join("");
    assert.match(fields, /name="weight"/);
    assert.match(fields, /type="date"/);
    assert.match(fields, /required/);
    assert.equal(app.EDITORS.weight.check({ date: dateKey(), weight: "4" }), "");
    assert.equal(
      app.EDITORS.weight.check({ date: dateKey(1), weight: "4" }),
      "Дата замера не может быть в будущем.",
    );
  });
});

describe("ресурс weights", () => {
  test("путь совпадает с urls.py", () => {
    assert.equal(app.RESOURCES.weights.path(7), "/weight/7");
  });

  test("null превращается в пустую строку и обратно", () => {
    assert.equal(app.RESOURCES.weights.fromServer({ id: 1, pet: 1, weight: null, date: "2026-10-01" }).weight, "");
    assert.equal(app.RESOURCES.weights.fromServer({ id: 1, pet: 1, weight: "4.8", date: "2026-10-01" }).weight, "4.8");
    assert.equal(app.RESOURCES.weights.toServer({ id: 1, pet: 1, weight: "", date: "2026-10-01" }).weight, null);
    assert.equal(app.RESOURCES.weights.toServer({ id: 1, pet: 1, weight: "4.8", date: "2026-10-01" }).weight, "4.8");
    assert.equal(app.RESOURCES.weights.toServer({ id: 3, pet: 1, weight: "1", date: "" }).id, 3);
  });
});

// Заглушка canvas 2d: любая «метод» — это запись вызова.
function stubCanvas() {
  const calls = [];
  const ctx = new Proxy(
    {},
    { get: (_target, prop) => (...args) => void calls.push([prop, ...args]) },
  );
  return { canvas: { width: 560, height: 180, getContext: () => ctx }, calls };
}

describe("график веса", () => {
  test("по нескольким точкам рисуется линия, точки и подписи дат", () => {
    const { canvas, calls } = stubCanvas();
    app.drawLineChart(canvas, [
      weightPoint(1, "4.00", "2026-09-01"),
      weightPoint(2, "4.80", "2026-10-01"),
    ]);
    assert.ok(calls.some(([prop]) => prop === "stroke"));
    assert.equal(calls.filter(([prop]) => prop === "arc").length, 2);
    // по оси X подписаны даты первой и последней точки (сентябрь и октябрь)
    const labels = calls.filter(([prop]) => prop === "fillText").map(([, x]) => String(x));
    assert.ok(labels.some((label) => label.includes("сент")), JSON.stringify(labels));
    assert.ok(labels.some((label) => label.includes("окт")), JSON.stringify(labels));
  });

  test("все точки у графика внутри области рисования", () => {
    const { canvas, calls } = stubCanvas();
    app.drawLineChart(canvas, [
      weightPoint(1, "3.00", "2026-09-01"),
      weightPoint(2, "6.00", "2026-10-01"),
    ]);
    const arcs = calls.filter(([prop]) => prop === "arc");
    for (const [, cx] of arcs) {
      assert.ok(cx > 0 && cx < 560, `x=${cx} вне canvas`);
    }
  });

  test("одна точка и отсутствие getContext не ломают страницу", () => {
    const { canvas, calls } = stubCanvas();
    app.drawLineChart(canvas, [weightPoint(1, "4.00", "2026-10-01")]);
    assert.deepEqual(calls, []);
    assert.doesNotThrow(() => app.drawLineChart({ width: 560, height: 180 }, [
      weightPoint(1, "4.00", "2026-10-01"),
      weightPoint(2, "5.00", "2026-10-02"),
    ]));
  });
});

describe("перезагрузка замеров", () => {
  test("после медкарты замеры перечитываются со всех питомцев", async () => {
    const rows = [
      { id: 1, pet: 1, weight: "4.80", date: "2026-10-01" },
      { id: 2, pet: 1, weight: "5.00", date: "2026-10-05" },
    ];
    const respond = (method, url) =>
      url.includes("/user/weight/") ? [200, rows] : [200, {}];
    ({ app } = await loadApp({ respond }));
    app.state.pets = [pet, { ...pet, id: 2, name: "Рекс" }];
    await app.reloadWeights();
    // объекты созданы в vm-контексте (другой прототип), поэтому сравниваем JSON
    assert.equal(
      JSON.stringify(app.state.weights),
      JSON.stringify([...rows, ...rows]),
    );
  });
});
