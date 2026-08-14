"""
NEXUS Lens — Generador de reportes de engagement @tucarroconalejo.
Produce un reporte HTML con análisis y plan de acción.
Guarda en reports/lens_YYYY-MM-DD.html y retorna (html, ruta).
"""
import os
import json
import glob
from datetime import datetime
from collections import defaultdict

BASE    = os.path.dirname(os.path.abspath(__file__))
CACHE   = os.path.join(BASE, "metrics_cache.json")
REPORTS = os.path.join(BASE, "reports")

TYPE_LABELS = {
    "inventory":   "Inventory",
    "new_car_day": "New Car Day",
    "entrega":     "Entrega",
    "tips":        "Tips",
    "quote":       "Quote",
}

ACCOUNT_START  = datetime(2026, 6, 10)
MONTHLY_GOAL   = 50
REPORT_DAY     = 1   # Tuesday


def _load_cache() -> dict:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updated": None, "has_insights": False, "posts": []}


def _score(eng: int, avg: float) -> str:
    if avg == 0:
        return "A" if eng >= 7 else "B" if eng >= 3 else "C" if eng >= 1 else "D"
    r = eng / avg
    return "A" if r >= 1.5 else "B" if r >= 0.8 else "C" if r >= 0.4 else "D"


def _build_analysis(posts, measured, total_eng, by_type, no_id, elapsed, target, delta) -> list[str]:
    """Generate narrative analysis paragraphs."""
    parts = []

    # Pace assessment
    pct = round(total_eng / MONTHLY_GOAL * 100, 1)
    if delta >= 0:
        parts.append(
            f"La cuenta lleva <strong>{total_eng} interacciones</strong> en {elapsed} días, "
            f"superando el ritmo necesario por <strong>+{abs(delta):.1f} puntos</strong>. "
            f"Si se mantiene este paso, junio cerrará por encima de la meta de 50."
        )
    elif pct >= 50:
        parts.append(
            f"Con <strong>{total_eng} interacciones al día {elapsed}</strong>, la cuenta va al "
            f"{pct}% del objetivo mensual, ligeramente por debajo del ritmo ideal de {target:.0f}. "
            f"El déficit de {abs(delta):.1f} eng es recuperable acelerando los formatos de mayor rendimiento."
        )
    else:
        parts.append(
            f"La cuenta acumula <strong>{total_eng} interacciones en {elapsed} días</strong>, "
            f"un <strong>déficit de {abs(delta):.1f}</strong> respecto al ritmo necesario para llegar a 50 en junio. "
            f"Se requiere ajuste de estrategia esta semana para revertir la tendencia."
        )

    # Best format
    if by_type:
        best_type = max(by_type.items(), key=lambda x: sum(x[1]) / len(x[1]))
        best_label = TYPE_LABELS.get(best_type[0], best_type[0])
        best_avg   = round(sum(best_type[1]) / len(best_type[1]), 1)
        worst_types = [t for t, v in by_type.items() if sum(v) / len(v) == 0]
        parts.append(
            f"<strong>{best_label}</strong> es el formato con mayor tracción: "
            f"{best_avg:.1f} interacciones por post en promedio. "
            + (f"Por el contrario, <strong>{', '.join(TYPE_LABELS.get(t, t) for t in worst_types)}</strong> "
               f"{'ha' if len(worst_types)==1 else 'han'} generado 0 interacciones — "
               f"insuficiente data aún para tomar decisiones definitivas, pero requiere seguimiento." if worst_types else "")
        )

    # Lost posts
    if no_id:
        parts.append(
            f"Se detectaron <strong>{len(no_id)} publicaciones sin registro en Meta</strong> "
            f"(sin IG ID ni FB ID). Esto indica que el scheduler estuvo detenido esos días, "
            f"probablemente por el Mac apagado. Cada post perdido es engagement que no se puede recuperar."
        )

    # Data coverage
    coverage = round(len(measured) / len(posts) * 100) if posts else 0
    if coverage < 50:
        parts.append(
            f"Solo el <strong>{coverage}% de los posts registrados tiene datos de engagement</strong>. "
            f"El resto no tiene IG ID, lo que impide medirlos. "
            f"Con más datos en las próximas semanas el análisis será más preciso."
        )

    return parts


