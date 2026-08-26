"""
PSKloud Prospector — Normalización de teléfonos Venezuela
Convierte cualquier formato local al internacional +58XXXXXXXXXX
"""
import re
from typing import Optional


def normalizar_telefono_ve(phone: str) -> str:
    """
    Normaliza un teléfono venezolano al formato internacional +58XXXXXXXXXX.
    
    Acepta cualquier formato razonable:
    - 04141234567, 0414-123-4567, (0414) 123-4567
    - +584141234567, +58 414 123 4567
    - 584141234567
    - 4141234567 (sin prefijo 0)
    - 02742630000 (fijo)
    """
    if not phone or not isinstance(phone, str):
        return ""
    
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    
    if not cleaned:
        return ""
    
    # Si ya empieza con +58
    if cleaned.startswith("+58"):
        digits = cleaned[3:]
        if 9 <= len(digits) <= 11:
            return f"+58{digits}"
        return ""
    
    # Si empieza con 58 (sin +)
    if cleaned.startswith("58") and len(cleaned) >= 11:
        digits = cleaned[2:]
        if 9 <= len(digits) <= 11:
            return f"+58{digits}"
    
    # Si empieza con 0 (formato local)
    if cleaned.startswith("0"):
        digits = cleaned[1:]
        if 9 <= len(digits) <= 11:
            return f"+58{digits}"
    
    # Si tiene 9-11 dígitos sin prefijo
    if 9 <= len(cleaned) <= 11:
        if not cleaned.startswith("0"):
            return f"+58{cleaned}"
    
    return ""


def es_telefono_ve(phone: str) -> bool:
    """Verifica si un teléfono parece venezolano válido."""
    normalizado = normalizar_telefono_ve(phone)
    if not normalizado:
        return False
    
    digits = normalizado[3:]  # Quitar +58
    if len(digits) == 10:
        return True
    if len(digits) == 11:
        return True
    # Also accept if it's 9 digits (some local formats)
    if len(digits) == 9:
        return True
    return False


def formato_whatsapp(phone: str) -> str:
    """Retorna el teléfono en formato wa.me (solo dígitos, sin +)."""
    normalizado = normalizar_telefono_ve(phone)
    if not normalizado:
        return ""
    return normalizado[1:]  # Quitar el +


def extraer_telefonos(texto: str) -> list:
    """
    Extrae y normaliza teléfonos venezolanos de un texto.
    Retorna lista de números normalizados en formato +58XXXXXXXXXX.
    """
    if not texto:
        return []
    
    phones = set()
    
    # Patrón general para teléfonos
    patterns = [
        r'(?:\+58[\s\-\.]?)?\(?\d{3,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}',
        r'(?:\+58)?\d{10,11}',
        r'0\d{3}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, texto):
            raw = match.group()
            normalizado = normalizar_telefono_ve(raw)
            if normalizado and es_telefono_ve(normalizado):
                phones.add(normalizado)
    
    return sorted(phones)


def extraer_emails(texto: str) -> list:
    """Extrae emails válidos de un texto, excluyendo genéricos yServiceProvider."""
    if not texto:
        return []
    
    GENERICOS = {
        "info", "contact", "contacto", "ventas", "sales", "support", "soporte",
        "admin", "help", "hola", "hello", "mail", "office", "comercial",
        "general", "servicio", "noreply", "no-reply", "donotreply",
        "example", "test", "prueba", "webmaster", "postmaster",
    }
    
    SKIP_DOMAINS = {
        "example.com", "sentry.io", "wixpress.com", "google.com",
        "facebook.com", "twitter.com", "instagram.com",
    }
    
    emails = set()
    for match in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', texto):
        email = match.group().lower()
        local = email.split("@")[0]
        domain = email.split("@")[1]
        
        if local in GENERICOS:
            continue
        if domain in SKIP_DOMAINS:
            continue
        if any(domain.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".css", ".js"]):
            continue
        
        emails.add(email)
    
    return sorted(emails)


def enriquecer_lead_telefono(lead: dict) -> dict:
    """Normaliza el teléfono de un lead al formato +58."""
    phone = lead.get("telefono", "")
    if phone:
        lead["telefono"] = normalizar_telefono_ve(phone)
        lead["telefono_original"] = phone
    return lead


def enriquecer_leads(leads: list) -> list:
    """Normaliza teléfonos de una lista de leads."""
    for lead in leads:
        enriquecer_lead_telefono(lead)
    return leads


# Tests rápidos
if __name__ == "__main__":
    tests = [
        ("04141234567", "+584141234567"),
        ("02742630000", "+582742630000"),
        ("+584141234567", "+584141234567"),
        ("584141234567", "+584141234567"),
        ("0414-123-4567", "+584141234567"),
        ("(0274) 263-0000", "+582742630000"),
        ("+58 414 123 4567", "+584141234567"),
        ("0414.123.4567", "+584141234567"),
        ("12345", ""),  # Muy corto
        ("", ""),  # Vacío
    ]
    
    for input_val, expected in tests:
        result = normalizar_telefono_ve(input_val)
        status = "OK" if result == expected else "FAIL"
        print(f"{status}: '{input_val}' -> '{result}' (expected: '{expected}')")
