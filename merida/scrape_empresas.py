"""
EMPRESAS MEDIANAS Y GRANDES - Mérida, Venezuela
Busca empresas industriales, comerciales grandes, hoteles, clínicas, universidades, etc.
Enfocado en obtener email + teléfono para contacto por WhatsApp Business o llamada fría.
"""
import sys, os, json, time, random, re

sys.stdout.reconfigure(encoding='utf-8')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    if any(x in p[0] for x in ["noreply","no-reply","test","example","abuse","postmaster","support"]): return False
    return True

def es_tel(t):
    d = re.sub(r'[^\d]', '', t)
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276",
                "412","414","416","424","426","413","415","417","274","271","275","276")
    if len(d) == 11 and d.startswith("0"):
        return d[:4] in prefixes
    if len(d) == 12 and d.startswith("58"):
        return d[2:6] in prefixes
    if len(d) == 10 and d.startswith("58"):
        return d[2:6] in prefixes
    return False

def ddg(query, n=10):
    try:
        from ddgs import DDGS
    except:
        from duckduckgo_search import DDGS
    for attempt in range(3):
        try:
            with DDGS() as d:
                return list(d.text(query, region="ve-ve", max_results=n))
        except Exception as ex:
            wait = 5 * (attempt + 1)
            print(f"  DDG retry {attempt+1}/3, waiting {wait}s...", flush=True)
            time.sleep(wait)
    return []

def extract(texto):
    email, tel = "", ""
    for e in EMAIL_REGEX.findall(texto):
        if ok_email(e):
            email = e.lower().strip()
            break
    for t in PHONE_FULL.findall(texto):
        if es_tel(t):
            tel = t
            break
    return email, tel

# ==================== SECTORES EMPRESARIALES ====================
SECTORES = {
    "industria": [
        "empresa industrial Merida Venezuela",
        "fabrica Merida Venezuela",
        "manufactura Merida Venezuela",
        "industria alimentaria Merida",
        "industria textil Merida",
        "industria quimica Merida",
        "planta industrial Merida Venezuela",
        "empresa productora Merida",
    ],
    "construccion_inmobiliaria": [
        "constructora grande Merida Venezuela",
        "empresa constructora Merida",
        "inmobiliaria Merida Venezuela",
        "desarrolladora inmobiliaria Merida",
        "empresa de construccion Merida",
        "promotora inmobiliaria Merida Venezuela",
    ],
    "comercio_mayorista": [
        "distribuidora Merida Venezuela",
        "empresa distribuidora Merida",
        "mayorista Merida Venezuela",
        "comercializadora Merida Venezuela",
        "importadora Merida Venezuela",
        "exportadora Merida Venezuela",
        "empresa de comercio exterior Merida",
    ],
    "turismo_hoteleria": [
        "hotel grande Merida Venezuela",
        "cadena hotelera Merida",
        "empresa turistica Merida",
        "hospedaje Merida Venezuela empresas",
        "posada grande Merida",
        "boutique hotel Merida",
        "empresa de turismo Merida Venezuela",
    ],
    "salud": [
        "clinica grande Merida Venezuela",
        "hospital privado Merida",
        "laboratorio clinico Merida Venezuela",
        "empresa farmaceutica Merida",
        "centro medico Merida Venezuela",
        "empresa de salud Merida",
        "clínica especializada Merida Venezuela",
    ],
    "educacion": [
        "universidad Merida Venezuela",
        "instituto universitario Merida",
        "colegio privado grande Merida",
        "academia Merida Venezuela empresas",
        "empresa educativa Merida Venezuela",
        "universidad privada Merida Venezuela",
    ],
    "servicios_profesionales": [
        "empresa de consultoria Merida Venezuela",
        "firma de abogados Merida",
        "despacho legal Merida Venezuela",
        "empresa de auditoria Merida",
        "empresa de contabilidad Merida Venezuela",
        "consultora empresarial Merida",
        "empresa de recursos humanos Merida",
    ],
    "tecnologia": [
        "empresa de tecnologia Merida Venezuela",
        "empresa de software Merida Venezuela",
        "empresa de informatica Merida",
        "empresa de sistemas Merida Venezuela",
        "empresa de telecomunicaciones Merida",
        "empresa IT Merida Venezuela",
    ],
    "transporte_logistica": [
        "empresa de transporte Merida Venezuela",
        "empresa de logistica Merida Venezuela",
        "transporte de carga Merida",
        "empresa de encomiendas Merida Venezuela",
        "empresa de mudanza Merida",
        "flota de transporte Merida",
    ],
    "energia": [
        "empresa de energia Merida Venezuela",
        "empresa electrica Merida Venezuela",
        "empresa de services electricos Merida",
        "empresa de climatizacion Merida Venezuela",
        "empresa de aire acondicionado Merida",
    ],
    "retail_grande": [
        "tienda grande Merida Venezuela",
        "cadena de tiendas Merida",
        "supermercado grande Merida Venezuela",
        "centro comercial Merida empresas",
        "empresa de retail Merida Venezuela",
    ],
    "agroindustria": [
        "empresa agricola Merida Venezuela",
        "empresa agroindustrial Merida",
        "empresa ganadera Merida Venezuela",
        "empresa avicola Merida",
        "empresa porcicola Merida Venezuela",
        "empresa lechera Merida",
    ],
    "medios_comunicacion": [
        "empresa de medios Merida Venezuela",
        "radio Merida Venezuela empresa",
        "empresa de publicidad Merida Venezuela",
        "agencia de publicidad Merida",
        "empresa de marketing Merida Venezuela",
        "empresa de comunicaciones Merida",
    ],
}

