"""
PSKloud Prospector — Exportación WhatsApp para OpenClaw
Genera JSON/CSV estructurados para el cerebro de OpenClaw,
y enlaces wa.me directos con mensaje personalizado.
"""
import json
import csv
import io
import os
from typing import List, Dict, Optional
from urllib.parse import quote
from datetime import datetime


def normalizar_telefono_ve(phone: str) -> str:
    """Normaliza teléfono venezolano a formato +58XXXXXXXXXX."""
    import re
    if not phone:
        return ""
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    if cleaned.startswith("+58"):
        return cleaned if 13 <= len(cleaned) <= 15 else ""
    if cleaned.startswith("58") and len(cleaned) >= 13:
        return f"+{cleaned}"
    if cleaned.startswith("0") and len(cleaned) >= 11:
        return f"+58{cleaned[1:]}"
    if 10 <= len(cleaned) <= 11:
        return f"+58{cleaned}" if cleaned.startswith(("04", "02")) else f"+58{cleaned}"
    return ""


def generar_wa_link(phone: str, mensaje: str) -> str:
    """Genera enlace wa.me con mensaje codificado."""
    clean = phone.replace("+", "").strip()
    if not clean or len(clean) < 12:
        return ""
    encoded_msg = quote(mensaje)
    return f"https://wa.me/{clean}?text={encoded_msg}"


def generar_mensaje_whatsapp(
    lead: dict,
    plantilla: str = "Hola {{nombre}}, le escribo desde PSKloud. ¿Tendría unos minutos para conversar sobre una oportunidad de negocio?",
    extra_vars: Optional[Dict] = None,
) -> str:
    """Personaliza el mensaje de WhatsApp con las variables del lead."""
    msg = plantilla
    vars_dict = {
        "nombre": lead.get("nombre", ""),
        "nombre_negocio": lead.get("nombre", ""),
        "rubro": lead.get("rubro", ""),
        "municipio": lead.get("municipio", ""),
        "telefono": lead.get("telefono", ""),
        "email": lead.get("email", ""),
        "direccion": lead.get("direccion", ""),
    }
    if extra_vars:
        vars_dict.update(extra_vars)
    
    for k, v in vars_dict.items():
        msg = msg.replace("{{" + k + "}}", str(v))
    
    return msg


def exportar_openclaw_json(
    leads: List[Dict],
    plantilla_mensaje: str,
    output_path: str,
    extra_vars: Optional[Dict] = None,
) -> str:
    """
    Exporta leads en formato JSON para OpenClaw.
    
    Formato:
    {
        "campaign_name": "merida_YYYYMMDD",
        "created_at": "...",
        "total_contacts": N,
        "contacts": [
            {
                "phone": "+584141234567",
                "name": "Nombre",
                "message": "Mensaje personalizado",
                "wa_link": "https://wa.me/...",
                "metadata": { ... }
            }
        ]
    }
    """
    contacts = []
    
    for lead in leads:
        phone = normalizar_telefono_ve(lead.get("telefono", ""))
        if not phone:
            continue
        
        msg = generar_mensaje_whatsapp(lead, plantilla_mensaje, extra_vars)
        wa_link = generar_wa_link(phone, msg)
        
        contacts.append({
            "phone": phone,
            "name": lead.get("nombre", ""),
            "business": lead.get("nombre", ""),
            "sector": lead.get("rubro", ""),
            "city": lead.get("municipio", ""),
            "address": lead.get("direccion", ""),
            "email": lead.get("email", ""),
            "website": lead.get("website", ""),
            "message": msg,
            "wa_link": wa_link,
            "status": "pending",
            "metadata": {
                "source": "pskloud_prospector",
                "campaign": "merida",
                "place_id": lead.get("place_id", ""),
                "maps_url": lead.get("maps_url", ""),
            },
        })
    
    export_data = {
        "campaign_name": f"merida_{datetime.now().strftime('%Y%m%d')}",
        "created_at": datetime.now().isoformat(),
        "platform": "openclaw",
        "total_contacts": len(contacts),
        "contacts": contacts,
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    return output_path


def exportar_openclaw_csv(
    leads: List[Dict],
    plantilla_mensaje: str,
    output_path: str,
    extra_vars: Optional[Dict] = None,
) -> str:
    """
    Exporta leads en formato CSV para OpenClaw o WhatsApp Business.
    """
    rows = []
    
    for lead in leads:
        phone = normalizar_telefono_ve(lead.get("telefono", ""))
        if not phone:
            continue
        
        msg = generar_mensaje_whatsapp(lead, plantilla_mensaje, extra_vars)
        wa_link = generar_wa_link(phone, msg)
        
        rows.append({
            "phone": phone,
            "name": lead.get("nombre", ""),
            "sector": lead.get("rubro", ""),
            "city": lead.get("municipio", ""),
            "message": msg,
            "wa_link": wa_link,
            "status": "pending",
        })
    
    if not rows:
        return ""
    
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    
    return output_path


def exportar_wa_links_csv(
    leads: List[Dict],
    plantilla_mensaje: str,
    extra_vars: Optional[Dict] = None,
) -> str:
    """
    Genera un CSV en memoria con todos los enlaces wa.me listos para usar.
    Retorna el CSV como string.
    """
    output = io.StringIO()
    
    rows = []
    for lead in leads:
        phone = normalizar_telefono_ve(lead.get("telefono", ""))
        if not phone:
            continue
        
        msg = generar_mensaje_whatsapp(lead, plantilla_mensaje, extra_vars)
        wa_link = generar_wa_link(phone, msg)
        
        rows.append({
            "nombre": lead.get("nombre", ""),
            "telefono": phone,
            "rubro": lead.get("rubro", ""),
            "municipio": lead.get("municipio", ""),
            "mensaje": msg,
            "enlace_wa": wa_link,
        })
    
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    
    return output.getvalue()


def estadisticas_exportacion(leads: List[Dict]) -> Dict:
    """Retorna estadísticas de la exportación."""
    con_tel = [l for l in leads if l.get("telefono")]
    phones_validos = [l for l in con_tel if normalizar_telefono_ve(l.get("telefono", ""))]
    
    return {
        "total_leads": len(leads),
        "con_telefono": len(con_tel),
        "telefonos_validos": len(phones_validos),
        "sin_telefono": len(leads) - len(con_tel),
        "telefonos_invalidos": len(con_tel) - len(phones_validos),
    }
