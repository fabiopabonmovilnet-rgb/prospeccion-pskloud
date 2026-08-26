"""
SCRAPEADOR EN CASCADA - Mérida, Venezuela
Cada lead pasa por TODOS los métodos hasta agotar opciones.
Guarda: completos (email+tel), parciales (solo email o solo tel), descartados.
Teléfonos truncados se buscan con métodos adicionales.
"""
import sys, os, json, time, random, re

sys.path.insert(0, r"C:\Users\fabio\prospeccion-pskloud\merida")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
PHONE_ANY = re.compile(r'(\d{4}[\s.-]?\d{3,4}[\s.-]?\d{3,4})')
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
        time.sleep(2)
        return []

def scrape_page(url, page):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(random.randint(1000, 2000))
        html = page.content()
        emails = list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))
        phones = []
        for t in PHONE_FULL.findall(html):
            if es_telefono_valido(t):
                phones.append(t)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        bio = meta.get("content", "") if meta else ""
        if bio:
            emails.extend([e.lower() for e in EMAIL_REGEX.findall(bio) if ok_email(e)])
            for t in PHONE_FULL.findall(bio):
                if es_telefono_valido(t):
                    phones.append(t)
        return emails, phones
    except:
        return [], []


def busqueda_cascada(nombre, rubro, municipio, page):
    email = ""
    telefono = ""
    website = ""
    fuente = ""

    # METODO 1: DDG snippets
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

    # METODO 2: Instagram
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

    # METODO 3: Facebook
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

    # METODO 4: Website directo
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

    # METODO 5: Busqueda complementaria si falta telefono o email
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

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    viewport={"width":1920,"height":1080}, locale="es-VE", timezone_id="America/Caracas"
)
ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')
page = ctx.new_page()

completos = []
parciales_email = []
parciales_tel = []
descartados = []

print(f"Procesando {len(leads)} negocios de Merida...")
print(f"Cascada: DDG -> Instagram -> Facebook -> Website -> Complemento")
print(f"Guarda: completos + parciales (email o telefono)\n")

for i, lead in enumerate(leads):
    nombre = lead.get("nombre", "")
    rubro = lead.get("rubro", "")
    municipio = lead.get("municipio", "Libertador")

    if not nombre:
        continue

    email_actual = lead.get("email", "").strip()
    tel_actual = lead.get("telefono", "").strip()

    if email_actual and tel_actual and es_telefono_valido(tel_actual):
        completos.append(lead)
        print(f"[{i+1}/{len(leads)}] {nombre[:40]}... YA COMPLETO, saltando", flush=True)
        continue

    print(f"[{i+1}/{len(leads)}] {nombre[:40]}...", end=" ", flush=True)

    email, telefono, website, fuente = busqueda_cascada(nombre, rubro, municipio, page)

    if email and not email_actual:
        lead["email"] = email
    if telefono and not tel_actual:
        lead["telefono"] = normalizar_tel(telefono) if not es_telefono_valido(telefono) else telefono
    if website:
        lead["website"] = website
    if fuente:
        lead["fuente_contacto"] = fuente
    lead["estado_contacto"] = lead.get("estado_contacto", "No Contactado")

    final_email = lead.get("email", "").strip()
    final_tel = lead.get("telefono", "").strip()
    tel_ok = es_telefono_valido(final_tel) if final_tel else False

    if final_email and tel_ok:
        completos.append(lead)
        print(f"COMPLETO ({fuente}) {final_email} {final_tel}", flush=True)
    elif final_email and not tel_ok:
        parciales_email.append(lead)
        print(f"PARCIAL-EMAIL ({fuente}) {final_email} tel:{final_tel or 'incompleto'}", flush=True)
    elif tel_ok and not final_email:
        parciales_tel.append(lead)
        print(f"PARCIAL-TEL ({fuente}) tel:{final_tel} sin email", flush=True)
    else:
        descartados.append({"nombre": nombre, "rubro": rubro, "razon": "sin datos"})
        print(f"DESCARTADO (sin datos)", flush=True)

    if (i+1) % 20 == 0:
        with open(r"C:\Users\fabio\prospeccion-pskloud\merida\leads_completos.json", "w", encoding="utf-8") as f:
            json.dump(completos, f, ensure_ascii=False, indent=2)
        with open(r"C:\Users\fabio\prospeccion-pskloud\merida\leads_parciales.json", "w", encoding="utf-8") as f:
            json.dump(parciales_email + parciales_tel, f, ensure_ascii=False, indent=2)
        print(f"\n  === PARCIAL: {len(completos)} completos, {len(parciales_email)} solo-email, {len(parciales_tel)} solo-tel, {len(descartados)} descartados ===\n", flush=True)

    time.sleep(random.uniform(0.3, 0.7))

browser.close()
pw.stop()

with open(r"C:\Users\fabio\prospeccion-pskloud\merida\leads_completos.json", "w", encoding="utf-8") as f:
    json.dump(completos, f, ensure_ascii=False, indent=2)
with open(r"C:\Users\fabio\prospeccion-pskloud\merida\leads_parciales.json", "w", encoding="utf-8") as f:
    json.dump(parciales_email + parciales_tel, f, ensure_ascii=False, indent=2)
with open(r"C:\Users\fabio\prospeccion-pskloud\merida\leads_descartados.json", "w", encoding="utf-8") as f:
    json.dump(descartados, f, ensure_ascii=False, indent=2)

print(f"\n{'='*50}")
print(f"RESULTADO FINAL:")
print(f"  Completos (email + telefono): {len(completos)}")
print(f"  Parciales solo email:         {len(parciales_email)}")
print(f"  Parciales solo telefono:      {len(parciales_tel)}")
print(f"  Descartados (sin datos):      {len(descartados)}")
total = len(completos) + len(parciales_email) + len(parciales_tel) + len(descartados)
util = len(completos) + len(parciales_email) + len(parciales_tel)
print(f"  Utilizables: {util}/{total} ({util*100//max(total,1)}%)")
print(f"{'='*50}")
