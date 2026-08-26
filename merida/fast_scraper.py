"""
PSKloud Prospector — Scraper rápido v2
Búsqueda directa en Google/Bing via Playwright (sin Google Maps).
Extrae negocios de snippets de resultados de búsqueda.
"""
import re
import time
import json
import os
import sys
import random
from typing import List, Dict, Optional
from urllib.parse import quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_utils import normalizar_telefono_ve, extraer_telefonos, extraer_emails

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "merida_leads.json")

# =============================================================================
# MATRIZ DE BÚSQUEDA B2B — ICP para venta de software/POS
# =============================================================================

MATRIZ_TARGET_SOFTWARE = {
    "Comercio al Detal / POS (Retail)": [
        "supermercado", "ferreteria", "farmacia", "bodegon", "tienda de repuestos",
        "venta de repuestos automotrices", "tienda de ropa", "zapateria",
        "tienda de electronica", "venta de pintura", "libreria", "quincalleria", "minimarket",
        "boutique", "joyeria", "optica", "floristeria", "mascotas", "deportes",
        "videojuegos", "papeleria", "bazar", "artesanias",
    ],
    "Mayoristas & Distribución (ERP / Inventarios)": [
        "distribuidora de alimentos", "mayorista", "empresa de envios", "encomiendas",
        "transporte de carga", "almacenadora", "comercializadora", "distribuidora de licores",
        "distribuidora de bebidas", "distribuidora de productos", "wholesale",
        "importadora", "exportadora",
    ],
    "Gastronomía & Servicios (Comandas / Puntos de Venta)": [
        "restaurante", "panaderia", "pizzeria", "cafe", "pasteleria", "heladeria",
        "bodegon gourmet", "cafeteria", "bar", "reposteria", "comida rapida",
        "polleria", "carniceria", "pescaderia", "comida china", "sushi",
    ],
    "Servicios, Salud & Educación (Facturación / Procesos)": [
        "clinica", "laboratorio clinico", "centro medico", "taller mecanico",
        "hotel", "posada", "colegio privado", "instituto", "constructora", "marmoleria",
        "consultorio medico", "dentista", "veterinaria", "gimnasio", "yoga",
        "fisioterapia", "farmacia", "imprenta", "fotocopia",
    ],
    "Automotriz & Industrial (Inventario / Facturación)": [
        "taller automotriz", "repuesto automotriz", "llanteria", "lavadero de autos",
        "venta de llantas", "mecanica diesel", "taller industrial", "metalmecanica",
        "soldadura", "herreria", "carpinteria", "maderera",
    ],
    "Profesionales & Tecnología (CRM / ERP)": [
        "abogado", "contador", "notaria", "seguros", "inmobiliaria",
        "consultoria", "publicidad", "marketing", "internet cafe",
        "reparacion de celulares", "soporte tecnico", "venta de computadoras",
    ],
}

# Ubicaciones geográficas precisas
UBICACIONES_PRECISAS_MERIDA = {
    "Libertador": "Mérida, Municipio Libertador, Mérida, Venezuela",
    "Alberto Adriani": "El Vigía, Municipio Alberto Adriani, Mérida, Venezuela",
    "Campo Elías": "Ejido, Municipio Campo Elías, Mérida, Venezuela",
    "Sucre": "Lagunillas, Municipio Sucre, Mérida, Venezuela",
}

# Compatibilidad: diccionarios viejos apuntan a los nuevos
DICCIONARIO_RUBROS = MATRIZ_TARGET_SOFTWARE
DICCIONARIO_UBICACIONES = {
    k: {"ciudad": v.split(",")[0], "query_suffix": v, "query_short": f"{v.split(',')[0]} Mérida Venezuela"}
    for k, v in UBICACIONES_PRECISAS_MERIDA.items()
}
CATEGORIAS_COMERCIALES_MERIDA = []
for cats in MATRIZ_TARGET_SOFTWARE.values():
    CATEGORIAS_COMERCIALES_MERIDA.extend(cats)
MUNICIPIOS = list(UBICACIONES_PRECISAS_MERIDA.keys())


