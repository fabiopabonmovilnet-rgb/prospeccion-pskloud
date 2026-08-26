"""
Directorios Venezolanos - Scraping de guías locales para Mérida, Venezuela.
Fuentes: GuiaPana, Infoguia, Directorio Telefónico, MeridaChevere.
"""
import re, time, requests
from typing import List, Dict, Callable
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def _extraer_telefonos(texto: str) -> List[str]:
    phones = []
    for m in re.finditer(r'(?:[\+]\d{1,3}[\s\-\.\(\)]*)?\d[\d\s\-\.\(\)]{6,}', texto):
        raw = m.group().strip()
        clean = re.sub(r'[^\d]', '', raw)
        if 8 <= len(clean) <= 15 and not clean.startswith("000"):
            phones.append(raw)
    return phones


def _extraer_emails(texto: str) -> List[str]:
    return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', texto)))


def _requests_get(url, timeout=10):
    try:
        return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except Exception:
        return None


# =============================================================================
# FUENTE 1: GuiaPana.com
# =============================================================================

def scrap_guia_pana(rubro: str, ciudad: str = "Merida", max_results: int = 20) -> List[Dict]:
    """
    Busca negocios en GuiaPana.com (guía gastronómica de Mérida).
    """
    resultados = []
    url = f"https://guiapana.com/buscar/?q={rubro.replace(' ', '+')}&loc={ciudad.replace(' ', '+')}"
    resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        return resultados

    soup = BeautifulSoup(resp.text, "html.parser")

    for card in soup.select(".listing-item, .card, article")[:max_results]:
        nombre = ""
        tel = ""
        email = ""
        direccion = ""

        # Nombre
        name_el = card.select_one("h2, h3, .title, .listing-title, a.title")
        if name_el:
            nombre = name_el.get_text(strip=True)

        # Teléfono
        tel_el = card.select_one(".phone, .telefono, a[href^='tel:']")
        if tel_el:
            if tel_el.name == "a":
                tel = tel_el.get("href", "").replace("tel:", "").strip()
            else:
                tel = tel_el.get_text(strip=True)

        if not tel:
            phones = _extraer_telefonos(card.get_text())
            if phones:
                tel = phones[0]

        # Email
        email_el = card.select_one("a[href^='mailto:']")
        if email_el:
            email = email_el.get("href", "").replace("mailto:", "").strip()

        # Dirección
        dir_el = card.select_one(".address, .direccion, .location")
        if dir_el:
            direccion = dir_el.get_text(strip=True)

        if nombre and len(nombre) > 2:
            resultados.append({
                "nombre": nombre,
                "telefono": tel,
                "email": email,
                "direccion": direccion,
                "fuente": "guiapana",
            })

    return resultados


# =============================================================================
# FUENTE 2: Infoguia.com
# =============================================================================

def scrap_infoguia(rubro: str, ciudad: str = "Merida", max_results: int = 20) -> List[Dict]:
    """
    Busca negocios en Infoguia.com (directorio de contactos).
    """
    resultados = []
    url = f"https://www.infoguia.com/buscar/{rubro.replace(' ', '-')}/{ciudad.replace(' ', '-')}"
    resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        # Intentar formato alternativo
        url = f"https://www.infoguia.com/buscar/?q={rubro.replace(' ', '+')}&loc={ciudad}"
        resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        return resultados

    soup = BeautifulSoup(resp.text, "html.parser")

    for card in soup.select(".result-item, .listing-item, .card, article")[:max_results]:
        nombre = ""
        tel = ""
        email = ""
        direccion = ""

        name_el = card.select_one("h2, h3, .title, a.title")
        if name_el:
            nombre = name_el.get_text(strip=True)

        tel_el = card.select_one("a[href^='tel:'], .phone, .telefono")
        if tel_el:
            if tel_el.name == "a":
                tel = tel_el.get("href", "").replace("tel:", "").strip()
            else:
                tel = tel_el.get_text(strip=True)

        if not tel:
            phones = _extraer_telefonos(card.get_text())
            if phones:
                tel = phones[0]

        email_el = card.select_one("a[href^='mailto:']")
        if email_el:
            email = email_el.get("href", "").replace("mailto:", "").strip()

        dir_el = card.select_one(".address, .direccion")
        if dir_el:
            direccion = dir_el.get_text(strip=True)

        if nombre and len(nombre) > 2:
            resultados.append({
                "nombre": nombre,
                "telefono": tel,
                "email": email,
                "direccion": direccion,
                "fuente": "infoguia",
            })

    return resultados


