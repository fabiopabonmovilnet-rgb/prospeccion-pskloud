"""Limpieza final - quita lo obviamente basura"""
import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)

JUNK_NAMES = {
    "tiktok", "youtube", "facebook", "instagram", "twitter",
    "contacto", "contact us", "contáctanos", "author details",
    "opiniones", "resumen de opiniones", "fotos", "videos",
    "ponte en contacto", "acerca de nosotros", "ayuda",
    "como llegar", "directorio", "directorioempresarial",
    "aralven 0412 9780484 email", "bdvenlínea personas",
    "ps4 раздача", "arroba (@)", "concesionarios",
    "teléfono y dirección", "contact", "datos de empresa",
    "contactenos", "decisiones del dia 14/08/2025",
    "authorised aerial examiners", "ccdrmrmcontacto",
    "aceites y grasas comestibles", "hikvision",
    "inter", "seguros", "agrícola por contrato",
}

JUNK_EMAILS = {
    "email@email.com", "merida@gmail.com", "sketkar@gmail.com",
    "usoyestilo@gmail.com", "test@test.com", "ejemplo@gmail.com",
}

def is_junk(lead):
    nombre = lead.get("nombre", "").strip().lower()
    email = lead.get("email", "").strip().lower()
    if nombre in JUNK_NAMES:
        return True
    if email in JUNK_EMAILS:
        return True
    # Russian/cyrillic
    if re.search(r'[\u0400-\u04FF]', nombre):
        return True
    # HTML in name
    if '<' in lead.get("nombre", ""):
        return True
    # Random short junk names
    if nombre in ("arriba", "abajo", "áreas", "ayuda", "fotos"):
        return True
    return False

cleaned = []
seen = set()
for lead in leads:
    if is_junk(lead):
        continue
    key = lead.get("email", "").lower().strip() or lead.get("nombre", "").lower().strip()
    if key in seen:
        continue
    seen.add(key)
    cleaned.append(lead)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

con_email = sum(1 for l in cleaned if l.get("email","").strip())
con_tel = sum(1 for l in cleaned if l.get("telefono","").strip())
from collections import Counter
rubros = Counter(l.get("rubro","") for l in cleaned)

print(f"Antes: {len(leads)} -> Despues: {len(cleaned)}")
print(f"Email: {con_email} | Tel: {con_tel}")
print()
for r, c in rubros.most_common():
    print(f"  {r}: {c}")
