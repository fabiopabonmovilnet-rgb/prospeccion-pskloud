"""
PARTE A: Extraer TELEFONOS de Google Maps para negocios ya encontrados
Busca cada nombre en Maps y saca telefono del panel lateral
"""
import sys, os, json, time, random, re
from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")
from phone_utils import normalizar_telefono_ve

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
BAD = {"sentry.io","wixpress.com","google.com","facebook.com","twitter.com",
    "instagram.com","linkedin.com","youtube.com","example.com","localhost"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example"]): return False
    return True

def extract_emails(html):
    return list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))

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

updated = 0
for i, lead in enumerate(leads):
    nombre = lead.get("nombre", "")
    if not nombre or lead.get("telefono"):
        continue
    
    print(f"[{i+1}/{len(leads)}] {nombre[:45]}...", end=" ", flush=True)
    
    try:
        from urllib.parse import quote
        page.goto(f'https://www.google.com/maps/search/{quote(nombre + " Merida Venezuela")}',
                 wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(random.randint(2000, 3500))
        
        html = page.content()
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        
        # Buscar telefono
        phone_patterns = [
            r'(\+58\s?4\d{2}[\s.-]?\d{3}[\s.-]?\d{4})',
            r'(\+58\s?2\d{2}[\s.-]?\d{3}[\s.-]?\d{4})',
            r'(\d{4}[\s.-]\d{4})',
            r'(\d{3}[\s.-]\d{3}[\s.-]\d{4})',
            r'(\(\d{4}\)\s?\d{3}[\s.-]?\d{4})',
        ]
        telefono = ""
        for pat in phone_patterns:
            m = re.search(pat, text)
            if m:
                telefono = normalizar_telefono_ve(m.group(1))
                if telefono:
                    break
        
        # Buscar email en el panel
        emails = extract_emails(html)
        
        # Buscar website
        website = ""
        for a in soup.select('a[data-item-id="authority"]'):
            href = a.get("href", "")
            if href.startswith("http") and "google.com" not in href:
                website = href
                break
        
        if telefono:
            lead["telefono"] = telefono
            updated += 1
            print(f"TEL: {telefono}", flush=True)
        else:
            print("sin tel", flush=True)
        
        if emails and not lead.get("email"):
            lead["email"] = emails[0]
        
        if website and not lead.get("website"):
            lead["website"] = website
        
    except Exception as e:
        print(f"error: {str(e)[:30]}", flush=True)
    
    time.sleep(random.uniform(0.8, 1.5))
    
    if (i+1) % 20 == 0:
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        con_tel = sum(1 for l in leads if l.get("telefono"))
        print(f"  --- PARCIAL: {con_tel} con telefono ---", flush=True)

browser.close()
pw.stop()

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

con_tel = sum(1 for l in leads if l.get("telefono"))
con_email = sum(1 for l in leads if l.get("email"))
print(f"\n=== FINAL: {len(leads)} leads, {con_tel} con telefono, {con_email} con email ===")
