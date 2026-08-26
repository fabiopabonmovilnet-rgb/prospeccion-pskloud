"""
EMAIL FINDER REAL - Instagram/Facebook bios via DuckDuckGo
Metodo probado para Latinoamerica:
1. DuckDuckGo busca Instagram/Facebook del negocio
2. Visita el perfil y extrae email + telefono del bio
3. Tambien busca email en snippets de busqueda
"""
import sys, os, json, time, random, re
from urllib.parse import quote

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'(\+?58[\s-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3}[\s.-]?\d{4}|\d{4}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example"]): return False
    return True

def ddg_search(query, max_r=10):
    try:
        from ddgs import DDGS
    except:
        from duckduckgo_search import DDGS
    try:
        with DDGS() as d:
            return list(d.text(query, region="ve-ve", max_results=max_r))
    except:
        return []

def scrape_ig_fb(url, page):
    """Visita Instagram/Facebook y extrae bio con email y telefono"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(random.randint(1500, 2500))
        html = page.content()
        
        emails = list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))
        phones = list(set(PHONE_REGEX.findall(html)))
        
        # Buscar en meta tags y bio
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        
        # Meta description (Instagram bio)
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        bio = meta.get("content", "") if meta else ""
        
        if bio:
            emails.extend([e.lower() for e in EMAIL_REGEX.findall(bio) if ok_email(e)])
            phones.extend(PHONE_REGEX.findall(bio))
        
        # Title
        title_el = soup.select_one("title")
        title = title_el.get_text() if title_el else ""
        
        return {
            "emails": list(set(emails)),
            "phones": list(set(phones)),
            "bio": bio[:200],
            "title": title[:100],
        }
    except:
        return {"emails": [], "phones": [], "bio": "", "title": ""}

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
with open(leads_file, encoding="utf-8", errors="replace") as f:
    leads = json.load(f)

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    viewport={"width":1920,"height":1080}, locale="es-VE", timezone_id="America/Caracas"
)
ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')
page = ctx.new_page()

stats = {"searched": 0, "found_ig": 0, "found_email": 0, "found_phone": 0}

for i, lead in enumerate(leads):
    nombre = lead.get("nombre", "")
    if not nombre or (lead.get("email") and lead.get("telefono")):
        continue
    
    print(f"[{i+1}/{len(leads)}] {nombre[:40]}...", end=" ", flush=True)
    stats["searched"] += 1
    
    # PASO 1: Buscar Instagram del negocio
    ig_results = ddg_search(f'site:instagram.com "{nombre}" Merida', 5)
    ig_url = ""
    for r in ig_results:
        href = r.get("href", "")
        if "instagram.com" in href and "/p/" not in href:
            ig_url = href
            break
    
    # PASO 2: Buscar Facebook del negocio
    fb_results = ddg_search(f'site:facebook.com "{nombre}" Merida', 5)
    fb_url = ""
    for r in fb_results:
        href = r.get("href", "")
        if "facebook.com" in href and "/posts/" not in href:
            fb_url = href
            break
    
    # PASO 3: Buscar email en snippets de DuckDuckGo
    email_snippets = ddg_search(f'"{nombre}" Merida email "@"', 5)
    for r in email_snippets:
        texto = r.get("title","") + " " + r.get("body","")
        for e in EMAIL_REGEX.findall(texto):
            if ok_email(e) and not lead.get("email"):
                lead["email"] = e.lower()
                stats["found_email"] += 1
    
    # PASO 4: Visitar Instagram si encontramos
    if ig_url and not (lead.get("email") and lead.get("telefono")):
        print(f"IG...", end=" ", flush=True)
        ig_data = scrape_ig_fb(ig_url, page)
        if ig_data["emails"] and not lead.get("email"):
            lead["email"] = ig_data["emails"][0]
            stats["found_email"] += 1
        if ig_data["phones"] and not lead.get("telefono"):
            lead["telefono"] = ig_data["phones"][0]
            stats["found_phone"] += 1
        stats["found_ig"] += 1
    
    # PASO 5: Visitar Facebook si encontramos
    if fb_url and not (lead.get("email") and lead.get("telefono")):
        print(f"FB...", end=" ", flush=True)
        fb_data = scrape_ig_fb(fb_url, page)
        if fb_data["emails"] and not lead.get("email"):
            lead["email"] = fb_data["emails"][0]
            stats["found_email"] += 1
        if fb_data["phones"] and not lead.get("telefono"):
            lead["telefono"] = fb_data["phones"][0]
            stats["found_phone"] += 1
    
    # PASO 6: Buscar website directo
    if not lead.get("email"):
        web_results = ddg_search(f'"{nombre}" Merida Venezuela sitio web', 3)
        for r in web_results:
            href = r.get("href", "")
            if href.startswith("http") and "google" not in href and "facebook" not in href and "instagram" not in href:
                try:
                    page.goto(href, wait_until="domcontentloaded", timeout=8000)
                    page.wait_for_timeout(1500)
                    site_emails = list(set(e.lower() for e in EMAIL_REGEX.findall(page.content()) if ok_email(e)))
                    if site_emails:
                        lead["email"] = site_emails[0]
                        lead["website"] = href
                        stats["found_email"] += 1
                        break
                except:
                    pass
    
    # Resultado
    marker = ""
    if lead.get("email"): marker += "EMAIL "
    if lead.get("telefono"): marker += "TEL "
    if not marker: marker = "---"
    print(marker, flush=True)
    
    # Guardar cada 15
    if (i+1) % 15 == 0:
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        con_em = sum(1 for l in leads if l.get("email"))
        con_tel = sum(1 for l in leads if l.get("telefono"))
        print(f"  === PARCIAL: {con_em} email, {con_tel} tel | IG:{stats['found_ig']} ===", flush=True)
    
    time.sleep(random.uniform(0.3, 0.8))

browser.close()
pw.stop()

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

con_em = sum(1 for l in leads if l.get("email"))
con_tel = sum(1 for l in leads if l.get("telefono"))
print(f"\n{'='*50}")
print(f"FINAL: {len(leads)} leads")
print(f"Con email: {con_em}")
print(f"Con telefono: {con_tel}")
print(f"Instagram encontrados: {stats['found_ig']}")
print(f"Emails nuevos: {stats['found_email']}")
print(f"Telefonos nuevos: {stats['found_phone']}")
