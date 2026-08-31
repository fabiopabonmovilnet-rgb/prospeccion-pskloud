"""
=============================================================================
PSKloud Prospector - Motor de Enriquecimiento de Leads
Busca teléfonos y datos de contacto en directorios públicos reales:
  - Páginas Amarillas (CO, PA, SV, GT, NI)
  - Yelu.cr (Costa Rica)
  - Infoguia.co.cr (Costa Rica)
  - Scraping directo de sitios web corporativos
=============================================================================
"""

import re
import time
import random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from fake_useragent import UserAgent

_cache: Dict[str, Dict] = {}
ua = UserAgent()

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Mapa: país -> código de país telefónico
CODIGOS_TELEFONO = {
    "Costa Rica": "506",
    "El Salvador": "503",
    "Panamá": "507",
    "Honduras": "504",
    "Colombia": "57",
}

# Países con Páginas Amarillas
PAISES_PA = {
    "El Salvador": "sv",
    "Colombia": "co",
    "Panamá": "pa",
}


def _get_headers() -> dict:
    h = HEADERS.copy()
    try:
        h["User-Agent"] = ua.random
    except Exception:
        h["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    return h


def _clean_phone(phone: str, pais: str = "") -> str:
    if not phone:
        return ""
    phone = re.sub(r"[^\d+]", "", phone)
    if phone.startswith("+"):
        return phone

    codigo = CODIGOS_TELEFONO.get(pais, "")
    if codigo and phone.startswith(codigo):
        return f"+{phone}"

    # Inteligencia básica según cantidad de dígitos
    if pais == "Costa Rica":
        if len(phone) == 8:
            return f"+506{phone}"
    elif pais == "El Salvador":
        if len(phone) == 8:
            return f"+503{phone}"
    elif pais == "Panamá":
        if len(phone) == 8:
            return f"+507{phone}"
    elif pais == "Colombia":
        if len(phone) == 10:
            return f"+57{phone}"
    elif pais == "Honduras":
        if len(phone) == 8:
            return f"+504{phone}"

    if codigo:
        return f"+{codigo}{phone}"
    return phone


def _extract_phones(text: str, pais: str = "") -> List[str]:
    if not text:
        return []
    patterns = [
        r"\+\d{7,15}",
        r"\d{4}[-\s]?\d{4}",
        r"\d{4}[-\s]?\d{3}[-\s]?\d{4}",
        r"\d{8}",
        r"\d{4}\s\d{4}",
        r"\(\d{3,4}\)[\s-]?\d{3,4}[\s-]?\d{4}",
    ]
    phones = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            cleaned = _clean_phone(match.group(), pais)
            if len(cleaned) >= 8:
                phones.add(cleaned)
    return list(phones)


def _extract_emails(text: str) -> List[str]:
    if not text:
        return []
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text)))


# =============================================================================
# SCRAPER GENÉRICO: Páginas Amarillas (multi-país)
# =============================================================================

def search_paginas_amarillas(company_name: str, country_code: str, pais_nombre: str) -> Dict:
    """
    Busca una empresa en Páginas Amarillas del país indicado.
    country_code: 'sv', 'co', 'pa'
    """
    cache_key = f"pa_{country_code}::{company_name.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "direccion": "", "sitio_web": "", "fuente": ""}
    try:
        from bs4 import BeautifulSoup
        url = f"https://www.paginasamarillas.com.{country_code}/buscar"
        resp = requests.get(url, params={"what": company_name}, headers=_get_headers(), timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.result-item, article.business-card, div.list-item, div.card-item")
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"(result|business|item|card)"))

        if cards:
            card = cards[0]
            tel_el = card.select_one(".phone, .telefono, [class*=phone], [class*=tel], a[href^=tel]")
            if tel_el:
                phone = tel_el.get_text(strip=True)
                result["telefonos"] = _extract_phones(phone, pais_nombre) or [phone]
            web_el = card.select_one("a[href^=http]")
            if web_el:
                result["sitio_web"] = web_el.get("href", "")
            dir_el = card.select_one(".address, .direccion, [class*=address]")
            if dir_el:
                result["direccion"] = dir_el.get_text(strip=True)

        if not result["telefonos"]:
            phones = _extract_phones(resp.text, pais_nombre)
            if phones:
                result["telefonos"] = phones

        result["fuente"] = f"Páginas Amarillas {pais_nombre}" if result["telefonos"] else ""
    except Exception:
        result["fuente"] = ""

    _cache[cache_key] = result
    time.sleep(random.uniform(1.0, 2.0))
    return result