# =============================================================================
# FUENTE 3: Directorio Telefónico (dirtelefonico.com)
# =============================================================================

def scrap_dirtelefonico(rubro: str, ciudad: str = "Merida", max_results: int = 20) -> List[Dict]:
    """
    Busca negocios en DirectorioTelefonico.com.
    """
    resultados = []
    url = f"https://www.dirtelefonico.com/buscar/{rubro.replace(' ', '-')}/{ciudad.replace(' ', '-')}"
    resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        url = f"https://www.dirtelefonico.com/buscar/?q={rubro.replace(' ', '+')}"
        resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        return resultados

    soup = BeautifulSoup(resp.text, "html.parser")

    for card in soup.select(".result, .listing, .card, article, .business")[:max_results]:
        nombre = ""
        tel = ""
        email = ""
        direccion = ""

        name_el = card.select_one("h2, h3, .name, .title")
        if name_el:
            nombre = name_el.get_text(strip=True)

        tel_el = card.select_one("a[href^='tel:'], .phone")
        if tel_el:
            if tel_el.name == "a":
                tel = tel_el.get("href", "").replace("tel:", "").strip()
            else:
                tel = tel_el.get_text(strip=True)

        if not tel:
            phones = _extraer_telefonos(card.get_text())
            if phones:
                tel = phones[0]

        email_el = card.select_one("a[href^='mailto:']")
        if email_el:
            email = email_el.get("href", "").replace("mailto:", "").strip()

        dir_el = card.select_one(".address, .location")
        if dir_el:
            direccion = dir_el.get_text(strip=True)

        if nombre and len(nombre) > 2:
            resultados.append({
                "nombre": nombre,
                "telefono": tel,
                "email": email,
                "direccion": direccion,
                "fuente": "dirtelefonico",
            })

    return resultados


# =============================================================================
# FUENTE 4: MeridaChevere.com (eventos y restaurantes)
# =============================================================================

def scrap_meridachereve(rubro: str = "", max_results: int = 20) -> List[Dict]:
    """
    Busca negocios en MeridaChevere.com (guía gastronómica y cultural).
    """
    resultados = []
    url = "https://meridachevere.com/categorias/restaurantes/"
    resp = _requests_get(url)
    if not resp or resp.status_code != 200:
        return resultados

    soup = BeautifulSoup(resp.text, "html.parser")

    for card in soup.select("article, .entry, .post, .card")[:max_results]:
        nombre = ""
        tel = ""
        email = ""
        direccion = ""

        name_el = card.select_one("h2, h3, .entry-title, a")
        if name_el:
            nombre = name_el.get_text(strip=True)

        text = card.get_text()
        phones = _extraer_telefonos(text)
        if phones:
            tel = phones[0]

        emails = _extraer_emails(text)
        if emails:
            email = emails[0]

        # Buscar WhatsApp
        wa_match = re.search(r'(?:whatsapp|wa\.me)[\s:]*(\+?\d[\d\s\-]{7,})', text, re.IGNORECASE)
        if wa_match and not tel:
            tel = wa_match.group(1).strip()

        if nombre and len(nombre) > 2:
            resultados.append({
                "nombre": nombre,
                "telefono": tel,
                "email": email,
                "direccion": direccion,
                "fuente": "meridachevere",
            })

    return resultados


# =============================================================================
# ORQUESTADOR: Busca en todos los directorios
# =============================================================================

def buscar_directorio(rubro: str, ubicacion: str, max_results: int = 20) -> List[Dict]:
    """
    Busca un rubro en todos los directorios venezolanos disponibles.
    """
    partes = [p.strip() for p in ubicacion.split(",")]
    ciudad = partes[0] if partes else "Merida"

    resultados = []
    vistos = set()

    # Buscar en cada directorio
    fuentes = [
        ("GuiaPana", lambda: scrap_guia_pana(rubro, ciudad, max_results)),
        ("Infoguia", lambda: scrap_infoguia(rubro, ciudad, max_results)),
        ("MeridaChevere", lambda: scrap_meridachereve(rubro, max_results)),
    ]

    for nombre_fuente, func in fuentes:
        try:
            items = func()
            for item in items:
                key = item["nombre"].lower().strip()
                if key not in vistos:
                    item["ubicacion"] = ubicacion
                    resultados.append(item)
                    vistos.add(key)
        except Exception as e:
            print(f"[DIR] Error en {nombre_fuente}: {e}")
        time.sleep(0.5)

    return resultados[:max_results]
