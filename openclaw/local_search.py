"""
PSKloud Prospector - Prospección Local multi-fuente
Fuentes: OpenStreetMap + DuckDuckGo
Sin API key. Funciona para cualquier país.
"""

import json, os, re, time, requests
from urllib.parse import quote
from typing import List, Dict, Optional, Callable
from bs4 import BeautifulSoup
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Shared data directory (mounted volume from docker-compose: ./ -> /app/data)
# Try mounted /app/data first, fallback to ../data relative to this file
_shared_candidate = "/app/data"
if os.path.isdir(_shared_candidate):
    SHARED_DATA_DIR = _shared_candidate
else:
    SHARED_DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
PROSPECTOS_LOCALES_FILE = os.path.join(SHARED_DATA_DIR, "prospectos_locales.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

PREFIJOS_PAIS = {
    "panama": "+507", "panamá": "+507", "costa rica": "+506",
    "honduras": "+504", "guatemala": "+502", "el salvador": "+503",
    "nicaragua": "+505", "mexico": "+52", "méxico": "+52",
    "colombia": "+57", "venezuela": "+58", "peru": "+51", "perú": "+51",
    "chile": "+56", "argentina": "+54", "ecuador": "+593",
    "bolivia": "+591", "paraguay": "+595", "uruguay": "+598",
    "brasil": "+55", "brazil": "+55", "republica dominicana": "+1",
    "cuba": "+53", "puerto rico": "+1",
}

REGION_DDG = {
    "panama": "pa-pa", "panamá": "pa-pa", "costa rica": "cr-cr",
    "honduras": "hn-hn", "guatemala": "gt-gt", "el salvador": "sv-sv",
    "nicaragua": "ni-ni", "mexico": "mx-mx", "méxico": "mx-mx",
    "colombia": "co-co", "venezuela": "ve-ve", "peru": "pe-pe", "perú": "pe-pe",
    "chile": "cl-cl", "argentina": "ar-ar", "ecuador": "ec-ec",
    "brasil": "br-br", "brazil": "br-br", "bolivia": "bo-bo",
    "paraguay": "py-py", "uruguay": "uy-uy",
}


def limpiar_telefono(phone: str) -> str:
    if not phone:
        return ""
    return re.sub(r'[^\d]', '', phone)


def generar_wa_url(phone: str, nombre_negocio: str) -> str:
    clean = limpiar_telefono(phone)
    if not clean or len(clean) < 8:
        return ""
    msg = f"Hola, buenos días. Un gusto saludarle a la gente de {nombre_negocio}."
    return f"https://wa.me/{clean}?text={quote(msg)}"


generar_whatsapp_url = generar_wa_url


def _detectar_prefijo(ubicacion: str) -> str:
    for key, val in PREFIJOS_PAIS.items():
        if key in ubicacion.lower():
            return val
    return ""


def _detectar_region_ddg(ubicacion: str) -> str:
    for key, val in REGION_DDG.items():
        if key in ubicacion.lower():
            return val
    return "wt-wt"


# Keywords that indicate the business is NOT what we're searching for
_NON_RUBRO_KEYWORDS = {
    'bienes raices': [
        'lavander', 'barber', 'pub', 'irish', 'spa', 'masaje', 'steakhouse',
        'cafe', 'café', 'restaurante', 'restaurant', 'pasta', 'pizza', 'hamburg',
        'gimnasio', 'gym', 'crossfit', 'colegio', 'institucion', 'escuela',
        'universidad', 'academia', 'deportes', 'taekwondo', 'karate',
        'beauty', 'salon', 'salón', 'belleza', 'peluqueria', 'clínica',
        'clinica', 'hospital', 'medico', 'farmacia', 'dental', 'odontolog',
        'abogado', 'legal', 'notaria', 'auto', 'mecanica', 'taller', 'carro',
        'tienda', 'boutique', 'moda', 'ropa', 'zapato', 'supermercado',
        'minimarket', 'panaderia', 'panadería', 'tortas', 'comida', 'comedor',
        'hotel', 'motel', 'hostal', 'iglesia', 'templo', 'guarderia',
        'museo', 'teatro', 'cine', 'viaje', 'turismo', 'tour', 'fotografi',
        'mascota', 'veterinari', 'musica', 'floristeria', 'funeraria',
        'carpinteri', 'herreria', 'pintura', 'transporte', 'flete',
        'seguro', 'contad', 'auditor', 'publicidad', 'marketing',
        'software', 'tecnolog', 'sistemas', 'computador', 'implant',
        'optica', 'arrend', 'alquiler', 'bitcoin', 'crypto', 'carniceria',
        'verduleria', 'licoreria', 'papeleria', 'ferreteria', 'bazar',
        'minisuper', 'grua', 'radio', 'banco', 'caja', 'credito',
        'fundacion', 'ONG', 'fisioterapia', 'pilates', 'yoga', 'boxing',
        'zumba', 'creperia', 'sushi', 'tacos', 'ceviche', 'poke',
        'express', 'delivery', 'domicilio', 'imprenta', 'arquitect',
        'ingenier', 'contador', 'policia', 'bombero', 'militar',
        'colchon', 'mueble', 'cemento', 'block', 'ladrillo', 'tubo',
        'plomeria', 'electric', 'aire acondicionado', 'seguridad',
        'fumigac', 'reciclaj', 'carwash', 'bisuteria', 'joyeria',
        'relojeria', 'tattoo', 'tatuaj', 'uñas', 'nails', 'manicure',
        'maquillaj', 'perfume', 'cosmetica', 'lenceria', 'deportiv',
        'accesorio', 'regalo', 'souvenir', 'bizcocho', 'galleta',
        'chocolate', 'helado', 'nieve', 'cerveza', 'cerveceria',
        'cafeteria', 'distribuidor', 'mayorista', 'abarrotes', 'bodega',
        'pulperia', 'quiosco', 'taxi', 'uber', 'funerar', 'sepelio',
        'consultori', 'consultorio', 'gabinete', 'despacho', 'copy',
        'videojuego', 'petshop', 'acuario', 'jardin', 'vivero',
        'electricidad', 'gas ',
    ],
}


def _nombre_consiste_con_rubro(nombre: str, rubro: str) -> bool:
    """Check if business name is consistent with the searched rubro.
    Returns False if name clearly indicates a different business type."""
    rubro_lower = rubro.lower().strip()
    nombre_lower = nombre.lower().strip()
    
    keywords = _NON_RUBRO_KEYWORDS.get(rubro_lower, [])
    if not keywords:
        return True  # No filter for this rubro
    
    for kw in keywords:
        if kw in nombre_lower:
            return False
    return True


# Palabras de industrias AJENAS a clínicas dentales (rechazo estricto a nivel de scrape)
_PALABRAS_AJENAS_DENTAL = [
    "farmacia", "droguer", "supermercado", "supermercado", "minimarket", "abi",
    "abarrote", "bodega", "pulperia", "pulpería", "quiosco", "tienda", "tiendita",
    "licorer", "panader", "pasteleria", "pastelería", "tortas", "helado", "cafe", "café",
    "restaurante", "restaurant", "comedor", "sushi", "pizza", "hamburg", "tacos",
    "ceviche", "bar", "pub", "discoteca", "carnicer", "verduler", "fruteria",
    "gimnasio", "gym", "crossfit", "pilates", "yoga", "boxing", "zumba",
    "taller", "mecanic", "carro", "auto", "llanta", "carwash", "grua", "transporte", "flete",
    "ferreter", "cemento", "block", "ladrillo", "plomeria", "electric", "aire acondicionado",
    "seguridad", "fumigac", "imprenta", "arquitect", "ingenier", "constructora", "inmobiliaria",
    "mueble", "colchon", "zapater", "boutique", "moda", "ropa", "lenceria", "accesorio", "regalo",
    "joyer", "relojer", "perfume", "cosmetic", "maquillaj", "salon", "salón", "belleza", "beauty",
    "peluquer", "barber", "unisex", "uñas", "nails", "manicure", "tattoo", "tatuaj", "estetica",
    "veterinaria", "mascotas", "petshop", "funeraria", "sepelio", "iglesia", "templo",
    "colegio", "escuela", "universidad", "academia", "guarderia", "kinder", "institucion",
    "banco", "cooperativa", "credito", "caja", "seguro", "abogado", "notaria", "contador",
    "contad", "auditor", "despacho", "consultori", "gabinete", "fundacion", "ONG", "policia",
    "hotel", "motel", "hostal", "viaje", "turismo", "tour", "museo", "cine", "teatro",
    "fotografi", "musica", "floristeria", "videojuego", "optica", "óptica", "electronica",
    "computador", "software", "tecnolog", "sistemas", "implant", "publicidad", "marketing",
    "distribuidor", "mayorista", "bazar", "codiller", "acopio", "reciclaj", "cementer",
    "militar", "radio", "tv", "gas", "gasolinera", "farmacos", "clinica de suenos",
    "centro de salud", "hospital", "medico", "medicina general", "pediatra", "psicolog",
    "fisioterapia", "fisioterapeuta", "audifono", "cirugia plastica",
    # comida / gastronomía / cadenas globales: nunca una clínica dental
    "mcdonald", "burger", "hamburg", "hamburgues", "kfc", "pizza", "pizzeria", "domino",
    "wendy", "taco", "tacos", "starbucks", "subway", "pollo", "campero", "church",
    "hardee", "carl", "popeyes", "dunkin", "denny", "ihop", "applebee", "outback",
    "chilli", "friday", "bembos", "grill", "parrilla", "comida rapida", "comida rápida",
    "drive thru", "snack", "helad", "helader", "fries", "bistro", "comedor", "comedores",
    "desayun", "almuerzo", "sandwich", "cabritos", "asado", "mariscos", "carnes",
    "tortillas", "tamales", "pupusas", "baleada", "casamiento", "gaseosa", "fresco",
    "burger king", "jamburgers", "cocacola", "pepsi", "coca-cola",
]

_RUBRO_DENTAL_KEYS = [
    "clinicas dentales", "clinica dental", "clínica dental", "clínicas dentales",
    "odontologia", "odontología", "odontologo", "dentista", "dental clinics",
    "ortodoncia", "implantes dentales", "blanqueamiento dental", "endodoncia",
    "periodoncia", "cirugia oral", "dental", "dientes",
]

# Positive keywords: name MUST contain at least one of these per rubro.
# If a rubro has entries here, ONLY businesses matching these are accepted.
# If a rubro has NO entries here, only the negative filter applies.
_RUBRO_POSITIVE_KEYWORDS = {
    'bienes raices': [
        'inmobiliaria', 'inmobiliari', 'bienes raices', 'bienes raíces',
        'real estate', 'propiedad', 'propiedades', 'constructora', 'constructor',
        'finca raiz', 'finca raíz', 'urbanizacion', 'urbanización',
        'asesor inmobiliario', 'agencia inmobiliaria', 'desarrolladora',
        'promotora inmobiliaria', 'remate', 'hipotecario',
        'lotero', 'terreno', 'lote', 'apartamento', 'casa venta',
        'vende', 'venta de', 'alquiler de',
    ],
    'inmobiliaria': [
        'inmobiliaria', 'inmobiliari', 'propiedad', 'propiedades',
        'constructora', 'constructor', 'finca raiz', 'finca raíz',
        'urbanizacion', 'urbanización', 'real estate',
        'asesor inmobiliario', 'desarrolladora',
    ],
    'real estate': [
        'inmobiliaria', 'inmobiliari', 'propiedad', 'propiedades',
        'constructora', 'constructor', 'real estate',
        'finca raiz', 'finca raíz', 'urbanizacion', 'urbanización',
        'asesor inmobiliario', 'desarrolladora',
    ],
    'restaurante': [
        'restaurante', 'restaurant', 'comedor', 'fonda', 'cocina',
        'comida', 'asador', 'parrilla', 'steakhouse', 'pizza', 'hamburguesa',
        'sushi', 'tacos', 'cevicheria', 'cevichería', 'poke',
    ],
    'salon de belleza': [
        'salon', 'salón', 'belleza', 'beauty', 'spa', 'estetica', 'estética',
        'peluqueria', 'peluquería', 'barber', 'barbería', 'nails', 'uñas',
        'maquillaj', 'makeup',
    ],
    'gimnasio': [
        'gimnasio', 'gym', 'fitness', 'crossfit', 'box', 'entrenamiento',
    ],
    'farmacia': [
        'farmacia', 'drogueria', 'droguería',
    ],
    'clinicas dentales': [
        'clinica', 'clínica', 'clinic', 'odontolog', 'dentista', 'dental',
        'ortodoncia', 'implante', 'endodoncia', 'periodoncia',
        'blanqueamiento', 'caries', 'muela', 'sonris', 'smile', 'dientes', 'maxilo',
    ],
    'clinica dental': ['clinica', 'clínicas', 'clinic', 'odontolog', 'dentista', 'dental'],
    'clínica dental': ['clinica', 'clínicas', 'clinic', 'odontolog', 'dentista', 'dental'],
    'odontologia': ['odontolog', 'dentista', 'dental'],
    'odontología': ['odontolog', 'dentista', 'dental'],
    'odontologo': ['odontolog', 'dentista'],
    'dentista': ['dentista', 'dental', 'odontolog'],
    'dental clinics': ['clinic', 'clínica', 'clinica', 'dental', 'odontolog', 'dentist'],
    'ortodoncia': ['ortodoncia', 'dentista', 'dental', 'clinica', 'clínica'],
    'implantes dentales': ['implante', 'dental', 'dentista', 'clinica', 'clínica'],
    'blanqueamiento dental': ['blanqueamiento', 'dental', 'dentista', 'clinica', 'clínica'],
    'endodoncia': ['endodoncia', 'dental', 'dentista', 'clinica', 'clínica'],
    'periodoncia': ['periodoncia', 'dental', 'dentista', 'clinica', 'clínica'],
    'cirugia oral': ['cirugia oral', 'maxil', 'dental', 'dentista', 'clinica', 'clínica'],
    'dental': ['dental', 'dentista', 'odontolog', 'clinica', 'clínica'],
}


def _nombre_consiste_con_rubro(nombre: str, rubro: str) -> bool:
    """Two-layer filter:
    1. NEGATIVE: reject if name clearly belongs to a different business type.
    2. POSITIVE: if this rubro has positive keywords, name MUST match at least one.
    If rubro has no positive keywords, negative filter alone is enough.
    Rubros dentales: además se rechazan palabras de industrias ajenas y se aceptan
    marcas genéricas (sin palabra de rubro) pero nunca negocios de otra categoría."""
    rubro_lower = rubro.lower().strip()
    nombre_lower = nombre.lower().strip()

    if rubro_lower in _RUBRO_DENTAL_KEYS:
        for w in _PALABRAS_AJENAS_DENTAL:
            if w in nombre_lower:
                return False
        # EXIGENTE: debe haber señal dental explícita en el nombre (mismo criterio que el envío)
        for kw in _RUBRO_POSITIVE_KEYWORDS.get("clinicas dentales", []):
            if kw in nombre_lower:
                return True
        return False

    # Layer 1: negative filter
    neg = _NON_RUBRO_KEYWORDS.get(rubro_lower, [])
    for kw in neg:
        if kw in nombre_lower:
            return False

    # Layer 2: positive filter (if defined for this rubro)
    pos = _RUBRO_POSITIVE_KEYWORDS.get(rubro_lower, [])
    if pos:
        for kw in pos:
            if kw in nombre_lower:
                return True
        return False  # no positive match = reject

    return True  # no positive filter defined = accept if not rejected by negative


def _construir(nombre, telefono, direccion, rubro, ubicacion, maps_url="", website="", fuente=""):
    wa = generar_wa_url(telefono, nombre) if telefono else ""
    partes = [p.strip() for p in ubicacion.split(",")]
    ciudad = partes[0] if len(partes) >= 1 else ""
    pais = partes[-1].strip() if len(partes) >= 2 else ""
    return {
        "nombre": nombre,
        "telefono": telefono,
        "telefono_formateado": telefono,
        "telefono_limpio": limpiar_telefono(telefono),
        "fuente_telefono": fuente,
        "direccion": direccion,
        "rubro": rubro,
        "pais": pais,
        "ciudad": ciudad,
        "ubicacion_busqueda": ubicacion,
        "maps_url": maps_url,
        "place_id": re.sub(r'[^a-z0-9]', '_', nombre.lower().strip())[:60],
        "lat": 0, "lng": 0, "rating": "", "total_reviews": "",
        "whatsapp_url": wa,
        "wa_url": wa,
        "estado_contacto": "No Contactado", "notas": "",
        "fecha_creacion": "", "fecha_contacto": "", "website": website,
    }


def _es_telefono_valido(clean: str) -> bool:
    return bool(clean and 8 <= len(clean) <= 15 and not clean.startswith("000"))


def _extraer_telefonos(texto: str, prefijo: str = "") -> List[str]:
    phones = []
    for m in re.finditer(r'(?:[\+]\d{1,3}[\s\-\.\(\)]*)?\d[\d\s\-\.\(\)]{6,}', texto):
        raw = m.group().strip()
        clean = limpiar_telefono(raw)
        if _es_telefono_valido(clean):
            if prefijo and not clean.startswith(limpiar_telefono(prefijo)):
                continue
            phones.append(raw)
    return phones


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EMAIL_ARTIFACT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".js", "@example", "@domain", "@email", "sentry")


