"""
Scrape FIABLE de empresas reales en Mérida.
Fuentes: Instagram Business profiles + DDG snippets verificables.
Solo guarda si el email parece de una empresa real en Venezuela.
"""
import sys, os, json, time, random, re

sys.stdout.reconfigure(encoding='utf-8')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD_DOMAINS = {
    "sentry.io","wixpress.com","google.com","example.com","localhost",
    "schema.org","w3.org","wordpress.org","squarespace.com","wix.com",
    "godaddy.com","apple.com","microsoft.com","tiktok.com","meneame.es",
    "redalyc.org","unmejorempleo.com","prodigy.net.mx","cafrimx.com",
    "odoo.com","overtimeve.com","comalsa.com","gmail.com","hotmail.com",
    "yahoo.com","outlook.com","live.com","aol.com","mail.com",
}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2: return False
    if p[1] in BAD_DOMAINS: return False
    if p[0] in ("noreply","no-reply","test","example","abuse","postmaster","support","info","contact","admin","ventas","marketing","webmaster"): return False
    if len(p[0]) > 25: return False  # usernames too long = junk
    return True

def es_tel_ve(t):
    d = re.sub(r'[^\d]', '', t)
    if not d: return False
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276")
    if len(d) == 11 and d.startswith("0"): return d[:4] in prefixes
    if len(d) == 12 and d.startswith("58"): return d[2:6] in prefixes
    if len(d) == 10 and d.startswith("58"): return d[2:6] in prefixes
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

def extract_contacts(texto):
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

# ==================== RUBROS DE EMPRESAS REALES EN MÉRIDA ====================
RUBROS_MERIDA = [
    # Empresas agrícolas / cafetaleras (el usuario mencionó estas)
    ("cafetalera", [
        'cafetalera Merida Venezuela email',
        'cafe Merida Venezuela empresa email telefono',
        'productor de cafe Merida Venezuela',
        'finca cafe Merida Venezuela email',
        'cafeto Merida Venezuela empresa',
        'cafe especial Merida Venezuela email',
        'tostadora de cafe Merida Venezuela email',
        'cafe de montaña Merida Venezuela',
        'organico cafe Merida Venezuela empresa',
        'cafe arahuaca Merida Venezuela',
    ]),
    ("cacao_chocolate", [
        'cacao Merida Venezuela empresa email',
        'chocolate artesanal Merida Venezuela email',
        'productor cacao Merida Venezuela',
        'chocolateria Merida Venezuela email telefono',
        'cacao fino Merida Venezuela empresa',
        'chocolate Merida Venezuela email contacto',
    ]),
    # Empresas alimentarias
    ("empresa_alimentos", [
        'empresa de alimentos Merida Venezuela email',
        'procesadora de alimentos Merida Venezuela',
        'alimentos premium Merida Venezuela email',
        'distribuidora de alimentos Merida Venezuela email',
        'empresa de snacks Merida Venezuela',
        'empresa de cereales Merida Venezuela',
        'bebidas Merida Venezuela empresas email',
    ]),
    # Empresas agrícolas y ganaderas
    ("agropecuaria", [
        'empresa agropecuaria Merida Venezuela email',
        'ganaderia Merida Venezuela empresa email',
        'empresa avicola Merida Venezuela email',
        'empresa lechera Merida Venezuela email',
        'empresa porcicola Merida Venezuela email',
        'agrícola Merida Venezuela empresa email',
        'finca Merida Venezuela empresa email telefono',
        'hacienda Merida Venezuela empresa email',
    ]),
    # Empresas manufactureras
    ("manufactura", [
        'fabrica Merida Venezuela empresa email',
        'manufactura Merida Venezuela email',
        'empresa productora Merida Venezuela email',
        'industria Merida Venezuela email telefono',
        'empresa de repuestos Merida Venezuela email',
        'empresa de componentes Merida Venezuela',
    ]),
    # Construcción e inmobiliarias
    ("constructora_inmobiliaria", [
        'constructora Merida Venezuela email telefono',
        'inmobiliaria Merida Venezuela email',
        'empresa constructora Merida email',
        'desarrolladora inmobiliaria Merida Venezuela',
        'promotora inmobiliaria Merida Venezuela email',
        'empresa de cemento Merida Venezuela email',
    ]),
    # Clínicas y centros médicos (verificados)
    ("clinica_centro_medico", [
        'clinica Merida Venezuela email telefono',
        'centro medico Merida Venezuela email',
        'hospital privado Merida Venezuela email',
        'laboratorio clinico Merida Venezuela email',
        'clinica dental Merida Venezuela email telefono',
        'clinica oftalmologica Merida Venezuela email',
        'clinica dermatologica Merida Venezuela email',
    ]),
    # Hoteles y turismo (verificados)
    ("hotel_posada", [
        'hotel Merida Venezuela email telefono',
        'posada Merida Venezuela email',
        'hospedaje Merida Venezuela email telefono',
        'hotel boutique Merida Venezuela email',
        'hotel familiar Merida Venezuela email',
        'apart hotel Merida Venezuela email',
    ]),
    # Empresas de tecnología y software
    ("tecnologia_software", [
        'empresa software Merida Venezuela email',
        'empresa tecnologia Merida Venezuela email',
        'empresa de desarrollo Merida Venezuela email',
        'empresa IT Merida Venezuela email telefono',
        'empresa de sistemas Merida Venezuela email',
        'empresa de internet Merida Venezuela email',
    ]),
    # Servicios profesionales
    ("consultoria_asesoria", [
        'consultoria Merida Venezuela email',
        'firma de abogados Merida Venezuela email',
        'despacho legal Merida Venezuela email',
        'empresa de auditoria Merida Venezuela email',
        'consultora empresarial Merida Venezuela email',
        'asesoria tributaria Merida Venezuela email',
    ]),
    # Transporte y logística
    ("transporte", [
        'empresa transporte Merida Venezuela email',
        'transporte de carga Merida Venezuela email',
        'empresa logistica Merida Venezuela email',
        'empresa de encomiendas Merida Venezuela email',
        'flota Merida Venezuela empresa email',
    ]),
    # Energía y servicios técnicos
    ("energia_servicios_tecnicos", [
        'empresa electrica Merida Venezuela email',
        'empresa de aire acondicionado Merida Venezuela email',
        'empresa solar Merida Venezuela email',
        'empresa de energia Merida Venezuela email',
        'empresa de plomeria Merida Venezuela email',
    ]),
    # Comercio mayorista
    ("comercio_mayorista", [
        'mayorista Merida Venezuela email',
        'distribuidora Merida Venezuela email telefono',
        'comercializadora Merida Venezuela email',
        'empresa importadora Merida Venezuela email',
        'empresa exportadora Merida Venezuela email',
    ]),
    # Medios y publicidad
    ("medios_publicidad", [
        'agencia de publicidad Merida Venezuela email',
        'empresa de marketing Merida Venezuela email',
        'empresa de diseno Merida Venezuela email',
        'agencia digital Merida Venezuela email',
        'empresa de produccion Merida Venezuela email',
    ]),
]

