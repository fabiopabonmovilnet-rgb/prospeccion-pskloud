"""
=============================================================================
PSKloud Prospector - Buscador silencioso con Playwright headless.
Sin ventanas, sin Chrome del usuario, sin interferencias.
Usa Chromium empaquetado de Playwright en modo headless para:
  - Buscar en Google (LinkedIn, emails públicos)
  - Visitar sitios web (extraer equipo, contactos)
  - Verificar emails por DNS/SMTP
=============================================================================
"""
import re
import json
import time
import random
import os
import requests
from typing import List, Dict
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

_cache: Dict[str, List] = {}

_GENERIC_PREFIXES = {
    "info", "contact", "contacto", "ventas", "sales", "support", "soporte",
    "admin", "help", "hola", "hello", "mail", "office", "comercial",
    "general", "servicio", "customer", "service", "webmaster", "postmaster",
    "marketing", "press", "media", "jobs", "careers", "empleo", "recruitment",
    "rrhh", "legal", "privacy", "abuse", "noc", "billing", "accounts",
    "finance", "partner", "partners", "editor", "web", "newsletter", "news",
    "inquiries", "enquiry", "enquiries", "team", "notificaciones", "no-reply",
    "noreply", "donotreply", "example", "test", "prueba"
}

CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-web-security",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _crear_contexto(p, headless=True):
    """Crea browser + context con Chromium empaquetado (no Chrome del usuario)."""
    browser = p.chromium.launch(headless=headless, args=CHROME_ARGS)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=USER_AGENT
    )
    return browser, context


# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE SEARCH (headless, sin ventanas)
# ═══════════════════════════════════════════════════════════════════════════

def _google_search_playwright(query: str, max_results: int = 10) -> List[Dict]:
    """Busca en Google usando Playwright headless. Sin ventanas."""
    results = []
    try:
        with sync_playwright() as p:
            browser, context = _crear_contexto(p)
            page = context.new_page()
            page.goto(
                f"https://www.google.com/search?q={query.replace(' ', '+')}",
                wait_until="domcontentloaded", timeout=30000
            )
            page.wait_for_timeout(random.randint(2000, 4000))
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        for h3 in soup.select("a h3")[:max_results]:
            a = h3.find_parent("a")
            if a:
                href = a.get("href", "")
                if href.startswith("/url?q="):
                    href = href.split("/url?q=")[1].split("&")[0]
                results.append({
                    "title": h3.get_text(strip=True),
                    "href": href,
                    "body": "",
                    "source": "Google"
                })
    except Exception as e:
        print(f"[browser_bot] Google search error: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# VISITAR SITIO WEB (headless, para ver JS)
# ═══════════════════════════════════════════════════════════════════════════

def _visit_page_playwright(url: str) -> str:
    """Visita una URL con Playwright headless, espera JS, devuelve HTML."""
    html = ""
    try:
        with sync_playwright() as p:
            browser, context = _crear_contexto(p)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(2000, 4000))
            html = page.content()
            browser.close()
    except Exception:
        pass
    return html


# ═══════════════════════════════════════════════════════════════════════════
# SMTP / DNS EMAIL VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def verify_email_smtp(email: str, timeout: int = 10) -> Dict:
    import dns.resolver
    import socket
    if not email or "@" not in email:
        return {"valido": False, "detalle": "Email inv\u00e1lido"}
    domain = email.split("@")[1].lower().strip()
    if email.split("@")[0].lower().strip() in _GENERIC_PREFIXES:
        return {"valido": False, "detalle": "Email gen\u00e9rico"}
    try:
        try:
            mx_records = dns.resolver.resolve(domain, "MX", lifetime=timeout)
            mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange)
        except Exception:
            return {"valido": False, "detalle": "No MX records"}
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((mx_host, 25))
        def recv():
            return sock.recv(1024).decode("utf-8", errors="ignore")
        def send(cmd):
            sock.sendall((cmd + "\r\n").encode("utf-8"))
        resp = recv()
        if "220" not in resp:
            sock.close()
            return {"valido": False, "detalle": f"SMTP no disponible: {resp[:50]}"}
        send(f"EHLO verify.pskloud.com"); recv()
        send("MAIL FROM: <verify@pskloud.com>"); recv()
        send(f"RCPT TO: <{email}>")
        resp = recv()
        send("QUIT")
        sock.close()
        if resp.startswith("250"):
            return {"valido": True, "detalle": "Email existe (SMTP confirmado)"}
        elif resp.startswith("55"):
            return {"valido": False, "detalle": "Email no existe"}
        else:
            return {"valido": None, "detalle": f"Respuesta SMTP: {resp[:50]}"}
    except socket.timeout:
        return {"valido": None, "detalle": "Timeout conexi\u00f3n SMTP"}
    except Exception as e:
        return {"valido": None, "detalle": f"Error: {str(e)[:60]}"}