def _crear_contexto(playwright):
    """Crea un contexto de navegador anti-detección."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="es-VE",
        timezone_id="America/Caracas",
    )
    # Inyectar script anti-detección
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['es-VE', 'es', 'en']});
    """)
    return browser, context


def _google_search_snippets(query: str, max_results: int = 15) -> List[Dict]:
    """
    Busca en Google y extrae snippets completos (título + URL + descripción).
    Retorna lista de dicts con: title, href, body, source.
    """
    from bs4 import BeautifulSoup

    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAST] Playwright no instalado")
        return []

    with sync_playwright() as p:
        browser, context = _crear_contexto(p)
        page = context.new_page()

        try:
            url = f"https://www.google.com/search?q={quote(query)}&hl=es&gl=ve"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(random.randint(1500, 3000))

            html = page.content()
        except Exception as e:
            print(f"[FAST] Error Google: {e}")
            html = ""
        finally:
            browser.close()

    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")

    # Buscar todos los bloques de resultado
    for g in soup.select("div.g, div[data-sokoban-container]")[:max_results]:
        try:
            # Título + URL
            a_tag = g.select_one("a")
            h3_tag = g.select_one("h3")
            if not h3_tag or not a_tag:
                continue

            title = h3_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]

            # Snippet / descripción
            body_el = g.select_one("div[data-sncf], div.VwiC3b, span.aCOpRe, div[style*='line-clamp']")
            body = body_el.get_text(strip=True) if body_el else ""

            # Teléfonos del snippet
            full_text = f"{title} {body}"
            phones = extraer_telefonos(full_text)

            # Emails del snippet
            emails = extraer_emails(full_text)

            results.append({
                "title": title,
                "href": href,
                "body": body,
                "phones": phones,
                "emails": emails,
                "source": "Google",
            })
        except Exception:
            continue

    return results


def _visit_and_extract_contacts(url: str, timeout: int = 10) -> Dict:
    """Visita una página y extrae teléfonos + emails."""
    from bs4 import BeautifulSoup

    if not url or not url.startswith("http"):
        return {"phones": [], "emails": [], "website": ""}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"phones": [], "emails": [], "website": ""}

    html = ""
    try:
        with sync_playwright() as p:
            browser, context = _crear_contexto(p)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(random.randint(1000, 2000))
            html = page.content()
            browser.close()
    except Exception:
        pass

    if not html:
        return {"phones": [], "emails": [], "website": ""}

    text = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
    return {
        "phones": extraer_telefonos(text),
        "emails": extraer_emails(text),
        "website": url,
    }


def _extract_business_name(title: str) -> str:
    """Limpia el nombre del negocio del título de Google."""
    # Remover - Google Maps, | Google, etc.
    name = re.split(r'[-–|•·]', title)[0].strip()
    # Remover sufijos comunes
    for suffix in ["Google Maps", "Google Search", "Wikipedia", "Facebook", "Instagram"]:
        name = name.replace(suffix, "").strip()
    return name.strip()


def _generar_queries(categoria: str, ubicacion: str) -> List[str]:
    """
    Genera queries de búsqueda optimizadas para una categoría y ubicación.
    """
    query_suffix = UBICACIONES_PRECISAS_MERIDA.get(ubicacion, f"{ubicacion}, Mérida, Venezuela")
    ciudad = query_suffix.split(",")[0]

    queries = [
        f'"{categoria}" {query_suffix} teléfono contacto',
        f'"{categoria}" {ciudad} Mérida Venezuela correo email',
        f'{categoria} {ciudad} Mérida Venezuela teléfono',
    ]

    return queries


