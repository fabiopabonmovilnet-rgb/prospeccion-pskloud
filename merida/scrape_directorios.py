"""
PARTE B: Scraping de DIRECTORIOS web de Merida
datosve.com, infoguia.com, gelvez.com.ve
Busca emails + teléfonos de negocios
"""
import json, re, time, httpx
from bs4 import BeautifulSoup

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

def scrape_url(url):
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True, 
                     headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        if r.status_code == 200:
            return r.text
    except: pass
    return ""

def find_emails(html):
    return list(set(e.lower() for e in EMAIL_REGEX.findall(html) if ok_email(e)))

def find_phones(text):
    phones = []
    patterns = [
        r'(\+58\s?4\d{2}[\s.-]?\d{3}[\s.-]?\d{4})',
        r'(\+58\s?2\d{2}[\s.-]?\d{3}[\s.-]?\d{4})',
        r'(\d{4}[\s.-]\d{4})',
        r'(\d{3}[\s.-]\d{3}[\s.-]\d{4})',
    ]
    for pat in patterns:
        phones.extend(re.findall(pat, text))
    return list(set(phones))

all_businesses = []

# === FUENTE 1: datosve.com ===
print("=== FUENTE 1: datosve.com ===")
sectores = ["comercio","retail","alimentos","salud","educacion","servicios","construccion","turismo","tecnologia"]
for sector in sectores:
    url = f"https://datosve.com/empresas/merida?sector={sector}"
    html = scrape_url(url)
    if html:
        soup = BeautifulSoup(html, "lxml")
        # Buscar cards/items de empresas
        for item in soup.select(".empresa, .card, .list-item, tr, .item"):
            text = item.get_text(" ", strip=True)
            emails = find_emails(str(item))
            phones = find_phones(text)
            # Extraer nombre
            name_el = item.select_one("h3, h4, .name, .title, a")
            name = name_el.get_text(strip=True) if name_el else ""
            if name and len(name) > 3:
                all_businesses.append({
                    "nombre": name,
                    "email": emails[0] if emails else "",
                    "telefono": phones[0] if phones else "",
                    "fuente": "datosve.com",
                })
    time.sleep(0.5)

print(f"  datosve.com: {len(all_businesses)} negocios")

# === FUENTE 2: infoguia.com ===
print("=== FUENTE 2: infoguia.com ===")
rubros_infoguia = [
    "farmacia","restaurante","hotel","supermercado","clinica",
    "taller-mecanico","ferreteria","panaderia","belleza","gimnasio",
    "veterinaria","colegio","contador","abogado","constructora",
    "distribuidora","auto-partes","joyeria","optica","inmobiliaria",
]
for rubro in rubros_infoguia:
    url = f"https://infoguia.com/ct.asp?key={rubro}-merida&cat=2&ciud=91"
    html = scrape_url(url)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".resultado, .listado-item, .empresa-item, .card"):
            text = item.get_text(" ", strip=True)
            emails = find_emails(str(item))
            phones = find_phones(text)
            name_el = item.select_one("h3, h4, .nombre, a")
            name = name_el.get_text(strip=True) if name_el else ""
            if name and len(name) > 3:
                all_businesses.append({
                    "nombre": name,
                    "email": emails[0] if emails else "",
                    "telefono": phones[0] if phones else "",
                    "fuente": "infoguia.com",
                })
    time.sleep(0.5)

print(f"  infoguia: +{sum(1 for b in all_businesses if b['fuente']=='infoguia.com')} negocios")

# === FUENTE 3: gelvez.com.ve ===
print("=== FUENTE 3: gelvez.com.ve ===")
html = scrape_url("https://gelvez.com.ve/merida/guia.html")
if html:
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select("li, tr, .item, .entry"):
        text = item.get_text(" ", strip=True)
        emails = find_emails(str(item))
        phones = find_phones(text)
        if phones or emails:
            name = text[:60]
            all_businesses.append({
                "nombre": name,
                "email": emails[0] if emails else "",
                "telefono": phones[0] if phones else "",
                "fuente": "gelvez.com.ve",
            })

print(f"  gelvez: +{sum(1 for b in all_businesses if b['fuente']=='gelvez.com.ve')} negocios")

# === FUENTE 4: listadocomercial.com ===
print("=== FUENTE 4: listadocomercial.com ===")
html = scrape_url("https://www.listadocomercial.com/empresa/merida/")
if html:
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".company, .listing, .result, article"):
        text = item.get_text(" ", strip=True)
        emails = find_emails(str(item))
        phones = find_phones(text)
        name_el = item.select_one("h2, h3, .name, a")
        name = name_el.get_text(strip=True) if name_el else ""
        if name and len(name) > 3:
            all_businesses.append({
                "nombre": name,
                "email": emails[0] if emails else "",
                "telefono": phones[0] if phones else "",
                "fuente": "listadocomercial.com",
            })

print(f"  listadocomercial: +{sum(1 for b in all_businesses if b['fuente']=='listadocomercial.com')} negocios")

# Guardar
out = r"C:\Users\fabio\prospeccion-pskloud\merida\directorio_empresas.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(all_businesses, f, ensure_ascii=False, indent=2)

con_email = sum(1 for b in all_businesses if b.get("email"))
con_tel = sum(1 for b in all_businesses if b.get("telefono"))
print(f"\n=== TOTAL: {len(all_businesses)} negocios, {con_tel} con telefono, {con_email} con email ===")
