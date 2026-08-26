"""
EXTRACCION RAPIDA - Para cada negocio busca telefono + email en Google
1 busqueda por negocio = ~1.5s = 284 negocios ~7 min
"""
import sys, os, json, time, random, re
from urllib.parse import quote
from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'(\+?58[\s-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}|\d{4}[\s.-]\d{4}|\d{3}[\s.-]\d{3}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","facebook.com","twitter.com",
    "instagram.com","linkedin.com","youtube.com","example.com","localhost","schema.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example"]): return False
    return True

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
    if not nombre or (lead.get("telefono") and lead.get("email")):
        continue
    
    query = quote(f'"{nombre}" Merida Venezuela telefono email contacto')
    print(f"[{i+1}/{len(leads)}] {nombre[:40]}...", end=" ", flush=True)
    
    try:
        page.goto(f"https://www.google.com/search?q={query}&hl=es&gl=ve",
                 wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(random.randint(1200, 2000))
        
        soup = BeautifulSoup(page.content(), "lxml")
        text = soup.get_text(" ", strip=True)
        
        # Telefono
        if not lead.get("telefono"):
            for m in PHONE_REGEX.findall(text):
                t = m.strip()
                if len(t) >= 8:
                    lead["telefono"] = t
                    break
        
        # Email
        if not lead.get("email"):
            for e in EMAIL_REGEX.findall(text):
                if ok_email(e):
                    lead["email"] = e.lower()
                    break
        
        # Website
        if not lead.get("website"):
            for a in soup.select("a"):
                href = a.get("href", "")
                if href.startswith("/url?q="):
                    href = href.split("/url?q=")[1].split("&")[0]
                if href.startswith("http") and "google.com" not in href and "facebook.com" not in href:
                    lead["website"] = href
                    break
        
        marker = ""
        if lead.get("telefono"): marker += "TEL "
        if lead.get("email"): marker += "EMAIL "
        if not marker: marker = "---"
        print(marker, flush=True)
        
        if lead.get("telefono") or lead.get("email"):
            updated += 1
        
    except Exception as e:
        print(f"err:{str(e)[:25]}", flush=True)
    
    time.sleep(random.uniform(0.5, 1.0))
    
    if (i+1) % 25 == 0:
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        con_tel = sum(1 for l in leads if l.get("telefono"))
        con_em = sum(1 for l in leads if l.get("email"))
        print(f"  === PARCIAL: {con_tel} tel, {con_em} email ===", flush=True)

browser.close()
pw.stop()

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

con_tel = sum(1 for l in leads if l.get("telefono"))
con_em = sum(1 for l in leads if l.get("email"))
print(f"\n=== FINAL: {len(leads)} leads, {con_tel} tel, {con_em} email ===")
