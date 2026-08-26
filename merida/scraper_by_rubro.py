"""
SCRAPER POR RUBRO - Busca negocios de un rubro específico en Mérida, Venezuela
Uso: python scraper_by_rubro.py "agencias de vehiculos"
     python scraper_by_rubro.py "ventas de motos"
     python scraper_by_rubro.py "restaurantes"
"""
import sys, os, json, time, random, re, argparse

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

def buscar_negocios_por_rubro(rubro, page):
    """Busca nombres de negocios de un rubro en Merida usando DDG"""
    negocios = []
    queries = [
        f'{rubro} Merida Venezuela',
        f'{rubro} en Merida Venezuela lista',
        f'mejores {rubro} Merida',
        f'{rubro} Merida opiniones',
        f'{rubro} Merida Venezuela direccion telefono',
    ]
    seen_names = set()
    for q in queries:
        results = ddg(q, 10)
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            texto = f"{title} {body}"
            # Extraer nombres de negocios del titulo y snippet
            # Tipicamente: "Nombre Del Negocio - Merida" o "Nombre Del Negocio | Merida"
            partes = re.split(r'[\-|–—:]', title)
            for p in partes:
                p = p.strip()
                # Quitar strings de contexto
                if any(x in p.lower() for x in ["merida", "venezuela", "google", "maps", "opiniones", "reviews", "facebook", "instagram"]):
                    continue
                if len(p) > 5 and len(p) < 60 and not p.startswith("http"):
                    nombre = p.strip()
                    norm = nombre.lower().strip()
                    if norm not in seen_names:
                        seen_names.add(norm)
                        negocios.append({
                            "nombre": nombre,
                            "rubro": rubro,
                            "municipio": "Libertador",
                            "fuente_busqueda": href,
                            "snippet": body[:200],
                        })
        time.sleep(random.uniform(0.5, 1.5))
    return negocios

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
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper por rubro - Merida, Venezuela")
    parser.add_argument("rubro", help='Rubro a buscar, ej: "agencias de vehiculos"')
    parser.add_argument("--municipio", default="Libertador", help="Municipio (default: Libertador)")
    args = parser.parse_args()

    rubro = args.rubro
    municipio = args.municipio
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"

    with open(leads_file, encoding="utf-8", errors="replace") as f:
        leads = json.load(f)

    existing_names = set(l.get("nombre", "").lower().strip() for l in leads)

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width":1920,"height":1080}, locale="es-VE", timezone_id="America/Caracas"
    )
    ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')
    page = ctx.new_page()

    print(f"=== BUSCANDO: {rubro} en {municipio}, Merida ===")
    print(f"Buscando negocios en DuckDuckGo...")
    negocios = buscar_negocios_por_rubro(rubro, page)
    print(f"Encontrados {len(negocios)} nombres de negocios\n")

    completos = []
    parciales = []

    for i, neg in enumerate(negocios):
        nombre = neg["nombre"]
        if nombre.lower().strip() in existing_names:
            print(f"[{i+1}/{len(negocios)}] {nombre[:40]}... YA EXISTE, saltando")
            continue

        print(f"[{i+1}/{len(negocios)}] {nombre[:40]}...", end=" ", flush=True)

        email, telefono, website, fuente = busqueda_cascada(nombre, rubro, municipio, page)

        lead = {
            "nombre": nombre,
            "rubro": rubro,
            "municipio": municipio,
            "estado_contacto": "No Contactado",
        }
        if email:
            lead["email"] = email
        if telefono:
            lead["telefono"] = normalizar_tel(telefono) if not es_telefono_valido(telefono) else telefono
        if website:
            lead["website"] = website
        if fuente:
            lead["fuente_contacto"] = fuente

        final_email = lead.get("email", "").strip()
        final_tel = lead.get("telefono", "").strip()
        tel_ok = es_telefono_valido(final_tel) if final_tel else False

        if final_email and tel_ok:
            completos.append(lead)
            leads.append(lead)
            existing_names.add(nombre.lower().strip())
            print(f"COMPLETO ({fuente}) {final_email} {final_tel}")
        elif final_email or tel_ok:
            parciales.append(lead)
            leads.append(lead)
            existing_names.add(nombre.lower().strip())
            print(f"PARCIAL ({fuente}) email:{final_email or '-'} tel:{final_tel or '-'}")
        else:
            print(f"SIN DATOS")

        if (i + 1) % 10 == 0:
            with open(leads_file, "w", encoding="utf-8") as f:
                json.dump(leads, f, ensure_ascii=False, indent=2)
            print(f"\n  === Guardado parcial: {len(leads)} leads totales ===\n")

        time.sleep(random.uniform(0.3, 0.7))

    browser.close()
    pw.stop()

    with open(leads_file, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"RESULTADO - {rubro.upper()}:")
    print(f"  Negocios encontrados: {len(negocios)}")
    print(f"  Completos (email+tel): {len(completos)}")
    print(f"  Parciales: {len(parciales)}")
    print(f"  Guardados en leads.json: {len(leads)} total")
    print(f"{'='*50}")
