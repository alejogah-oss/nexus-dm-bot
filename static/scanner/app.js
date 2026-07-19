/* NEXUS Scanner — wizard 4 pasos. Estado en memoria; reintento sin perder fotos. */
"use strict";

const $ = (id) => document.getElementById(id);

// ── Estado de la sesión (solo memoria) ──────────────────────────────
const session = {
  vin: "", car: {},
  mileage: null, price: null, color: "", notes: "",
  photos: [],        // [{file, url}]
  video: null,       // File
  title: "", description: "",
  saved: false,
};
let step = 1;
let lastFailedAction = null; // () => Promise — para Reintentar

// ── Clave de acceso ─────────────────────────────────────────────────
function getKey() { return localStorage.getItem("scannerKey") || ""; }

function showKeyOverlay() {
  $("keyInput").value = getKey();
  $("keyOverlay").classList.remove("hidden");
}

$("keySaveBtn").addEventListener("click", () => {
  const k = $("keyInput").value.trim();
  if (!k) return;
  localStorage.setItem("scannerKey", k);
  $("keyOverlay").classList.add("hidden");
});
$("keyBadgeBtn").addEventListener("click", showKeyOverlay);
if (!getKey()) showKeyOverlay();

// ── Red: helper con auth + manejo de error/reintento ────────────────
async function api(path, options) {
  const opts = options || {};
  opts.headers = Object.assign({}, opts.headers, { "X-Scanner-Key": getKey() });
  const r = await fetch(path, opts);
  if (r.status === 401) { showKeyOverlay(); throw new Error("Clave inválida — revísala."); }
  if (!r.ok) {
    let msg = "Error del servidor (" + r.status + ")";
    try { const j = await r.json(); if (j.error) msg = j.error; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function showError(msg, retryFn) {
  $("errorMsg").textContent = msg;
  lastFailedAction = retryFn;
  $("errorBanner").classList.add("show");
}
function hideError() { $("errorBanner").classList.remove("show"); lastFailedAction = null; }
$("retryBtn").addEventListener("click", () => {
  const fn = lastFailedAction;
  hideError();
  if (fn) fn();
});

function setBusy(busy, label) {
  $("nextBtn").disabled = busy;
  $("nextBtnSpinner").classList.toggle("hidden", !busy);
  if (label) $("nextBtnLabel").textContent = label;
}

// ── Navegación del wizard ───────────────────────────────────────────
const NEXT_LABELS = { 1: "Continuar", 2: "Continuar", 3: "Generar copy", 4: "Listo" };

function goTo(n) {
  step = n;
  document.querySelectorAll(".step").forEach((s) =>
    s.classList.toggle("active", Number(s.dataset.step) === n));
  document.querySelectorAll(".progress-step").forEach((p) =>
    p.classList.toggle("active", Number(p.dataset.step) <= n));
  document.querySelectorAll(".progress-labels span").forEach((l) =>
    l.classList.toggle("current", Number(l.dataset.label) === n));
  $("backBtn").classList.toggle("hidden", n === 1);
  if (n !== 1 && typeof stopLiveScan === "function") stopLiveScan();
  $("nextBtnLabel").textContent = NEXT_LABELS[n];
  $("nextBtn").classList.toggle("hidden", n === 4);
  hideError();
  window.scrollTo(0, 0);
}

$("backBtn").addEventListener("click", () => { if (step > 1) goTo(step - 1); });

$("nextBtn").addEventListener("click", () => {
  if (step === 1) {
    const vin = $("vinField").value.trim().toUpperCase();
    if (vin.length !== 17) { showError("El VIN debe tener 17 caracteres. Escanéalo o escríbelo.", null); return; }
    session.vin = vin;
    session.car = {
      yr: $("carYr").value.trim(), make: $("carMake").value.trim(),
      model: $("carModel").value.trim(), trim: $("carTrim").value.trim(),
      engine: $("carEngine").value.trim(), fuel: $("carFuel").value.trim(),
      body: $("carBody").value.trim(), drive: $("carDrive").value.trim(),
    };
    goTo(2);
  } else if (step === 2) {
    const price = parseInt($("priceField").value, 10);
    const color = $("colorField").value.trim();
    if (!price || price <= 0) { showError("El precio es obligatorio.", null); return; }
    if (!color) { showError("El color es obligatorio.", null); return; }
    session.mileage = parseInt($("mileageField").value, 10) || 0;
    session.price = price;
    session.color = color;
    session.notes = $("notesField").value.trim();
    goTo(3);
  } else if (step === 3) {
    if (session.photos.length === 0) { showError("Agrega al menos una foto del carro.", null); return; }
    goTo(4);
    generateCopy();
  }
});

// ── Compresión de fotos para OCR (rápido en LTE, bajo el límite de la API) ──
async function shrinkForOcr(file, maxDim) {
  maxDim = maxDim || 2000;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, maxDim / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.size < 3 * 1048576) { bmp.close(); return file; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
    const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85));
    return blob || file;
  } catch (_) { return file; } // formato raro — sube el original
}

