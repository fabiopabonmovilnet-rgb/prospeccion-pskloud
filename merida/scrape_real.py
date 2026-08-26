"""
SCRAPER REAL - Google Maps + websites para Merida, Venezuela
Solo fuentes verificadas: Google Maps listings + websites de negocios
"""
import sys, os, json, time, random, re
from bs4 import BeautifulSoup
from urllib.parse import quote

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
BAD = {"sentry.io","wixpress.com","google.com","facebook.com","twitter.com",
    "instagram.com","linkedin.com","youtube.com","example.com","localhost",
    "wordpress.org","w3.org","schema.org","googleapis.com","gstatic.com",
    "cloudflare.com","tiktok.com","nytimes.com","booking.com","airbnb.com"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example","abuse","postmaster"]): return False
    return True

def extract_emails_from_html(html):
    return list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    viewport={"width":1920,"height":1080}, locale="es-VE", timezone_id="America/Caracas"
)
ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')
page = ctx.new_page()

RUBROS = ["farmacia", "restaurante", "panaderia", "hotel", "clinica", 
          "taller mecanico", "ferreteria", "supermercado", "salon de belleza",
          "gimnasio", "veterinaria", "colegio privado", "contador", "abogado",
          "constructora", "distribuidora", "auto partes", "joyeria", "optica",
          "inmobiliaria", "agencia de viajes", "academia de idiomas", "bar",
          "pizzeria", "cafeteria", "heladeria", "libreria", "transporte", "seguros"]

all_leads = []
seen_names = set()

for rubro in RUBROS:
    query = f"{rubro} Merida Venezuela"
    print(f"\n[{rubro.upper()}]", flush=True)
    
    try:
        page.goto(f"https://www.google.com/maps/search/{query.replace(' ', '+')}", 
                  wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(random.randint(2500, 4000))
        
        feed = page.query_selector('div[role="feed"]')
        if feed:
            for _ in range(3):
                feed.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(1500)
        
        soup = BeautifulSoup(page.content(), "lxml")
        
        names = []
        for el in soup.select(".qBF1Pd, .NrDZNb, .fontHeadlineSmall"):
            name = el.get_text(strip=True)
            if name and len(name) > 3 and name.lower() not in seen_names:
                names.append(name)
                seen_names.add(name.lower())
        
        print(f"  Negocios: {len(names)}", flush=True)
        
        for name in names[:25]:
            email = ""
            website = ""
            
            try:
                page.goto(f'https://www.google.com/search?q={quote(f"{name} Merida Venezuela email contacto")}&hl=es&gl=ve',
                         wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(random.randint(1000, 2000))
                search_html = page.content()
                
                emails = extract_emails_from_html(search_html)
                
                for a in BeautifulSoup(search_html, "lxml").select("a"):
                    href = a.get("href", "")
                    if href.startswith("http") and "google.com" not in href and "facebook.com" not in href and "instagram.com" not in href:
                        website = href
                        break
                
                if website and not emails:
                    try:
                        page.goto(website, wait_until="domcontentloaded", timeout=10000)
                        page.wait_for_timeout(1500)
                        emails = extract_emails_from_html(page.content())
                    except:
                        pass
                
                email = emails[0] if emails else ""
            except:
                pass
            
            marker = "EMAIL" if email else "---"
            print(f"    {name[:40]:40s} {marker} {email}", flush=True)
            
            all_leads.append({
                "nombre": name, "rubro": rubro, "municipio": "Libertador",
                "telefono": "", "email": email, "website": website,
                "fuente": "google_maps", "estado_contacto": "No Contactado",
            })
            
            time.sleep(random.uniform(0.8, 1.5))
    
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
    
    out = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)
    
    con_email = sum(1 for l in all_leads if l.get("email"))
    print(f"  PARCIAL: {len(all_leads)} leads, {con_email} con email", flush=True)

browser.close()
pw.stop()

con_email = sum(1 for l in all_leads if l.get("email"))
print(f"\n=== FINAL: {len(all_leads)} leads, {con_email} con email ===")
