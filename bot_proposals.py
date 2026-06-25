"""
NEXUS Bot Proposals — Sistema de aprobación de mejoras.
- Pulse/Wire crean propuestas con estado: pending
- Alejo recibe WhatsApp con resumen + link de aprobación
- Aprobación vía GET /bot/proposals/approve/<id>
- Rechazo vía GET /bot/proposals/reject/<id>
- Solo cuando status=approved se registra en bot_improvements.md
"""
import json
import os
from datetime import datetime

PROPOSALS_FILE = os.path.join(os.path.dirname(__file__), "bot_proposals.json")


def _load() -> dict:
    try:
        with open(PROPOSALS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_proposal(area: str, cambio: str, motivo: str, autor: str = "Pulse") -> str:
    """
    Crea una propuesta de mejora y notifica a Alejo por WhatsApp.
    Retorna el proposal_id.
    """
    import uuid
    from pulse import pulse_notify

    data = _load()
    pid = uuid.uuid4().hex[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    data[pid] = {
        "id": pid,
        "area": area,
        "cambio": cambio,
        "motivo": motivo,
        "autor": autor,
        "status": "pending",
        "created_at": now,
        "resolved_at": None,
    }
    _save(data)

    approve_url = f"https://bot.tucarroconalejo.com/bot/proposals/approve/{pid}"
    reject_url  = f"https://bot.tucarroconalejo.com/bot/proposals/reject/{pid}"

    pulse_notify(
        event="HOT_LEAD",
        detail=(
            f"🔧 MEJORA PROPUESTA — {autor}\n"
            f"Área: {area}\n"
            f"Cambio: {cambio}\n"
            f"Motivo: {motivo}\n\n"
            f"✅ Aprobar:\n{approve_url}\n\n"
            f"❌ Rechazar:\n{reject_url}"
        )
    )

    print(f"[PROPOSALS] Nueva propuesta {pid} | {area} | {autor}")
    return pid


def approve_proposal(pid: str) -> dict:
    """Marca la propuesta como aprobada y la registra en bot_improvements.md."""
    data = _load()
    if pid not in data:
        return {"error": "Propuesta no encontrada"}

    proposal = data[pid]
    if proposal["status"] != "pending":
        return {"error": f"Propuesta ya está en estado: {proposal['status']}"}

    proposal["status"] = "approved"
    proposal["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save(data)

    _log_to_improvements(proposal)
    print(f"[PROPOSALS] ✅ Aprobada — {pid} | {proposal['area']}")
    return {"ok": True, "proposal": proposal}


def reject_proposal(pid: str) -> dict:
    """Marca la propuesta como rechazada."""
    data = _load()
    if pid not in data:
        return {"error": "Propuesta no encontrada"}

    proposal = data[pid]
    if proposal["status"] != "pending":
        return {"error": f"Propuesta ya está en estado: {proposal['status']}"}

    proposal["status"] = "rejected"
    proposal["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save(data)

    print(f"[PROPOSALS] ❌ Rechazada — {pid} | {proposal['area']}")
    return {"ok": True, "proposal": proposal}


def get_pending() -> list:
    """Retorna lista de propuestas pendientes."""
    data = _load()
    return [p for p in data.values() if p["status"] == "pending"]


def _log_to_improvements(proposal: dict):
    """Agrega la propuesta aprobada al log semanal bot_improvements.md."""
    log_path = os.path.join(os.path.dirname(__file__), "bot_improvements.md")
    week = datetime.now().strftime("%Y-%m-%d")
    line = (
        f"| — | {proposal['area']} | {proposal['cambio']} "
        f"| {proposal['motivo']} _(aprobado {proposal['resolved_at']})_ |\n"
    )
    try:
        with open(log_path, encoding="utf-8") as f:
            content = f.read()

        week_header = f"## Semana del {week}"
        if week_header in content:
            content = content.replace(
                "### Cambios implementados\n\n| # | Área | Cambio | Motivo |\n|---|------|--------|--------|\n",
                f"### Cambios implementados\n\n| # | Área | Cambio | Motivo |\n|---|------|--------|--------|\n{line}",
                1,
            )
        else:
            content += (
                f"\n---\n\n{week_header}\n\n"
                f"### Cambios implementados\n\n"
                f"| # | Área | Cambio | Motivo |\n|---|------|--------|--------|\n"
                f"{line}"
            )

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"[PROPOSALS] No se pudo escribir en improvements log: {e}")
