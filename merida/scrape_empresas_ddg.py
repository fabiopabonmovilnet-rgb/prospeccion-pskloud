"""
Empresas medianas/grandes Mérida - DDG ultra dirijido.
Busca empresas REALES por nombre + contacto en snippets.
Sin Overpass, sin Playwright. Solo DDG optimizado.
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
    if p[0] in ("noreply","no-reply","test","example","abuse","postmaster","support"): return False
    return True

def es_tel_ve(t):
    d = re.sub(r'[^\d]', '', t)
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276")
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
        if es_tel_ve(t):
            tel = t
            break
    return email, tel

# ==================== DIRECTORIOS EMPRESARIALES ONLINE ====================
DIRECTORIOS = [
    "https://www.directorioempresarial.com.ve",
    "https://www.cybo.com/VE-biz/merida",
    "https://www.ayuda.com.ve",
    "https://www.locu.com/v/merida-venezuela",
]

# Queries optimizadas para encontrar empresas REALES de Merida
# con email o telefono en snippets
QUERIES_EMPRESAS = [
    # Industria y manufactura
    ('industria', [
        'industrias Merida Venezuela email contacto',
        'fabrica Merida Venezuela "gmail.com" OR "hotmail.com"',
        'manufactura Merida Venezuela telefono',
        'empresa industrial Merida Venezuela "@" email',
        'industria alimentaria Merida "@" gmail',
        'industria textil Merida Venezuela email',
        'planta procesadora Merida Venezuela',
        'empresa de envases Merida Venezuela',
        'empresa de empaque Merida Venezuela',
    ]),
    # Construccion e inmobiliarias
    ('construccion', [
        'constructora Merida Venezuela "@" email',
        'inmobiliaria Merida "@" gmail.com OR hotmail.com',
        'empresa construccion Merida Venezuela telefono',
        'promotora inmobiliaria Merida email contacto',
        'desarrolladora inmobiliaria Merida Venezuela',
        'empresa de cemento Merida Venezuela',
        'blocks Merida Venezuela empresas email',
        'acero Merida Venezuela empresas',
    ]),
    # Distribuidoras y mayoristas
    ('distribuidora', [
        'distribuidora Merida "@" email gmail hotmail',
        'mayorista Merida Venezuela email telefono',
        'comercializadora Merida Venezuela "@" email',
        'empresa importadora Merida Venezuela',
        'empresa exportadora Merida Venezuela',
        'distribuidora de alimentos Merida Venezuela email',
        'distribuidora de bebidas Merida Venezuela email',
        'distribuidora de aceites Merida Venezuela',
    ]),
    # Salud grande
    ('clinica_hospital', [
        'clinica Merida "@" email gmail hotmail',
        'hospital privado Merida Venezuela email',
        'laboratorio clinico Merida "@" email',
        'centro medico Merida Venezuela email telefono',
        'empresa farmaceutica Merida Venezuela email',
        'clinica especializada Merida Venezuela email',
        'clinica dental Merida Venezuela empresas email',
        'clinica oftalmologica Merida Venezuela email',
        'clinica pediatrica Merida Venezuela email',
        'clinica dermatologica Merida Venezuela email',
    ]),
    # Hoteles y turismo grande
    ('hotel_turismo', [
        'hotel Merida "@" email gmail hotmail',
        'posada Merida Venezuela email telefono',
        'hospedaje Merida Venezuela email',
        'empresa turistica Merida Venezuela email',
        'tour operador Merida Venezuela email',
        'agencia de viajes Merida Venezuela email',
        'hotel boutique Merida Venezuela email',
        'hotel gran mama Merida email',
    ]),
    # Tecnologia y software
    ('tecnologia', [
        'empresa software Merida "@" email',
        'empresa tecnologia Merida Venezuela email',
        'empresa de sistemas Merida Venezuela email',
        'empresa IT Merida "@" gmail hotmail',
        'empresa informatica Merida Venezuela email',
        'empresa de desarrollo web Merida Venezuela',
        'empresa de internet Merida Venezuela email',
        'data center Merida Venezuela empresas',
    ]),
    # Servicios profesionales
    ('servicios_profesionales', [
        'consultoria Merida "@" email gmail hotmail',
        'firma de abogados Merida Venezuela email',
        'despacho legal Merida Venezuela email',
        'empresa de auditoria Merida Venezuela email',
        'consultora empresarial Merida Venezuela email',
        'empresa de contabilidad Merida "@" email',
        'asesoria empresarial Merida Venezuela email',
        'empresa de seguridad Merida Venezuela email',
    ]),
    # Transporte y logistica
    ('transporte_logistica', [
        'empresa transporte Merida "@" email gmail',
        'empresa logistica Merida Venezuela email',
        'transporte de carga Merida Venezuela email',
        'empresa de encomiendas Merida Venezuela email',
        'furgoneta Merida Venezuela empresas email',
        'flota de vehiculos Merida Venezuela',
        'empresa de mudanza Merida Venezuela email',
    ]),
    # Energia y servicios
    ('energia_servicios', [
        'empresa electrica Merida "@" email',
        'empresa de aire acondicionado Merida email',
        'empresa de climatizacion Merida Venezuela email',
        'empresa solar Merida Venezuela email',
        'empresa de energia Merida Venezuela email',
        'empresa de gas Merida Venezuela email',
        'empresa de plomeria Merida Venezuela email',
    ]),
    # Agroindustria
    ('agroindustria', [
        'empresa agricola Merida "@" email gmail',
        'empresa ganadera Merida Venezuela email',
        'empresa avicola Merida Venezuela email',
        'empresa lechera Merida Venezuela email',
        'empresa porcicola Merida Venezuela email',
        'empresa de cafe Merida Venezuela email',
        'empresa de cacao Merida Venezuela email',
        'empresa de tabaco Merida Venezuela email',
    ]),
    # Comercio grande
    ('comercio_grande', [
        'tienda grande Merida "@" email gmail',
        'cadena de tiendas Merida Venezuela email',
        'empresa comercial Merida Venezuela email',
        'empresa de electrodomesticos Merida email',
        'empresa de muebles Merida Venezuela email',
        'empresa de materiales Merida Venezuela email',
        'empresa de ferreteria Merida Venezuela email',
    ]),
    # Medios y publicidad
    ('medios_publicidad', [
        'agencia de publicidad Merida "@" email',
        'empresa de marketing Merida Venezuela email',
        'empresa de medios Merida Venezuela email',
        'radio Merida Venezuela email empresas',
        'empresa de produccion Merida Venezuela email',
        'empresa de diseno Merida Venezuela email',
        'empresa de impresion Merida Venezuela email',
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
    for sector, queries in QUERIES_EMPRESAS:
        print(f"\n{'='*40}", flush=True)
        print(f"SECTOR: {sector.upper()}", flush=True)
        
        all_results = []
        for q in queries:
            results = ddg(q, 10)
            all_results.extend(results)
            time.sleep(random.uniform(2, 4))
        
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
                skip_words = ["merida","venezuela","google","maps","opiniones","facebook","instagram","gov","twitter","wikipedia","buscar","800"," DIRECTORIO ","Empresas en"]
                if any(x.lower() in p.lower() for x in skip_words):
                    continue
                if len(p) > 4 and len(p) < 80 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen and len(norm) > 3:
                        seen.add(norm)
                        negocios.append({"nombre": p, "email": email, "telefono": tel, "url": href, "snippet": body[:200]})
        
        print(f"  Negocios encontrados: {len(negocios)}", flush=True)
        
        nuevos_sector = 0
        for neg in negocios:
            nombre = neg["nombre"]
            if nombre.lower().strip() in existing:
                continue
            
            email = neg.get("email", "")
            tel = neg.get("telefono", "")
            
            lead = {
                "nombre": nombre,
                "rubro": sector,
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
        
        print(f"  {sector}: {nuevos_sector} nuevos", flush=True)
        
        # Save after each sector
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*40}", flush=True)
    print(f"RESULTADO: {total_nuevos} nuevos -> {len(leads)} totales", flush=True)
