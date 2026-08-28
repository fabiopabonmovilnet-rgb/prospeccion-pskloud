from __future__ import annotations

import json, os, uuid
from datetime import datetime
from typing import List, Optional

from models import Client, WhatsAppChannel, EmailChannel, InstagramChannel, MessageTemplateSet, TemplateMessage

DATA_DIR = "/app/data"
CLIENTS_FILE = os.path.join(DATA_DIR, "clientes.json")
TEMPLATES_FILE = os.path.join(DATA_DIR, "plantillas.json")


def _load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _migrate_client_data(data: dict) -> dict:
    """Convert flat dashboard format to nested Pydantic format if needed."""
    if "whatsapp" in data or "email" in data or "instagram" in data:
        return data  # Already nested
    return {
        "id": data.get("id", ""),
        "name": data.get("name", ""),
        "rubros": data.get("rubros", []),
        "ubicaciones": data.get("ubicaciones", []),
        "whatsapp": {
            "enabled": data.get("whatsapp_enabled", True),
            "max_daily": data.get("whatsapp_max_daily", 20),
            "min_delay_seconds": 60,
            "max_delay_seconds": 120,
            "typing_delay_min_ms": 3000,
            "typing_delay_max_ms": 5000,
            "hour_start": data.get("whatsapp_hour_start", 9),
            "hour_end": data.get("whatsapp_hour_end", 16),
            "work_days": [0, 1, 2, 3, 4],
            "evolution_api_url": data.get("whatsapp_api_url", ""),
            "evolution_api_key": data.get("whatsapp_api_key", ""),
            "evolution_instance": data.get("whatsapp_instance", ""),
        },
        "email": {
            "enabled": data.get("email_enabled", False),
            "max_daily": data.get("email_max_daily", 50),
            "min_delay_seconds": 120,
            "max_delay_seconds": 300,
            "typing_delay_min_ms": 3000,
            "typing_delay_max_ms": 5000,
            "hour_start": 9,
            "hour_end": 17,
            "work_days": [0, 1, 2, 3, 4],
            "smtp_host": data.get("email_smtp_host", ""),
            "smtp_port": data.get("email_smtp_port", 587),
            "smtp_user": data.get("email_smtp_user", ""),
            "smtp_password": data.get("email_smtp_password", ""),
            "from_name": data.get("email_from_name", ""),
            "from_email": data.get("email_from_email", ""),
        },
        "instagram": {
            "enabled": data.get("instagram_enabled", False),
            "max_daily": data.get("instagram_max_daily", 3),
            "min_delay_seconds": 180,
            "max_delay_seconds": 300,
            "typing_delay_min_ms": 3000,
            "typing_delay_max_ms": 5000,
            "hour_start": 9,
            "hour_end": 17,
            "work_days": [0, 1, 2, 3, 4, 5, 6],
            "instagram_username": data.get("instagram_username", ""),
            "instagram_password": data.get("instagram_password", ""),
            "ig_proxy": data.get("ig_proxy", ""),
            "ig_hashtags": data.get("ig_hashtags", ["boutique", "moda", "shopping", "accesorios"]),
            "ig_wa_phone": data.get("ig_wa_phone", ""),
        },
        "created_at": data.get("created_at", datetime.now().isoformat()),
    }


def list_clients() -> list[Client]:
    return [Client(**_migrate_client_data(c)) for c in _load_json(CLIENTS_FILE)]


def get_client(client_id: str) -> Optional[Client]:
    for c in list_clients():
        if c.id == client_id:
            return c
    return None


def save_client(client: Client):
    clients = _load_json(CLIENTS_FILE)
    if not client.id:
        client.id = str(uuid.uuid4())[:8]
    idx = next((i for i, c in enumerate(clients) if c.get("id") == client.id), None)
    data = client.model_dump(mode="json")
    if idx is not None:
        clients[idx] = data
    else:
        clients.append(data)
    _save_json(CLIENTS_FILE, clients)


def delete_client(client_id: str):
    clients = _load_json(CLIENTS_FILE)
    clients = [c for c in clients if c.get("id") != client_id]
    _save_json(CLIENTS_FILE, clients)
    # Also delete templates
    templates = _load_json(TEMPLATES_FILE)
    templates = [t for t in templates if t.get("client_id") != client_id]
    _save_json(TEMPLATES_FILE, templates)