def verify_email_light(email: str) -> Dict:
    import dns.resolver
    if not email or "@" not in email:
        return {"valido": False, "detalle": "Email inv\u00e1lido"}
    local, domain = email.split("@", 1)
    domain = domain.lower().strip()
    if local.lower().strip() in _GENERIC_PREFIXES:
        return {"valido": False, "detalle": "Email gen\u00e9rico"}
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return {"valido": False, "detalle": "Formato inv\u00e1lido"}
    try:
        dns.resolver.resolve(domain, "MX", lifetime=5)
        return {"valido": True, "detalle": "Dominio con MX v\u00e1lido"}
    except Exception:
        return {"valido": False, "detalle": "Dominio sin MX"}


# ═══════════════════════════════════════════════════════════════════════════
# LINKEDIN PROFILE EXTRACTOR (p�blico, headless)
# ═══════════════════════════════════════════════════════════════════════════

def visit_linkedin_profile(url: str) -> Dict:
    """Visita perfil p�blico de LinkedIn con Playwright headless."""
    profile = {"name": "", "title": "", "location": "", "telefono": "", "linkedin_url": url}
    try:
        html = _visit_page_playwright(url)
        if not html:
            return profile
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.select_one("h1")
        if h1:
            profile["name"] = h1.get_text(strip=True)
        title_el = soup.select_one("div.text-body-medium")
        if title_el:
            profile["title"] = title_el.get_text(strip=True)
        phones = _extract_phones(html)
        if phones:
            profile["telefono"] = phones[0]
    except Exception:
        pass
    return profile


# ═══════════════════════════════════════════════════════════════════════════
# EXTRACCI�N DE NOMBRES DE SITIO WEB (headless, para JS)
# ═══════════════════════════════════════════════════════════════════════════

_TEAM_PATHS = ["/team", "/equipo", "/about", "/nosotros", "/contacto", "/staff"]

def _scrape_team_page_playwright(domain: str) -> List[Dict]:
    """Scrapea p\u00e1ginas del equipo usando Playwright headless (para sitios con JS)."""
    encontrados = []
    all_phones = []
    if not domain.startswith("http"):
        domain = "https://" + domain

    for path in _TEAM_PATHS:
        url = domain.rstrip("/") + path
        try:
            html = _visit_page_playwright(url)
            if not html or len(html) < 1000:
                continue
            soup = BeautifulSoup(html, "lxml")

            # Extraer tel\u00e9fonos de la p\u00e1gina
            phones = _extract_phones(html)
            for p in phones:
                if p not in all_phones:
                    all_phones.append(p)

            # schema.org
            for item in soup.select('[itemtype*="Person"], [itemtype*="Employee"]'):
                name_el = item.select_one('[itemprop="name"]')
                title_el = item.select_one('[itemprop="jobTitle"]')
                if name_el:
                    n = name_el.get_text(strip=True)
                    t = title_el.get_text(strip=True) if title_el else ""
                    if _es_nombre_valido(n):
                        encontrados.append({"nombre": n, "cargo": t, "telefono": "", "url": url})
            # Tarjetas team
            for card in soup.select("[class*='team' i], [class*='member' i], [class*='staff' i], [class*='person' i]"):
                h = card.select_one("h1, h2, h3, h4, h5")
                if h:
                    n = h.get_text(strip=True)
                    t = ""
                    t_el = card.select_one("span, p, small, [class*='title' i], [class*='position' i], [class*='cargo' i], [class*='role' i]")
                    if t_el:
                        t = t_el.get_text(strip=True)
                    if _es_nombre_valido(n):
                        encontrados.append({"nombre": n, "cargo": t, "telefono": "", "url": url})
            # <li>Nombre - Cargo</li>
            for li in soup.select("li"):
                txt = li.get_text(strip=True)
                for sep in [" - ", " \u2013 ", " | ", " \u2014 "]:
                    if sep in txt:
                        parts = txt.split(sep, 1)
                        if _es_nombre_valido(parts[0]) and len(parts[0].split()) >= 2:
                            encontrados.append({"nombre": parts[0].strip(), "cargo": parts[1].strip(), "telefono": "", "url": url})
                            break
        except Exception:
            continue

    # Adjuntar tel\u00e9fonos globales al primer resultado
    if all_phones and encontrados:
        encontrados[0]["telefono"] = "; ".join(all_phones[:3])

    return encontrados


