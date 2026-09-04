"""
clean_pool.py — Limpieza y clasificación del pool de prospectos.
Lee prospectos_locales.json, normaliza, clasifica e inserta en pool_clasificado.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import distribuidores_store as store

POOL_FILE = os.path.join(os.path.dirname(__file__), "data", "prospectos_locales.json")

# Mapeo de normalización
PAIS_MAP = {
    "COLOMBIA": "Colombia", "colombia": "Colombia",
    "EL_SALVADOR": "El Salvador", "el salvador": "El Salvador", "El salvador": "El Salvador",
    "COSTA_RICA": "Costa Rica", "costa rica": "Costa Rica", "Costa rica": "Costa Rica",
    "NICARAGUA": "Nicaragua", "nicaragua": "Nicaragua",
    "HONDURAS": "Honduras", "honduras": "Honduras",
    "PANAMA": "Panama", "panama": "Panama", "PANAMÁ": "Panamá", "panamá": "Panamá",
}

RUBRO_MAP = {
    "restaurantes": "Restaurantes",
    "restaurante": "Restaurantes",
    "Restaurantes": "Restaurantes",
    "Ferreterías": "Ferreterias",
    "ferreterías": "Ferreterias",
    "ferreterias": "Ferreterias",
}

# Rubros que son DISTRIBUIDOR (del motor)
RUBROS_DISTRIBUIDOR = {
    "Firmas Contables", "Soporte TI", "Integradores POS",
    "Consultores Fiscales", "Revendedores ERP",
}


def normalize_pais(p: str) -> str:
    return PAIS_MAP.get(p, p).strip().title() if p else ""


def normalize_rubro(r: str) -> str:
    return RUBRO_MAP.get(r, r).strip() if r else ""


def classify_tipo(rubro: str) -> str:
    if rubro in RUBROS_DISTRIBUIDOR:
        return "DISTRIBUIDOR"
    return "CLIENTE_FINAL"


def canal_contacto(email: str, telefono: str) -> str:
    has_email = bool(email and email.strip())
    has_phone = bool(telefono and telefono.strip())
    if has_email and has_phone:
        return "AMBOS"
    if has_email:
        return "EMAIL"
    if has_phone:
        return "WHATSAPP"
    return "SIN_DATOS"


def load_pool() -> list:
    try:
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("leads", [])
        return data
    except Exception as e:
        print(f"Error loading pool: {e}")
        return []


def clean_and_classify():
    pool = load_pool()
    print(f"Pool original: {len(pool)} leads")

    # Normalizar
    for lead in pool:
        lead["pais"] = normalize_pais(lead.get("pais", ""))
        lead["rubro"] = normalize_rubro(lead.get("rubro", ""))
        lead["tipo"] = classify_tipo(lead.get("rubro", ""))
        lead["email"] = (lead.get("email") or "").strip()
        lead["telefono"] = (lead.get("telefono") or lead.get("phone") or "").strip()
        lead["canal_contacto"] = canal_contacto(lead["email"], lead["telefono"])

    # Eliminar sin datos de contacto
    before = len(pool)
    pool = [l for l in pool if l["canal_contacto"] != "SIN_DATOS"]
    eliminated = before - len(pool)
    print(f"Eliminados sin contacto: {eliminated}")
    print(f"Restantes con contacto: {len(pool)}")

    # Deduplicar por nombre+pais+rubro
    seen = set()
    deduped = []
    for l in pool:
        key = (l.get("nombre", "").lower().strip(), l["pais"], l["rubro"])
        if key not in seen:
            seen.add(key)
            deduped.append(l)
    dedups = len(pool) - len(deduped)
    print(f"Deduplicados: {dedups}")
    print(f"Finales: {len(deduped)}")

    # Estadísticas
    from collections import Counter
    tipos = Counter(l["tipo"] for l in deduped)
    canales = Counter(l["canal_contacto"] for l in deduped)
    paises = Counter(l["pais"] for l in deduped)
    rubros = Counter(l["rubro"] for l in deduped)

    print(f"\n=== Por tipo ===")
    for t, c in tipos.most_common():
        print(f"  {t}: {c}")
    print(f"\n=== Por canal ===")
    for t, c in canales.most_common():
        print(f"  {t}: {c}")
    print(f"\n=== Por pais ===")
    for t, c in paises.most_common():
        print(f"  {t}: {c}")
    print(f"\n=== Por rubro ===")
    for t, c in rubros.most_common():
        print(f"  {t}: {c}")

    # Limpiar pool anterior y insertar nuevos
    store.limpiar_pool()
    inserted = store.insertar_pool_batch(deduped)
    print(f"\nInsertados en pool_clasificado: {inserted}")

    stats = store.estadisticas_pool()
    print(f"\n=== Stats finales ===")
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    clean_and_classify()