def _validar_email(email: str) -> bool:
    e = (email or "").strip().lower()
    return bool(e and 5 < len(e) < 254 and _EMAIL_RE.fullmatch(e) and not any(a in e for a in _EMAIL_ARTIFACT))


def _extraer_email(texto: str) -> List[str]:
    unicos = {}
    for m in _EMAIL_RE.finditer(texto or ""):
        e = m.group(0).strip().lower().strip(".")
        if _validar_email(e) and e not in unicos:
            unicos[e] = e
    return list(unicos.values())


def _validar_website(website: str) -> str:
    w = (website or "").strip()
    if not w:
        return ""
    if w.lower().startswith("www."):
        w = "https://" + w
    if not w.lower().startswith(("http://", "https://")):
        w = "https://" + w
    return w


_DIRECTORIOS_DOMINIOS = (
    "yellowpages", "paginasamarillas", "paginas-amarillas", "paginasamarrillas",
    "paginas amarillas", "yp.com", "yptogo", "duckduckgo", "google.", "bing",
    "mercadolibre", "linkedin.com", "facebook.", "instagram.", "twitter.",
    "yelp", "cylex", "infoisinfo", "tupagina", "directorioweb", "guia",
    "directorio", "admision", "lapaginadelprogreso", "encuentra24", "comercioyempresa",
    "1000directorio", "directoriodeempresas", "empresite", "infobel", "bizpedia",
    "tuparada", "empresasde", "directoriohoy", "portaldirectorio", "paginaspro",
    "colombiatelefonos", "telefonos", "listado", "azdirectory", "nuestroproveedor",
)

