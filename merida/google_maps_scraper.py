"""
GOOGLE MAPS + EMAIL SCRAPER - Merida, Venezuela
1. Google Maps Search -> extrae nombre, telefono, website, address
2. Visita website -> busca email en HTML completo (including mailto:, meta, JS)
3. Google Search -> "nombre negocio" merida email
"""
import re, json, time, os, random, sys
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_utils import normalizar_telefono_ve, extraer_telefonos

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
BAD_DOMAINS = {"sentry.io","wixpress.com","google.com","facebook.com","twitter.com",
    "instagram.com","linkedin.com","youtube.com","example.com","localhost",
    "wordpress.org","w3.org","schema.org","googleapis.com","gstatic.com",
    "cloudflare.com","tiktok.com","nytimes.com","airbnb.com","booking.com",
    "tripadvisor.com","fodors.com","wanderlog.com","travelweekly.com",
    "sentry.io","wixpress.com","schema.org"}

def _ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD_DOMAINS: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example","abuse","postmaster"]): return False
    return True

def _crear_browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="es-VE",
        timezone_id="America/Caracas",
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return pw, browser, ctx

def google_maps_search(query: str, page, max_results: int = 20) -> List[Dict]:
    """Busca en Google Maps y extrae listings del panel lateral."""
    from bs4 import BeautifulSoup
    results = []
    
    try:
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(random.randint(2000, 4000))
        
        # Scroll en el panel de resultados para cargar mas
        feed = page.query_selector('div[role="feed"]')
        if feed:
            for _ in range(3):
                feed.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(1500)
        
        html = page.content()
    except Exception as e:
        print(f"    Maps error: {e}")
        return []
    
    soup = BeautifulSoup(html, "lxml")
    
    # Buscar cards de resultados en Google Maps
    for item in soup.select('div.Nv2PK, a.hfpxzc, div[jsaction*="mouseover"]'):
        try:
            # Nombre
            name_el = item.select_one('.qBF1Pd, .fontHeadlineSmall, .NrDZNb')
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            
            # Rating + reviews
            rating_el = item.select_one('.MW4etd')
            rating = rating_el.get_text(strip=True) if rating_el else ""
            
            # Tipo/categoria
            cat_el = item.select_one('.W4Efsd span:last-child')
            category = cat_el.get_text(strip=True) if cat_el else ""
            
            # Link to Maps listing
            link = ""
            a_tag = item.select_one('a.hfpxzc, a[data-item-id]')
            if a_tag:
                link = a_tag.get('href', '')
            
            results.append({
                "nombre": name,
                "rating": rating,
                "categoria_maps": category,
                "maps_url": link,
            })
            
            if len(results) >= max_results:
                break
        except:
            continue
    
    return results

def google_maps_detail(maps_url: str, page) -> Dict:
    """Abre un listing de Google Maps y extrae telefono, website, direccion."""
    from bs4 import BeautifulSoup
    info = {"telefono": "", "website": "", "direccion": ""}
    
    if not maps_url:
        return info
    
    try:
        page.goto(maps_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(random.randint(2000, 3000))
        html = page.content()
    except:
        return info
    
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    
    # Telefono - patron comun en Google Maps
    phone_match = re.search(r'(\+?58[\s-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}|\d{4}[\s.-]\d{4}|\d{3}[\s.-]\d{3}[\s.-]\d{4})', text)
    if phone_match:
        info["telefono"] = normalizar_telefono_ve(phone_match.group(0))
    
    # Website
    for a in soup.select('a[data-item-id="authority"]'):
        href = a.get("href", "")
        if href.startswith("http") and "google.com" not in href:
            info["website"] = href
            break
    
    # Direccion
    addr_el = soup.select_one('div[data-item-id="address"] div.fontBodyMedium')
    if addr_el:
        info["direccion"] = addr_el.get_text(strip=True)
    
    return info

def extract_emails_from_html(html: str) -> List[str]:
    """Extrae emails de HTML - busca en mailto, meta tags, JavaScript, comentarios."""
    emails = set()
    
    # Buscar en todo el HTML
    for e in EMAIL_REGEX.findall(html):
        if _ok_email(e):
            emails.add(e.lower())
    
    # Buscar en mailto links
    mailto_matches = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html, re.IGNORECASE)
    for e in mailto_matches:
        if _ok_email(e):
            emails.add(e.lower())
    
    # Buscar en atributos data y JavaScript
    data_matches = re.findall(r'["\']([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})["\']', html)
    for e in data_matches:
        if _ok_email(e):
            emails.add(e.lower())
    
    return sorted(emails)

def visit_website_for_email(url: str, page, timeout: int = 12) -> List[str]:
    """Visita un website y busca emails en el HTML completo."""
    if not url or not url.startswith("http"):
        return []
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(random.randint(1000, 2000))
        html = page.content()
        return extract_emails_from_html(html)
    except:
        return []