// ── PASO 1: Escáner en vivo (código de barras de la etiqueta del VIN) ──
// Validación de check digit en el cliente: filtra frames malos sin ir al servidor
const VIN_MAP = {A:1,B:2,C:3,D:4,E:5,F:6,G:7,H:8,J:1,K:2,L:3,M:4,N:5,P:7,R:9,
                 S:2,T:3,U:4,V:5,W:6,X:7,Y:8,Z:9};
const VIN_WEIGHTS = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2];
function vinCheckDigitOk(vin) {
  if (vin.length !== 17 || /[IOQ]/.test(vin) || !/^[A-Z0-9]+$/.test(vin)) return false;
  let total = 0;
  for (let i = 0; i < 17; i++) {
    const c = vin[i];
    const val = c >= "0" && c <= "9" ? Number(c) : VIN_MAP[c];
    if (val === undefined) return false;
    total += val * VIN_WEIGHTS[i];
  }
  const check = total % 11;
  return vin[8] === (check === 10 ? "X" : String(check));
}

function extractVinFromScan(text) {
  const up = text.toUpperCase()
    .replace(/[IOQ]/g, (m) => ({ I: "1", O: "0", Q: "0" }[m]))
    .replace(/[^A-Z0-9]/g, "");
  for (let i = 0; i + 17 <= up.length; i++) {
    const w = up.slice(i, i + 17);
    if (vinCheckDigitOk(w)) return w;
  }
  return up.length === 17 ? up : ""; // 17 sin check válido: el servidor intenta repararlo
}

let zxingReader = null;
let liveScanTimer = null;

function stopLiveScan() {
  if (zxingReader) { try { zxingReader.reset(); } catch (_) {} zxingReader = null; }
  if (liveScanTimer) { clearTimeout(liveScanTimer); liveScanTimer = null; }
  $("liveScanBox").classList.add("hidden");
  $("liveScanBtn").classList.remove("hidden");
  $("liveHint").textContent = "Buscando el código del VIN…";
}

$("liveStopBtn").addEventListener("click", stopLiveScan);

$("liveScanBtn").addEventListener("click", () => {
  if (typeof ZXing === "undefined") {
    showError("El lector no cargó — usa la foto de la placa.", null);
    return;
  }
  $("liveScanBtn").classList.add("hidden");
  $("liveScanBox").classList.remove("hidden");
  const hints = new Map();
  hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
    ZXing.BarcodeFormat.CODE_39, ZXing.BarcodeFormat.CODE_128,
    ZXing.BarcodeFormat.DATA_MATRIX, ZXing.BarcodeFormat.QR_CODE,
    ZXing.BarcodeFormat.PDF_417,
  ]);
  hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
  zxingReader = new ZXing.BrowserMultiFormatReader(hints);
  liveScanTimer = setTimeout(() => {
    if ($("liveHint")) $("liveHint").textContent =
      "¿No lo encuentra? Acércate al código de la etiqueta de la puerta, o cancela y usa la foto.";
  }, 12000);
  zxingReader
    .decodeFromVideoDevice(null, $("liveVideo"), (result) => {
      if (!result) return; // frames sin código — seguir buscando
      const vin = extractVinFromScan(result.getText());
      if (!vin) return;
      stopLiveScan();
      if (navigator.vibrate) navigator.vibrate(80);
      resolveScannedVin(vin);
    })
    .catch(() => {
      stopLiveScan();
      showError("No pude abrir la cámara — usa la foto de la placa.", null);
    });
});

