"""
SCRAPER RÁPIDO - Solo DDG, sin Playwright. Busca negocios y extrae email/tel de snippets.
Uso: python fast_scrape.py "constructora"
     python fast_scrape.py "constructora" "clinica" "distribuidora"
"""
import sys, os, json, time, random, re

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD_DOMAINS = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","tiktok.com","apple.com","microsoft.com"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5:
        return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD_DOMAINS:
        return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example","abuse","postmaster"]):
        return False
    return True

def es_telefono_ve(t):
    d = re.sub(r'[^\d]', '', t)
    if len(d) == 11 and d.startswith("0"):
        return d[:4] in ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276")
    if len(d) == 12 and d.startswith("58"):
        return d[2:6] in ("412","414","416","424","426","413","415","417","274","271","275","276")
    if len(d) == 10 and d.startswith("58"):
        return d[2:6] in ("412","414","416","424","426","413","415","417","274","271","275","276")
    return False

def ddg(query, n=10):
    try:
        from ddgs import DDGS
    except:
        from duckduckgo_search import DDGS
    try:
        with DDGS() as d:
            return list(d.text(query, region="ve-ve", max_results=n))
    except Exception as ex:
        print(f"  [DDG error: {str(ex)[:50]}]")
        time.sleep(5)
        return []

def buscar_negocios(rubro):
    negocios = []
    seen = set()
    queries = [
        f'{rubro} Merida Venezuela email telefono',
        f'{rubro} en Merida Venezuela lista',
        f'mejores {rubro} Merida',
        f'{rubro} Merida opiniones',
        f'{rubro} Merida Venezuela direccion',
        f'{rubro} Merida WhatsApp',
        f'{rubro} Merida correo electronico',
        f'{rubro} Merida Venezuela contactos',
    ]
    for q in queries:
        results = ddg(q, 10)
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            texto = f"{title} {body}"
            partes = re.split(r'[\-|–—:]', title)
            for p in partes:
                p = p.strip()
                if any(x in p.lower() for x in ["merida","venezuela","google","maps","opiniones","reviews","facebook","instagram","wikipedia","gov","twitter"]):
                    continue
                if len(p) > 5 and len(p) < 60 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen:
                        seen.add(norm)
                        negocios.append({
                            "nombre": p.strip(),
                            "snippet": body[:300],
                            "url": href,
                        })
        time.sleep(random.uniform(0.5, 1.5))
    return negocios

def extraer_email_tel(texto):
    email = ""
    tel = ""
    for e in EMAIL_REGEX.findall(texto):
        if ok_email(e):
            email = e.lower().strip()
            break
    for t in PHONE_FULL.findall(texto):
        if es_telefono_ve(t):
            tel = t
            break
    return email, tel

def buscar_contactos(nombre, snippet):
    email, tel = extraer_email_tel(snippet)
    
    queries_extra = [
        f'"{nombre}" Merida email correo',
        f'"{nombre}" Merida telefono WhatsApp',
        f'"{nombre}" Merida "@" gmail.com',
        f'"{nombre}" Merida "@" hotmail.com',
        f'"{nombre}" "@" Merida Venezuela',
    ]
    
    if not email:
        for q in queries_extra[:3]:
            for r in ddg(q, 5):
                texto = r.get("title", "") + " " + r.get("body", "")
                e, t = extraer_email_tel(texto)
                if e and not email:
                    email = e
                if t and not tel:
                    tel = t
            if email:
                break
            time.sleep(0.3)
    
    if not tel:
        for q in queries_extra[3:]:
            for r in ddg(q, 5):
                texto = r.get("title", "") + " " + r.get("body", "")
                e, t = extraer_email_tel(texto)
                if e and not email:
                    email = e
                if t and not tel:
                    tel = t
            if tel:
                break
            time.sleep(0.3)
    
    if email and not tel:
        dominio = email.split("@")[1]
        for r in ddg(f'"{nombre}" "{dominio}" telefono Merida', 3):
            texto = r.get("title", "") + " " + r.get("body", "")
            _, t = extraer_email_tel(texto)
            if t:
                tel = t
                break
    
    return email, tel

def scrape_rubro(rubro, existing_names, leads):
    print(f"\n{'='*50}")
    print(f"BUSCANDO: {rubro}")
    print(f"{'='*50}")
    
    negocios = buscar_negocios(rubro)
    print(f"  Encontrados {len(negocios)} nombres de negocios")
    
    nuevos = 0
    completos = 0
    
    for i, neg in enumerate(negocios):
        nombre = neg["nombre"]
        if nombre.lower().strip() in existing_names:
            continue
        
        email, tel = buscar_contactos(nombre, neg.get("snippet", ""))
        
        lead = {
            "nombre": nombre,
            "rubro": rubro,
            "municipio": "Libertador",
            "estado_contacto": "No Contactado",
        }
        if email:
            lead["email"] = email
        if tel:
            lead["telefono"] = tel
        if neg.get("url"):
            lead["fuente_contacto"] = "ddg"
        
        tiene_email = bool(lead.get("email", "").strip())
        tiene_tel = bool(lead.get("telefono", "").strip())
        
        if tiene_email or tiene_tel:
            leads.append(lead)
            existing_names.add(nombre.lower().strip())
            nuevos += 1
            if tiene_email and tiene_tel:
                completos += 1
                print(f"  [{nuevos}] {nombre[:35]} COMPLETO  {lead.get('email','')}  {lead.get('telefono','')}")
            elif tiene_email:
                print(f"  [{nuevos}] {nombre[:35]} EMAIL  {lead.get('email','')}")
            else:
                print(f"  [{nuevos}] {nombre[:35]} TEL  {lead.get('telefono','')}")
        
        time.sleep(random.uniform(0.3, 0.8))
    
    print(f"\n  RESULTADO {rubro}: {nuevos} nuevos ({completos} completos)")
    return nuevos


if __name__ == "__main__":
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    
    with open(leads_file, encoding="utf-8", errors="replace") as f:
        leads = json.load(f)
    
    existing_names = set(l.get("nombre", "").lower().strip() for l in leads)
    initial = len(leads)
    print(f"Leads actuales: {initial}")
    
    rubros = sys.argv[1:] if len(sys.argv) > 1 else [
        "constructora",
        "clinica privada",
        "distribuidora",
        "inmobiliaria",
        "abogado despacho legal",
    ]
    
    total_nuevos = 0
    for rubro in rubros:
        nuevos = scrape_rubro(rubro, existing_names, leads)
        total_nuevos += nuevos
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        print(f"  Guardado: {len(leads)} leads totales")
    
    print(f"\n{'='*50}")
    print(f"RESUMEN FINAL:")
    print(f"  Leads iniciales: {initial}")
    print(f"  Leads nuevos: {total_nuevos}")
    print(f"  Leads totales: {len(leads)}")
    print(f"  Rubros procesados: {', '.join(rubros)}")
