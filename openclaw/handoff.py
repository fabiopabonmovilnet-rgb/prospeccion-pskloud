from __future__ import annotations

import logging
from config import settings
from evolution_client import evolution_default
from models import Lead

logger = logging.getLogger("openclaw.handoff")


async def send_handoff_alert(lead: Lead, message: str, conversation_summary: str):
    phone = settings.handoff_phone
    if not phone:
        logger.warning("HANDOFF_PHONE not configured, skipping alert")
        return

    alert_text = (
        f"🚨 *HANDOFF - Lead calificado*\n\n"
        f"*Empresa:* {lead.empresa}\n"
        f"*Contacto:* {lead.nombre}\n"
        f"*Teléfono:* {lead.telefono}\n"
        f"*Rubro:* {lead.rubro}\n"
        f"*País:* {lead.pais}\n\n"
        f"*Mensaje del lead:*\n{message}\n\n"
        f"*Resumen conversación:*\n{conversation_summary}\n\n"
        f"➡️ Responder lo antes posible."
    )

    try:
        evo = evolution_default()
        await evo.send_typing(phone)
        await evo.send_text(phone, alert_text, delay_ms=1000)
        logger.info(f"Handoff alert sent for lead {lead.empresa} ({lead.telefono})")
    except Exception as e:
        logger.error(f"Failed to send handoff alert: {e}")
