"""
RE-SCRAPER DE CONTACTOS - Busca email/teléfono para leads que les falta
Toma leads sin email o sin teléfono válido y les ejecuta la cascada completa.
Actualiza leads.json directamente.
"""
import sys, os, json, time, random, re

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example"]): return False
    return True

def es_telefono_valido(t):
    digits = re.sub(r'[^\d]', '', t)
    return len(digits) >= 10

def normalizar_tel(texto):
    digits = re.sub(r'[^\d]', '', texto)
    if len(digits) == 8 and digits.startswith("0"):
        digits = "58" + digits
    if len(digits) == 10 and not digits.startswith("58"):
        digits = "58" + digits
    if len(digits) == 11 and digits.startswith("0"):
        digits = "58" + digits[1:]
    return f"+{digits}" if len(digits) >= 10 else ""

def ddg(query, n=8):
    try:
        from ddgs import DDGS
    except:
        from duckduckgo_search import DDGS
    try:
        with DDGS() as d:
            return list(d.text(query, region="ve-ve", max_results=n))
    except Exception:
        time.sleep(3)
        return []

def scrape_page(url, page):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(random.randint(1000, 2000))
        html = page.content()
        emails = list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))
        phones = [t for t in PHONE_FULL.findall(html) if es_telefono_valido(t)]
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        bio = meta.get("content", "") if meta else ""
        if bio:
            emails.extend([e.lower() for e in EMAIL_REGEX.findall(bio) if ok_email(e)])
            phones.extend([t for t in PHONE_FULL.findall(bio) if es_telefono_valido(t)])
        return emails, phones
    except:
        return [], []

def busqueda_cascada(nombre, rubro, municipio, page):
    email = ""
    telefono = ""
    website = ""
    fuente = ""

    queries = [
        f'"{nombre}" Merida Venezuela email telefono',
        f'"{nombre}" Merida "@" gmail.com',
        f'"{nombre}" Merida "@" hotmail.com',
    ]
    for q in queries:
        for r in ddg(q, 8):
            texto = r.get("title", "") + " " + r.get("body", "")
            if not email:
                for e in EMAIL_REGEX.findall(texto):
                    if ok_email(e):
                        email = e.lower()
                        break
            if not telefono:
                for t in PHONE_FULL.findall(texto):
                    if es_telefono_valido(t):
                        telefono = t
                        break
        if email and telefono:
            return email, telefono, "", "ddg_snippets"

    ig_results = ddg(f'site:instagram.com "{nombre}" Merida', 5)
    for r in ig_results:
        href = r.get("href", "")
        if "instagram.com" in href and "/p/" not in href:
            ig_emails, ig_phones = scrape_page(href, page)
            if ig_emails and not email:
                email = ig_emails[0]
            if ig_phones and not telefono:
                telefono = ig_phones[0]
            fuente = "instagram"
            if email and telefono:
                return email, telefono, href, fuente
            break

    fb_results = ddg(f'site:facebook.com "{nombre}" Merida', 5)
    for r in fb_results:
        href = r.get("href", "")
        if "facebook.com" in href and "/posts/" not in href:
            fb_emails, fb_phones = scrape_page(href, page)
            if fb_emails and not email:
                email = fb_emails[0]
            if fb_phones and not telefono:
                telefono = fb_phones[0]
            fuente = "facebook"
            if email and telefono:
                return email, telefono, href, fuente
            break

    web_results = ddg(f'"{nombre}" Merida Venezuela sitio web', 3)
    for r in web_results:
        href = r.get("href", "")
        if href.startswith("http") and "google" not in href and "facebook" not in href and "instagram" not in href:
            web_emails, web_phones = scrape_page(href, page)
            if web_emails and not email:
                email = web_emails[0]
            if web_phones and not telefono:
                telefono = web_phones[0]
            website = href
            fuente = "website"
            if email and telefono:
                return email, telefono, website, fuente
            break

    if not telefono and email:
        dominio = email.split("@")[1]
        r = ddg(f'"{nombre}" "{dominio}" telefono Merida', 5)
        for res in r:
            texto = res.get("title", "") + " " + res.get("body", "")
            for t in PHONE_FULL.findall(texto):
                if es_telefono_valido(t):
                    telefono = t
                    fuente = "ddg_complemento_tel"
                    break
            if telefono:
                break

    if not email and telefono:
        r = ddg(f'"{nombre}" "{telefono}" email Merida', 5)
        for res in r:
            texto = res.get("title", "") + " " + res.get("body", "")
            for e in EMAIL_REGEX.findall(texto):
                if ok_email(e):
                    email = e.lower()
                    fuente = "ddg_complemento_email"
                    break
            if email:
                break

    return email, telefono, website, fuente