def _dominio_firma(link: str) -> str:
    """Devuelve un dominio real de la empresa si un enlace NO es de un directorio/chimenea.
    Usado para alimentar Hunter por dominio. Retorna '' si es un directorio (no sirve)."""
    link = (link or "").strip()
    if not link:
        return ""
    m = re.match(r'https?://([^/]+)', link)
    if not m:
        return ""
    host = m.group(1).lower()
    host_clean = host.replace("www.", "")
    # quitar subdominios comunes de portales
    for part in host_clean.split("."):
        if part in ("yellowpages", "paginasamarillas", "directorio", "guia", "portal", "infoisinfo", "cylex"):
            return ""
    if host_clean.startswith(("m.", "www.")):
        host_clean = host_clean[2:]
    if not host_clean or "." not in host_clean:
        return ""
    if any(d in host_clean for d in _DIRECTORIOS_DOMINIOS):
        return ""
    # rechaza enlaces a directorios con rutas conocidas
    if any(k in link.lower() for k in ("/directorio", "paginas-amarillas", "yellowpages", "infobel")):
        return ""
    return host_clean


# =============================================================================
# FUENTE 1: OpenStreetMap
# =============================================================================

_NOMBRES_GENERICOS = {
    "restaurante", "restaurant", "cafe", "bar", "tienda", "farmacia",
    "supermercado", "hotel", "clinica", "clínica", "dentista", "dental",
    "peluqueria", "peluquería", "taller", "mecánico", "mecanico",
    "gasolinera", "ferreteria", "ferretería", "gimnasio", "veterinaria",
    "libreria", "librería", "optica", "óptica", "panaderia", "panadería",
    "abogado", "contador", "inmobiliaria", "deportes",
    "sin nombre", "no name", "unnamed", "unknown", "n/a", "s/d",
    "local", "negocio", "comercio", "establecimiento",
}


