"""
Scrub Zona Sur Mérida + Empresas medianas/grandes.
Rubros: distribuidoras, cafetaleras, plátanos, lácteos, consecionarios.
"""
import sys, os, json, time, random, re

sys.stdout.reconfigure(encoding='utf-8')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD_DOMAINS = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com","meneame.es","redalyc.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 6: return False
    p = e.split("@")
    if len(p) != 2: return False
    if p[1] in BAD_DOMAINS: return False
    if p[0] in ("noreply","no-reply","test","example","abuse","postmaster","support"): return False
    if len(p[0]) > 25: return False
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

RUBROS = [
    ("distribuidora_alimentos", [
        "distribuidora alimentos Merida Venezuela email",
        "distribuidora de granos Merida Venezuela",
        "distribuidora de arroz Merida Venezuela email",
        "distribuidora de aceites Merida Venezuela email",
        "distribuidora de harina Merida Venezuela",
        "distribuidora de conservas Merida Venezuela",
        "mayorista alimentos Merida Venezuela email",
        "abastos Merida Venezuela empresas email",
        "distribuidora perecederos Merida Venezuela",
    ]),
    ("cafetalera_cafe", [
        "cafetalera Merida Venezuela email",
        "cafe Merida Venezuela empresa email",
        "tostadora cafe Merida Venezuela email",
        "cafe de montana Merida Venezuela",
        "cafe arahuaca Merida Venezuela email",
        "productor cafe Merida Venezuela email",
        "finca cafe Merida Venezuela email",
        "cafe organico Merida Venezuela empresa",
        "cafe especial Merida Venezuela email",
        "alimentos cafe Merida Venezuela",
    ]),
    ("lacteos_queseria", [
        "lacteos Merida Venezuela empresa email",
        "queseria Merida Venezuela email",
        "queso Merida Venezuela empresa email",
        "leche Merida Venezuela empresa email",
        "lacteo Merida Venezuela email telefono",
        "produccion lechera Merida Venezuela",
        "queso artesanal Merida Venezuela email",
        "mantequilla Merida Venezuela empresa",
        "yogurt Merida Venezuela empresa email",
    ]),
    ("platano_banana", [
        "platano Merida Venezuela empresa email",
        "banana Merida Venezuela empresa",
        "productor platano Merida Venezuela email",
        "agropecuaria platano Merida Venezuela",
        "cultivo platano Merida Venezuela empresa",
        "exportador platano Merida Venezuela",
        "frutas tropicales Merida Venezuela email",
        "agricola platano Merida Venezuela email",
    ]),
    ("concesionario_vehiculos", [
        "concesionario vehiculos Merida Venezuela email",
        "agencia automotriz Merida Venezuela email",
        "venta de autos Merida Venezuela email",
        "venta de carros Merida Venezuela email",
        "concesionario Merida Venezuela email telefono",
        "automotriz Merida Venezuela empresa email",
        "vehiculos Merida Venezuela concesionario email",
        "autobaires Merida Venezuela email",
        "camionetas Merida Venezuela empresa email",
    ]),
    ("distribuidora_cerveza_bebidas", [
        "distribuidora cerveza Merida Venezuela email",
        "distribuidora bebidas Merida Venezuela email",
        "distribuidora gaseosa Merida Venezuela",
        "distribuidora agua Merida Venezuela email",
        "distribuidora jugos Merida Venezuela email",
        "mayorista bebidas Merida Venezuela",
        "distribuidora alcohol Merida Venezuela",
    ]),
    ("constructora_grande", [
        "constructora Merida Venezuela email telefono",
        "empresa constructora Merida email",
        "inmobiliaria Merida Venezuela email telefono",
        "desarrolladora Merida Venezuela email",
        "empresa cemento Merida Venezuela email",
        "bloquera Merida Venezuela email",
        "materiales de construccion Merida email",
    ]),
    ("clinica_especializada", [
        "clinica Merida Venezuela email telefono",
        "centro medico Merida Venezuela email",
        "hospital privado Merida Venezuela email",
        "laboratorio clinico Merida Venezuela email",
        "especialista medico Merida Venezuela email",
        "consulta medica Merida Venezuela email",
    ]),
    ("transporte_flota", [
        "transporte Merida Venezuela empresa email",
        "flota vehiculos Merida Venezuela email",
        "transporte de carga Merida Venezuela email",
        "empresa mudanza Merida Venezuela email",
        "furgones Merida Venezuela email",
        "camiones Merida Venezuela empresa email",
    ]),
    ("energia_aire_acondicionado", [
        "aire acondicionado Merida Venezuela empresa email",
        "climatizacion Merida Venezuela email",
        "refrigeracion Merida Venezuela empresa email",
        "energia solar Merida Venezuela email",
        "paneles solares Merida Venezuela email",
        "electricidad Merida Venezuela empresa email",
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
    for rubro, queries in RUBROS:
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
            email, tel = extract(texto)
            
            partes = re.split(r'[\-|–—:]', title)
            for p in partes:
                p = p.strip()
                skip = ["merida","venezuela","google","maps","opiniones","facebook",
                        "instagram","gov","twitter","wikipedia","buscar","directorio",
                        "empresas en","lista","mejores","opiniones de","como llegar"]
                if any(x.lower() in p.lower() for x in skip):
                    continue
                if len(p) > 4 and len(p) < 60 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen:
                        seen.add(norm)
                        negocios.append({"nombre": p, "email": email, "telefono": tel, "url": href, "snippet": body[:200]})
        
        nuevos = 0
        for neg in negocios:
            nombre = neg["nombre"]
            if nombre.lower().strip() in existing:
                continue
            email = neg.get("email", "")
            tel = neg.get("telefono", "")
            
            if not email and not tel:
                continue
            
            lead = {
                "nombre": nombre,
                "rubro": rubro,
                "municipio": "Libertador",
                "estado_contacto": "No Contactado",
                "fecha_creacion": time.strftime("%Y-%m-%d"),
            }
            if email: lead["email"] = email
            if tel: lead["telefono"] = tel
            if neg.get("url"): lead["fuente_contacto"] = "ddg"
            
            leads.append(lead)
            existing.add(nombre.lower().strip())
            nuevos += 1
            total_nuevos += 1
            tipo = "AMBOS" if (email and tel) else ("EMAIL" if email else "TEL")
            print(f"    [{nuevos}] {nombre[:35]} {tipo}  {email[:30]}  {tel}", flush=True)
        
        print(f"  {rubro}: {nuevos} nuevos", flush=True)
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    
    con_email = sum(1 for l in leads if l.get("email","").strip())
    con_tel = sum(1 for l in leads if l.get("telefono","").strip())
    print(f"\n{'='*40}", flush=True)
    print(f"RESULTADO: {total_nuevos} nuevos -> {len(leads)} totales", flush=True)
    print(f"Email: {con_email} | Tel: {con_tel}", flush=True)
