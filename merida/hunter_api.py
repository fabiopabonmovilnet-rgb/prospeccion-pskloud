"""
PSKloud Prospector — Integración Hunter.io API
Busca emails corporativos de empresas por dominio o nombre.
"""
import requests
import time
from typing import List, Dict, Optional, Tuple


HUNTER_API_URL = "https://api.hunter.io/v2"


def buscar_email_hunter(
    dominio: str,
    api_key: str,
    first_name: str = "",
    last_name: str = "",
) -> Dict:
    """
    Busca emails en Hunter.io por dominio.
    
    Args:
        dominio: Dominio de la empresa (ej: "empresa.com.ve")
        api_key: API key de Hunter.io
        first_name: Nombre del contacto (opcional)
        last_name:Apellido del contacto (opcional)
    
    Returns:
        Dict con: email, confidence, sources, position
    """
    if not api_key or not dominio:
        return {"email": "", "confidence": 0, "sources": [], "error": "Missing API key or domain"}

    # Limpiar dominio
    dominio = dominio.replace("http://", "").replace("https://", "").split("/")[0].strip()

    try:
        params = {
            "domain": dominio,
            "api_key": api_key,
        }
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name

        resp = requests.get(
            f"{HUNTER_API_URL}/domain-search",
            params=params,
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json().get("data", {})
            emails = data.get("emails", [])

            if emails:
                # Tomar el email con mayor confianza
                best = max(emails, key=lambda x: x.get("confidence", 0))
                return {
                    "email": best.get("value", ""),
                    "confidence": best.get("confidence", 0),
                    "position": best.get("position", ""),
                    "first_name": best.get("first_name", ""),
                    "last_name": best.get("last_name", ""),
                    "sources": [s.get("uri", "") for s in best.get("sources", [])],
                    "organization": data.get("organization", dominio),
                }

            return {"email": "", "confidence": 0, "sources": [], "organization": data.get("organization", dominio)}

        elif resp.status_code == 429:
            return {"email": "", "confidence": 0, "sources": [], "error": "Rate limit exceeded"}
        elif resp.status_code == 401:
            return {"email": "", "confidence": 0, "sources": [], "error": "Invalid API key"}
        else:
            return {"email": "", "confidence": 0, "sources": [], "error": f"HTTP {resp.status_code}"}

    except Exception as e:
        return {"email": "", "confidence": 0, "sources": [], "error": str(e)[:100]}


def enrich_leads_hunter(
    leads: List[Dict],
    api_key: str,
    max_leads: int = 100,
    delay: float = 1.0,
    progress_callback=None,
) -> Tuple[List[Dict], int]:
    """
    Enriquece una lista de leads con emails de Hunter.io.
    
    Args:
        leads: Lista de leads (dicts)
        api_key: API key de Hunter.io
        max_leads: Máximo de leads a enriquecer
        delay: Delay entre requests (segundos)
        progress_callback: Función callback(current, total, lead_name)
    
    Returns:
        Tuple de (leads_enriquecidos, cantidad_nuevos)
    """
    enriched_count = 0
    total_to_process = min(len(leads), max_leads)

    for i, lead in enumerate(leads[:max_leads]):
        # Si ya tiene email, saltar
        if lead.get("email"):
            continue

        # Obtener dominio del website
        website = lead.get("website", "")
        if not website:
            continue

        dominio = website.replace("http://", "").replace("https://", "").split("/")[0].strip()
        if not dominio or "." not in dominio:
            continue

        # Buscar en Hunter
        result = buscar_email_hunter(dominio, api_key)

        if result.get("email"):
            lead["email"] = result["email"]
            lead["email_confidence"] = result.get("confidence", 0)
            lead["email_source"] = "hunter.io"
            lead["email_position"] = result.get("position", "")
            enriched_count += 1

        # Callback de progreso
        if progress_callback:
            progress_callback(i + 1, total_to_process, lead.get("nombre", ""))

        # Delay entre requests
        if delay > 0:
            time.sleep(delay)

    return leads, enriched_count


def verificar_api_key_hunter(api_key: str) -> Tuple[bool, str]:
    """
    Verifica si una API key de Hunter.io es válida.
    
    Returns:
        Tuple de (es_valida, mensaje)
    """
    if not api_key:
        return False, "API key vacía"

    try:
        resp = requests.get(
            f"{HUNTER_API_URL}/account",
            params={"api_key": api_key},
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json().get("data", {})
            plan = data.get("plan_name", "Free")
            requests_count = data.get("requests", {}).get("used", 0)
            requests_limit = data.get("requests", {}).get("available", 0)
            return True, f"Plan: {plan} | Requests: {requests_count}/{requests_limit}"

        elif resp.status_code == 401:
            return False, "API key inválida"
        else:
            return False, f"Error HTTP {resp.status_code}"

    except Exception as e:
        return False, f"Error de conexión: {str(e)[:80]}"


def extraer_dominio(website: str) -> str:
    """Extrae el dominio limpio de una URL."""
    if not website:
        return ""
    dominio = website.replace("http://", "").replace("https://", "").split("/")[0].strip()
    return dominio if "." in dominio else ""
