"""
Empresas medianas/grandes en Mérida vía Overpass API (OSM) + DDG para email/tel.
OSM da nombres reales de negocios; DDG busca el contacto.
"""
import sys, os, json, time, random, re, urllib.request, urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com","meneame.es","redalyc.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 5: return False
    p = e.split("@")
    if len(p) != 2 or p[1] in BAD: return False
    skip_users = {"noreply","no-reply","test","example","abuse","postmaster","support"}
    if p[0] in skip_users: return False
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

# ==================== OVERPASS: BUSINESS NAMES ====================
# Mérida bounds approx: 8.55,-71.25 to 8.65,-71.10
OVERPASS_CATEGORIES = [
    # Large businesses / offices
    ("office", '[amenity="office"]'),
    ("hotel", '[tourism="hotel"]'),
    ("hospital", '[amenity="hospital"]'),
    ("clinic", '[amenity="clinic"]'),
    ("bank", '[amenity="bank"]'),
    ("school", '[amenity="school"]'),
    ("university", '[amenity="university"]'),
    ("pharmacy", '[amenity="pharmacy"]'),
    ("restaurant", '[amenity="restaurant"]'),
    ("cafe", '[amenity="cafe"]'),
    ("bar", '[amenity="bar"]'),
    ("supermarket", '[shop="supermarket"]'),
    ("convenience", '[shop="convenience"]'),
    ("car_repair", '[shop="car_repair"]'),
    ("car_parts", '[shop="car_parts"]'),
    ("hardware", '[shop="hardware"]'),
    ("furniture", '[shop="furniture"]'),
    ("electronics", '[shop="electronics"]'),
    ("clothes", '[shop="clothes"]'),
    ("shoes", '[shop="shoes"]'),
    ("jewelry", '[shop="jewelry"]'),
    ("optician", '[shop="optician"]'),
    ("beauty", '[shop="beauty"]'),
    ("chemist", '[shop="chemist"]'),
    ("florist", '[shop="florist"]'),
    ("printer", '[shop="printer"]'),
    ("stationery", '[shop="stationery"]'),
    ("bakery", '[shop="bakery"]'),
    ("butcher", '[shop="butcher"]'),
    ("chemist2", '[shop="chemist"]'),
    ("travel_agency", '[office="travel_agent"]'),
    ("insurance", '[office="insurance"]'),
    ("estate_agent", '[office="estate_agent"]'),
    ("telecom", '[office="telecommunication"]'),
    ("it_services", '[office="it"]'),
    ("constructor", '[office="construction_company"]'),
]

SOUTH, NORTH, WEST, EAST = 8.50, 8.70, -71.30, -71.05

def query_overpass(tag_filter):
    bbox = f"{SOUTH},{WEST},{NORTH},{EAST}"
    q = f'[out:json][timeout:25];(node{tag_filter}({bbox});way{tag_filter}({bbox}););out center 30;'
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": q}).encode()
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())["elements"]
    except Exception as ex:
        print(f"    Overpass error: {str(ex)[:60]}", flush=True)
        return []

def get_osm_businesses():
    seen = set()
    businesses = []
    for cat_name, tag in OVERPASS_CATEGORIES:
        print(f"  OSM: {cat_name}...", end=" ", flush=True)
        elements = query_overpass(tag)
        count = 0
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name", "").strip()
            if not name or len(name) < 3:
                continue
            norm = name.lower()
            if norm in seen:
                continue
            seen.add(norm)
            
            phone = tags.get("phone", tags.get("contact:phone", ""))
            email = tags.get("email", tags.get("contact:email", ""))
            website = tags.get("website", tags.get("contact:website", ""))
            
            businesses.append({
                "nombre": name,
                "osm_category": cat_name,
                "osm_phone": phone,
                "osm_email": email,
                "osm_website": website,
            })
            count += 1
        print(f"{count} ({len(elements)} raw)", flush=True)
        time.sleep(1)
    return businesses

# ==================== MAIN ====================
if __name__ == "__main__":
    leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
    
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    existing = set(l.get("nombre","").lower().strip() for l in leads)
    initial = len(leads)
    
    print(f"Leads actuales: {initial}", flush=True)
    print(f"\n=== PASO 1: Overpass API - negocios de OSM ===", flush=True)
    
    businesses = get_osm_businesses()
    print(f"\nTotal negocios OSM: {len(businesses)}", flush=True)
    
    print(f"\n=== PASO 2: Buscar contactos via DDG ===", flush=True)
    
    nuevos = 0
    for i, biz in enumerate(businesses):
        nombre = biz["nombre"]
        if nombre.lower().strip() in existing:
            continue
        
        email = biz.get("osm_email", "")
        tel = biz.get("osm_phone", "")
        website = biz.get("osm_website", "")
        
        # If no email/tel from OSM, search DDG
        if not email or not tel:
            q1 = f'"{nombre}" Merida Venezuela email correo telefono'
            for r in ddg(q1, 5):
                texto = r.get("title","") + " " + r.get("body","")
                e2, t2 = extract(texto)
                if e2 and not email: email = e2
                if t2 and not tel: tel = t2
                # Also check URL for website
                if not website:
                    href = r.get("href", "")
                    if href.startswith("http") and "google" not in href and "facebook" not in href and "instagram" not in href:
                        website = href
            if email and tel:
                pass  # got both
            elif not email and not tel:
                time.sleep(random.uniform(1, 3))
                continue  # skip if nothing found
        
        lead = {
            "nombre": nombre,
            "rubro": biz.get("osm_category", "empresa"),
            "municipio": "Libertador",
            "estado_contacto": "No Contactado",
            "tipo_empresa": "mediana-grande",
        }
        if email: lead["email"] = email
        if tel: lead["telefono"] = tel
        if website: lead["website"] = website
        lead["fuente_contacto"] = "osm+ddg"
        
        tiene = bool(lead.get("email","").strip()) or bool(lead.get("telefono","").strip())
        if tiene:
            leads.append(lead)
            existing.add(nombre.lower().strip())
            nuevos += 1
            tipo = "AMBOS" if (email and tel) else ("EMAIL" if email else "TEL")
            print(f"  [{nuevos}] {nombre[:40]} {tipo}  {email[:30]}  {tel}", flush=True)
        
        if (i + 1) % 25 == 0:
            with open(leads_file, "w", encoding="utf-8") as f:
                json.dump(leads, f, ensure_ascii=False, indent=2)
            print(f"  ... guardado parcial ({len(leads)} leads, {nuevos} nuevos)", flush=True)
        
        time.sleep(random.uniform(1, 3))
    
    with open(leads_file, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*40}", flush=True)
    print(f"RESULTADO: {nuevos} nuevos leads de OSM", flush=True)
    print(f"Total leads: {len(leads)}", flush=True)