def scrape_sector(nombre_sector, queries, existing_names, leads):
    print(f"\n{'='*50}", flush=True)
    print(f"SECTOR: {nombre_sector.upper()}", flush=True)
    print(f"{'='*50}", flush=True)
    
    all_results = []
    for q in queries:
        print(f"  Buscando: {q[:50]}...", end=" ", flush=True)
        results = ddg(q, 10)
        print(f"-> {len(results)}", flush=True)
        all_results.extend(results)
        time.sleep(random.uniform(3, 6))
    
    # Extract business names + contacts from snippets
    negocios = []
    seen = set()
    for r in all_results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        texto = f"{title} {body}"
        
        email, tel = extract(texto)
        
        partes = re.split(r'[\-|–—:]', title)
        for p in partes:
            p = p.strip()
            if any(x in p.lower() for x in ["merida","venezuela","google","maps","opiniones","facebook","instagram","gov","twitter","wikipedia","buscar"]):
                continue
            if len(p) > 5 and len(p) < 60 and not p.startswith("http"):
                norm = p.lower().strip()
                if norm not in seen:
                    seen.add(norm)
                    negocios.append({
                        "nombre": p,
                        "email": email,
                        "telefono": tel,
                        "url": href,
                        "snippet": body[:300],
                    })
    
    print(f"\n  Negocios encontrados: {len(negocios)}", flush=True)
    
    nuevos = 0
    for neg in negocios:
        nombre = neg["nombre"]
        if nombre.lower().strip() in existing_names:
            continue
        
        email = neg.get("email", "")
        tel = neg.get("telefono", "")
        
        # If no email/tel in snippet, try targeted search
        if not email or not tel:
            for q_extra in [f'"{nombre}" Merida email correo', f'"{nombre}" Merida telefono WhatsApp']:
                for r in ddg(q_extra, 5):
                    texto = r.get("title","") + " " + r.get("body","")
                    e2, t2 = extract(texto)
                    if e2 and not email: email = e2
                    if t2 and not tel: tel = t2
                if email and tel:
                    break
                time.sleep(random.uniform(2, 4))
        
        lead = {
            "nombre": nombre,
            "rubro": nombre_sector,
            "municipio": "Libertador",
            "estado_contacto": "No Contactado",
            "tipo_empresa": "mediana-grande",
        }
        if email: lead["email"] = email
        if tel: lead["telefono"] = tel
        if neg.get("url"): lead["fuente_contacto"] = "ddg"
        if neg.get("snippet"): lead["notas"] = neg["snippet"][:200]
        
        tiene = bool(lead.get("email","").strip()) or bool(lead.get("telefono","").strip())
        if tiene:
            leads.append(lead)
            existing.add(nombre.lower().strip())
            nuevos += 1
            tipo = "AMBOS" if (email and tel) else ("EMAIL" if email else "TEL")
            print(f"    [{nuevos}] {nombre[:40]} {tipo}  {email[:30]}  {tel}", flush=True)
        
        time.sleep(random.uniform(1, 3))
    
    print(f"\n  RESULTADO {nombre_sector}: {nuevos} nuevos leads", flush=True)
    return nuevos

if __name__ == "__main__":
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    existing = set(l.get("nombre","").lower().strip() for l in leads)
    initial = len(leads)
    
    print(f"Leads actuales: {initial}", flush=True)
    print(f"Sectores a buscar: {len(SECTORES)}", flush=True)
    
    # Process specified sectors or all
    if len(sys.argv) > 1:
        sector_keys = sys.argv[1:]
    else:
        sector_keys = list(SECTORES.keys())
    
    total_nuevos = 0
    for sector_key in sector_keys:
        if sector_key in SECTORES:
            nuevos = scrape_sector(sector_key, SECTORES[sector_key], existing, leads)
            total_nuevos += nuevos
            # Save after each sector
            with open(leads_file, "w", encoding="utf-8") as f:
                json.dump(leads, f, ensure_ascii=False, indent=2)
            print(f"  Guardado: {len(leads)} leads totales", flush=True)
        else:
            print(f"  Sector '{sector_key}' no encontrado", flush=True)
    
    print(f"\n{'='*50}", flush=True)
    print(f"RESUMEN FINAL:", flush=True)
    print(f"  Leads iniciales: {initial}", flush=True)
    print(f"  Leads nuevos: {total_nuevos}", flush=True)
    print(f"  Leads totales: {len(leads)}", flush=True)