def _nombre_valido(nombre: str) -> bool:
    n = nombre.lower().strip()
    if len(n) < 4:
        return False
    if n in _NOMBRES_GENERICOS:
        return False
    parts = n.split()
    if len(parts) <= 2 and all(c.isascii() and c.isalpha() for c in n.replace(" ", "")):
        return False
    if re.match(r'^[a-z]{1,3}\s*$', n):
        return False
    return True

_RUBRO_OSM = {
    "restaurante": ["amenity=restaurant", "amenity=fast_food", "amenity=food_court"],
    "restaurant": ["amenity=restaurant", "amenity=fast_food", "amenity=food_court"],
    "café": ["amenity=cafe"], "cafe": ["amenity=cafe"],
    "bar": ["amenity=bar", "amenity=pub"],
    "farmacia": ["amenity=pharmacy", "shop=chemist"],
    "supermercado": ["shop=supermarket", "shop=convenience"],
    "tienda": ["shop=supermarket", "shop=convenience", "shop=general"],
    "panadería": ["shop=bakery"], "panaderia": ["shop=bakery"],
    "taller": ["shop=car_repair", "shop=car", "amenity=car_workshop"],
    "mecánico": ["shop=car_repair", "shop=car", "amenity=car_workshop"],
    "mecanico": ["shop=car_repair", "shop=car", "amenity=car_workshop"],
    "automotriz": ["shop=car_repair", "shop=car", "amenity=car_workshop"],
    "auto": ["shop=car_repair", "shop=car"],
    "hotel": ["tourism=hotel", "tourism=hostel"],
    "clinica": ["amenity=clinic", "healthcare=clinic"],
    "clínica": ["amenity=clinic", "healthcare=clinic"],
    "dentista": ["amenity=dentist", "healthcare=dentist"],
    "dental": ["amenity=dentist", "healthcare=dentist"],
    "clinicas dentales": ["amenity=dentist", "healthcare=dentist"],
    "clinica dental": ["amenity=dentist", "healthcare=dentist"],
    "clínica dental": ["amenity=dentist", "healthcare=dentist"],
    "clínicas dentales": ["amenity=dentist", "healthcare=dentist"],
    "odontologia": ["amenity=dentist", "healthcare=dentist"],
    "odontología": ["amenity=dentist", "healthcare=dentist"],
    "odontologo": ["amenity=dentist", "healthcare=dentist"],
    "dental clinics": ["amenity=dentist", "healthcare=dentist"],
    "ortodoncia": ["amenity=dentist", "healthcare=dentist"],
    "implantes dentales": ["amenity=dentist", "healthcare=dentist"],
    "blanqueamiento dental": ["amenity=dentist", "healthcare=dentist"],
    "endodoncia": ["amenity=dentist", "healthcare=dentist"],
    "periodoncia": ["amenity=dentist", "healthcare=dentist"],
    "cirugia oral": ["amenity=dentist", "healthcare=dentist"],
    "dientes": ["amenity=dentist", "healthcare=dentist"],
    "peluqueria": ["shop=hairdresser"],
    "peluquería": ["shop=hairdresser"],
    "gasolinera": ["amenity=fuel"],
    "ferreteria": ["shop=hardware"],
    "ferretería": ["shop=hardware"],
    "gimnasio": ["leisure=fitness_centre"],
    "veterinaria": ["amenity=veterinary"],
    "libreria": ["shop=books"],
    "librería": ["shop=books"],
    "optica": ["shop=optician"],
    "electrónica": ["shop=electronics"],
    "computadora": ["shop=computer"],
    "lavanderia": ["shop=laundry"],
    "inmobiliaria": ["office=estate_agent", "office=agent"],
    "bienes raices": ["office=estate_agent", "office=agent"],
    "bienes raíces": ["office=estate_agent", "office=agent"],
    "real estate": ["office=estate_agent", "office=agent"],
    "propiedades": ["office=estate_agent", "office=agent"],
    "constructora": ["office=construction_company", "building=construction"],
}