async function resolveScannedVin(vin) {
  setBusy(true, "VIN detectado — buscando ficha…");
  try {
    const res = await api("/api/scanner/vin-decode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vin }),
    });
    fillVinResult(res);
    hideError();
  } catch (err) {
    // sin señal: al menos deja el VIN puesto para seguir a mano
    fillVinResult({ vin, valid: vinCheckDigitOk(vin), car: {} });
    showError(err.message + " — el VIN quedó puesto, la ficha se puede llenar a mano.",
              () => resolveScannedVin(vin));
  } finally {
    setBusy(false, NEXT_LABELS[step]);
  }
}

function fillVinResult(res) {
  $("vinField").value = res.vin || "";
  const badge = $("vinBadge");
  badge.textContent = res.valid ? "VIN ✓" : "VIN no válido — corrígelo";
  const card = $("vinResultCard");
  card.classList.toggle("valid", res.valid);
  card.classList.toggle("invalid", !res.valid);
  const car = res.car || {};
  $("carYr").value = car.yr || ""; $("carMake").value = car.make || "";
  $("carModel").value = car.model || ""; $("carTrim").value = car.trim || "";
  $("carEngine").value = car.engine || ""; $("carFuel").value = car.fuel || "";
  $("carBody").value = car.body || ""; $("carDrive").value = car.drive || "";
  card.classList.remove("hidden");
}

// ── PASO 1: VIN por foto (respaldo) ─────────────────────────────────
$("vinPhotoInput").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) scanVin(file);
  e.target.value = "";
});

async function scanVin(file) {
  $("vinPreviewImg").src = URL.createObjectURL(file);
  $("vinPreviewImg").classList.remove("hidden");
  $("vinCaptureHint").classList.add("hidden");
  $("vinCaptureLabel").textContent = "Repetir foto del VIN";
  setBusy(true, "Leyendo VIN…");
  try {
    const fd = new FormData();
    fd.append("photo", await shrinkForOcr(file), "photo.jpg");
    const res = await api("/api/scanner/vin", { method: "POST", body: fd });
    fillVinResult(res);
    hideError();
  } catch (err) {
    $("vinResultCard").classList.remove("hidden"); // permite digitar manual sin señal
    showError(err.message + " — puedes reintentar o escribir el VIN a mano.", () => scanVin(file));
  } finally {
    setBusy(false, NEXT_LABELS[step]);
  }
}

// ── PASO 2: Odómetro ────────────────────────────────────────────────
$("odoPhotoInput").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) scanOdometer(file);
  e.target.value = "";
});

async function scanOdometer(file) {
  $("odoPreviewImg").src = URL.createObjectURL(file);
  $("odoPreviewImg").classList.remove("hidden");
  $("odoCaptureHint").classList.add("hidden");
  $("odoCaptureLabel").textContent = "Repetir foto del odómetro";
  setBusy(true, "Leyendo millaje…");
  try {
    const fd = new FormData();
    fd.append("photo", await shrinkForOcr(file), "photo.jpg");
    const res = await api("/api/scanner/odometer", { method: "POST", body: fd });
    $("mileageField").value = res.mileage || "";
    hideError();
  } catch (err) {
    showError(err.message + " — reintenta o escribe el millaje a mano.", () => scanOdometer(file));
  } finally {
    setBusy(false, NEXT_LABELS[step]);
  }
}

// ── PASO 3: Fotos + video ───────────────────────────────────────────
$("photosInput").addEventListener("change", (e) => {
  for (const file of e.target.files) {
    session.photos.push({ file, url: URL.createObjectURL(file) });
  }
  e.target.value = "";
  renderThumbs();
});

function renderThumbs() {
  const grid = $("photoGrid");
  grid.innerHTML = "";
  session.photos.forEach((p, i) => {
    const div = document.createElement("div");
    div.className = "photo-thumb";
    const img = document.createElement("img");
    img.src = p.url;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "remove-photo";
    del.textContent = "✕";
    del.addEventListener("click", () => {
      URL.revokeObjectURL(p.url);
      session.photos.splice(i, 1);
      renderThumbs();
    });
    div.appendChild(img);
    div.appendChild(del);
    grid.appendChild(div);
  });
  $("videoAddLabel").classList.remove("hidden");
}

