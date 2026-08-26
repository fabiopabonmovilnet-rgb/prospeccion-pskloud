"""
EMPRESAS MEDIANAS/GRANDES - Ultra-rápido, sin queries extra por lead.
Extrae email/tel directo de snippets DDG.
"""
import sys, os, json, time, random, re

sys.stdout.reconfigure(encoding='utf-8')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com","meneame.es","redalyc.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    blacklist_usernames = {"noreply","no-reply","test","example","abuse","postmaster","support","marketingmx","luzysonidotnt","jdoe"}
    if p[0] in blacklist_usernames: return False
    # Skip generic/directory emails with long usernames
    generic_domains = {"merida.gob.mx","hotmail.com","gmail.com","yahoo.com","outlook.com"}
    if p[1] in generic_domains and len(p[0]) > 15: return False
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
        except:
            time.sleep(5 * (attempt + 1))
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

# ==================== SECTORES ====================
SECTORES = [
    ("empresa_grande_industrial", [
        "empresa industrial Merida Venezuela email telefono",
        "fabrica Merida Venezuela empresas",
        "manufactura Merida Venezuela",
        "industria alimentaria Merida empresas",
        "industria textil Merida Venezuela",
        "empresa productora Merida Venezuela",
        "planta industrial Merida",
    ]),
    ("construccion_inmobiliaria", [
        "constructora grande Merida Venezuela",
        "empresa constructora Merida email",
        "inmobiliaria Merida Venezuela empresas",
        "desarrolladora inmobiliaria Merida",
        "promotora inmobiliaria Merida Venezuela",
    ]),
    ("distribuidora_mayorista", [
        "distribuidora Merida Venezuela empresas",
        "empresa distribuidora Merida email",
        "mayorista Merida Venezuela",
        "comercializadora Merida Venezuela",
        "importadora exportadora Merida Venezuela",
    ]),
    ("turismo_hoteleria_grande", [
        "hotel grande Merida Venezuela empresas",
        "cadena hotelera Merida Venezuela",
        "empresa turistica Merida Venezuela",
        "hoteles Merida Venezuela email telefono",
        "posada grande Merida empresas",
    ]),
    ("salud_grande", [
        "clinica grande Merida Venezuela empresas",
        "hospital privado Merida Venezuela",
        "laboratorio clinico Merida Venezuela empresas",
        "centro medico Merida Venezuela email",
        "empresa farmaceutica Merida Venezuela",
    ]),
    ("educacion_universidad", [
        "universidad Merida Venezuela email",
        "instituto universitario Merida Venezuela",
        "universidad privada Merida Venezuela empresas",
        "colegio privado grande Merida empresas",
    ]),
    ("servicios_profesionales", [
        "empresa consultoria Merida Venezuela email",
        "firma abogados Merida Venezuela empresas",
        "despacho legal Merida Venezuela",
        "empresa auditoria Merida Venezuela",
        "consultora empresarial Merida Venezuela email",
        "empresa contabilidad Merida Venezuela",
    ]),
    ("tecnologia_empresas", [
        "empresa tecnologia Merida Venezuela email",
        "empresa software Merida Venezuela",
        "empresa informatica Merida Venezuela",
        "empresa telecomunicaciones Merida Venezuela",
        "empresa IT Merida Venezuela email",
    ]),
    ("transporte_logistica", [
        "empresa transporte Merida Venezuela email",
        "empresa logistica Merida Venezuela",
        "transporte carga Merida Venezuela empresas",
        "empresa encomiendas Merida Venezuela",
        "flota transporte Merida Venezuela",
    ]),
    ("energia_servicios", [
        "empresa energia Merida Venezuela email",
        "empresa electrica Merida Venezuela",
        "empresa climatizacion Merida Venezuela",
        "empresa aire acondicionado Merida Venezuela empresas",
    ]),
    ("retail_cadenas", [
        "cadena tiendas Merida Venezuela empresas",
        "tienda grande Merida Venezuela email",
        "supermercado grande Merida Venezuela empresas",
        "centro comercial Merida empresas email",
    ]),
    ("agroindustria", [
        "empresa agricola Merida Venezuela email",
        "empresa agroindustrial Merida Venezuela",
        "empresa ganadera Merida Venezuela",
        "empresa avicola Merida Venezuela",
        "empresa lechera Merida Venezuela",
    ]),
    ("medios_publicidad", [
        "empresa publicidad Merida Venezuela email",
        "agencia publicidad Merida Venezuela",
        "empresa marketing Merida Venezuela email",
        "empresa comunicaciones Merida Venezuela",
        "radio Merida Venezuela empresas email",
    ]),
]

if __name__ == "__main__":
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    existing = set(l.get("nombre","").lower().strip() for l in leads)
    initial = len(leads)
    
    print(f"Leads actuales: {initial}", flush=True)
    
    total_nuevos = 0
    for sector_key, queries in SECTORES:
        print(f"\n{'='*40}", flush=True)
        print(f"SECTOR: {sector_key.upper()}", flush=True)
        
        all_results = []
        for q in queries:
            print(f"  {q[:50]}...", end=" ", flush=True)
            results = ddg(q, 10)
            print(f"-> {len(results)}", flush=True)
            all_results.extend(results)
            time.sleep(random.uniform(3, 5))
        
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
                if any(x in p.lower() for x in ["merida","venezuela","google","maps","opiniones","facebook","instagram","gov","twitter","wikipedia","buscar","800"]):
                    continue
                if len(p) > 5 and len(p) < 60 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen:
                        seen.add(norm)
                        negocios.append({"nombre": p, "email": email, "telefono": tel, "url": href, "snippet": body[:200]})
        
        nuevos_sector = 0
        for neg in negocios:
            nombre = neg["nombre"]
            if nombre.lower().strip() in existing:
                continue
            
            email = neg.get("email", "")
            tel = neg.get("telefono", "")
            
            lead = {
                "nombre": nombre,
                "rubro": sector_key,
                "municipio": "Libertador",
                "estado_contacto": "No Contactado",
                "tipo_empresa": "mediana-grande",
            }
            if email: lead["email"] = email
            if tel: lead["telefono"] = tel
            if neg.get("url"): lead["fuente_contacto"] = "ddg"
            
            tiene = bool(lead.get("email","").strip()) or bool(lead.get("telefono","").strip())
            if tiene:
                leads.append(lead)
                existing.add(nombre.lower().strip())
                nuevos_sector += 1
                total_nuevos += 1
                tipo = "AMBOS" if (email and tel) else ("EMAIL" if email else "TEL")
                print(f"    [{nuevos_sector}] {nombre[:40]} {tipo}  {email[:30]}  {tel}", flush=True)
        
        print(f"  {sector_key}: {nuevos_sector} nuevos", flush=True)
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*40}", flush=True)
    print(f"TOTAL: {total_nuevos} nuevos de {initial} iniciales -> {len(leads)} totales", flush=True)
