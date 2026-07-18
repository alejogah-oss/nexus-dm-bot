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

// ── PASO 1: VIN ─────────────────────────────────────────────────────
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
    $("vinResultCard").classList.remove("hidden");
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

// ── No perder la sesión por accidente ───────────────────────────────
window.addEventListener("beforeunload", (e) => {
  const hasData = session.vin || session.photos.length > 0;
  if (hasData && !session.saved) { e.preventDefault(); e.returnValue = ""; }
});

goTo(1);
