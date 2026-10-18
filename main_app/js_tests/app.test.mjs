// Тесты фронтенда (static/js/app.js): фото и аватарки питомцев.
// Запуск из папки main_app:  node --test js_tests/
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

import { loadApp, str } from "./harness.mjs";

const withPhoto = { id: 1, name: "Барсик", species: "Кот", breed: "", birth: "", photo: "/media/pets/barsik.png" };
const noPhoto = { id: 2, name: "Рекс", species: "Собака", breed: "", birth: "", photo: "" };

let app;
let fetchCalls;

beforeEach(async () => {
  ({ app, fetchCalls } = await loadApp());
  app.state.pets = [withPhoto, noPhoto];
  fetchCalls.length = 0;
});

// Форма-заглушка с полями photo и remove_photo, как в photoField().
const petForm = ({ file, removeChecked } = {}) => ({
  elements: {
    photo: { files: file ? [file] : [] },
    ...(removeChecked !== undefined && { remove_photo: { checked: removeChecked } }),
  },
});

describe("petAvatar", () => {
  test("с фото — картинка", () => {
    const html = str(app.petAvatar(withPhoto));
    assert.match(html, /^<span class="avatar ">/);
    assert.match(html, /<img src="\/media\/pets\/barsik.png" alt="">/);
  });

  test("без фото — первая буква имени", () => {
    assert.equal(str(app.petAvatar(noPhoto)), '<span class="avatar ">Р</span>');
  });

  test("класс размера", () => {
    assert.match(str(app.petAvatar(noPhoto, "small")), /class="avatar small"/);
  });

  test("адрес фото и имя экранируются", () => {
    const evil = { name: "<b>", photo: '"><script>alert(1)</script>' };
    const html = str(app.petAvatar(evil));
    assert.doesNotMatch(html, /<script>/);
    assert.match(html, /src="&quot;&gt;&lt;script&gt;/);
    assert.equal(str(app.petAvatar({ name: "<b>", photo: "" })), '<span class="avatar ">&lt;</span>');
  });
});

describe("petTag", () => {
  test("маленькая аватарка и имя", () => {
    const html = str(app.petTag(1));
    assert.match(html, /^<span class="pet-tag"><span class="avatar small"><img src="\/media\/pets\/barsik.png"/);
    assert.match(html, /Барсик<\/span>$/);
  });

  test("id-строка из data-атрибута тоже находит питомца", () => {
    assert.match(str(app.petTag("2")), /pet-tag.*Рекс/);
  });

  test("неизвестный питомец — просто текст", () => {
    assert.equal(str(app.petTag(999)), "Питомец не найден");
  });
});

describe("аватарки в разделах", () => {
  const record = { id: 10, pet: 1, type: "Вакцинация", title: "Прививка", date: "2026-10-01", note: "", done: true };

  test("напоминания и дела на главной", () => {
    const html = str(app.eventRow({ ...record, done: false, time: "" }));
    assert.match(html, /<small><span class="pet-tag"><span class="avatar small"><img src="\/media\/pets\/barsik.png"/);
  });

  test("история здоровья", () => {
    assert.match(str(app.healthRecord(record)), /class="eyebrow"><span class="pet-tag">.*Барсик/);
  });

  test("питание", () => {
    const food = { id: 5, pet: 2, title: "Корм", status: "Подошло", note: "" };
    assert.match(str(app.foodCard(food)), /class="eyebrow"><span class="pet-tag"><span class="avatar small">Р<\/span>Рекс/);
  });

  test("медкарта — обычная аватарка рядом с именем", () => {
    const html = str(app.medCard(withPhoto));
    assert.match(html, /<div class="pet-title"><span class="avatar "><img src="\/media\/pets\/barsik.png" alt=""><\/span><h2>Барсик<\/h2><\/div>/);
  });

  test("«Мои питомцы» и блок на главной", () => {
    assert.match(str(app.petCard(withPhoto)), /<span class="avatar "><img src="\/media\/pets\/barsik.png"/);
    assert.match(str(app.miniPet(noPhoto)), /<span class="avatar ">Р<\/span>/);
  });

  test("запись удалённого питомца не ломает разметку", () => {
    assert.match(str(app.healthRecord({ ...record, pet: 999 })), /Питомец не найден · Вакцинация/);
  });
});

describe("поле фото в форме питомца", () => {
  test("новый питомец — только выбор файла", () => {
    const html = str(app.photoField({}));
    assert.match(html, /<label for="field-photo">Фото<\/label>/);
    assert.match(html, /<input id="field-photo" name="photo" type="file" accept="image\/\*">/);
    assert.doesNotMatch(html, /photo-preview|remove_photo/);
  });

  test("питомец с фото — превью, замена и удаление", () => {
    const html = str(app.photoField(withPhoto));
    assert.match(html, /Заменить фото/);
    assert.match(html, /<img class="photo-preview" src="\/media\/pets\/barsik.png"/);
    assert.match(html, /name="remove_photo"/);
  });

  test("форма питомца включает поле фото", () => {
    assert.ok(app.EDITORS.pet.fields(withPhoto).some((field) => str(field).includes('name="photo"')));
  });
});

describe("проверка фото до отправки", () => {
  const check = (file) => app.EDITORS.pet.check({}, petForm({ file }));

  test("без файла и с картинкой — ок", () => {
    assert.equal(check(undefined), "");
    assert.equal(check(new File(["x"], "cat.png", { type: "image/png" })), "");
  });

  test("не картинка", () => {
    assert.equal(check(new File(["x"], "cat.txt", { type: "text/plain" })), "Выберите файл с картинкой.");
  });

  test("больше 5 МБ", () => {
    const big = { type: "image/jpeg", size: app.PHOTO_MAX_SIZE + 1 };
    assert.equal(check(big), "Фото должно быть не больше 5 МБ.");
    assert.equal(check({ type: "image/jpeg", size: app.PHOTO_MAX_SIZE }), "");
  });
});

describe("запросы к серверу", () => {
  const serverPet = { id: 1, name: "Барсик", species: "Кот", breed: "", birth_date: null, photo: "/media/pets/new.png" };

  beforeEach(async () => {
    ({ app, fetchCalls } = await loadApp({ respond: () => [200, serverPet] }));
    fetchCalls.length = 0;
  });

  test("фото из ответа сервера попадает в запись, null — пустая строка", () => {
    assert.equal(app.RESOURCES.pets.fromServer(serverPet).photo, "/media/pets/new.png");
    assert.equal(app.RESOURCES.pets.fromServer({ ...serverPet, photo: null }).photo, "");
  });

  test("фото не уходит в JSON при сохранении карточки", () => {
    assert.equal("photo" in app.RESOURCES.pets.toServer(withPhoto), false);
  });

  test("JSON-запрос ставит Content-Type и CSRF", async () => {
    await app.request("PUT", "/", { id: 1 });
    const [call] = fetchCalls;
    assert.equal(call.headers["Content-Type"], "application/json");
    assert.equal(call.headers["X-CSRFToken"], "test-token");
    assert.equal(call.body, '{"id":1}');
  });

  test("загрузка фото — multipart без ручного Content-Type", async () => {
    const file = new File(["png"], "cat.png", { type: "image/png" });
    const saved = await app.api.savePhoto(1, file);
    const [call] = fetchCalls;
    assert.equal(call.method, "POST");
    assert.equal(call.url, "/user/pet_photo/1");
    assert.ok(call.body instanceof FormData);
    assert.equal(call.body.get("photo").name, "cat.png");
    assert.equal("Content-Type" in call.headers, false);
    assert.equal(call.headers["X-CSRFToken"], "test-token");
    assert.equal(saved.photo, "/media/pets/new.png");
  });

  test("удаление фото", async () => {
    await app.api.removePhoto(7);
    assert.equal(fetchCalls[0].method, "DELETE");
    assert.equal(fetchCalls[0].url, "/user/pet_photo/7");
  });

  test("ошибка сервера доходит до формы текстом из detail", async () => {
    ({ app } = await loadApp({ respond: () => [400, { detail: "Файл не похож на изображение." }] }));
    await assert.rejects(app.api.savePhoto(1, new File(["x"], "x.png")), {
      message: "Файл не похож на изображение.",
      status: 400,
    });
  });
});

describe("afterSave формы питомца", () => {
  beforeEach(async () => {
    ({ app, fetchCalls } = await loadApp({ respond: (method) => [200, { id: 1, name: "Барсик", photo: method === "POST" ? "/media/pets/new.png" : null }] }));
    fetchCalls.length = 0;
  });

  test("выбран файл — загружает его", async () => {
    const file = new File(["png"], "cat.png", { type: "image/png" });
    const pet = await app.EDITORS.pet.afterSave(withPhoto, petForm({ file, removeChecked: true }));
    assert.equal(fetchCalls.length, 1);
    assert.equal(fetchCalls[0].method, "POST"); // новый файл важнее галочки «удалить»
    assert.equal(pet.photo, "/media/pets/new.png");
  });

  test("отмечено «Удалить фото» — удаляет", async () => {
    const pet = await app.EDITORS.pet.afterSave(withPhoto, petForm({ removeChecked: true }));
    assert.equal(fetchCalls[0].method, "DELETE");
    assert.equal(pet.photo, "");
  });

  test("ничего не выбрано — без запросов", async () => {
    const pet = await app.EDITORS.pet.afterSave(withPhoto, petForm({ removeChecked: false }));
    assert.equal(fetchCalls.length, 0);
    assert.equal(pet, withPhoto);
  });

  test("у нового питомца нет галочки — без запросов", async () => {
    await app.EDITORS.pet.afterSave(noPhoto, petForm());
    assert.equal(fetchCalls.length, 0);
  });
});

describe("replaceItem", () => {
  test("заменяет существующую запись и добавляет новую", () => {
    app.replaceItem("pets", { ...withPhoto, photo: "" });
    app.replaceItem("pets", { id: 3, name: "Кеша", photo: "" });
    assert.deepEqual(app.state.pets.map((pet) => [pet.id, pet.photo]), [[1, ""], [2, ""], [3, ""]]);
  });

  test("id-строка находит запись с числовым id", () => {
    app.replaceItem("pets", { ...noPhoto, id: "2", photo: "/media/pets/rex.png" });
    assert.equal(app.state.pets.length, 2);
    assert.equal(app.state.pets[1].photo, "/media/pets/rex.png");
  });
});
