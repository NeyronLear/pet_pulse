/* Хелперы для виджета тамагочи. Какой питомец есть у пользователя, решает сервер
   (app.js вызывает showPet/removePet), в localStorage остаётся только положение на экране. */
(() => {
  const DATA_KEY   = "pet_widget_data";
  const POS_KEY    = "pet_widget_pos";
  const EXISTS_KEY = "pet_widget_exists";
  const PET_ID     = "pet";

  function getPet() {
    const el = document.getElementById(PET_ID) || document.querySelector("pet-widget");
    return el && typeof el.destroy === "function" ? el : null;
  }

  function hardReset() {
    Object.keys(localStorage).forEach((k) => {
      if (k === EXISTS_KEY || k.startsWith(DATA_KEY) || k.startsWith(POS_KEY)) {
        localStorage.removeItem(k);
      }
    });
  }

  // Показывает питомца с данными сервера { name, type }; уже показанного — обновляет.
  function showPet({ name, type }) {
    const pet = getPet();
    if (pet) {
      if (pet.petName !== name) pet.petName = name;
      if (pet.petType !== type) pet.petType = type;
      return pet;
    }

    // Виджет берёт имя и тип из localStorage (ключ с суффиксом id), если они там есть.
    // Записываем данные сервера заранее: так виджет считает питомца «своим»
    // и не сбрасывает сохранённое положение.
    localStorage.setItem(DATA_KEY + "_" + PET_ID, JSON.stringify({ pet_name: name, pet_type: type }));
    const el = document.createElement("pet-widget");
    el.id = PET_ID;
    el.setAttribute("name", name);
    el.setAttribute("type", type);
    document.body.appendChild(el);
    return getPet();
  }

  // Убирает питомца со страницы без события pet-closed (например, при выходе из аккаунта).
  function removePet() {
    const pet = getPet();
    if (pet) pet.remove();
    hardReset();
  }

  const domReady = document.readyState === "loading"
    ? new Promise((r) => document.addEventListener("DOMContentLoaded", r, { once: true }))
    : Promise.resolve();

  const ready = Promise.all([customElements.whenDefined("pet-widget"), domReady]);

  window.PetApp = { getPet, showPet, removePet, hardReset, ready };
})();
