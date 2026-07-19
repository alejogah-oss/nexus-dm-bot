/* NEXUS Admin — admin.js
   Panel /admin: lista inventario del scanner, badges de estado,
   edita los no publicados y dispara publicación a Marketplace de uno a la vez.
   El bot NUNCA publica solo — el botón solo llena el formulario en el Mac Pro,
   Alejo da clic en Publicar y luego marca como publicado aquí. */
"use strict";

const $ = (id) => document.getElementById(id);

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
    renderCars(res.items || [], res.publishing);
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
  if (item.published) {
    return { cls: "published", label: "🟢 Publicado " + (item.published_at || "") };
  }
  if (item.last_error) {
    return { cls: "failed", label: "🔴 Falló: " + item.last_error };
  }
  return { cls: "pending", label: "🟡 Sin publicar" };
}

function renderCars(items, publishing) {
  const cars = $("cars");
  cars.innerHTML = "";
  if (!items.length) {
    cars.innerHTML = '<p class="hint">No hay carros guardados todavía.</p>';
    return;
  }
  items.forEach((item) => cars.appendChild(buildCarCard(item, publishing)));
}

function buildCarCard(item, publishing) {
  const card = document.createElement("div");
  card.className = "car-card";
  card.dataset.slug = item.slug;

  const badge = statusBadge(item);
  const badgeEl = document.createElement("span");
  badgeEl.className = "badge " + badge.cls;
  badgeEl.textContent = badge.label;
  card.appendChild(badgeEl);

  const photo = document.createElement("div");
  photo.className = "car-photo";
  const img = document.createElement("img");
  img.src = "/api/scanner/inventory/" + item.slug + "/photo/1?key=" + encodeURIComponent(getKey());
  img.alt = "";
  photo.appendChild(img);
  card.appendChild(photo);

  const info = document.createElement("div");
  info.className = "car-info";

  const title = document.createElement("p");
  title.className = "car-title";
  title.textContent = [item.yr, item.make, item.model].filter(Boolean).join(" ") || item.title || item.slug;
  info.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "car-meta";
  meta.textContent = "$" + (item.price || 0).toLocaleString() + " · " +
    (item.mileage || 0).toLocaleString() + " mi";
  info.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "car-actions";

  if (!item.published) {
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "ghost";
    editBtn.textContent = "Editar";
    editBtn.addEventListener("click", () => openEdit(item.slug));
    actions.appendChild(editBtn);

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

  info.appendChild(actions);
  card.appendChild(info);
  return card;
}

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
    $("eTitle").value = d.title || "";
    $("eDesc").value = d.description || "";
    $("eMake").value = d.make || "";
    $("ePrice").value = d.price || "";
    $("eMileage").value = d.mileage || "";
    $("eColor").value = d.color || "";
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

$("eSaveBtn").addEventListener("click", async () => {
  if (!editSlug) return;
  const btn = $("eSaveBtn");
  btn.disabled = true;
  btn.textContent = "Guardando…";
  try {
    await api("/api/scanner/inventory/" + editSlug, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: $("eTitle").value.trim(),
        description: $("eDesc").value.trim(),
        make: $("eMake").value.trim(),
        price: Number($("ePrice").value) || 0,
        mileage: Number($("eMileage").value) || 0,
        color: $("eColor").value.trim(),
      }),
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