# =============================================================================
# SCRAPER: Yelu.cr (Costa Rica)
# =============================================================================

def search_yelu_cr(company_name: str) -> Dict:
    cache_key = f"yelu_cr::{company_name.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "direccion": "", "sitio_web": "", "fuente": ""}
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://www.yelu.cr/search",
            params={"q": company_name},
            headers=_get_headers(), timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        listings = soup.select("div.listing-card, div.business-card, div.result-item, article")
        if not listings:
            listings = soup.find_all("div", class_=re.compile(r"(listing|business|card)"))

        if listings:
            card = listings[0]
            tel_link = card.select_one("a[href^=tel]")
            if tel_link:
                result["telefonos"] = [tel_link.get("href", "").replace("tel:", "")]
            else:
                phones = _extract_phones(card.get_text(), "Costa Rica")
                if phones:
                    result["telefonos"] = phones
            web_link = card.select_one("a[href^=http]")
            if web_link:
                result["sitio_web"] = web_link.get("href", "")
            dir_el = card.select_one("[class*=address], [class*=direccion]")
            if dir_el:
                result["direccion"] = dir_el.get_text(strip=True)

        if not result["telefonos"]:
            phones = _extract_phones(resp.text, "Costa Rica")
            if phones:
                result["telefonos"] = phones[:2]
        result["fuente"] = "Yelu.cr (CR)" if result["telefonos"] else ""
    except Exception:
        result["fuente"] = ""

    _cache[cache_key] = result
    time.sleep(random.uniform(0.5, 1.5))
    return result


# =============================================================================
# SCRAPER: Infoguia.co.cr (Costa Rica)
# =============================================================================

def search_infoguia_cr(company_name: str) -> Dict:
    cache_key = f"infoguia_cr::{company_name.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "direccion": "", "sitio_web": "", "fuente": ""}
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://infoguia.co.cr/buscar/",
            params={"q": company_name},
            headers=_get_headers(), timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".listing-item, .business-item, .result-item, article, .item-box")
        if not items:
            items = soup.find_all("div", class_=re.compile(r"(item|result|business)"))

        if items:
            card = items[0]
            phones = _extract_phones(card.get_text(), "Costa Rica")
            if phones:
                result["telefonos"] = phones
            web_el = card.select_one("a[href^=http]")
            if web_el:
                href = web_el.get("href", "")
                if "infoguia" not in href and "buscar" not in href:
                    result["sitio_web"] = href

        if not result["telefonos"]:
            phones = _extract_phones(resp.text, "Costa Rica")
            if phones:
                result["telefonos"] = phones[:2]
        result["fuente"] = "Infoguía Costa Rica" if result["telefonos"] else ""
    except Exception:
        result["fuente"] = ""

    _cache[cache_key] = result
    time.sleep(random.uniform(0.5, 1.5))
    return result


# =============================================================================
# SCRAPER: Sitio web corporativo
# =============================================================================

def scrape_website(website_url: str) -> Dict:
    if not website_url:
        return {"telefonos": [], "emails": [], "fuente": ""}
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    cache_key = f"web::{website_url.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "emails": [], "fuente": ""}
    pages_to_try = [
        website_url,
        f"{website_url.rstrip('/')}/contacto",
        f"{website_url.rstrip('/')}/contact",
        f"{website_url.rstrip('/')}/contactenos",
        f"{website_url.rstrip('/')}/nosotros",
        f"{website_url.rstrip('/')}/about",
        f"{website_url.rstrip('/')}/about-us",
    ]
    all_text = ""
    for page_url in pages_to_try:
        try:
            resp = requests.get(page_url, headers=_get_headers(), timeout=10)
            if resp.status_code == 200:
                all_text += resp.text + "\n"
        except Exception:
            continue

    if all_text:
        result["telefonos"] = _extract_phones(all_text)
        result["emails"] = [
            e for e in _extract_emails(all_text)
            if not any(x in e.lower() for x in ["noreply", "no-reply", "donotreply", "example"])
        ]

    if result["telefonos"]:
        result["fuente"] = "Sitio web corporativo"
    _cache[cache_key] = result
    return result


