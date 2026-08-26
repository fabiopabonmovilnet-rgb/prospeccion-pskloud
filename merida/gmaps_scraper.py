"""
Scraping rápido de Google Maps para Mérida, Venezuela.
Usa Playwright headless para buscar negocios por rubro en Google Maps.
"""
import re, time, json, os, sys
from typing import List, Dict, Optional
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_utils import normalizar_telefono_ve
from fast_scraper import MATRIZ_TARGET_SOFTWARE, UBICACIONES_PRECISAS_MERIDA, MUNICIPIOS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "merida_leads.json")


def _extract_phones(text: str) -> List[str]:
    """Extrae y normaliza teléfonos venezolanos de texto."""
    phones = []
    for m in re.finditer(r'(?:[\+]\d{1,3}[\s\-\.\(\)]*)?\d[\d\s\-\.\(\)]{7,}', text):
        raw = m.group().strip()
        normalizado = normalizar_telefono_ve(raw)
        if normalizado:
            phones.append(normalizado)
    return phones


def _extract_emails(text: str) -> List[str]:
    """Extrae emails de texto."""
    emails = []
    for m in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
        e = m.group().lower()
        if not any(skip in e for skip in ["example", "sentry", "wix", "google", "facebook"]):
            emails.append(e)
    return list(set(emails))


def scrape_google_maps(rubro: str, municipio: str, max_results: int = 30) -> List[Dict]:
    """
    Busca negocios en Google Maps usando Playwright headless.
    Retorna lista de dict con: nombre, rubro, municipio, telefono, email, direccion, maps_url.
    """
    resultados = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[GMAPS] Playwright no instalado. pip install playwright && playwright install chromium")
        return []

    queries = [
        f"{rubro} en {municipio}, Merida, Venezuela",
        f"{rubro} {municipio}, Merida, Venezuela telefono",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for query in queries:
            if len(resultados) >= max_results:
                break

            try:
                search_url = f"https://www.google.com/maps/search/{quote(query)}"
                page.goto(search_url, wait_until="networkidle", timeout=20000)
                time.sleep(2)

                # Scroll para cargar más resultados
                for _ in range(3):
                    page.mouse.wheel(0, 500)
                    time.sleep(1)

                # Buscar elementos de resultados
                cards = page.query_selector_all('[class*="Nv2PK"]') or page.query_selector_all('.section-result')

                if not cards:
                    # Intentar otro selector
                    cards = page.query_selector_all('a[href*="/maps/place/"]')

                for card in cards[:max_results]:
                    try:
                        nombre = ""
                        # Obtener nombre del título
                        title_el = card.query_selector('.qBF1Pd') or card.query_selector('.fontHeadlineSmall') or card.query_selector('[class*="heading"]')
                        if title_el:
                            nombre = title_el.inner_text().strip()

                        if not nombre or len(nombre) < 3:
                            continue

                        # Obtener rating/reseñas
                        rating = ""
                        rating_el = card.query_selector('.MW4etd')
                        if rating_el:
                            rating = rating_el.inner_text().strip()

                        # Obtener tipo de negocio
                        tipo = ""
                        tipo_el = card.query_selector('.W4Efsd')
                        if tipo_el:
                            tipo = tipo_el.inner_text().strip()

                        # Obtener dirección del snippet
                        direccion = ""
                        addr_el = card.query_selector('.W4Efsd:nth-child(2)')
                        if addr_el:
                            direccion = addr_el.inner_text().strip()

                        # Obtener teléfono del snippet
                        telefono = ""
                        snippet_text = card.inner_text()
                        phones = _extract_phones(snippet_text)
                        if phones:
                            telefono = phones[0]

                        # Obtener link de Google Maps
                        link_el = card.query_selector('a[href*="/maps/place/"]')
                        maps_url = link_el.get_attribute("href") if link_el else ""

                        # Obtener email del snippet (raro en Maps pero por si acaso)
                        email = ""
                        emails = _extract_emails(snippet_text)
                        if emails:
                            email = emails[0]

                        resultados.append({
                            "nombre": nombre,
                            "rubro": rubro,
                            "municipio": municipio,
                            "telefono": telefono,
                            "email": email,
                            "direccion": direccion,
                            "rating": rating,
                            "tipo_negocio": tipo,
                            "maps_url": maps_url,
                            "fuente": "google_maps",
                            "fecha_creacion": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        })

                    except Exception as e:
                        continue

                print(f"[GMAPS] {query}: {len(resultados)} resultados")

            except Exception as e:
                print(f"[GMAPS] Error en query '{query}': {e}")
                continue

        browser.close()

    # Dedup por nombre
    seen = set()
    unique = []
    for r in resultados:
        key = r["nombre"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique[:max_results]


def scrape_all_rubros(max_per_rubro: int = 20) -> List[Dict]:
    """Scrapea todos los rubros en todos los municipios."""
    all_results = []

    for municipio in MUNICIPIOS:
        ciudad = UBICACIONES_PRECISAS_MERIDA.get(municipio, "").split(",")[0]
        for segmento, categorias in MATRIZ_TARGET_SOFTWARE.items():
            for categoria in categorias[:3]:  # Top 3 por segmento
                print(f"\n[GMAPS] Scraping {categoria} en {municipio} ({ciudad})...")
                results = scrape_google_maps(categoria, municipio, max_per_rubro)
                all_results.extend(results)
                print(f"[GMAPS] {categoria}/{municipio}: {len(results)} encontrados")
                time.sleep(2)

    # Dedup final
    seen = set()
    unique = []
    for r in all_results:
        key = r["nombre"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def save_leads(leads: List[Dict]):
    """Guarda leads en JSON."""
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    print(f"[GMAPS] Guardados {len(leads)} leads en {RESULTS_FILE}")


def load_leads() -> List[Dict]:
    """Carga leads desde JSON."""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    print("=" * 60)
    print("  Google Maps Scraper - Mérida, Venezuela")
    print("=" * 60)

    leads = scrape_all_rubros(max_per_rubro=20)
    save_leads(leads)

    con_tel = sum(1 for l in leads if l.get("telefono"))
    con_email = sum(1 for l in leads if l.get("email"))
    print(f"\nTotal: {len(leads)} leads")
    print(f"Con teléfono: {con_tel}")
    print(f"Con email: {con_email}")