def _es_nombre_valido(texto: str) -> bool:
    texto = texto.strip()
    if not texto or len(texto) < 5 or len(texto) > 45:
        return False
    if not re.match(r"^[A-Z\u00C0-\u024f][A-Za-z\u00C0-\u024f .\-\']{2,}(?: [A-Z\u00C0-\u024f][A-Za-z\u00C0-\u024f .\-\']+)+$", texto):
        return False
    palabras = texto.split()
    if len(palabras) < 2:
        return False
    prohibidas = {"team", "equipo", "staff", "our", "the", "meet", "conoce",
                  "nuestro", "contact", "contacto", "page", "home", "related",
                  "posts", "section", "get", "direccion", "direcci\u00f3n",
                  "ubicacion", "ubicaci\u00f3n", "servicios", "services",
                  "productos", "products", "about", "nosotros", "menu",
                  "inicio", "home", "follow", "siguenos"}
    pal_lower = texto.lower().split()
    if any(p in prohibidas for p in pal_lower):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# GENERAR EMAILS POR PATR�N
# ═══════════════════════════════════════════════════════════════════════════

def _generar_emails(nombre: str, apellido: str, domain: str) -> List[str]:
    if not domain or domain == "N/A":
        return []
    n = nombre.lower().strip()
    a = apellido.lower().strip()
    d = domain.lower().strip().lstrip("www.")
    patterns = [
        f"{n}.{a}@{d}",
        f"{n[0]}.{a}@{d}",
        f"{n[0]}{a}@{d}",
        f"{n}.{a[0]}@{d}",
        f"{n[0]}{a[0]}@{d}",
        f"{n}@{d}",
    ]
    return list(set(patterns))


# ═══════════════════════════════════════════════════════════════════════════
# ORQUESTADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

_PHONE_BLACKLIST = re.compile(
    r"^(\+?\d{1,3})?("
    r"0{7,}|1{7,}|2{7,}|3{7,}|4{7,}|5{7,}|6{7,}|7{7,}|8{7,}|9{7,}"
    r"|12345678|23456789|34567890|45678901"
    r"|87654321|98765432|11111111|22222222|33333333"
    r"|44444444|55555555|66666666|77777777|88888888|99999999|00000000"
    r"|10000000|20000000|30000000"
    r")$",
    re.IGNORECASE,
)