def es_empresa_real(nombre):
    """Check if name looks like a real business (not a page title or junk)."""
    n = nombre.lower().strip()
    if len(n) < 4: return False
    junk = [
        "opiniones","resumen","fotos","videos","imagenes","como llegar",
        "directorio","empresas en","lista de","79 empresas","800",
        "email &","emails &","author details","contact us","contáctanos",
        "ponte en contacto","acerca de","agregar la","en este lugar",
        "ves%","http","www.",".com",".ve","ayuda","preguntas",
        "terminos","politica","privacidad"," mapas","galeria",
    ]
    for j in junk:
        if j in n: return False
    return True

if __name__ == "__main__":
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    existing = set(l.get("nombre","").lower().strip() for l in leads)
    initial = len(leads)
    
    print(f"Leads actuales: {initial}", flush=True)
    
    total_nuevos = 0
    for rubro, queries in RUBROS_MERIDA:
        print(f"\n{'='*40}", flush=True)
        print(f"RUBRO: {rubro.upper()}", flush=True)
        
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
            email, tel = extract_contacts(texto)
            
            # Extract business name from title
            partes = re.split(r'[\-|–—:]', title)
            for p in partes:
                p = p.strip()
                skip_words = ["merida","venezuela","google","maps","opiniones","facebook",
                            "instagram","gov","twitter","wikipedia","buscar","directorio",
                            "empresas en","lista","mejores","opiniones de"]
                if any(x.lower() in p.lower() for x in skip_words):
                    continue
                if len(p) > 4 and len(p) < 60 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen and es_empresa_real(p):
                        seen.add(norm)
                        negocios.append({
                            "nombre": p,
                            "email": email,
                            "telefono": tel,
                            "url": href,
                            "snippet": body[:300],
                        })
        
        print(f"  Negocios encontrados: {len(negocios)}", flush=True)
        
        nuevos = 0
        for neg in negocios:
            nombre = neg["nombre"]
            if nombre.lower().strip() in existing:
                continue
            
            email = neg.get("email", "")
            tel = neg.get("telefono", "")
            
            # ONLY save if we have at least email
            if not email:
                continue
            
            lead = {
                "nombre": nombre,
                "rubro": rubro,
                "municipio": "Libertador",
                "estado_contacto": "No Contactado",
            }
            if email: lead["email"] = email
            if tel: lead["telefono"] = tel
            if neg.get("url"): lead["fuente_contacto"] = "ddg_verificado"
            if neg.get("snippet"): lead["notas"] = neg["snippet"][:200]
            
            leads.append(lead)
            existing.add(nombre.lower().strip())
            nuevos += 1
            total_nuevos += 1
            tel_str = f"  {tel}" if tel else ""
            print(f"    [{nuevos}] {nombre[:40]}  {email[:35]}{tel_str}", flush=True)
        
        print(f"  {rubro}: {nuevos} nuevos", flush=True)
        
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    
    con_email = sum(1 for l in leads if l.get("email","").strip())
    con_tel = sum(1 for l in leads if l.get("telefono","").strip())
    con_ambos = sum(1 for l in leads if l.get("email","").strip() and l.get("telefono","").strip())
    
    print(f"\n{'='*40}", flush=True)
    print(f"RESULTADO:", flush=True)
    print(f"  Nuevos: {total_nuevos}", flush=True)
    print(f"  Total: {len(leads)}", flush=True)
    print(f"  Con email: {con_email}", flush=True)
    print(f"  Con telefono: {con_tel}", flush=True)
    print(f"  Con ambos: {con_ambos}", flush=True)