def scrape_fast(rubro: str, municipio: str, max_results: int = 20, visit_sites: bool = False) -> List[Dict]:
    """
    Scraping rápido: busca en Google y extrae negocios de snippets.
    """
    resultados = []
    seen_names = set()

    queries = _generar_queries(rubro, municipio)

    for query in queries:
        if len(resultados) >= max_results:
            break

        snippets = _google_search_snippets(query, max_results=max_results)

        for s in snippets:
            nombre = _extract_business_name(s["title"])
            if not nombre or len(nombre) < 3:
                continue
            if nombre.lower() in seen_names:
                continue

            telefono = s["phones"][0] if s["phones"] else ""
            email = s["emails"][0] if s["emails"] else ""

            if visit_sites and s["href"] and (not telefono or not email):
                contacts = _visit_and_extract_contacts(s["href"])
                if not telefono and contacts["phones"]:
                    telefono = contacts["phones"][0]
                if not email and contacts["emails"]:
                    email = contacts["emails"][0]

            lead = {
                "nombre": nombre,
                "rubro": rubro,
                "municipio": municipio,
                "ciudad": UBICACIONES_PRECISAS_MERIDA.get(municipio, "").split(",")[0],
                "telefono": normalizar_telefono_ve(telefono) if telefono else "",
                "email": email,
                "direccion": "",
                "website": s["href"] if s["href"] and not s["href"].startswith("/url") else "",
                "maps_url": "",
                "fuente": "google_search",
                "fecha_creacion": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            resultados.append(lead)
            seen_names.add(nombre.lower())

            if len(resultados) >= max_results:
                break

        time.sleep(0.3)

    return resultados[:max_results]


def scrape_barrido_total(municipios: List[str], max_por_categoria: int = 10, visit_sites: bool = False) -> List[Dict]:
    """
    MODO BARRIDO TOTAL B2B: Busca TODAS las categorías del MATRIZ_TARGET_SOFTWARE.
    OPTIMIZADO: 1 query por categoría (no 3), dedup agresivo.
    """
    all_results = []
    seen_names = set()
    seen_websites = set()

    total_categorias = len(CATEGORIAS_COMERCIALES_MERIDA)
    total_combos = total_categorias * len(municipios)

    for municipio in municipios:
        ubicacion_query = UBICACIONES_PRECISAS_MERIDA.get(municipio, f"{municipio}, Mérida, Venezuela")
        ciudad = ubicacion_query.split(",")[0]

        for segmento, categorias in MATRIZ_TARGET_SOFTWARE.items():
            for categoria in categorias:
                # SOLO 1 query por categoría (la más efectiva)
                query = f'"{categoria}" {ubicacion_query} teléfono email'

                snippets = _google_search_snippets(query, max_results=5)

                for s in snippets:
                    nombre = _extract_business_name(s["title"])
                    if not nombre or len(nombre) < 3:
                        continue
                    if nombre.lower() in seen_names:
                        continue

                    # Dedup por website
                    website = s["href"] if s["href"] and not s["href"].startswith("/url") else ""
                    if website and website in seen_websites:
                        continue

                    telefono = s["phones"][0] if s["phones"] else ""
                    email = s["emails"][0] if s["emails"] else ""

                    lead = {
                        "nombre": nombre,
                        "rubro": categoria,
                        "segmento": segmento,
                        "categoria_busqueda": categoria,
                        "municipio": municipio,
                        "ciudad": ciudad,
                        "telefono": normalizar_telefono_ve(telefono) if telefono else "",
                        "email": email,
                        "direccion": "",
                        "website": website,
                        "maps_url": "",
                        "fuente": "barrido_total_b2b",
                        "fecha_creacion": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }

                    all_results.append(lead)
                    seen_names.add(nombre.lower())
                    if website:
                        seen_websites.add(website)

                time.sleep(0.2)  # Pausa mínima

    # Dedup final
    unique = []
    seen_final = set()
    for r in all_results:
        key = r["nombre"].lower().strip()
        if key not in seen_final:
            seen_final.add(key)
            unique.append(r)

    print(f"[BARRIDO] Total: {len(unique)} leads")
    return unique


def save_leads(leads: List[Dict]):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    print(f"[FAST] Guardados {len(leads)} leads")


def load_leads() -> List[Dict]:
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    print("=" * 60)
    print("  Scraper Rápido v2 — Mérida, Venezuela")
    print("=" * 60)

    leads = scrape_all_fast(max_per_rubro=15, visit_sites=False)
    save_leads(leads)

    con_tel = sum(1 for l in leads if l.get("telefono"))
    con_email = sum(1 for l in leads if l.get("email"))
    print(f"\nTotal: {len(leads)} leads")
    print(f"Con teléfono: {con_tel}")
    print(f"Con email: {con_email}")
