/* NEXUS Admin — admin.js
   Panel /admin: lista inventario del scanner, badges de estado,
   edita los no publicados y dispara publicación a Marketplace de uno a la vez.
   El bot NUNCA publica solo — el botón solo llena el formulario en el Mac Pro,
   Alejo da clic en Publicar y luego marca como publicado aquí. */
"use strict";

const $ = (id) => document.getElementById(id);

// ── Copiar VIN al portapapeles ───────────────────────────────────────
async function copyVin(btn, vin) {
  const original = btn.textContent;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(vin);
    } else {
      const ta = document.createElement("textarea");
      ta.value = vin;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    btn.textContent = "✓ VIN copiado";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = original; btn.classList.remove("copied"); }, 1400);
  } catch (_) {
    btn.textContent = vin;
  }
}

// ── Clave de acceso ─────────────────────────────────────────────────
function getKey() { return localStorage.getItem("nexus_scanner_key") || ""; }

function showKeyOverlay() {
  $("keyInput").value = getKey();
  $("keyOverlay").classList.remove("hidden");
}

function hideKeyOverlay() {
  $("keyOverlay").classList.add("hidden");
}

$("keySaveBtn").addEventListener("click", () => {
  const k = $("keyInput").value.trim();
  if (!k) return;
  localStorage.setItem("nexus_scanner_key", k);
  hideKeyOverlay();
  load();
});

if (!getKey()) {
  showKeyOverlay();
} else {
  load();
}