$("videoInput").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  session.video = file;
  $("videoName").textContent = "🎥 " + file.name + " (" + Math.round(file.size / 1048576) + " MB)";
  $("videoStatus").classList.remove("hidden");
  $("videoAddLabel").classList.add("hidden");
  e.target.value = "";
});

$("removeVideoBtn").addEventListener("click", () => {
  session.video = null;
  $("videoStatus").classList.add("hidden");
  $("videoAddLabel").classList.remove("hidden");
});

// Mostrar el label de video desde el inicio del paso 3
$("videoAddLabel").classList.remove("hidden");

// ── PASO 4: Copy ────────────────────────────────────────────────────
$("genCopyBtn").addEventListener("click", generateCopy);

async function generateCopy() {
  $("genCopyBtn").classList.add("hidden");
  $("copyBlock").classList.add("hidden");
  $("copyActions").classList.add("hidden");
  renderCopyPreview();
  try {
    const body = Object.assign({}, session.car, {
      mileage: session.mileage, price: session.price,
      notes: (session.notes + (session.color ? " | Color: " + session.color : "")).trim(),
    });
    const res = await api("/api/scanner/listing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    session.title = res.title || "";
    session.description = res.description || "";
    const t = $("copyTitle"), d = $("copyDescription");
    t.textContent = session.title;
    d.textContent = session.description;
    t.contentEditable = "true";
    d.contentEditable = "true";
    $("copyBlock").classList.remove("hidden");
    $("copyActions").classList.remove("hidden");
    hideError();
  } catch (err) {
    $("genCopyBtn").classList.remove("hidden");
    $("genCopyBtn").textContent = "Reintentar copy";
    showError(err.message, generateCopy);
  }
}

$("copyBtn").addEventListener("click", async () => {
  session.title = $("copyTitle").textContent.trim();
  session.description = $("copyDescription").textContent.trim();
  const text = session.title + "\n\n" + session.description;
  try {
    await navigator.clipboard.writeText(text);
    $("copyBtn").textContent = "✓ Copiado";
    setTimeout(() => { $("copyBtn").textContent = "Copiar título + descripción"; }, 2000);
  } catch (_) {
    // Fallback iOS viejo
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    $("copyBtn").textContent = "✓ Copiado";
    setTimeout(() => { $("copyBtn").textContent = "Copiar título + descripción"; }, 2000);
  }
});

$("saveInventoryBtn").addEventListener("click", saveInventory);

async function saveInventory() {
  session.title = $("copyTitle").textContent.trim();
  session.description = $("copyDescription").textContent.trim();
  const btn = $("saveInventoryBtn");
  btn.disabled = true;
  btn.textContent = "Guardando…";
  try {
    const data = {
      vin: session.vin, yr: session.car.yr, model: session.car.model,
      trim: session.car.trim, color: session.color, price: session.price,
      mileage: session.mileage, title: session.title,
      description: session.description, notes: session.notes,
    };
    const fd = new FormData();
    fd.append("data", JSON.stringify(data));
    session.photos.forEach((p, i) => fd.append("photos", p.file, (i + 1) + ".jpg"));
    if (session.video) fd.append("video", session.video, "video.mp4");
    const res = await api("/api/scanner/inventory", { method: "POST", body: fd });
    session.saved = true;
    const folder = (res.folder || "").split("/").pop();
    $("folderResult").textContent = "✓ Guardado en NEXUS: " + folder;
    $("folderResult").classList.remove("hidden");
    btn.textContent = "✓ Guardado";
    hideError();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Guardar en NEXUS";
    showError(err.message + " — tus fotos siguen aquí, reintenta.", saveInventory);
  }
}

// ── Previsualización de fotos en el paso Copy ───────────────────────
function renderCopyPreview() {
  const grid = $("copyPhotoPreview");
  grid.innerHTML = "";
  session.photos.forEach((p) => {
    const img = document.createElement("img");
    img.src = p.url;
    grid.appendChild(img);
  });
  grid.classList.toggle("hidden", session.photos.length === 0);
}

// ── Pendientes por subir ────────────────────────────────────────────
let pendSlug = null;

function showPendList() {
  pendSlug = null;
  $("pendDetail").classList.add("hidden");
  $("pendList").classList.remove("hidden");
  $("pendTitle").textContent = "Pendientes por subir";
}

$("pendBtn").addEventListener("click", async () => {
  $("pendView").classList.remove("hidden");
  showPendList();
  const list = $("pendList");
  list.innerHTML = '<p class="hint">Cargando…</p>';
  try {
    const res = await api("/api/scanner/inventory", { method: "GET" });
    list.innerHTML = "";
    if (!res.items.length) {
      list.innerHTML = '<p class="hint">No hay carros guardados todavía.</p>';
      return;
    }
    res.items.forEach((it) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pend-item";
      const img = document.createElement("img");
      img.src = "/api/scanner/inventory/" + it.slug + "/photo/1?key=" + encodeURIComponent(getKey());
      img.alt = "";
      const info = document.createElement("div");
      info.className = "pend-info";
      const name = document.createElement("div");
      name.className = "pend-name";
      name.textContent = it.title || (it.yr + " " + it.model + " " + it.trim);
      const meta = document.createElement("div");
      meta.className = "pend-meta";
      meta.textContent = "$" + (it.price || 0).toLocaleString() + " · " +
        (it.mileage || 0).toLocaleString() + " mi · " + it.photos + " fotos" +
        (it.video ? " · 🎥" : "");
      info.appendChild(name);
      info.appendChild(meta);
      btn.appendChild(img);
      btn.appendChild(info);
      btn.addEventListener("click", () => openPendiente(it.slug));
      list.appendChild(btn);
    });
  } catch (err) {
    list.innerHTML = '<p class="hint">Error: ' + err.message + "</p>";
  }
});