def _rubro_a_osm_tags(rubro: str) -> List[str]:
    r = rubro.lower().strip()
    for key, tags in _RUBRO_OSM.items():
        if key in r or r in key:
            return tags
    return ["shop", "amenity"]


def _geocodificar(ciudad: str, pais: str = "") -> Optional[tuple]:
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={quote(ciudad)}&format=json&limit=5"
        resp = requests.get(url, headers={"User-Agent": "PSKloudProspector/1.0"}, timeout=10).json()
        if not resp:
            return None
        if pais:
            for r in resp:
                if pais.lower() in [p.strip() for p in r.get("display_name", "").lower().split(",")]:
                    return (float(r["lat"]), float(r["lon"]))
        return (float(resp[0]["lat"]), float(resp[0]["lon"]))
    except Exception:
        return None


def _buscar_overpass(rubro: str, ubicacion: str) -> List[Dict]:
    resultados, vistos = [], set()
    ciudad = ubicacion.split(",")[0].strip()
    pais = ubicacion.split(",")[-1].strip() if "," in ubicacion else ""
    coords = _geocodificar(ubicacion, pais) or _geocodificar(ciudad, pais)
    if not coords:
        return []

    tags = _rubro_a_osm_tags(rubro)
    for radio in [15000, 30000, 50000]:
        filters = []
        for t in tags:
            if "=" in t:
                k, v = t.split("=", 1)
                filters.append(f'["{k}"="{v}"]')
            else:
                filters.append(f'["{t}"]')

        parts = []
        for f in filters:
            for e in ["node", "way", "relation"]:
                parts.append(f'  {e}{f}(around:{radio},{coords[0]},{coords[1]});')

        q = f"[out:json][timeout:60];\n(\n{chr(10).join(parts)}\n);\nout center body;"
        data = None
        for ep in ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]:
            try:
                r = requests.post(ep, data={"data": q}, headers={"Accept": "application/json", "User-Agent": "PSKloudProspector/1.0"}, timeout=60)
                if r.status_code == 200:
                    data = r.json()
                    break
            except Exception:
                continue
        if not data:
            continue

        for el in data.get("elements", []):
            t = el.get("tags", {})
            name = t.get("name", "")
            if not name or not _nombre_valido(name):
                continue
            if not _nombre_consiste_con_rubro(name, rubro):
                continue
            key = name.lower().strip()
            if key in vistos:
                continue
            vistos.add(key)

            phone = t.get("phone", t.get("contact:phone", t.get("telephone", "")))
            resultados.append(_construir(
                nombre=name,
                telefono=phone,
                direccion=", ".join(filter(None, [t.get("addr:street",""), t.get("addr:housenumber",""), t.get("addr:city","")])),
                rubro=rubro, ubicacion=ubicacion,
                maps_url=f"https://www.google.com/maps?q={el.get('lat', el.get('center',{}).get('lat',0))},{el.get('lon', el.get('center',{}).get('lon',0))}",
                website=t.get("website", t.get("contact:website", "")),
                fuente="osm" if phone else "",
            ))

    return resultados


