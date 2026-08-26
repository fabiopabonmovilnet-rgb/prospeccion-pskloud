from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from config import settings
from models import Classification

logger = logging.getLogger("openclaw.aprendizaje")

MEMORIA_FILE = os.path.join(settings.data_dir, "aprendizaje.json")
MAX_ENTRIES = 150


def _load() -> list[dict]:
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def _save(data: list[dict]):
    try:
        os.makedirs(os.path.dirname(MEMORIA_FILE), exist_ok=True)
        with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _resultado(clasificacion: Classification) -> str:
    if clasificacion in (Classification.INTERESADO, Classification.HANDOFF):
        return "cerrado_con_interes"
    if clasificacion == Classification.YA_TIENE_SISTEMA:
        return "opciones_enviadas"
    if clasificacion == Classification.NO_INTERESADO:
        return "cerrado_sin_interes"
    if clasificacion == Classification.CONTACTO_EQUIVOCADO:
        return "contacto_equivocado_excluido"
    return "continua"


def registrar_caso(phone: str, lead_msg: str, bot_reply: str, clasificacion: Classification):
    """Guardar una experiencia para que el agente aprenda de ella."""
    casos = _load()
    casos.append(
        {
            "fecha": datetime.now().isoformat(),
            "lead_msg": (lead_msg or "")[:280],
            "bot_reply": (bot_reply or "")[:280],
            "categoria": clasificacion.value,
            "resultado": _resultado(clasificacion),
        }
    )
    _save(casos[-MAX_ENTRIES:])


def obtener_lecciones(limit: int = 8) -> str:
    """Resumen breve de experiencias recientes para guiar a Gemini (sin costo)."""
    casos = _load()[-limit:]
    if not casos:
        return ""
    lines = ["Experiencias recientes que debes usar para mejorar tus respuestas:"]
    for c in casos:
        lines.append(
            f"- Lead dijo: {c['lead_msg']!r} | Respondimos: {c['bot_reply']!r} | Resultado: {c['resultado']}"
        )
    return "\n".join(lines)