def _normalize_template_msg(m: dict) -> dict:
    """Nivela el media anidado ({enabled,type,url,caption}) a media_url/media_type."""
    out = dict(m)
    if not out.get("media_url"):
        media = out.get("media") or {}
        out["media_url"] = media.get("url", "") if (media.get("enabled", True) if isinstance(media, dict) else True) else ""
        out["media_type"] = media.get("type", "")
    out.pop("media", None)
    out.pop("media_enabled", None)
    out.pop("caption", None)
    return out


def list_templates(client_id: str = None) -> list[MessageTemplateSet]:
    all_t = _load_json(TEMPLATES_FILE)
    if client_id:
        all_t = [t for t in all_t if t.get("client_id") == client_id]
    results = []
    for t in all_t:
        t = dict(t)
        msgs = t.get("messages") or []
        if isinstance(msgs, list):
            t["messages"] = [_normalize_template_msg(m) for m in msgs if isinstance(m, dict)]
        results.append(MessageTemplateSet(**t))
    return results


def get_template(client_id: str, channel: str) -> Optional[MessageTemplateSet]:
    for t in list_templates(client_id):
        if t.channel == channel:
            return t
    return None


def save_template(template: MessageTemplateSet):
    templates = _load_json(TEMPLATES_FILE)
    idx = next(
        (i for i, t in enumerate(templates) if t.get("client_id") == template.client_id and t.get("channel") == template.channel),
        None,
    )
    data = template.model_dump(mode="json")
    if idx is not None:
        templates[idx] = data
    else:
        templates.append(data)
    _save_json(TEMPLATES_FILE, templates)


def get_default_templates(client_id: str) -> dict:
    """Return default template sets for WA, Email, IG for a new client."""
    return {
        "whatsapp": MessageTemplateSet(
            client_id=client_id,
            channel="whatsapp",
            messages=[
                TemplateMessage(step=1, text="Buenos días, señores de {nombre_empresa}, un gusto saludarles."),
                TemplateMessage(step=2, text="Quería consultarles brevemente: ¿actualmente disponen de un software administrativo, contable y de control de inventario/POS que cumpla con las exigencias de ley?"),
                TemplateMessage(step=3, text="Pertenezco a la casa Premium-Soft creadora del software administrativo y contable diseñado para adaptarse a todas las normativas de ley y facturación electrónica. Si tienes un espacio de tiempo esta semana, podemos agendar una llamada o videollamada para una demostración en vivo."),
            ],
        ),
        "email": MessageTemplateSet(
            client_id=client_id,
            channel="email",
            messages=[
                TemplateMessage(step=1, text="Hola {nombre_empresa},\n\nSomos Premium-Soft, especialistas en software administrativo y contable para Latinoamérica.\n\n¿Les gustaría conocer cómo podemos ayudarles a optimizar su gestión?"),
                TemplateMessage(step=2, text="Hola {nombre_empresa},\n\nQueríamos dar seguimiento a nuestro anterior mensaje. Tenemos planes flexibles adaptados a empresas como la suya."),
                TemplateMessage(step=3, text="Hola {nombre_empresa},\n\nComo último contacto, les ofrecemos una demo gratuita de nuestra suite administrativa. Sin compromiso."),
            ],
        ),
        "instagram": MessageTemplateSet(
            client_id=client_id,
            channel="instagram",
            messages=[
                TemplateMessage(step=1, text="¡Hola {nombre_empresa}! Soy Fabio Pabón, consultor de ventas internacional de PSKloud (Premium-Soft). Somos creadores del software administrativo, contable y de inventario/POS líder en Latinoamérica, adaptado a las normativas de ley de cada país. ¿Les interesaría conocer cómo podemos ayudarles a optimizar su gestión?"),
                TemplateMessage(step=2, text="Contamos con planes flexibles y una demostración en vivo sin compromiso. ¿Les parece si agendamos una breve llamada esta semana para mostrarles la plataforma?"),
            ],
        ),
    }