async function openPendiente(slug) {
  try {
    const res = await api("/api/scanner/inventory/" + slug, { method: "GET" });
    pendSlug = slug;
    const d = res.data;
    $("pendTitle").textContent = (d.yr || "") + " " + (d.model || "") + " " + (d.trim || "");
    $("pTitle").value = d.title || "";
    $("pDesc").value = d.description || "";
    $("pPrice").value = d.price || "";
    $("pMileage").value = d.mileage || "";
    const grid = $("pendPhotos");
    grid.innerHTML = "";
    for (let i = 1; i <= res.photos; i++) {
      const img = document.createElement("img");
      img.src = "/api/scanner/inventory/" + slug + "/photo/" + i + "?key=" + encodeURIComponent(getKey());
      grid.appendChild(img);
    }
    $("pendList").classList.add("hidden");
    $("pendDetail").classList.remove("hidden");
  } catch (err) {
    showError(err.message, () => openPendiente(slug));
  }
}

$("pSaveBtn").addEventListener("click", async () => {
  if (!pendSlug) return;
  const btn = $("pSaveBtn");
  btn.disabled = true;
  btn.textContent = "Guardando…";
  try {
    await api("/api/scanner/inventory/" + pendSlug, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: $("pTitle").value.trim(),
        description: $("pDesc").value.trim(),
        price: parseInt($("pPrice").value, 10) || 0,
        mileage: parseInt($("pMileage").value, 10) || 0,
      }),
    });
    btn.textContent = "✓ Guardado";
  } catch (err) {
    btn.textContent = "Guardar cambios";
    alert("No se pudo guardar: " + err.message);
  } finally {
    btn.disabled = false;
    setTimeout(() => { btn.textContent = "Guardar cambios"; }, 2000);
  }
});

$("pCopyBtn").addEventListener("click", async () => {
  const text = $("pTitle").value.trim() + "\n\n" + $("pDesc").value.trim();
  try { await navigator.clipboard.writeText(text); } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove();
  }
  $("pCopyBtn").textContent = "✓ Copiado";
  setTimeout(() => { $("pCopyBtn").textContent = "Copiar título + descripción"; }, 2000);
});

$("pBackBtn").addEventListener("click", () => { showPendList(); $("pendBtn").click(); });
$("pendCloseBtn").addEventListener("click", () => $("pendView").classList.add("hidden"));

// ── No perder la sesión por accidente ───────────────────────────────
window.addEventListener("beforeunload", (e) => {
  const hasData = session.vin || session.photos.length > 0;
  if (hasData && !session.saved) { e.preventDefault(); e.returnValue = ""; }
});

goTo(1);