// ── Red: helper con auth ─────────────────────────────────────────────
async function api(path, options) {
  const opts = options || {};
  opts.headers = Object.assign({}, opts.headers, { "X-Scanner-Key": getKey() });
  const r = await fetch(path, opts);
  if (r.status === 401) {
    localStorage.removeItem("nexus_scanner_key");
    showKeyOverlay();
    throw new Error("Clave inválida — revísala.");
  }
  if (!r.ok) {
    let msg = "Error del servidor (" + r.status + ")";
    try { const j = await r.json(); if (j.error) msg = j.error; } catch (_) {}
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  if (r.status === 204) return {};
  return r.json();
}

// ── Cargar inventario ────────────────────────────────────────────────
async function load() {
  const cars = $("cars");
  cars.innerHTML = '<p class="hint">Cargando…</p>';
  try {
    const res = await api("/api/admin/inventory", { method: "GET" });
    renderPublishingBanner(res.publishing);
    allItems = res.items || [];
    currentPublishing = res.publishing;
    renderCars();
  } catch (err) {
    cars.innerHTML = '<p class="hint">Error: ' + err.message + "</p>";
  }
}

function renderPublishingBanner(publishing) {
  const banner = $("publishingBanner");
  if (publishing) {
    banner.textContent = "Publicando " + publishing + " — termina en el Mac Pro y marca como publicado.";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

function statusBadge(item) {
  if (item.inactive) {
    return { cls: "inactive", label: "⚫ Inactivo " + (item.inactive_at || "") };
  }
  if (item.published) {
    return { cls: "published", label: "🟢 Publicado " + (item.published_at || "") };
  }
  if (item.last_error) {
    return { cls: "failed", label: "🔴 Falló: " + item.last_error };
  }
  return { cls: "pending", label: "🟡 Sin publicar" };
}

// ── Buscador por VIN + filtro de estado ─────────────────────────────
let allItems = [];
let currentPublishing = null;
let statusFilter = "active";

function matchesSearch(item, q) {
  if (!q) return true;
  const vin = (item.vin || "").toUpperCase();
  const qVin = q.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (qVin && vin.includes(qVin)) return true;
  const title = [item.yr, item.make, item.model, item.title].join(" ").toLowerCase();
  return title.includes(q.toLowerCase());
}

function renderCars() {
  const cars = $("cars");
  cars.innerHTML = "";
  const nInactive = allItems.filter((i) => i.inactive).length;
  $("cntActive").textContent = allItems.length - nInactive;
  $("cntInactive").textContent = nInactive;
  if (!allItems.length) {
    cars.innerHTML = '<p class="hint">No hay carros guardados todavía.</p>';
    return;
  }
  const q = $("searchInput").value.trim();
  const items = allItems.filter((i) =>
    (statusFilter === "all" || (statusFilter === "inactive") === !!i.inactive) &&
    matchesSearch(i, q));
  if (!items.length) {
    cars.innerHTML = '<p class="hint">' +
      (q ? "Ningún carro coincide con “" + q.replace(/[<>&]/g, "") + "”." : "No hay carros en esta lista.") +
      "</p>";
    return;
  }
  items.forEach((item) => cars.appendChild(buildCarCard(item, currentPublishing)));
}

$("searchInput").addEventListener("input", renderCars);

document.querySelectorAll("#statusSeg button").forEach((b) => {
  b.addEventListener("click", () => {
    statusFilter = b.dataset.f;
    document.querySelectorAll("#statusSeg button").forEach((x) => x.classList.toggle("on", x === b));
    renderCars();
  });
});

function buildCarCard(item, publishing) {
  const card = document.createElement("div");
  card.className = "car-card" + (item.inactive ? " is-inactive" : "");
  card.dataset.slug = item.slug;

  const badge = statusBadge(item);
  const badgeEl = document.createElement("span");
  badgeEl.className = "badge " + badge.cls;
  badgeEl.textContent = badge.label;

  const photo = document.createElement("div");
  photo.className = "car-photo";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.decoding = "async";
  img.src = "/api/scanner/inventory/" + item.slug + "/photo/1?w=400&key=" + encodeURIComponent(getKey());
  img.alt = "";
  photo.appendChild(img);
  card.appendChild(photo);

  const info = document.createElement("div");
  info.className = "car-info";
  info.appendChild(badgeEl);

  const title = document.createElement("p");
  title.className = "car-title";
  title.textContent = [item.yr, item.make, item.model].filter(Boolean).join(" ") || item.title || item.slug;
  info.appendChild(title);

  if (item.vin) {
    const vin = document.createElement("button");
    vin.type = "button";
    vin.className = "car-vin";
    vin.title = "Toca para copiar el VIN";
    vin.textContent = "VIN " + item.vin;
    vin.addEventListener("click", () => copyVin(vin, item.vin));
    info.appendChild(vin);
  }

  const meta = document.createElement("p");
  meta.className = "car-meta";
  meta.textContent = "$" + (item.price || 0).toLocaleString() + " · " +
    (item.mileage || 0).toLocaleString() + " mi" +
    (item.internal_price ? " · 🔒 $" + item.internal_price.toLocaleString() : "") +
    (item.updated_at ? " · editado " + item.updated_at : "");
  info.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "car-actions";

  if (item.inactive) {
    const reBtn = document.createElement("button");
    reBtn.type = "button";
    reBtn.className = "ghost";
    reBtn.textContent = "Reactivar";
    reBtn.addEventListener("click", () => reactivateCar(item));
    actions.appendChild(reBtn);
    info.appendChild(actions);
    card.appendChild(info);
    return card;
  }

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "ghost";
  editBtn.textContent = "Editar";
  editBtn.addEventListener("click", () => openEdit(item.slug));
  actions.appendChild(editBtn);

  if (!item.published) {
    const pubBtn = document.createElement("button");
    pubBtn.type = "button";
    pubBtn.className = "btn-primary";
    pubBtn.textContent = "Publicar este carro";
    pubBtn.disabled = !!publishing;
    pubBtn.addEventListener("click", () => publishCar(item.slug));
    actions.appendChild(pubBtn);

    if (publishing === item.slug) {
      const markBtn = document.createElement("button");
      markBtn.type = "button";
      markBtn.className = "btn-primary";
      markBtn.textContent = "Marcar publicado";
      markBtn.addEventListener("click", () => markPublished(item.slug));
      actions.appendChild(markBtn);
    }
  }

  const inBtn = document.createElement("button");
  inBtn.type = "button";
  inBtn.className = "ghost danger";
  inBtn.textContent = "Inactivar";
  inBtn.disabled = publishing === item.slug;
  inBtn.addEventListener("click", () => openInactivate(item));
  actions.appendChild(inBtn);

  info.appendChild(actions);
  card.appendChild(info);
  return card;
}

function carLabel(item) {
  return [item.yr, item.make, item.model].filter(Boolean).join(" ") || item.title || item.slug;
}

// ── Inactivar / reactivar ────────────────────────────────────────────
// Quita el carro de tucarroconalejo.com (de ahí leen los bots) y lo deja en
// Inactivos. Facebook lo marca Alejo a mano en Marketplace.
let inactItem = null;

function openInactivate(item) {
  inactItem = item;
  $("iCar").textContent = carLabel(item) + (item.vin ? " · VIN " + item.vin : "");
  $("iOkBtn").disabled = false;
  $("iOkBtn").textContent = "Sí, inactivar";
  $("inactModal").classList.remove("hidden");
}

function closeInactivate() {
  inactItem = null;
  $("inactModal").classList.add("hidden");
}

$("iCancelBtn").addEventListener("click", closeInactivate);

$("iOkBtn").addEventListener("click", async () => {
  if (!inactItem) return;
  const btn = $("iOkBtn");
  btn.disabled = true;
  btn.textContent = "Inactivando…";
  try {
    await api("/api/admin/inactivate/" + inactItem.slug, { method: "POST" });
    closeInactivate();
    load();
  } catch (err) {
    alert("No se pudo inactivar: " + err.message);
    btn.disabled = false;
    btn.textContent = "Sí, inactivar";
  }
});

async function reactivateCar(item) {
  if (!confirm("¿Reactivar " + carLabel(item) + "?\n\nVuelve a subirse a tucarroconalejo.com como PENDIENTE: apruébalo en admin.html para que se vea.")) return;
  try {
    await api("/api/admin/reactivate/" + item.slug, { method: "POST" });
  } catch (err) {
    alert("No se pudo reactivar: " + err.message);
  } finally {
    load();
  }
}

// ── Cuadrar con el lote ───────────────────────────────────────────────
// Alejo pega los VINs que tiene hoy; el panel muestra los que sobran y los
// inactiva uno por uno con pausa (ráfagas al sitio activan el anti-bots de Hostinger).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let lotRunning = false;

function showLotStep(n) {
  $("lotStep1").classList.toggle("hidden", n !== 1);
  $("lotStep2").classList.toggle("hidden", n !== 2);
}

$("lotBtn").addEventListener("click", () => {
  showLotStep(1);
  $("lotModal").classList.remove("hidden");
  $("lotText").focus();
});

$("lotCloseBtn").addEventListener("click", () => {
  if (lotRunning) return;
  $("lotModal").classList.add("hidden");
  load();
});

$("lotBackBtn").addEventListener("click", () => { if (!lotRunning) showLotStep(1); });

$("lotCompareBtn").addEventListener("click", async () => {
  const btn = $("lotCompareBtn");
  btn.disabled = true;
  btn.textContent = "Comparando…";
  try {
    const res = await api("/api/admin/reconcile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vins: $("lotText").value }),
    });
    renderLotResult(res);
    showLotStep(2);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Comparar";
  }
});

function renderLotResult(res) {
  const list = $("lotList");
  list.innerHTML = "";
  const missing = res.missing || [];
  $("lotSummary").innerHTML = "Pegaste <b>" + res.pasted + "</b> VINs · coinciden <b>" + res.matched +
    "</b> carros del scanner. " + (missing.length
      ? "<b>" + missing.length + "</b> " + (missing.length === 1 ? "carro activo NO está" : "carros activos NO están") + " en tu lista:"
      : "Todos los carros activos están en tu lista. ✓");
  missing.forEach((m) => {
    const row = document.createElement("label");
    row.className = "lot-item";
    row.dataset.slug = m.slug;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    const txt = document.createElement("span");
    txt.textContent = (m.title || m.slug) + (m.on_site ? "" : " · no está en la web");
    const vin = document.createElement("span");
    vin.className = "lot-vin";
    vin.textContent = m.vin;
    txt.appendChild(vin);
    row.appendChild(cb);
    row.appendChild(txt);
    list.appendChild(row);
  });
  const back = res.back_in_lot || [];
  $("lotBackInLot").textContent = back.length
    ? "Ojo: " + back.length + " " + (back.length === 1 ? "carro está inactivo" : "carros están inactivos") +
      " pero sigue" + (back.length === 1 ? "" : "n") + " en tu lista — si volvió, reactívalo en Inactivos: " +
      back.map((b) => (b.title || b.slug) + " (" + b.vin.slice(-6) + ")").join(", ")
    : "";
  $("lotBackInLot").classList.toggle("hidden", !back.length);
  const ns = res.not_scanned || [];
  $("lotNotScanned").textContent = ns.length
    ? "En tu lista pero nunca pasaron por el scanner (" + ns.length + "): " + ns.join(", ")
    : "";
  $("lotNotScanned").classList.toggle("hidden", !ns.length);
  $("lotProgress").classList.add("hidden");
  $("lotGoBtn").classList.toggle("hidden", !missing.length);
  $("lotGoBtn").disabled = false;
  $("lotGoBtn").textContent = "Inactivar seleccionados";
}

$("lotGoBtn").addEventListener("click", async () => {
  const rows = [...document.querySelectorAll("#lotList .lot-item")]
    .filter((r) => r.querySelector("input").checked && !r.classList.contains("done"));
  if (!rows.length) return;
  if (!confirm("¿Inactivar " + rows.length + " carros? Se quitan de la web y los bots dejan de ofrecerlos.")) return;
  lotRunning = true;
  const go = $("lotGoBtn");
  go.disabled = true;
  const prog = $("lotProgress");
  prog.classList.remove("hidden");
  let ok = 0, fail = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    prog.textContent = "Inactivando " + (i + 1) + " de " + rows.length + "…";
    r.classList.remove("err");
    try {
      await api("/api/admin/inactivate/" + r.dataset.slug, { method: "POST" });
      r.classList.add("done");
      r.querySelector("input").disabled = true;
      const okTag = document.createElement("span");
      okTag.className = "lot-ok";
      okTag.textContent = " · inactivado ✓";
      r.querySelector("span").insertBefore(okTag, r.querySelector(".lot-vin"));
      ok++;
    } catch (err) {
      r.classList.add("err");
      r.title = err.message;
      fail++;
    }
    if (i < rows.length - 1) await sleep(1500);
  }
  lotRunning = false;
  prog.textContent = "Listo: " + ok + " inactivados" + (fail ? " · " + fail + " fallaron (en rojo) — reintenta" : "") + ".";
  go.disabled = !fail;
  go.textContent = fail ? "Reintentar los que fallaron" : "Inactivar seleccionados";
});

// ── Publicar / marcar publicado ──────────────────────────────────────
async function publishCar(slug) {
  try {
    await api("/api/admin/publish/" + slug, { method: "POST" });
    alert("Chrome se abrió en el Mac Pro. Revisa el formulario y dale Publicar. Luego vuelve y marca como publicado.");
  } catch (err) {
    if (err.status === 409) {
      alert("Ya hay una publicación en curso.");
    } else {
      alert("No se pudo publicar: " + err.message);
    }
  } finally {
    load();
  }
}

async function markPublished(slug) {
  try {
    await api("/api/admin/mark/" + slug, { method: "POST" });
  } catch (err) {
    alert("No se pudo marcar como publicado: " + err.message);
  } finally {
    load();
  }
}

// ── Editar carro ──────────────────────────────────────────────────────
let editSlug = null;

async function openEdit(slug) {
  try {
    const res = await api("/api/scanner/inventory/" + slug, { method: "GET" });
    const d = res.data || {};
    editSlug = slug;
    const vinBtn = $("eVin");
    if (d.vin) {
      vinBtn.textContent = "VIN " + d.vin;
      vinBtn.onclick = () => copyVin(vinBtn, d.vin);
      vinBtn.classList.remove("hidden");
    } else {
      vinBtn.classList.add("hidden");
    }
    $("eTitle").value = d.title || "";
    $("eDesc").value = d.description || "";
    $("eMake").value = d.make || "";
    $("ePrice").value = d.price || "";
    $("eMileage").value = d.mileage || "";
    $("eColor").value = d.color || "";
    $("eInternalPrice").value = d.internal_price || "";
    $("eAltPriceLow").value = d.alt_price_low || "";
    $("eAltPriceHigh").value = d.alt_price_high || "";
    // Publicado: el listing público ya salió a Marketplace y no se puede
    // editar desde acá (no se re-sincroniza) — solo el precio real privado.
    $("ePublicFields").classList.toggle("hidden", !!d.published);
    $("ePublishedNote").classList.toggle("hidden", !d.published);
    $("editModal").classList.remove("hidden");
  } catch (err) {
    alert("No se pudo cargar el carro: " + err.message);
  }
}

function closeEdit() {
  editSlug = null;
  $("editModal").classList.add("hidden");
}

$("eCancelBtn").addEventListener("click", closeEdit);

$("eRegenBtn").addEventListener("click", async () => {
  if (!editSlug) return;
  const btn = $("eRegenBtn");
  btn.disabled = true;
  btn.textContent = "Generando…";
  try {
    const out = await api("/api/admin/regenerate/" + editSlug, { method: "POST" });
    $("eTitle").value = out.title || "";
    $("eDesc").value = out.description || "";
  } catch (err) {
    alert("No se pudo regenerar el copy: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "✨ Regenerar copy";
  }
});

$("eSaveBtn").addEventListener("click", async () => {
  if (!editSlug) return;
  const btn = $("eSaveBtn");
  btn.disabled = true;
  btn.textContent = "Guardando…";
  try {
    const publicFieldsVisible = !$("ePublicFields").classList.contains("hidden");
    const body = {
      internal_price: Number($("eInternalPrice").value) || 0,
      alt_price_low: Number($("eAltPriceLow").value) || 0,
      alt_price_high: Number($("eAltPriceHigh").value) || 0,
    };
    // Publicado: nunca reenviar los campos del listing público, ni sin querer
    // (no se re-sincronizan con Marketplace de todos modos, mejor no tocarlos).
    if (publicFieldsVisible) {
      Object.assign(body, {
        title: $("eTitle").value.trim(),
        description: $("eDesc").value.trim(),
        make: $("eMake").value.trim(),
        price: Number($("ePrice").value) || 0,
        mileage: Number($("eMileage").value) || 0,
        color: $("eColor").value.trim(),
      });
    }
    await api("/api/scanner/inventory/" + editSlug, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    closeEdit();
    load();
  } catch (err) {
    alert("No se pudo guardar: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Guardar cambios";
  }
});