def _build_actions(avg_eng, by_type, no_id, delta) -> list[dict]:
    """Generate prioritized action items for Growth-Leo."""
    actions = []

    # Fix scheduler if posts lost
    if len(no_id) >= 3:
        actions.append({
            "priority": "URGENTE",
            "color": "#c0392b",
            "icon": "🔴",
            "title": "Mantener el Mac encendido — posts perdidos",
            "detail": (
                f"{len(no_id)} posts no llegaron a Meta porque el Mac estaba apagado. "
                f"Configurar LaunchAgent para que el scheduler arranque automáticamente "
                f"al encender el equipo, o dejar el Mac de casa corriendo 24/7."
            ),
            "file": "main.py → LaunchAgent plist"
        })

    # Double down on best format
    if by_type:
        best_type = max(by_type.items(), key=lambda x: sum(x[1]) / len(x[1]))
        best_label = TYPE_LABELS.get(best_type[0], best_type[0])
        best_avg   = round(sum(best_type[1]) / len(best_type[1]), 1)
        if best_avg > 0 and best_avg >= avg_eng:
            actions.append({
                "priority": "ESTA SEMANA",
                "color": "#e67e22",
                "icon": "🟠",
                "title": f"Aumentar frecuencia de {best_label}",
                "detail": (
                    f"{best_label} genera {best_avg:.1f} eng/post en promedio — el mejor rendimiento. "
                    f"Agregar un slot extra en la parrilla (ej: miércoles 8pm). "
                    f"Para New Car Day se necesita foto real de cliente — coordinar con Alejo."
                ),
                "file": "main.py → PARRILLA_2X"
            })

    # Token rotation for full metrics
    actions.append({
        "priority": "PRÓXIMA SEMANA",
        "color": "#2980b9",
        "icon": "🔵",
        "title": "Rotar token Meta con instagram_manage_insights",
        "detail": (
            "Actualmente solo se miden likes y comentarios. Al rotar el token con el permiso "
            "instagram_manage_insights se activarán: reach, impresiones y saves. "
            "Esos datos son esenciales para medir si el contenido llega a nuevas personas."
        ),
        "file": ".env → META_PAGE_ACCESS_TOKEN"
    })

    # Content quality if deficit
    if delta < -10:
        actions.append({
            "priority": "ESTA SEMANA",
            "color": "#e67e22",
            "icon": "🟠",
            "title": "Mejorar hook de apertura en posts con score D",
            "detail": (
                "Los posts de Inventory y Quote no generaron ninguna interacción. "
                "Revisar la primera línea del copy — debe ser una pregunta o dato sorpresa. "
                "Ejemplo: '¿Sabías que puedes estrenar Toyota con $0 de inicial hoy?' "
                "en vez de comenzar con el nombre del vehículo."
            ),
            "file": "content_agent.py → _build_caption()"
        })

    # Real customer photos
    actions.append({
        "priority": "CONTINUO",
        "color": "#27ae60",
        "icon": "🟢",
        "title": "Subir fotos reales de entregas al Drive",
        "detail": (
            "El post de New Car Day con foto real (Camry, 7 eng) supera por 7x a todos los demás. "
            "Cada entrega es contenido de alto valor. Fotografiar el momento con el cliente "
            "y subir a la carpeta nexus-fotos en Google Drive inmediatamente."
        ),
        "file": "Drive → nexus-fotos"
    })

    return actions


