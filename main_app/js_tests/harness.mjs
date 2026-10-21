// Загружает static/js/app.js в изолированный контекст vm с минимальной заглушкой браузера.
// Настоящий DOM не нужен: тесты проверяют HTML-строки, которые строит app.js, и запросы к серверу.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const APP_JS = new URL("../static/js/app.js", import.meta.url);

// Элемент-заглушка: принимает любые свойства, которые app.js выставляет при старте.
class FakeElement {
  constructor() {
    this.innerHTML = "";
    this.textContent = "";
    this.hidden = false;
    this.open = false;
    this.value = "";
    this.dataset = {};
    this.elements = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener() {}
  setAttribute() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  reset() {}
  click() {}
  remove() {}
  querySelector() { return new FakeElement(); }
}

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
  text: async () => (body === undefined ? "" : JSON.stringify(body)),
});

// Возвращает объект с функциями и состоянием app.js и журналом запросов fetch.
// respond(method, url, options) → [status, body] — как сервер отвечает на запрос.
export async function loadApp({ respond = () => [401, { detail: "Требуется вход." }] } = {}) {
  const elements = new Map();
  const document = {
    cookie: "csrftoken=test-token",
    title: "",
    readyState: "complete",
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new FakeElement());
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    createElement: () => new FakeElement(),
    addEventListener() {},
  };
  const fetchCalls = [];
  const context = {
    document,
    window: { addEventListener() {} },
    location: { hash: "", pathname: "/user/", search: "" },
    history: { replaceState() {} },
    PetApp: {
      getPet: () => null,
      showPet() {},
      removePet() {},
      ready: Promise.resolve(),
    },
    fetch: async (url, options) => {
      fetchCalls.push({ url, ...options });
      const [status, body] = respond(options.method, url, options);
      return jsonResponse(status, body);
    },
    FormData,
    File,
    Blob,
    console: { ...console, error() {} }, // ошибки сети app.js пишет в console.error
    confirm: () => true,
    setTimeout,
    clearTimeout,
    URL,
  };
  vm.createContext(context);
  vm.runInContext(readFileSync(APP_JS, "utf8"), context, { filename: "app.js" });
  // init() ждёт ответ на /auth/me — даём промисам завершиться
  await new Promise((resolve) => setImmediate(resolve));

  // const и function верхнего уровня видны следующему скрипту в том же контексте
  const app = vm.runInContext(`({
    state, ui, RESOURCES, EDITORS, api, request,
    petAvatar, petTag, photoField, miniPet, petCard, medCard,
    healthRecord, foodCard, eventRow, replaceItem, PHOTO_MAX_SIZE,
    petAge, lastWeight, nextEventFor, formatWeight,
    drawLineChart, drawWeightCharts, reloadWeights,
  })`, context);
  return { app, fetchCalls, $: (selector) => document.querySelector(selector) };
}

// Строка HTML из результата html`` (SafeHtml) или массива таких результатов.
export const str = (value) => String(value);
