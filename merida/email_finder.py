"""
Buscador de Emails - Encuentra correos electrónicos de negocios.
Fuentes: scraping web, DuckDuckGo, Hunter.io, Google search.
"""
import re, time, requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

GENERIC_PREFIXES = {
    "info", "contact", "contacto", "ventas", "sales", "support", "soporte",
    "admin", "help", "hola", "hello", "mail", "office", "comercial",
    "atencion", "servicio", "cliente", "clientes", "webmaster", "postmaster",
    "noreply", "no-reply", "donotreply", "abuse", "spam", "billing",
}

BAD_DOMAINS = {
    "sentry.io", "wixpress.com", "google.com", "facebook.com",
    "twitter.com", "instagram.com", "linkedin.com", "youtube.com",
    "example.com", "localhost", "wordpress.org", "w3.org",
    "schema.org", "googleapis.com", "gstatic.com",
}


def _es_email_valido(email: str) -> bool:
    """Valida que el email no sea genérico ni de dominio basura."""
    email = email.lower().strip()
    if len(email) > 100:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if domain in BAD_DOMAINS:
        return False
    prefix = local.split(".")[0].split("+")[0]
    if prefix in GENERIC_PREFIXES:
        return False
    if not re.match(r'^[a-z0-9._%+-]+$', local):
        return False
    return True


def _extraer_emails(texto: str) -> List[str]:
    """Extrae emails válidos de un texto."""
    raw = EMAIL_REGEX.findall(texto)
    return list(set(e for e in raw if _es_email_valido(e)))


def _requests_get(url: str, timeout: int = 10) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True)
    except Exception:
        return None


# =============================================================================
# FUENTE 1: Scraping web del negocio
# =============================================================================

def scrape_website_emails(website: str) -> List[str]:
    """
    Visita páginas del sitio web y extrae emails.
    Revisa: página principal, contacto, about, etc.
    """
    if not website:
        return []

    # Normalizar URL
    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    base_url = f"{urlparse(website).scheme}://{urlparse(website).netloc}"
    paths = ["/", "/contacto", "/contact", "/contactenos", "/nosotros",
             "/about", "/about-us", "/equipo", "/team", "/info"]

    all_emails = set()
    for path in paths:
        url = base_url + path
        resp = _requests_get(url, timeout=8)
        if resp and resp.status_code == 200:
            emails = _extraer_emails(resp.text)
            all_emails.update(emails)
        time.sleep(0.3)

    return list(all_emails)


# =============================================================================
# FUENTE 2: DuckDuckGo
# =============================================================================

def ddg_search_email(nombre: str, ubicacion: str) -> List[str]:
    """Busca email del negocio en DuckDuckGo."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []

    ciudad = ubicacion.split(",")[0].strip()
    queries = [
        f'"{nombre}" {ciudad} email contacto',
        f'"{nombre}" {ciudad} correo electronico',
        f'"{nombre}" Venezuela email',
    ]

    all_emails = set()
    for q in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, region="ve-ve", max_results=5, backend="mojeek,yahoo,startpage"))
            for r in results:
                full = r.get("title", "") + " " + r.get("body", "")
                emails = _extraer_emails(full)
                all_emails.update(emails)
        except Exception:
            continue
        time.sleep(0.5)

    return list(all_emails)


# =============================================================================
# FUENTE 3: Hunter.io API
# =============================================================================

def hunter_search_email(dominio: str, api_key: str) -> Tuple[Optional[str], float]:
    """
    Busca email usando Hunter.io domain-search.
    Retorna (email, confidence) o (None, 0).
    """
    if not dominio or not api_key:
        return None, 0

    # Limpiar dominio
    dominio = dominio.replace("https://", "").replace("http://", "").replace("www.", "")
    dominio = dominio.split("/")[0]

    url = f"https://api.hunter.io/v2/domain-search?domain={dominio}&api_key={api_key}&limit=5"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            emails = data.get("emails", [])
            if emails:
                # Ordenar por confidence
                best = max(emails, key=lambda e: e.get("confidence", 0))
                email = best.get("value", "")
                confidence = best.get("confidence", 0)
                if email and _es_email_valido(email):
                    return email, confidence
        elif resp.status_code == 429:
            print(f"[HUNTER] Rate limit alcanzado")
    except Exception as e:
        print(f"[HUNTER] Error: {e}")

    return None, 0


# =============================================================================
# ORQUESTADOR: Busca email usando todas las fuentes
# =============================================================================

def buscar_email_completo(
    nombre: str,
    ubicacion: str = "",
    website: str = "",
    hunter_api_key: str = "",
    use_website: bool = True,
    use_ddg: bool = True,
    use_hunter: bool = True,
) -> Dict:
    """
    Busca el email de un negocio usando múltiples fuentes.
    Retorna dict con email encontrado, fuente, y confianza.
    """
    result = {
        "email": "",
        "fuente": "",
        "confianza": 0,
        "emails_todos": [],
    }

    # Fuente 1: Website scraping
    if use_website and website:
        emails = scrape_website_emails(website)
        if emails:
            result["email"] = emails[0]
            result["fuente"] = "website"
            result["confianza"] = 80
            result["emails_todos"] = emails
            return result

    # Fuente 2: DuckDuckGo
    if use_ddg:
        emails = ddg_search_email(nombre, ubicacion)
        if emails:
            result["email"] = emails[0]
            result["fuente"] = "duckduckgo"
            result["confianza"] = 60
            result["emails_todos"] = emails
            return result

    # Fuente 3: Hunter.io
    if use_hunter and hunter_api_key and website:
        dominio = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        email, confidence = hunter_search_email(dominio, hunter_api_key)
        if email:
            result["email"] = email
            result["fuente"] = "hunter"
            result["confianza"] = confidence
            result["emails_todos"] = [email]
            return result

    return result


# =============================================================================
# Enriquecimiento masivo
# =============================================================================

def enrich_leads_batch(
    leads: List[Dict],
    hunter_api_key: str = "",
    max_leads: int = 100,
    delay: float = 1.0,
    progress_callback=None,
) -> Tuple[List[Dict], int]:
    """
    Enriquece una lista de leads con emails.
    Retorna (leads_actualizados, cantidad_encontrados).
    """
    found_count = 0

    for i, lead in enumerate(leads[:max_leads]):
        if lead.get("email"):
            continue

        result = buscar_email_completo(
            nombre=lead.get("nombre", ""),
            ubicacion=lead.get("municipio", "") + ", " + lead.get("ciudad", ""),
            website=lead.get("website", ""),
            hunter_api_key=hunter_api_key,
        )

        if result["email"]:
            lead["email"] = result["email"]
            lead["fuente_email"] = result["fuente"]
            lead["email_confianza"] = result["confianza"]
            if result["emails_todos"]:
                lead["emails_extra"] = result["emails_todos"]
            found_count += 1

        if progress_callback:
            progress_callback(i + 1, len(leads[:max_leads]), lead.get("nombre", ""))

        time.sleep(delay)

    return leads, found_count