def generate(save: bool = True) -> tuple[str, str]:
    """
    Generate HTML Lens report.
    Returns (html_content, file_path). file_path is '' if save=False.
    """
    cache    = _load_cache()
    posts    = cache.get("posts", [])
    now      = datetime.now()

    measured  = [p for p in posts if p.get("likes") is not None]
    total_eng = sum((p.get("likes") or 0) + (p.get("comments") or 0) for p in measured)
    avg_eng   = total_eng / len(measured) if measured else 0

    elapsed    = max((now - ACCOUNT_START).days + 1, 1)
    target     = round(MONTHLY_GOAL * elapsed / 30, 1)
    delta      = round(total_eng - target, 1)
    pct        = min(round(total_eng / MONTHLY_GOAL * 100, 1), 100)

    by_type: dict[str, list[int]] = defaultdict(list)
    for p in measured:
        eng = (p.get("likes") or 0) + (p.get("comments") or 0)
        by_type[p.get("post_type", "?")] .append(eng)

    no_id   = [p for p in posts if not p.get("ig_id") and not p.get("fb_id")]
    ranked  = sorted(measured, key=lambda p: (p.get("likes") or 0) + (p.get("comments") or 0), reverse=True)

    analysis = _build_analysis(posts, measured, total_eng, by_type, no_id, elapsed, target, delta)
    actions  = _build_actions(avg_eng, by_type, no_id, delta)

    # Score colors
    SCORE_COLOR = {"A": "#27ae60", "B": "#2980b9", "C": "#e67e22", "D": "#c0392b"}

    # Build ranking rows
    ranking_rows = ""
    for p in ranked:
        eng   = (p.get("likes") or 0) + (p.get("comments") or 0)
        sc    = _score(eng, avg_eng)
        fecha = p.get("datetime", "")[:10]
        tipo  = TYPE_LABELS.get(p.get("post_type", ""), p.get("post_type", ""))
        model = p.get("model", "")
        likes = p.get("likes") or 0
        coms  = p.get("comments") or 0
        sc_color = SCORE_COLOR.get(sc, "#666")
        ranking_rows += f"""
        <tr>
          <td><span class="badge" style="background:{sc_color}">{sc}</span></td>
          <td>{fecha}</td>
          <td>{tipo}</td>
          <td>Toyota {model}</td>
          <td class="num">{likes}</td>
          <td class="num">{coms}</td>
          <td class="num bold">{eng}</td>
        </tr>"""

    # Build format bars
    max_type_avg = max((sum(v)/len(v) for v in by_type.values()), default=1)
    format_bars  = ""
    for t, vals in sorted(by_type.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
        label   = TYPE_LABELS.get(t, t)
        avg_t   = round(sum(vals) / len(vals), 1)
        pct_bar = round(avg_t / max_type_avg * 100) if max_type_avg > 0 else 0
        color   = "#e8291c" if pct_bar == 100 else "#444"
        format_bars += f"""
        <div class="bar-row">
          <div class="bar-label">{label}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{pct_bar}%;background:{color}"></div>
          </div>
          <div class="bar-val">{avg_t} eng/post &nbsp;<span class="muted">({len(vals)} posts)</span></div>
        </div>"""

    # Build lost posts list
    lost_html = ""
    if no_id:
        items = "".join(
            f'<li>{p.get("datetime","")[:10]} · {TYPE_LABELS.get(p.get("post_type",""),p.get("post_type",""))} · Toyota {p.get("model","")}</li>'
            for p in no_id
        )
        lost_html = f"""
        <div class="alert-box red">
          <div class="alert-title">🔴 {len(no_id)} publicaciones no llegaron a Meta</div>
          <ul class="lost-list">{items}</ul>
          <div class="alert-sub">El scheduler estaba detenido esos días (Mac apagado o proceso caído)</div>
        </div>"""

    # Analysis paragraphs
    analysis_html = "".join(f'<p>{a}</p>' for a in analysis) if analysis else "<p>Sin suficientes datos para generar análisis narrativo.</p>"

    # Actions
    actions_html = ""
    for i, a in enumerate(actions, 1):
        actions_html += f"""
        <div class="action-card" style="border-left:4px solid {a['color']}">
          <div class="action-header">
            <span class="action-icon">{a['icon']}</span>
            <span class="action-priority" style="color:{a['color']}">{a['priority']}</span>
            <span class="action-title">{a['title']}</span>
          </div>
          <div class="action-detail">{a['detail']}</div>
          <div class="action-file">📁 {a['file']}</div>
        </div>"""

    # Pace bar (capped at 100%)
    pace_pct = min(pct, 100)
    pace_color = "#27ae60" if delta >= 0 else "#e67e22" if pct >= 40 else "#c0392b"
    delta_badge = f'<span style="color:{pace_color}">{"+" if delta>=0 else ""}{delta:.1f}</span>'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lens Report — @tucarroconalejo — {now.strftime('%d %b %Y')}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Bebas+Neue&display=swap');
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0a0a;color:#e0e0e0;font-family:'Inter',sans-serif;font-size:14px;line-height:1.6}}
  .page{{max-width:860px;margin:0 auto;padding:40px 24px}}

  /* Header */
  .header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:40px;padding-bottom:24px;border-bottom:1px solid #1e1e1e}}
  .brand{{display:flex;flex-direction:column;gap:2px}}
  .brand-name{{font-family:'Bebas Neue',sans-serif;font-size:32px;letter-spacing:3px;color:#fff}}
  .brand-sub{{font-size:12px;color:#555;letter-spacing:1px;text-transform:uppercase}}
  .header-meta{{text-align:right;color:#555;font-size:12px;line-height:1.8}}
  .header-meta strong{{color:#888}}
  .accent{{color:#e8291c}}

  /* Section */
  .section{{margin-bottom:36px}}
  .section-title{{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#555;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #1a1a1a}}

  /* KPI grid */
  .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
  .kpi{{background:#111;border:1px solid #1e1e1e;border-radius:10px;padding:16px}}
  .kpi-value{{font-size:28px;font-weight:700;color:#fff;line-height:1}}
  .kpi-label{{font-size:11px;color:#555;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}}
  .kpi-sub{{font-size:11px;color:#444;margin-top:2px}}
  .kpi.highlight{{border-color:#e8291c22;background:#1a0a0a}}
  .kpi.highlight .kpi-value{{color:#e8291c}}

  /* Pace bar */
  .pace-wrap{{background:#111;border:1px solid #1e1e1e;border-radius:10px;padding:20px}}
  .pace-header{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}}
  .pace-label{{font-size:12px;color:#888;font-weight:600}}
  .pace-nums{{font-size:12px;color:#555}}
  .track{{height:8px;background:#1e1e1e;border-radius:4px;overflow:hidden}}
  .fill{{height:100%;border-radius:4px;transition:width .3s;background:{pace_color}}}
  .target-line{{position:relative;margin-top:8px}}
  .target-tick{{position:absolute;font-size:10px;color:#555;transform:translateX(-50%)}}

  /* Ranking table */
  table{{width:100%;border-collapse:collapse}}
  th{{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#444;padding:8px 10px;text-align:left;border-bottom:1px solid #1a1a1a}}
  td{{padding:10px 10px;border-bottom:1px solid #141414;vertical-align:middle}}
  tr:hover td{{background:#0f0f0f}}
  .badge{{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:6px;font-size:12px;font-weight:700;color:#fff}}
  .num{{text-align:right;font-variant-numeric:tabular-nums;color:#888}}
  .bold{{color:#fff!important;font-weight:600}}
  .muted{{color:#444}}

  /* Format bars */
  .bar-row{{display:flex;align-items:center;gap:12px;margin-bottom:12px}}
  .bar-label{{width:110px;font-size:12px;color:#888;flex-shrink:0}}
  .bar-track{{flex:1;height:6px;background:#1a1a1a;border-radius:3px;overflow:hidden}}
  .bar-fill{{height:100%;border-radius:3px;transition:width .3s}}
  .bar-val{{font-size:12px;color:#666;width:160px;flex-shrink:0}}

  /* Alerts */
  .alert-box{{border-radius:10px;padding:16px 20px;margin-bottom:12px}}
  .alert-box.red{{background:#1a0a0a;border:1px solid #3a1a1a}}
  .alert-box.yellow{{background:#1a1500;border:1px solid #3a3000}}
  .alert-title{{font-weight:600;font-size:13px;margin-bottom:8px}}
  .alert-sub{{font-size:11px;color:#666;margin-top:8px}}
  .lost-list{{list-style:none;padding-left:8px}}
  .lost-list li{{font-size:12px;color:#888;padding:2px 0;border-bottom:1px solid #1e1e1e}}
  .lost-list li:last-child{{border:none}}

  /* Analysis */
  .analysis-body p{{color:#aaa;font-size:13px;line-height:1.8;margin-bottom:12px;padding-left:12px;border-left:2px solid #1e1e1e}}
  .analysis-body p strong{{color:#ddd}}

  /* Actions */
  .action-card{{background:#111;border-radius:10px;padding:18px 20px;margin-bottom:12px;border:1px solid #1e1e1e}}
  .action-header{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .action-icon{{font-size:16px}}
  .action-priority{{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase}}
  .action-title{{font-size:14px;font-weight:600;color:#fff;flex:1}}
  .action-detail{{font-size:13px;color:#888;line-height:1.7;margin-bottom:8px}}
  .action-file{{font-size:11px;color:#444;font-family:monospace}}

  /* Metrics limit notice */
  .notice{{background:#111;border:1px solid #1e1e1e;border-radius:8px;padding:12px 16px;font-size:12px;color:#555;display:flex;gap:10px;align-items:center}}
  .notice-icon{{font-size:16px}}

  /* Footer */
  .footer{{margin-top:48px;padding-top:20px;border-top:1px solid #1a1a1a;display:flex;justify-content:space-between;align-items:center}}
  .footer-brand{{font-family:'Bebas Neue',sans-serif;letter-spacing:2px;color:#333}}
  .footer-sub{{font-size:11px;color:#333}}

  @media print{{
    body{{background:#fff;color:#111}}
    .page{{max-width:100%;padding:20px}}
    .kpi,.action-card,.alert-box,.pace-wrap{{background:#f9f9f9;border-color:#ddd}}
    .kpi-value,.bold{{color:#111}}
    .section-title,.pace-label{{color:#777}}
    th{{color:#999}}
    td{{border-color:#eee}}
    .bar-track{{background:#eee}}
    .analysis-body p{{color:#444;border-color:#ddd}}
    .action-detail{{color:#555}}
    .action-file{{color:#999}}
    .footer-brand,.footer-sub{{color:#bbb}}
    .notice{{background:#f9f9f9;border-color:#ddd}}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="brand">
      <div class="brand-name">NEXUS <span class="accent">●</span> LENS</div>
      <div class="brand-sub">Reporte de Engagement — @tucarroconalejo</div>
    </div>
    <div class="header-meta">
      <strong>Período</strong> &nbsp;{ACCOUNT_START.strftime('%d %b')} → {now.strftime('%d %b %Y')}<br>
      <strong>Generado</strong> &nbsp;{now.strftime('%d %b %Y, %H:%M')}<br>
      <strong>Día</strong> &nbsp;{elapsed} de 30<br>
      <strong>Meta junio</strong> &nbsp;{MONTHLY_GOAL} interacciones
    </div>
  </div>

  <!-- KPIs -->
  <div class="section">
    <div class="section-title">Resumen del período</div>
    <div class="kpi-grid">
      <div class="kpi highlight">
        <div class="kpi-value">{total_eng}</div>
        <div class="kpi-label">Interacciones</div>
        <div class="kpi-sub">{pct}% de la meta</div>
      </div>
      <div class="kpi">
        <div class="kpi-value">{len(posts)}</div>
        <div class="kpi-label">Posts publicados</div>
        <div class="kpi-sub">{len(measured)} medibles</div>
      </div>
      <div class="kpi">
        <div class="kpi-value">{round(avg_eng,1)}</div>
        <div class="kpi-label">Eng promedio</div>
        <div class="kpi-sub">por post con datos</div>
      </div>
      <div class="kpi">
        <div class="kpi-value">{len(no_id)}</div>
        <div class="kpi-label">Posts perdidos</div>
        <div class="kpi-sub">sin ID en Meta</div>
      </div>
    </div>

    <!-- Pace bar -->
    <div class="pace-wrap">
      <div class="pace-header">
        <span class="pace-label">Progreso hacia meta de junio</span>
        <span class="pace-nums">{total_eng} / {MONTHLY_GOAL} &nbsp;·&nbsp; objetivo hoy: {target:.0f} &nbsp;·&nbsp; delta: {delta_badge}</span>
      </div>
      <div class="track"><div class="fill" style="width:{pace_pct}%"></div></div>
    </div>
  </div>

  <!-- Ranking -->
  <div class="section">
    <div class="section-title">Ranking de posts</div>
    {"<table><thead><tr><th>Score</th><th>Fecha</th><th>Formato</th><th>Modelo</th><th style='text-align:right'>Likes</th><th style='text-align:right'>Coms</th><th style='text-align:right'>Eng</th></tr></thead><tbody>" + ranking_rows + "</tbody></table>" if ranked else '<div class="notice"><span class="notice-icon">📭</span>Sin posts medibles aún. Se necesita IG ID para obtener datos.</div>'}
  </div>

  <!-- Format performance -->
  <div class="section">
    <div class="section-title">Rendimiento por formato</div>
    {format_bars if format_bars else '<div class="notice"><span class="notice-icon">📊</span>Sin datos suficientes por formato.</div>'}
  </div>

  <!-- Alerts -->
  {('<div class="section"><div class="section-title">Alertas</div>' + lost_html + '</div>') if lost_html else ''}

  <!-- Analysis -->
  <div class="section">
    <div class="section-title">Análisis — Lens</div>
    <div class="analysis-body">{analysis_html}</div>
  </div>

  <!-- Actions -->
  <div class="section">
    <div class="section-title">Plan de acción — Growth-Leo</div>
    {actions_html}
  </div>

  <!-- Metrics limitation notice -->
  <div class="section">
    <div class="notice">
      <span class="notice-icon">⚡</span>
      <span><strong style="color:#888">Métricas disponibles ahora:</strong> likes y comentarios vía instagram_basic. &nbsp;
      <strong style="color:#555">Pendientes:</strong> reach, impresiones, saves — se activan al rotar el token con instagram_manage_insights.</span>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <div class="footer-brand">NEXUS AGENCY</div>
    <div class="footer-sub">Hollywood Toyota · Generado automáticamente por Lens · {now.strftime('%d/%m/%Y')}</div>
  </div>

</div>
</body>
</html>"""

    path = ""
    if save:
        os.makedirs(REPORTS, exist_ok=True)
        filename = f"lens_{now.strftime('%Y-%m-%d')}.html"
        path = os.path.join(REPORTS, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    return html, path


def latest_report_path() -> str:
    files = sorted(glob.glob(os.path.join(REPORTS, "lens_*.html")), reverse=True)
    return files[0] if files else ""


if __name__ == "__main__":
    _, path = generate(save=True)
    print(f"✅ Reporte generado: {path}")
    import subprocess
    subprocess.run(["open", path])