# =============================================================================
# FUENTE 2: DuckDuckGo — búsqueda masiva desde snippets
# =============================================================================

def _ddgs():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None


def _ddg_text(query, region="wt-wt", max_results=5, timeout_sec=20):
    """DDG text search with timeout using concurrent.futures."""
    DDGS = _ddgs()
    if not DDGS:
        return []
    from concurrent.futures import ThreadPoolExecutor
    def _search():
        with DDGS() as d:
            return list(d.text(query, region=region, max_results=max_results, backend="mojeek,yahoo,startpage,yandex"))
    with ThreadPoolExecutor(1) as ex:
        try:
            return ex.submit(_search).result(timeout=timeout_sec)
        except Exception:
            return []


def _buscar_ddg_batch(rubro: str, ubicacion: str, max_results: int = 30) -> List[Dict]:
    """Busca en DDG y extrae negocios + teléfonos directamente de los snippets."""
    resultados, vistos = [], set()
    ciudad = ubicacion.split(",")[0].strip()
    prefijo = _detectar_prefijo(ubicacion)
    region = _detectar_region_ddg(ubicacion)

    queries = [
        f"{rubro} en {ciudad} telefono",
        f"directorio {rubro} {ciudad} telefono",
        f"paginas amarillas {rubro} {ciudad}",
        f"lista {rubro} {ciudad} numero telefono",
        f"guia {rubro} {ubicacion} telefono",
        f"mejores {rubro} {ciudad} contacto",
    ]

    for q in queries:
        if len(resultados) >= max_results:
            break
        for r in _ddg_text(q, region=region, max_results=10):
            if len(resultados) >= max_results:
                break
            try:
                title = r.get("title", "")
                snippet = r.get("body", "")
                link = r.get("href", "")
                full = f"{title}\n{snippet}"

                phones = _extraer_telefonos(full, prefijo)
                if not phones:
                    continue

                name = re.split(r'\s*[\|\-–:]\s*', title)[0].strip()
                if not name or not _nombre_valido(name) or name.lower() in vistos:
                    continue
                if not _nombre_consiste_con_rubro(name, rubro):
                    continue
                vistos.add(name.lower())

                emails = _extraer_email(full)
                web_email = emails[0] if emails else ""
                firm_domain = _dominio_firma(link)
                sitio = "https://" + firm_domain if firm_domain else link

                lead = _construir(name, phones[0], "", rubro, ubicacion, link, sitio, fuente="ddg_batch")
                lead["email"] = web_email
                lead["web_email"] = web_email
                lead["dominio_firma"] = firm_domain
                resultados.append(lead)
            except Exception:
                continue

    return resultados