def _es_telefono_valido(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7 or len(digits) > 15:
        return False
    if _PHONE_BLACKLIST.match(digits):
        return False
    # Rechazar números donde después del código de país vienen 00...
    # Ej: 50300347275 → 503 es código, 00347275 empieza con 00
    for cc in ("506", "503", "507", "504", "57", "505", "1", "52", "54", "55", "56", "58"):
        if digits.startswith(cc):
            resto = digits[len(cc):]
            if resto.startswith("00") or resto.startswith("000"):
                return False
            break
    return True

def _extract_phones(text: str) -> List[str]:
    phones = []
    # CR: +506 XXXX-XXXX, 8 dígitos
    for p in re.findall(r"(?:\+506[\s-]?)?\d{4}[\s-]?\d{4}", text):
        p = re.sub(r"[\s-]", "", p)
        if len(p) >= 8 and p not in phones and _es_telefono_valido(p):
            phones.append(p)
    # SV: +503 XXXX-XXXX
    for p in re.findall(r"(?:\+503[\s-]?)?\d{4}[\s-]?\d{4}", text):
        p = re.sub(r"[\s-]", "", p)
        if len(p) >= 8 and p not in phones and _es_telefono_valido(p):
            phones.append(p)
    # NI: +505 XXXX-XXXX
    for p in re.findall(r"(?:\+505[\s-]?)?\d{4}[\s-]?\d{4}", text):
        p = re.sub(r"[\s-]", "", p)
        if len(p) >= 8 and p not in phones and _es_telefono_valido(p):
            phones.append(p)
    # US/international: +1 XXX-XXX-XXXX
    for p in re.findall(r"\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{2,4}[\s-]?\d{2,4}", text):
        p = re.sub(r"[\s-]", "", p)
        if len(p) >= 8 and p not in phones and _es_telefono_valido(p):
            phones.append(p)
    return phones


def buscar_contactos_browser(
    company_name: str, domain: str, country: str = "", limite: int = 10
) -> List[Dict]:
    """
    Busca contactos B2B reales usando Playwright headless (sin ventanas):
    1. Google search para LinkedIn profiles
    2. Visita LinkedIn p�blico para nombre + cargo
    3. Google search para emails p�blicos
    4. Scrapea sitio web de la empresa (team page)
    5. Verificaci�n DNS de emails
    """
    contactos = []
    seen_emails = set()
    seen_li = set()

    # 1. LinkedIn profiles via Google
    linkedin_urls = []
    for q in [
        f'linkedin "{company_name}"',
        f'linkedin "{domain}"' if domain and domain != "N/A" else "",
    ]:
        if not q:
            continue
        for r in _google_search_playwright(q, max_results=8):
            href = r.get("href", "").split("?")[0].rstrip("/")
            if "linkedin.com/in/" in href and href not in seen_li:
                seen_li.add(href)
                linkedin_urls.append(href)
        if len(linkedin_urls) >= limite:
            break

    # 2. Visitar LinkedIn profiles + extraer teléfonos
    for url in linkedin_urls[:limite]:
        profile = visit_linkedin_profile(url)
        name = profile.get("name", "").strip()
        if not name or "linkedin" in name.lower() or "nete" in name.lower():
            continue
        parts = name.split(" ", 1)
        telefono_linkedin = profile.get("telefono", "")
        contactos.append({
            "email": "", "nombre": parts[0] if parts else "",
            "apellido": parts[1] if len(parts) > 1 else "",
            "cargo": profile.get("title", ""),
            "confianza": 65, "tipo": "personal",
            "telefono": telefono_linkedin,
            "linkedin": url, "fuente": "Google + LinkedIn"
        })

    # 3. Emails via Google
    if domain and domain != "N/A":
        found_emails = []
        for q in [f'"@{domain}" "{company_name}"', f'"{company_name}" email contact']:
            for r in _google_search_playwright(q, max_results=5):
                for e in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                                    r.get("title", "") + " " + r.get("body", "")):
                    local = e.split("@")[0].lower()
                    dom = e.split("@")[-1].lower()
                    if local in _GENERIC_PREFIXES:
                        continue
                    if domain.replace("www.", "") in dom:
                        if e not in seen_emails:
                            seen_emails.add(e)
                            found_emails.append(e)
            if len(found_emails) >= 5:
                break

        for email in found_emails[:5]:
            v = verify_email_light(email)
            conf = 85 if v.get("valido") else 70
            matched = False
            for c in contactos:
                name = f"{c.get('nombre', '')} {c.get('apellido', '')}".lower().strip()
                if name and email.split("@")[0].lower() in name:
                    c["email"] = email
                    c["confianza"] = max(c["confianza"], conf)
                    matched = True
                    break
            if not matched:
                contactos.append({
                    "email": email, "nombre": "", "apellido": "",
                    "cargo": "", "confianza": conf, "tipo": "personal",
                    "telefono": "", "linkedin": "", "fuente": "Google + DNS"
                })

    # 3.5 Teléfonos via Google
    if domain and domain != "N/A":
        phones_found = []
        for q in [f'"{company_name}" teléfono contacto', f'"{company_name}" phone contact']:
            for r in _google_search_playwright(q, max_results=5):
                phones = _extract_phones(r.get("title", "") + " " + r.get("body", ""))
                for p in phones:
                    if p not in phones_found:
                        phones_found.append(p)
            if phones_found:
                break

        if phones_found and contactos:
            contactos[0]["telefono"] = "; ".join(phones_found[:3])

    # 4. Scrapeo directo del sitio web (team page, con JS)
    if domain and domain != "N/A":
        miembros = _scrape_team_page_playwright(domain)
        for m in miembros:
            nombre_completo = m.get("nombre", "").strip()
            if not nombre_completo:
                continue
            partes = nombre_completo.split(None, 1)
            nombre = partes[0]
            apellido = partes[1] if len(partes) > 1 else ""

            # Ver si ya existe por LinkedIn
            ya_existe = False
            for c in contactos:
                c_full = f"{c.get('nombre', '')} {c.get('apellido', '')}".lower().strip()
                if nombre_completo.lower() in c_full or c_full in nombre_completo.lower():
                    if not c.get("cargo") and m.get("cargo"):
                        c["cargo"] = m["cargo"]
                    if not c.get("email"):
                        for e in _generar_emails(nombre, apellido, domain):
                            if e not in seen_emails:
                                seen_emails.add(e)
                                v = verify_email_light(e)
                                if v.get("valido"):
                                    c["email"] = e
                                    c["confianza"] = min(c["confianza"] + 15, 100)
                                    break
                    ya_existe = True
                    break

            if not ya_existe:
                email = ""
                conf = 60
                for e in _generar_emails(nombre, apellido, domain):
                    if e not in seen_emails:
                        seen_emails.add(e)
                        v = verify_email_light(e)
                        if v.get("valido"):
                            email = e
                            conf = 75
                            break
                telefono_web = m.get("telefono", "")
                contactos.append({
                    "email": email, "nombre": nombre, "apellido": apellido,
                    "cargo": m.get("cargo", ""), "confianza": conf,
                    "tipo": "personal", "telefono": telefono_web, "linkedin": "",
                    "fuente": "Sitio web + patr\u00f3n email"
                })

    return contactos[:limite]