# =============================================================================
# LUSHA API (teléfonos directos + datos de empresa + contacto por email)
# =============================================================================

LUSHA_API_URL = "https://api.lusha.com/people"
LUSHA_COMPANY_API_URL = "https://api.lusha.com/companies"

def search_lusha_company(api_key: str, company_name: str) -> Dict:
    """
    Enriquecimiento de empresa vía Lusha Company API.
    Devuelve teléfono, dominio, industria, tamaño, ubicación.
    """
    if not api_key:
        return {"telefonos": [], "fuente": ""}

    cache_key = f"lusha_company::{company_name.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "sitio_web": "", "direccion": "", "industria": "", "empleados": 0, "fuente": ""}
    try:
        payload = {"companyName": company_name}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        resp = requests.post(LUSHA_COMPANY_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            phones = data.get("phones", [])
            if phones:
                result["telefonos"] = [p.get("phoneNumber", p) if isinstance(p, dict) else p for p in phones[:2]]
            domain = data.get("domain", "") or data.get("website", "")
            if domain:
                result["sitio_web"] = domain if domain.startswith("http") else f"https://{domain}"
            loc = data.get("location", {}) or {}
            ciudad = loc.get("city", "") or data.get("city", "")
            pais = loc.get("country", "") or data.get("country", "")
            if ciudad or pais:
                result["direccion"] = f"{ciudad}, {pais}".strip(", ")
            result["industria"] = data.get("industry", "") or data.get("sector", "")
            result["empleados"] = data.get("employeeCount", 0) or data.get("employees", 0)
            result["fuente"] = "Lusha Company" if (result["telefonos"] or result["sitio_web"]) else ""
        elif resp.status_code == 402:
            result["fuente"] = "Lusha: créditos agotados"
        else:
            result["fuente"] = ""
    except Exception:
        result["fuente"] = ""
    _cache[cache_key] = result
    time.sleep(random.uniform(0.3, 0.8))
    return result


def search_lusha_by_email(api_key: str, email: str, company_name: str = "") -> Dict:
    """
    Enriquecimiento de contacto vía Lusha People API usando email.
    Devuelve nombre, teléfono directo, cargo.
    """
    if not api_key or not email:
        return {"telefonos": [], "emails": [], "nombre": "", "cargo": "", "fuente": ""}

    cache_key = f"lusha_email::{email.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "emails": [], "nombre": "", "cargo": "", "fuente": ""}
    try:
        payload = {"email": email}
        if company_name:
            payload["company"] = company_name
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        resp = requests.post(LUSHA_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            phones = data.get("phones", [])
            emails = data.get("emails", [])
            if phones:
                result["telefonos"] = [p.get("phoneNumber", p) if isinstance(p, dict) else p for p in phones[:3]]
            if emails:
                result["emails"] = [e.get("email", e) if isinstance(e, dict) else e for e in emails[:3]]
            result["nombre"] = data.get("firstName", "") + " " + data.get("lastName", "")
            result["cargo"] = data.get("jobTitle", "") or data.get("title", "") or data.get("position", "")
            result["fuente"] = "Lusha" if (result["telefonos"] or result["emails"] or result["nombre"]) else ""
        elif resp.status_code == 402:
            result["fuente"] = "Lusha: créditos agotados"
        else:
            result["fuente"] = ""
    except Exception:
        result["fuente"] = ""
    _cache[cache_key] = result
    return result


def search_lusha(api_key: str, first_name: str, last_name: str, company: str) -> Dict:
    """
    Busca un contacto en Lusha usando nombre + empresa.
    Lusha provee teléfonos directos (no solo de la empresa) y emails.
    Plan free: 70 créditos/mes.
    """
    if not api_key or not first_name:
        return {"telefonos": [], "emails": [], "fuente": ""}

    cache_key = f"lusha::{company.lower().strip()}/{first_name.lower()}/{last_name.lower()}"
    if cache_key in _cache:
        return _cache[cache_key]

    result = {"telefonos": [], "emails": [], "fuente": ""}
    try:
        payload = {
            "firstName": first_name,
            "lastName": last_name or "",
            "company": company
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        resp = requests.post(LUSHA_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            phones = data.get("phones", [])
            emails = data.get("emails", [])
            if phones:
                result["telefonos"] = [p.get("phoneNumber", p) if isinstance(p, dict) else p for p in phones[:3]]
            if emails:
                result["emails"] = [e.get("email", e) if isinstance(e, dict) else e for e in emails[:3]]
            result["fuente"] = "Lusha" if (result["telefonos"] or result["emails"]) else ""
        elif resp.status_code == 402:
            result["fuente"] = "Lusha: créditos agotados"
        else:
            result["fuente"] = ""
    except Exception:
        result["fuente"] = ""
    _cache[cache_key] = result
    return result


# =============================================================================
# ORQUESTADOR: Enriquecimiento multi-fuente
# =============================================================================

def enrich_company(
    company_name: str,
    country: str,
    website: Optional[str] = None,
    lusha_api_key: Optional[str] = None,
    contact_first_name: Optional[str] = None,
    contact_last_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    timeout: int = 30,
) -> Dict:
    """
    Busca datos de contacto de una empresa en TODAS las fuentes disponibles
    y fusiona los resultados.

    Países soportados: Costa Rica, El Salvador, Panamá, Honduras, Colombia
    Opcional: Lusha API para teléfonos directos del contacto y datos de empresa.
    """
    results = {
        "telefonos": [],
        "emails": [],
        "direccion": "",
        "sitio_web": website or "",
        "industria": "",
        "empleados": 0,
        "contacto_nombre": "",
        "contacto_cargo": "",
        "fuentes_usadas": [],
    }

    tasks = []

    # Scrapers por país
    if country == "El Salvador":
        tasks.append(("Páginas Amarillas SV", lambda: search_paginas_amarillas(company_name, "sv", "El Salvador")))
    elif country == "Colombia":
        tasks.append(("Páginas Amarillas CO", lambda: search_paginas_amarillas(company_name, "co", "Colombia")))
    elif country == "Panamá":
        tasks.append(("Páginas Amarillas PA", lambda: search_paginas_amarillas(company_name, "pa", "Panamá")))
    elif country == "Costa Rica":
        tasks.append(("Yelu.cr", lambda: search_yelu_cr(company_name)))
        tasks.append(("Infoguía CR", lambda: search_infoguia_cr(company_name)))

    # Sitio web corporativo
    if website:
        tasks.append(("Sitio web", lambda: scrape_website(website)))

    # Lusha: enriquecimiento de empresa (teléfono, dominio, industria)
    if lusha_api_key:
        tasks.append(("Lusha Company", lambda: search_lusha_company(lusha_api_key, company_name)))

    # Lusha: enriquecimiento de contacto por email (si hay email)
    if lusha_api_key and contact_email:
        tasks.append(("Lusha Email", lambda: search_lusha_by_email(lusha_api_key, contact_email, company_name)))

    # Lusha: enriquecimiento de contacto por nombre+empresa
    if lusha_api_key and contact_first_name:
        tasks.append(("Lusha", lambda: search_lusha(lusha_api_key, contact_first_name, contact_last_name or "", company_name)))

    if not tasks:
        return results

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(task_fn): task_name
            for task_name, task_fn in tasks
        }
        for future in as_completed(future_map, timeout=timeout):
            task_name = future_map[future]
            try:
                data = future.result()
                if data.get("telefonos"):
                    results["telefonos"].extend(data["telefonos"])
                    results["fuentes_usadas"].append(task_name)
                if data.get("emails"):
                    results["emails"].extend(data["emails"])
                if data.get("direccion") and not results["direccion"]:
                    results["direccion"] = data["direccion"]
                if data.get("sitio_web") and not results["sitio_web"]:
                    results["sitio_web"] = data["sitio_web"]
                if data.get("industria") and not results["industria"]:
                    results["industria"] = data["industria"]
                if data.get("empleados") and not results["empleados"]:
                    results["empleados"] = data["empleados"]
                if data.get("nombre") and not results["contacto_nombre"]:
                    results["contacto_nombre"] = data["nombre"]
                if data.get("cargo") and not results["contacto_cargo"]:
                    results["contacto_cargo"] = data["cargo"]
            except Exception:
                continue

    results["telefonos"] = list(dict.fromkeys(results["telefonos"]))
    results["emails"] = list(dict.fromkeys(results["emails"]))
    return results


def clear_cache():
    _cache.clear()


def get_cache_stats() -> dict:
    return {
        "entradas": len(_cache),
        "fuentes_consultadas": len(
            set(v.get("fuente", "") for v in _cache.values() if v.get("fuente"))
        ),
    }
