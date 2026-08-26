"""Ultra-rápido: extrae SOLO de snippets DDG sin queries extra por lead"""
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
    try:
        with DDGS() as d:
            return list(d.text(query, region="ve-ve", max_results=n))
    except Exception as ex:
        print(f"  DDG error: {str(ex)[:60]}", flush=True)
        time.sleep(8)
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

rubro = sys.argv[1] if len(sys.argv) > 1 else "constructora"
leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"

with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)
existing = set(l.get("nombre","").lower().strip() for l in leads)
initial = len(leads)

print(f"Rubro: {rubro} | Leads actuales: {initial}", flush=True)

queries = [
    f'{rubro} Merida Venezuela email telefono',
    f'{rubro} en Merida Venezuela lista',
    f'mejores {rubro} Merida opiniones',
    f'{rubro} Merida WhatsApp contacto correo',
    f'{rubro} Merida sitio web direccion',
]

all_results = []
for q in queries:
    print(f"  Buscando: {q[:50]}...", end=" ", flush=True)
    results = ddg(q, 10)
    print(f"-> {len(results)} resultados", flush=True)
    all_results.extend(results)
    time.sleep(random.uniform(2, 4))

# Collect business names + try to extract contacts directly from snippets
nombres = []
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
        if any(x in p.lower() for x in ["merida","venezuela","google","maps","opiniones","facebook","instagram","gov","twitter","wikipedia","buscar","buscar"]):
            continue
        if len(p) > 5 and len(p) < 60 and not p.startswith("http"):
            norm = p.lower().strip()
            if norm not in seen:
                seen.add(norm)
                nombres.append({
                    "nombre": p,
                    "email": email,
                    "telefono": tel,
                    "url": href,
                })

print(f"\nNegocios encontrados: {len(nombres)}", flush=True)

nuevos = 0
for neg in nombres:
    nombre = neg["nombre"]
    if nombre.lower().strip() in existing:
        continue
    
    lead = {
        "nombre": nombre,
        "rubro": rubro,
        "municipio": "Libertador",
        "estado_contacto": "No Contactado",
    }
    if neg.get("email"):
        lead["email"] = neg["email"]
    if neg.get("telefono"):
        lead["telefono"] = neg["telefono"]
    if neg.get("url"):
        lead["fuente_contacto"] = "ddg"
    
    tiene = bool(lead.get("email","").strip()) or bool(lead.get("telefono","").strip())
    if tiene:
        leads.append(lead)
        existing.add(nombre.lower().strip())
        nuevos += 1
        tipo = "AMBOS" if (lead.get("email","").strip() and lead.get("telefono","").strip()) else ("EMAIL" if lead.get("email","").strip() else "TEL")
        print(f"  [{nuevos}] {nombre[:40]} {tipo}  {lead.get('email','')[:30]}  {lead.get('telefono','')}", flush=True)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

print(f"\n{rubro.upper()}: {nuevos} nuevos leads", flush=True)
print(f"Total leads: {len(leads)}", flush=True)