def google_search_email(nombre: str, ubicacion: str, page) -> List[str]:
    """Busca email especifico de un negocio en Google."""
    from bs4 import BeautifulSoup
    emails = set()
    
    queries = [
        f'"{nombre}" "{ubicacion}" email "@"',
        f'"{nombre}" "{ubicacion}" correo electronico',
        f'"{nombre}" merida venezuela "@" gmail.com',
    ]
    
    for q in queries:
        try:
            from urllib.parse import quote
            page.goto(f"https://www.google.com/search?q={quote(q)}&hl=es&gl=ve", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(random.randint(1000, 2000))
            html = page.content()
            for e in extract_emails_from_html(html):
                emails.add(e)
        except:
            pass
        time.sleep(0.5)
    
    return sorted(emails)

def scrape_rubro_completo(rubro: str, municipio: str, max_results: int = 30) -> List[Dict]:
    """Scraping completo de un rubro: Maps -> Websites -> Google Search emails."""
    from playwright.sync_api import sync_playwright
    
    print(f"\n{'='*50}")
    print(f"SCRAPING: {rubro} en {municipio}")
    print(f"{'='*50}")
    
    leads = []
    seen_names = set()
    
    pw, browser, ctx = _crear_browser()
    page = ctx.new_page()
    
    try:
        # PASO 1: Google Maps Search
        ubicacion = f"{rubro} {municipio} Mérida Venezuela"
        print(f"  [1/3] Google Maps: {ubicacion}")
        map_results = google_maps_search(ubicacion, page, max_results=max_results + 10)
        print(f"    Encontrados en Maps: {len(map_results)}")
        
        # PASO 2: Detalle de cada listing (telefono, website)
        print(f"  [2/3] Obteniendo detalles...")
        for i, mr in enumerate(map_results):
            nombre = mr["nombre"]
            if nombre.lower() in seen_names:
                continue
            seen_names.add(nombre.lower())
            
            # Detail from Maps
            detail = google_maps_detail(mr.get("maps_url", ""), page)
            
            lead = {
                "nombre": nombre,
                "rubro": rubro,
                "municipio": municipio,
                "telefono": detail.get("telefono", ""),
                "email": "",
                "website": detail.get("website", ""),
                "direccion": detail.get("direccion", ""),
                "maps_url": mr.get("maps_url", ""),
                "fuente": "google_maps",
                "estado_contacto": "No Contactado",
            }
            
            # PASO 3: Buscar email en website
            if lead["website"]:
                print(f"    [{i+1}] {nombre} -> visitando website...")
                emails = visit_website_for_email(lead["website"], page)
                if emails:
                    lead["email"] = emails[0]
                    print(f"      EMAIL: {emails[0]}")
            
            # PASO 3b: Si no hay email, buscar en Google
            if not lead["email"]:
                print(f"    [{i+1}] {nombre} -> buscando email en Google...")
                emails = google_search_email(nombre, municipio, page)
                if emails:
                    lead["email"] = emails[0]
                    print(f"      EMAIL: {emails[0]}")
            
            leads.append(lead)
            
            if len(leads) >= max_results:
                break
            
            time.sleep(random.uniform(1, 2))
    
    finally:
        browser.close()
        pw.stop()
    
    return leads

def scrape_todos_los_rubros(max_por_rubro: int = 30):
    """Scrapea todos los rubros目标 y guarda en leads.json."""
    RUBROS = [
        "farmacia", "panaderia", "restaurante", "hotel", "supermercado",
        "clinica", "taller mecanico", "ferreteria", "salon de belleza",
        "gimnasio", "veterinaria", "colegio privado", "academia de idiomas",
        "contador publico", "abogado", "constructora", "distribuidora",
        "auto partes", "tienda de electronica", "joyeria", "optica",
        "inmobiliaria", "agencia de viajes", "transporte", "seguros",
        "bar", "pizzeria", "cafeteria", "heladeria", "libreria",
    ]
    
    all_leads = []
    
    for rubro in RUBROS:
        leads = scrape_rubro_completo(rubro, "Mérida", max_results=max_por_rubro)
        all_leads.extend(leads)
        
        # Guardar parcial
        out = os.path.join(BASE_DIR, "leads_google_maps.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_leads, f, ensure_ascii=False, indent=2)
        
        con_email = sum(1 for l in all_leads if l.get("email"))
        print(f"  TOTAL PARCIAL: {len(all_leads)} leads, {con_email} con email")
    
    # Guardar final
    out = os.path.join(BASE_DIR, "leads_google_maps.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)
    
    con_email = sum(1 for l in all_leads if l.get("email"))
    con_tel = sum(1 for l in all_leads if l.get("telefono"))
    print(f"\n{'='*50}")
    print(f"FINAL: {len(all_leads)} leads, {con_tel} con telefono, {con_email} con email")
    print(f"{'='*50}")
    
    return all_leads

if __name__ == "__main__":
    scrape_todos_los_rubros(max_por_rubro=30)