# =============================================================================
# FUENTE 3: DuckDuckGo — búsqueda individual por nombre
# =============================================================================

def _buscar_telefono_individual(nombre: str, ubicacion: str, prefijo: str, timeout: int = 8) -> str:
    queries = [
        f'{nombre} {ubicacion} telefono whatsapp',
        f'{nombre} {ubicacion} contacto celular',
        f'{nombre} {ubicacion} telefono',
        f'{nombre} {ubicacion} numero',
    ]
    for q in queries:
        for r in _ddg_text(q, max_results=3, timeout_sec=timeout):
            phones = _extraer_telefonos(f"{r.get('title','')}\n{r.get('body','')}", prefijo)
            if phones:
                return phones[0]
    return ""


def _buscar_grokipedia_batch(sin_telefono: List[Dict], ubicacion: str, prefijo: str, max_checks: int = 40) -> int:
    """Phone lookup via DDG individual search (8s timeout)."""
    found = 0
    for r in sin_telefono[:max_checks]:
        name = r.get("nombre", "")
        if not name:
            continue
        phone = _buscar_telefono_individual(name, ubicacion, prefijo, timeout=8)
        if phone:
            r["telefono"] = phone
            r["telefono_formateado"] = phone
            r["telefono_limpio"] = limpiar_telefono(phone)
            r["fuente_telefono"] = "ddg_individual"
            r["whatsapp_url"] = generar_wa_url(phone, r["nombre"])
            r["wa_url"] = generar_wa_url(phone, r["nombre"])
            found += 1
    return found


