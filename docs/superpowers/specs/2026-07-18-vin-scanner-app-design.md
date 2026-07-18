# VIN Scanner App — Diseño

**Fecha:** 2026-07-18 · **Aprobado por:** Alejo · **Arquitectura:** Opción A (PWA + backend NEXUS)

## Qué es

PWA instalable en el iPhone de Alejo para crear listings de Facebook Marketplace desde el lote: foto del VIN → ficha técnica automática → foto del odómetro → millaje automático → precio manual → fotos y video del carro → copy bilingüe (EN + ES) listo para pegar, y todo guardado como inventario NEXUS con opción de publicar después vía `marketplace_poster`.

## Decisiones cerradas

- **Plataforma:** PWA (manifest + ícono home screen), no app nativa. Cámara vía `<input capture>` / getUserMedia.
- **Destino del copy:** ambas cosas — copiar/pegar inmediato Y guardar en inventario NEXUS.
- **Video:** parte del listing (Marketplace ya acepta video) y reutilizable por Shot para contenido.
- **Millaje:** foto del odómetro leída por IA, editable antes de confirmar. Precio: campo manual.
- **Idioma del copy:** bilingüe, inglés primero y español después, en el mismo listing.
- **Identidad visual:** rojo Toyota `#EB0A1E`, Anton/Bebas Neue/Inter. Todo lo visual lo ejecuta Shot (regla absoluta).
- **Acceso:** solo Alejo — login simple (token/clave fija en .env).

## Arquitectura

```
PWA (celular) ──HTTPS──> backend nexus-automation (Flask, mismo servicio actual)
                              ├─ POST /api/vin       foto VIN → Claude vision (OCR) → check digit → NHTSA vPIC (gratis) → ficha
                              ├─ POST /api/odometer  foto tablero → Claude vision → millaje
                              ├─ POST /api/listing   ficha+millaje+precio+notas → copy bilingüe (voz Ink)
                              └─ POST /api/inventory guarda carro completo
                                        └─ inventario/<año-modelo-VIN>/  fotos/, video, listing.json, copy.md
```

- `listing.json` usa el formato que `marketplace_poster` ya consume, para conectar la publicación después sin migrar datos.
- **La integración con el bot de Marketplace queda fuera de v1** (decisión Alejo 2026-07-18): el bot vive en el MacBook Pro y se retoma luego. V1 solo guarda inventario compatible.
- Modelo IA: Haiku para OCR de VIN/odómetro (barato), Sonnet para el copy.

## Flujo de la PWA (4 pasos)

1. **VIN** — cámara, captura, muestra ficha decodificada para confirmar.
2. **Odómetro** — cámara, muestra millaje leído, editable. Campo de precio + notas opcionales (un solo dueño, llantas nuevas…).
3. **Fotos/Video** — multi-captura, miniaturas reordenables, un video opcional.
4. **Copy** — título (≤100 chars), descripción EN/ES, botón **Copiar**, botón **Guardar en NEXUS**.

## Manejo de errores

- VIN ilegible o check digit inválido → pedir recaptura o digitación manual (17 chars, validados).
- NHTSA sin datos → seguir con lo que Claude extraiga + campos editables.
- Sin señal en el lote → la PWA retiene las fotos en memoria y reintenta el envío; no se pierde la sesión de captura.

## Ejecución con equipo NEXUS (optimización de tokens)

| Tarea | Responsable |
|---|---|
| Endpoints backend + guardado inventario | **wire** (subagente Sonnet) |
| UI de la PWA (flujo 4 pasos, PWA manifest) | **shot** dirige lo visual; frontend con flujo Magic/ui-ux-pro-max |
| Prompt del copy bilingüe (voz, estructura, hooks) | **ink** (subagente Sonnet) |
| Coordinación y revisión | Claude principal (mínimo token) |

## Testing

- Unit: validador de check digit del VIN; parser de respuesta NHTSA.
- Manual E2E: Alejo prueba con un carro real del lote (VIN + odómetro reales) antes de dar por terminado.

## Fuera de alcance (v1)

- Toda integración con `marketplace_poster` (cola y publicación — se retoma luego en el MacBook Pro), multiusuario, app nativa, extracción de frames del video.