def search_web(query: str, max_results: int = 10) -> List[Dict]:
    """B�squeda web con Google via Playwright headless."""
    cache_key = f"w::{query.lower().strip()}"
    if cache_key in _cache:
        return _cache[cache_key][:max_results]
    results = _google_search_playwright(query, max_results)
    if results:
        _cache[cache_key] = results
    return results


def clear_cache():
    _cache.clear()


# ═══════════════════════════════════════════════════════════════════════════
# APOLLO.IO SCRAPER — extrae leads SIN usar créditos de exportación
# ═══════════════════════════════════════════════════════════════════════════

APOLLO_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".apollo_profile")


def scrape_apollo_search(
    search_url: str,
    max_pages: int = 50,
    headless: bool = False,
    progress_callback=None,
) -> List[Dict]:
    """
    Scrapea resultados de búsqueda de Apollo.io usando Playwright.
    Se conecta a tu Chrome/Edge ya abierto (con sesión iniciada de Apollo)
    a través de Chrome DevTools Protocol (CDP) en el puerto 9222.

    NO usa créditos de exportación porque extrae datos visibles de la UI
    (nunca presiona el botón "Export").

    Args:
        search_url: URL completa de la búsqueda en Apollo
        max_pages: Máximo de páginas (25 leads c/u)
        headless: no aplica cuando se conecta a browser existente
        progress_callback: función(lideres_extraidos, pagina_actual, total_paginas)

    Returns:
        Lista de dicts con: nombre, cargo, empresa, email, teléfono, linkedin, ubicación
    """
    todos = []
    seen_links = set()

    print("=" * 60)
    print("🚀 APOLLO SCRAPER")
    print("=" * 60)
    print("Conectando a Chrome/Edge en puerto 9222...")
    print("")
    print("⚠️  Si ves un error de conexión, haz esto:")
    print("    1. CIERRA todas las ventanas de Chrome/Edge")
    print("    2. Abre PowerShell como Administrador y pega:")
    print("")
    print('       start msedge --remote-debugging-port=9222')
    print("       (o chrome en vez de msedge si usas Chrome)")
    print("")
    print("    3. En la ventana que se abre, navega a Apollo e inicia sesión")
    print("    4. Vuelve aquí y presiona 'Extraer Leads' otra vez")
    print("=" * 60)

    with sync_playwright() as p:
        # Conectar al navegador ya abierto con remote debugging
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            print("[Apollo] ✅ Conectado a tu navegador existente")
        except Exception as e:
            print(f"[Apollo] ❌ No se pudo conectar: {e}")
            print("[Apollo] Abriendo navegador nuevo como fallback...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=APOLLO_PROFILE_DIR,
                headless=headless,
                args=["--window-size=1280,900"],
                viewport={"width": 1280, "height": 900},
            )
            print("[Apollo] ⚠️  Se abrió un navegador nuevo. Inicia sesión en Apollo manualmente.")

        # Usar la primera página o crear una nueva
        page = None
        for pg in context.pages:
            if "apollo.io" in pg.url:
                page = pg
                break
        if not page:
            page = context.new_page()

        # Navegar a la URL de búsqueda
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        pagina_actual = 0
        # Archivo de depuración: se guarda el HTML de la primera página para inspección
        debug_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_apollo_debug.html")

        while pagina_actual < max_pages:
            pagina_actual += 1
            page.wait_for_timeout(random.randint(3000, 5000))

            try:
                # Verificar que la página sigue estable
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                print(f"[Apollo] ⚠️ La página se navegó/recargó en página {pagina_actual}, reintentando...")
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=30000)
                    page.wait_for_timeout(3000)
                except Exception:
                    print("[Apollo] ❌ No se pudo recuperar la navegación")
                    break

            # Obtener HTML completo de la página
            try:
                html = page.content()
            except Exception as e:
                print(f"[Apollo] ⚠️ Error obteniendo HTML: {e}")
                continue

            try:
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                continue

            # Guardar HTML de la primera página para depuración
            if pagina_actual == 1:
                try:
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"[Apollo] HTML guardado en {debug_file} para depuración")
                except Exception:
                    pass

            # Estrategia 1: Buscar todos los textos largos que contengan email + nombre
            # Apollo usualmente renderiza cada persona en un contenedor con texto plano
            raw_texts = set()

            # Buscar en todos los elementos que podrían ser tarjetas de persona
            for tag in soup.find_all(["div", "tr", "li", "article", "section"]):
                t = tag.get_text(" ", strip=True)
                if len(t) < 60 or len(t) > 2000:
                    continue
                # Debe tener al menos un email O linkedin O un nombre completo con @ cerca
                has_email = "@" in t and "." in t[t.index("@"):]
                has_li = "linkedin.com" in t.lower()
                # Un nombre completo (dos palabras con mayúscula inicial)
                has_name = bool(re.search(r"\b[A-Z][a-záéíóúñ]+ [A-Z][a-záéíóúñ]+\b", t))
                if (has_email or has_li) and has_name:
                    raw_texts.add(t)

            # Estrategia 2: Si no se encontró nada, buscar todo el texto de la página
            # y extraer personas por patrón
            if not raw_texts:
                body_text = soup.get_text(" ", strip=True)
                # Buscar emails
                emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", body_text)
                if emails:
                    # Para cada email, buscar contexto alrededor
                    for email in emails[:50]:  # máx 50 por página
                        idx = body_text.index(email)
                        start = max(0, idx - 300)
                        end = min(len(body_text), idx + 100)
                        context = body_text[start:end]
                        raw_texts.add(context)

            # Procesar cada bloque
            for text in raw_texts:
                entry = {"nombre": "", "cargo": "", "empresa": "", "email": "",
                         "telefono": "", "linkedin": "", "ubicacion": ""}

                # Email
                m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
                if m:
                    entry["email"] = m.group(0)

                # Teléfono
                m = re.search(r"\+\d{7,15}", text)
                if m:
                    entry["telefono"] = m.group(0)

                # LinkedIn
                m = re.search(r"linkedin\.com/[a-zA-Z0-9_%/-]+", text)
                if m:
                    entry["linkedin"] = "https://www." + m.group(0)

                # Dividir en líneas
                lineas = [l.strip() for l in text.split("\n") if l.strip()]
                if not lineas:
                    continue

                # Primera línea = nombre
                partes = lineas[0].split()
                if len(partes) >= 2:
                    entry["nombre"] = lineas[0]

                # Clasificar líneas
                for linea in lineas:
                    if "@" in linea and "@" not in entry["email"]:
                        entry["email"] = linea
                    elif re.search(r"\+\d{7,}", linea) and not entry["telefono"]:
                        entry["telefono"] = linea
                    elif re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)*, [A-Z]", linea) and not entry["ubicacion"]:
                        entry["ubicacion"] = linea

                # Líneas intermedias: cargo y empresa
                intermedias = [
                    l for l in lineas
                    if l != lineas[0]
                    and "@" not in l
                    and not re.search(r"^\+?\d", l)
                    and not re.match(r"^[A-Z][a-z]+.*, [A-Z]", l)
                    and not re.search(r"linkedin", l, re.I)
                ]
                for i, linea in enumerate(intermedias):
                    if i == 0 and not entry["cargo"]:
                        entry["cargo"] = linea
                    elif i == 1 and not entry["empresa"]:
                        entry["empresa"] = linea

                # Deducir empresa desde email si no se encontró
                if not entry["empresa"] and entry["email"]:
                    dominio = entry["email"].split("@")[-1]
                    entry["empresa"] = dominio.replace(".com", "").replace(".net", "").title()

                clave = entry.get("email", "") or entry.get("linkedin", "")
                if clave and clave not in seen_links:
                    seen_links.add(clave)
                    todos.append(entry)

            if progress_callback:
                progress_callback(len(todos), pagina_actual, max_pages)

            # Scroll down para triggerear carga de más resultados (infinite scroll)
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(random.randint(1000, 2000))
            except Exception:
                pass

            # Intentar ir a la siguiente página
            encontrado_boton = False
            for selector in [
                'button:has-text("Next")',
                'button:has-text("next")', 
                '[aria-label="Next"]',
                '[aria-label="Next page"]',
                'button:has-text("›")',
                'button:has-text(">")',
                'a:has-text("Next")',
                '[data-test-id="pagination-next"]',
                '.pagination-next',
            ]:
                try:
                    btn = page.query_selector(selector)
                    if btn and btn.is_enabled():
                        btn.scroll_into_view_if_needed()
                        page.wait_for_timeout(random.randint(1000, 2000))
                        btn.click()
                        page.wait_for_timeout(random.randint(4000, 7000))
                        encontrado_boton = True
                        break
                except Exception:
                    continue

            if not encontrado_boton:
                # Intentar con JavaScript como último recurso
                try:
                    clicked = page.evaluate("""
                        () => {
                            // Buscar cualquier botón/enlace que avance de página
                            const btns = document.querySelectorAll('button, a');
                            for (const btn of btns) {
                                const t = btn.textContent.trim().toLowerCase();
                                if (['next', 'siguiente', '›', '>', '→'].includes(t) || 
                                    btn.getAttribute('aria-label')?.toLowerCase().includes('next')) {
                                    if (!btn.disabled && btn.offsetParent !== null) {
                                        btn.click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        page.wait_for_timeout(random.randint(4000, 7000))
                        encontrado_boton = True
                except Exception:
                    pass

            if not encontrado_boton:
                break

    return todos