# ==================== MAIN ====================
leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
with open(leads_file, encoding="utf-8", errors="replace") as f:
    leads = json.load(f)

# Filtrar: solo los que les falta email O telefono valido
necesitan = []
for i, l in enumerate(leads):
    tiene_email = bool(l.get("email", "").strip())
    tiene_tel = es_telefono_valido(l.get("telefono", "")) if l.get("telefono") else False
    if not tiene_email or not tiene_tel:
        necesitan.append((i, l, tiene_email, tiene_tel))

print(f"Total leads: {len(leads)}")
print(f"Necesitan re-busqueda: {len(necesitan)}")
print(f"  - Sin email: {sum(1 for _,_,e,t in necesitan if not e)}")
print(f"  - Sin teléfono válido: {sum(1 for _,_,e,t in necesitan if not t)}")
print(f"  - Sin ambos: {sum(1 for _,_,e,t in necesitan if not e and not t)}")
print()

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    viewport={"width":1920,"height":1080}, locale="es-VE", timezone_id="America/Caracas"
)
ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')
page = ctx.new_page()

mejorados = 0
nuevos_completos = 0

for count, (idx, lead, tiene_email, tiene_tel) in enumerate(necesitan):
    nombre = lead.get("nombre", "")
    rubro = lead.get("rubro", "")
    municipio = lead.get("municipio", "Libertador")

    print(f"[{count+1}/{len(necesitan)}] {nombre[:40]}...", end=" ", flush=True)

    email, telefono, website, fuente = busqueda_cascada(nombre, rubro, municipio, page)

    antes_email = lead.get("email", "").strip()
    antes_tel = lead.get("telefono", "").strip()

    if email and not antes_email:
        lead["email"] = email
        lead["fuente_contacto"] = fuente
        mejorados += 1

    if telefono:
        nuevo_tel = normalizar_tel(telefono) if not es_telefono_valido(telefono) else telefono
        if not antes_tel or not es_telefono_valido(antes_tel):
            lead["telefono"] = nuevo_tel
            lead["fuente_contacto"] = fuente
            mejorados += 1

    if website and not lead.get("website"):
        lead["website"] = website

    despues_email = lead.get("email", "").strip()
    despues_tel = lead.get("telefono", "").strip()
    tel_ok = es_telefono_valido(despues_tel) if despues_tel else False

    if despues_email and tel_ok:
        lead["estado_contacto"] = lead.get("estado_contacto", "No Contactado")
        nuevos_completos += 1
        print(f"COMPLETO ({fuente}) {despues_email} {despues_tel}", flush=True)
    elif despues_email and not tel_ok:
        print(f"PARCIAL ({fuente}) email:{despues_email} tel:?", flush=True)
    elif tel_ok and not despues_email:
        print(f"PARCIAL ({fuente}) tel:{despues_tel} sin email", flush=True)
    else:
        print(f"SIN CAMBIOS", flush=True)

    if (count + 1) % 10 == 0:
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        print(f"\n  === Guardado parcial ({count+1}/{len(necesitan)}) ===\n")

    time.sleep(random.uniform(0.3, 0.7))

browser.close()
pw.stop()

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

total_con_email = sum(1 for l in leads if l.get("email", "").strip())
total_con_tel = sum(1 for l in leads if l.get("telefono") and es_telefono_valido(l.get("telefono", "")))
total_ambos = sum(1 for l in leads if l.get("email", "").strip() and l.get("telefono") and es_telefono_valido(l.get("telefono", "")))

print(f"\n{'='*50}")
print(f"RE-BUSQUEDA COMPLETADA:")
print(f"  Leads procesados: {len(necesitan)}")
print(f"  Datos mejorados: {mejorados}")
print(f"  Nuevos completos (email+tel): {nuevos_completos}")
print(f"\nESTADO FINAL:")
print(f"  Total leads: {len(leads)}")
print(f"  Con email: {total_con_email}")
print(f"  Con teléfono válido: {total_con_tel}")
print(f"  Con ambos: {total_ambos}")
print(f"{'='*50}")