def _groki_phone(nombre: str, ubicacion: str, prefijo: str) -> str:
    """Unused — Grokipedia typeahead API doesn't handle Spanish phone queries."""
    return ""


# =============================================================================
# ORQUESTADOR
# =============================================================================

def scrape_local(rubro: str, ubicacion: str,
                 max_results: int = 300,
                 progress_callback: Optional[Callable] = None) -> List[Dict]:
    resultados, vistos = [], set()
    prefijo = _detectar_prefijo(ubicacion)

    def _agregar(lista):
        added = 0
        for r in lista:
            k = r["nombre"].lower().strip()
            if k not in vistos:
                resultados.append(r)
                vistos.add(k)
                added += 1
        return added

    # FASE 1: OSM (rápido, muchos nombres, algunos con teléfono)
    _agregar(_buscar_overpass(rubro, ubicacion))
    con_tel = sum(1 for r in resultados if r.get("telefono"))
    print(f"[LS] OSM: {len(resultados)} negocios ({con_tel} con teléfono)")

    # FASE 2: DDG batch (negocios con teléfono desde snippets)
    if len(resultados) < max_results:
        remaining = max_results - len(resultados)
        batch = _buscar_ddg_batch(rubro, ubicacion, min(remaining, 40))
        _agregar(batch)
        con_tel = sum(1 for r in resultados if r.get("telefono"))
        print(f"[LS] DDG batch: {len(batch)} ({con_tel} con teléfono)")

    # FASE 3: Web scraping para negocios con website (rápido)
    sin_tel = [r for r in resultados if not r.get("telefono") and r.get("website") and "openstreetmap" not in r["website"]]
    for r in sin_tel[:30]:
        try:
            resp = requests.get(r["website"], headers={"User-Agent": USER_AGENT}, timeout=5)
            if resp.status_code == 200:
                phones = _extraer_telefonos(BeautifulSoup(resp.text, "html.parser").get_text(separator=" ", strip=True)[:5000], prefijo)
                if phones:
                    r["telefono"] = phones[0]
                    r["telefono_formateado"] = phones[0]
                    r["telefono_limpio"] = limpiar_telefono(phones[0])
                    r["fuente_telefono"] = "website_scrape"
                    r["whatsapp_url"] = generar_wa_url(phones[0], r["nombre"])
                    r["wa_url"] = generar_wa_url(phones[0], r["nombre"])
        except Exception:
            continue
    print(f"[LS] Web scrape: {min(len(sin_tel), 30)} revisados")

    # FASE 4: Grokipedia batch en vez de DDG individual
    sin_tel = [r for r in resultados if not r.get("telefono")]
    grok = _buscar_grokipedia_batch(sin_tel, ubicacion, prefijo, max_checks=40)
    print(f"[LS] Grokipedia: {grok} teléfonos encontrados de {len(sin_tel)}")

    con_tel = sum(1 for r in resultados if r.get("telefono"))
    print(f"[LS] TOTAL: {len(resultados)} negocios, {con_tel} con teléfono")
    return resultados


# =============================================================================
# Persistencia
# =============================================================================

def cargar_prospectos_locales() -> List[Dict]:
    if os.path.exists(PROSPECTOS_LOCALES_FILE):
        try:
            with open(PROSPECTOS_LOCALES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def guardar_prospectos_locales(prospectos: List[Dict]):
    with open(PROSPECTOS_LOCALES_FILE, "w", encoding="utf-8") as f:
        json.dump(prospectos, f, ensure_ascii=False, indent=2)


def agregar_prospectos_locales(nuevos: List[Dict]) -> int:
    existentes = cargar_prospectos_locales()
    ids = {p.get("place_id") for p in existentes if p.get("place_id")}
    count = 0
    for p in nuevos:
        pid = p.get("place_id")
        if (pid and pid not in ids) or not pid:
            existentes.append(p)
            if pid:
                ids.add(pid)
            count += 1
    guardar_prospectos_locales(existentes)
    return count


def actualizar_prospecto(place_id: str, estado: str = None, notas: str = None):
    todos = cargar_prospectos_locales()
    for p in todos:
        if p.get("place_id") == place_id:
            if estado:
                p["estado_contacto"] = estado
                p["fecha_contacto"] = datetime.now().isoformat()
            if notas is not None:
                p["notas"] = notas
            break
    guardar_prospectos_locales(todos)
