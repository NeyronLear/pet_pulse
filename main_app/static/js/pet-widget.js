class PetWidget extends HTMLElement {
  static STORAGE_KEY_DATA   = "pet_widget_data";
  static STORAGE_KEY_POS    = "pet_widget_pos";
  static STORAGE_KEY_EXISTS = "pet_widget_exists";

  static hardReset() {
    Object.keys(localStorage).forEach((k) => {
      if (
        k === PetWidget.STORAGE_KEY_EXISTS ||
        k.startsWith(PetWidget.STORAGE_KEY_DATA) ||
        k.startsWith(PetWidget.STORAGE_KEY_POS)
      ) {
        localStorage.removeItem(k);
      }
    });
  }

  static hasSavedPet() {
    return !!localStorage.getItem(PetWidget.STORAGE_KEY_EXISTS);
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._storageSuffix = "";
    this._initialized = false;

    this.animTick = 0;
    this.happyTimer = 0;
    this.playMode = false;
    this.hearts = [];
    this.speechTimer = 0;
    this.speechText = "";

    this.petX = 0;
    this.petY = 0;
    this.petVx = 0;
    this.petVy = 0;

    this._dragging = false;
    this._dragMoved = false;
    this._dragOffsetX = 0;
    this._dragOffsetY = 0;

    this._mouseX = 0;
    this._mouseY = 0;

    this._lastDrawTs = 0;
    this._rafId = null;
    this._moveIntervalId = null;
    this._posSaveTimer = null;

    this._onMouseMove       = this._onMouseMove.bind(this);
    this._onWindowMouseMove = this._onWindowMouseMove.bind(this);
    this._onWindowMouseUp   = this._onWindowMouseUp.bind(this);
    this._onWindowTouchMove = this._onWindowTouchMove.bind(this);
    this._onWindowTouchEnd  = this._onWindowTouchEnd.bind(this);
    this._onResize          = this._onResize.bind(this);
    this._drawLoop          = this._drawLoop.bind(this);
  }

  connectedCallback() {
    if (this._initialized) return;
    this._initialized = true;

    this._storageSuffix = this.id ? "_" + this.id : "";

    this._loadData();

    if (!this._isExistingPet && localStorage.getItem(PetWidget.STORAGE_KEY_EXISTS)) {
      const otherPet = Array.from(document.querySelectorAll("pet-widget"))
        .find((el) => el !== this && el.isConnected);

      if (otherPet) {
        console.warn("[pet-widget] Питомец уже существует. Удалите текущего через destroy().");
        this._initialized = false;
        this.remove();
        return;
      }
      PetWidget.hardReset();
    }

    if (!this._isExistingPet) this._saveData();
    localStorage.setItem(PetWidget.STORAGE_KEY_EXISTS, "1");

    this._buildDOM();
    this._loadPosition();
    this._bindEvents();

    this.speechText = "Привет! Я " + this.data.pet_name + "!";
    this.speechTimer = 60;

    this._applyPosition();
    this._rafId = requestAnimationFrame(this._drawLoop);
    this._moveIntervalId = setInterval(() => this._updateMovement(), 30);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._rafId);
    clearInterval(this._moveIntervalId);
    clearTimeout(this._posSaveTimer);

    window.removeEventListener("mousemove", this._onWindowMouseMove);
    window.removeEventListener("mouseup",   this._onWindowMouseUp);
    window.removeEventListener("touchmove", this._onWindowTouchMove);
    window.removeEventListener("touchend",  this._onWindowTouchEnd);
    window.removeEventListener("mousemove", this._onMouseMove);
    window.removeEventListener("resize",    this._onResize);
  }

  // ==================== ПУБЛИЧНОЕ API ====================

  get petName() { return this.data ? this.data.pet_name : undefined; }
  set petName(value) {
    const v = (value || "").trim();
    if (!v || !this.data) return;
    this.data.pet_name = v;
    this._saveData();
    this.speechText = "Меня теперь зовут " + v + "!";
    this.speechTimer = 60;
  }

  get petType() { return this.data ? this.data.pet_type : undefined; }
  set petType(value) {
    if ((value !== "dog" && value !== "cat") || !this.data) return;
    this.data.pet_type = value;
    this._saveData();
    this.speechText = value === "cat" ? "Мяу! Теперь я котик" : "Гав! Теперь я собачка";
    this.speechTimer = 60;
    this._spawnHearts(4);
  }

  get isPlaying() { return this.playMode; }

  startPlay()      { if (!this.playMode) this._togglePlay(); }
  stopPlay()       { if (this.playMode)  this._togglePlay(); }
  togglePlayMode() { this._togglePlay(); }

  destroy() {
    clearTimeout(this._posSaveTimer);
    this._posSaveTimer = null;
    PetWidget.hardReset();
    this.dispatchEvent(new CustomEvent("pet-closed", { bubbles: true }));
    this.remove();
  }

  // ==================== ДАННЫЕ ====================

  _dataKey() { return PetWidget.STORAGE_KEY_DATA + this._storageSuffix; }
  _posKey()  { return PetWidget.STORAGE_KEY_POS  + this._storageSuffix; }

  _loadData() {
    const defaultData = {
      pet_name: this.getAttribute("name") || "Бобик",
      pet_type: this.getAttribute("type") || "dog"
    };
    const raw = localStorage.getItem(this._dataKey());
    this._isExistingPet = !!raw;
    try {
      this.data = raw
        ? Object.assign({}, defaultData, JSON.parse(raw))
        : Object.assign({}, defaultData);
    } catch (e) {
      this.data = Object.assign({}, defaultData);
      this._isExistingPet = false;
    }
  }

  _saveData() {
    try {
      localStorage.setItem(this._dataKey(), JSON.stringify(this.data));
    } catch (e) { /* quota */ }
  }

  _loadPosition() {
    const w = this.widget.offsetWidth  || 230;
    const h = this.widget.offsetHeight || 246;
    let pos = null;
    try {
      const raw = localStorage.getItem(this._posKey());
      if (raw) pos = JSON.parse(raw);
    } catch (e) { /* ignore */ }

    if (pos && typeof pos.x === "number" && typeof pos.y === "number") {
      this.petX = pos.x;
      this.petY = pos.y;
    } else {
      this.petX = window.innerWidth  - w - 30;
      this.petY = window.innerHeight - h - 20;
    }
    this._clampToViewport();
  }

  _savePosition() {
    clearTimeout(this._posSaveTimer);
    this._posSaveTimer = setTimeout(() => {
      if (!this.isConnected) return;
      try {
        localStorage.setItem(this._posKey(), JSON.stringify({ x: this.petX, y: this.petY }));
      } catch (e) { /* ignore */ }
    }, 200);
  }

  // ==================== РАЗМЕТКА ====================

  _buildDOM() {
    this.shadowRoot.innerHTML = [
      '<style>',
      ':host { position: fixed; z-index: 9999; }',
      '#widget { width:230px; background:transparent; overflow:visible;',
      '  user-select:none; touch-action:none; font-family:Arial, sans-serif; }',
      'canvas { display:block; width:230px; height:214px; background:transparent; cursor:grab; }',
      'canvas:active { cursor:grabbing; }',
      '</style>',
      '<div id="widget"><canvas id="canvas" width="230" height="214"></canvas></div>'
    ].join("\n");

    this.widget = this.shadowRoot.getElementById("widget");
    this.canvas = this.shadowRoot.getElementById("canvas");
    this.ctx    = this.canvas.getContext("2d");
  }

  _applyPosition() {
    this.style.left = this.petX + "px";
    this.style.top  = this.petY + "px";
  }

  _clampToViewport() {
    const w = this.widget.offsetWidth  || 230;
    const h = this.widget.offsetHeight || 246;
    this.petX = Math.max(0, Math.min(this.petX, window.innerWidth  - w));
    this.petY = Math.max(0, Math.min(this.petY, window.innerHeight - h));
  }

  // ==================== СОБЫТИЯ ====================

  _bindEvents() {
    this.canvas.addEventListener("mousedown",  (e) => this._startDrag(e));
    this.canvas.addEventListener("touchstart", (e) => this._startDrag(e), { passive: true });

    window.addEventListener("mousemove", this._onWindowMouseMove);
    window.addEventListener("mouseup",   this._onWindowMouseUp);
    window.addEventListener("touchmove", this._onWindowTouchMove, { passive: true });
    window.addEventListener("touchend",  this._onWindowTouchEnd);
    window.addEventListener("mousemove", this._onMouseMove);
    window.addEventListener("resize",    this._onResize);
  }

  _onMouseMove(e) {
    this._mouseX = e.clientX;
    this._mouseY = e.clientY;
  }

  _onWindowMouseMove(e) { this._doDrag(e); }
  _onWindowMouseUp()    { this._endDrag(); }
  _onWindowTouchMove(e) { this._doDrag(e); }
  _onWindowTouchEnd()   { this._endDrag(); }

  _onResize() {
    this._clampToViewport();
    this._applyPosition();
  }

  _startDrag(e) {
    if (this.playMode) return;
    this._dragging  = true;
    this._dragMoved = false;
    const point = e.touches ? e.touches[0] : e;
    this._dragOffsetX = point.clientX - this.petX;
    this._dragOffsetY = point.clientY - this.petY;
  }

  _doDrag(e) {
    if (!this._dragging || this.playMode) return;
    const point = e.touches ? e.touches[0] : e;
    const newX = point.clientX - this._dragOffsetX;
    const newY = point.clientY - this._dragOffsetY;
    if (Math.abs(newX - this.petX) > 2 || Math.abs(newY - this.petY) > 2) {
      this._dragMoved = true;
    }
    this.petX = newX;
    this.petY = newY;
    this._applyPosition();
  }

  _endDrag() {
    if (this._dragging) {
      if (!this._dragMoved) {
        this._triggerHappy("pet");
      } else {
        this._clampToViewport();
        this._applyPosition();
        this._savePosition();
      }
    }
    this._dragging = false;
  }

  // ==================== ЛОГИКА ====================

  _randRange(min, max) { return Math.random() * (max - min) + min; }

  _spawnHearts(count) {
    count = count || 6;
    for (let i = 0; i < count; i++) {
      this.hearts.push([
        this._randRange(60, 170),
        this._randRange(90, 140),
        this._randRange(1.5, 3.0),
        this._randRange(0, 6.28)
      ]);
    }
  }

  _triggerHappy(kind) {
    kind = kind || "pet";
    this.happyTimer = 20;
    this._spawnHearts(kind === "pet" ? 8 : 4);

    if (kind === "play_catch") {
      const variants = ["Поймал!", "Догнал!", "Ты не уйдёшь!"];
      this.speechText = variants[Math.floor(Math.random() * variants.length)];
    } else if (kind === "pet") {
      const sound = this.data.pet_type === "cat" ? "Мур-мур-мур!" : "Гав-гав!";
      this.speechText = sound + " Так приятно!";
    }
    this.speechTimer = 75;
  }

  _togglePlay() {
    this.playMode = !this.playMode;
    if (this.playMode) {
      this.speechText = "Ура! Бежим играть!";
      this.speechTimer = 60;
      this.petVx = (Math.random() < 0.5 ? -1 : 1) * this._randRange(2, 5);
      this.petVy = (Math.random() < 0.5 ? -1 : 1) * this._randRange(2, 5);
    } else {
      this.speechText = "Отдыхаем...";
      this.speechTimer = 60;
      this.petVx = 0;
      this.petVy = 0;
      this._savePosition();
    }
    this.dispatchEvent(new CustomEvent("pet-play-changed", {
      detail: { playing: this.playMode },
      bubbles: true
    }));
  }

  // ==================== ФИЗИКА ====================

  _updateMovement() {
    if (!this.playMode || !this.isConnected) return;

    const w = this.widget.offsetWidth;
    const h = this.widget.offsetHeight;

    const cx = this.petX + 115;
    const cy = this.petY + 105;

    const dx = this._mouseX - cx;
    const dy = this._mouseY - cy;
    const dist = Math.hypot(dx, dy);

    if (dist > 50) {
      this.petVx += (dx / dist) * 0.8;
      this.petVy += (dy / dist) * 0.8;
    } else {
      if (this.happyTimer <= 0) this._triggerHappy("play_catch");
      if (dist > 0) {
        this.petVx -= (dx / dist) * 2;
        this.petVy -= (dy / dist) * 2;
      }
    }

    this.petVx *= 0.92;
    this.petVy *= 0.92;

    const speed = Math.hypot(this.petVx, this.petVy);
    if (speed > 12) {
      this.petVx = (this.petVx / speed) * 12;
      this.petVy = (this.petVy / speed) * 12;
    }

    this.petX += this.petVx;
    this.petY += this.petVy;

    if (this.petX < 0) { this.petX = 0; this.petVx = Math.abs(this.petVx) * 0.8; }
    else if (this.petX > window.innerWidth - w) { this.petX = window.innerWidth - w; this.petVx = -Math.abs(this.petVx) * 0.8; }

    if (this.petY < 0) { this.petY = 0; this.petVy = Math.abs(this.petVy) * 0.8; }
    else if (this.petY > window.innerHeight - h) { this.petY = window.innerHeight - h; this.petVy = -Math.abs(this.petVy) * 0.8; }

    this._applyPosition();
    this._savePosition();
  }

  // ==================== ОТРИСОВКА ====================

  _roundRect(x, y, w, h, r) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  _drawEllipse(x1, y1, x2, y2, fill, stroke, lineWidth) {
    const ctx = this.ctx;
    const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
    const rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    if (fill)   { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth || 1; ctx.stroke(); }
  }

  _drawArc(x1, y1, x2, y2, startDeg, extentDeg, opts) {
    opts = opts || {};
    const ctx = this.ctx;
    const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
    const rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2;
    const startRad = -startDeg * Math.PI / 180;
    const endRad   = -(startDeg + extentDeg) * Math.PI / 180;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, startRad, endRad, true);
    if (opts.fill) {
      ctx.lineTo(cx, cy); ctx.closePath();
      ctx.fillStyle = opts.fill; ctx.fill();
    }
    if (opts.stroke) {
      ctx.strokeStyle = opts.stroke;
      ctx.lineWidth = opts.lineWidth || 1;
      ctx.lineCap = "round";
      ctx.stroke();
    }
  }

  _wrapText(text, x, y, maxWidth, lineHeight) {
    const ctx = this.ctx;
    const words = String(text).split(" ");
    const lines = [];
    let current = "";
    for (const word of words) {
      const test = current ? current + " " + word : word;
      if (ctx.measureText(test).width > maxWidth && current) {
        lines.push(current);
        current = word;
      } else {
        current = test;
      }
    }
    if (current) lines.push(current);
    const totalHeight = lines.length * lineHeight;
    const startY = y - totalHeight / 2 + lineHeight / 2;
    lines.forEach((line, i) => ctx.fillText(line, x, startY + i * lineHeight));
  }

  _drawLoop(ts) {
    if (!this.isConnected || !this.ctx) return;
    if (ts - this._lastDrawTs >= 50) {
      this._lastDrawTs = ts;
      this._drawScene();
    }
    this._rafId = requestAnimationFrame(this._drawLoop);
  }

  _drawScene() {
    const ctx = this.ctx;
    this.animTick++;

    ctx.clearRect(0, 0, 230, 214);

    const isHappy = this.happyTimer > 0;
    if (this.happyTimer  > 0) this.happyTimer--;
    if (this.speechTimer > 0) this.speechTimer--;

    const isMoving = Math.hypot(this.petVx, this.petVy) > 1.5;
    let bounce, tailSpeed;
    if (isHappy) {
      bounce = -Math.abs(Math.sin(this.animTick * 0.45)) * 16;
      tailSpeed = 0.8;
    } else if (isMoving && this.playMode) {
      bounce = -Math.abs(Math.sin(this.animTick * 0.6)) * 8;
      tailSpeed = 0.7;
    } else {
      bounce = Math.sin(this.animTick * 0.15) * 3;
      tailSpeed = 0.2;
    }

    const cx = 115;
    const cy = 130 + bounce;
    const petType = this.data.pet_type || "dog";
    const outlineColor = "#0e4a38";
    let mainColor, earColor, bellyColor;
    if (petType === "dog") {
      mainColor = "#1d6f55"; earColor = "#165c49"; bellyColor = "#FFFFFF";
    } else {
      mainColor = "#A5D6A7"; earColor = "#66BB6A"; bellyColor = "#FFFFFF";
    }

    const tailWag = Math.sin(this.animTick * tailSpeed) * ((isHappy || isMoving) ? 16 : 7);
    ctx.beginPath();
    ctx.moveTo(cx + 35, cy + 25);
    ctx.lineTo(cx + 62, cy + 5 + tailWag);
    ctx.strokeStyle = earColor;
    ctx.lineWidth = 7;
    ctx.lineCap = "round";
    ctx.stroke();

    this._drawEllipse(cx - 38, cy + 5,  cx + 38, cy + 55, mainColor, outlineColor, 1.5);
    this._drawEllipse(cx - 22, cy + 15, cx + 22, cy + 50, bellyColor, null);

    const earBob = isHappy ? Math.sin(this.animTick * 0.3) * 3 : 0;
    if (petType === "dog") {
      this._drawEllipse(cx - 52, cy - 28 + earBob, cx - 26, cy + 16 + earBob, earColor, outlineColor, 1.5);
      this._drawEllipse(cx + 26, cy - 28 + earBob, cx + 52, cy + 16 + earBob, earColor, outlineColor, 1.5);
    } else {
      ctx.fillStyle = mainColor; ctx.strokeStyle = outlineColor; ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - 40, cy - 10); ctx.lineTo(cx - 32, cy - 48 - earBob); ctx.lineTo(cx - 10, cy - 24);
      ctx.closePath(); ctx.fill(); ctx.stroke();

      ctx.fillStyle = "#E8F5E9";
      ctx.beginPath();
      ctx.moveTo(cx - 35, cy - 15); ctx.lineTo(cx - 31, cy - 38 - earBob); ctx.lineTo(cx - 16, cy - 22);
      ctx.closePath(); ctx.fill();

      ctx.fillStyle = mainColor;
      ctx.beginPath();
      ctx.moveTo(cx + 40, cy - 10); ctx.lineTo(cx + 32, cy - 48 - earBob); ctx.lineTo(cx + 10, cy - 24);
      ctx.closePath(); ctx.fill(); ctx.stroke();

      ctx.fillStyle = "#E8F5E9";
      ctx.beginPath();
      ctx.moveTo(cx + 35, cy - 15); ctx.lineTo(cx + 31, cy - 38 - earBob); ctx.lineTo(cx + 16, cy - 22);
      ctx.closePath(); ctx.fill();
    }

    this._drawEllipse(cx - 42, cy - 32, cx + 42, cy + 28, mainColor, outlineColor, 1.5);

    const cheekColor = isHappy ? "#4caf88" : "#3d9b73";
    this._drawEllipse(cx - 32, cy + 2, cx - 18, cy + 11, cheekColor, null);
    this._drawEllipse(cx + 18, cy + 2, cx + 32, cy + 11, cheekColor, null);

    const blink = (this.animTick % 70) <= 2;
    const eyeColor = "#0a2b20";
    if (isHappy) {
      this._drawArc(cx - 24, cy - 10, cx - 8,  cy + 4, 20, 140, { stroke: eyeColor, lineWidth: 3 });
      this._drawArc(cx + 8,  cy - 10, cx + 24, cy + 4, 20, 140, { stroke: eyeColor, lineWidth: 3 });
    } else if (blink) {
      ctx.beginPath();
      ctx.moveTo(cx - 22, cy - 4); ctx.lineTo(cx - 10, cy - 4);
      ctx.moveTo(cx + 10, cy - 4); ctx.lineTo(cx + 22, cy - 4);
      ctx.strokeStyle = eyeColor; ctx.lineWidth = 3; ctx.stroke();
    } else {
      this._drawEllipse(cx - 22, cy - 11, cx - 10, cy + 1, eyeColor, null);
      this._drawEllipse(cx - 19, cy - 9,  cx - 15, cy - 5, "white",  null);
      this._drawEllipse(cx + 10, cy - 11, cx + 22, cy + 1, eyeColor, null);
      this._drawEllipse(cx + 13, cy - 9,  cx + 17, cy - 5, "white",  null);
    }

    const noseColor = petType === "dog" ? "#0a2b20" : "#4CAF50";
    this._drawEllipse(cx - 5, cy - 1, cx + 5, cy + 6, noseColor, null);

    if (isHappy) {
      this._drawArc(cx - 10, cy + 2, cx + 10, cy + 18, 180, 180, { fill: "#EF9A9A", stroke: outlineColor, lineWidth: 1.5 });
    } else {
      this._drawArc(cx - 9, cy + 3, cx,     cy + 11, 180, 180, { stroke: outlineColor, lineWidth: 2 });
      this._drawArc(cx,     cy + 3, cx + 9, cy + 11, 180, 180, { stroke: outlineColor, lineWidth: 2 });
    }

    if (petType === "cat") {
      ctx.strokeStyle = outlineColor; ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - 45, cy - 1); ctx.lineTo(cx - 28, cy + 2);
      ctx.moveTo(cx - 45, cy + 6); ctx.lineTo(cx - 28, cy + 6);
      ctx.moveTo(cx + 45, cy - 1); ctx.lineTo(cx + 28, cy + 2);
      ctx.moveTo(cx + 45, cy + 6); ctx.lineTo(cx + 28, cy + 6);
      ctx.stroke();
    }

    const pawY = cy + 48;
    this._drawEllipse(cx - 28, pawY - 6, cx - 10, pawY + 8, bellyColor, outlineColor, 1.5);
    this._drawEllipse(cx + 10, pawY - 6, cx + 28, pawY + 8, bellyColor, outlineColor, 1.5);

    ctx.font = "bold 14px Arial";
    ctx.fillStyle = "#4CAF50";
    ctx.textAlign = "center";
    for (let i = this.hearts.length - 1; i >= 0; i--) {
      const hh = this.hearts[i];
      hh[1] -= hh[2];
      hh[0] += Math.sin(this.animTick * 0.2 + hh[3]) * 0.8;
      ctx.fillText("♥", hh[0], hh[1]);
      if (hh[1] < 20) this.hearts.splice(i, 1);
    }
    ctx.textAlign = "left";

    if (this.speechTimer > 0 && this.speechText) {
      ctx.fillStyle = "white";
      ctx.strokeStyle = "#A5D6A7";
      ctx.lineWidth = 1.5;
      this._roundRect(14, 12, 202, 28, 6);
      ctx.fill(); ctx.stroke();

      ctx.fillStyle = "#2E7D32";
      ctx.font = "bold 12px Arial";
      ctx.textAlign = "center";
      this._wrapText(this.speechText, 115, 26, 190, 14);
      ctx.textAlign = "left";
    }
  }
}

if (!customElements.get("pet-widget")) {
  customElements.define("pet-widget", PetWidget);
}

window.PetWidget = PetWidget;
