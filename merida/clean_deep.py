"""Limpieza PROFUNDA final"""
import json, re

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"

with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)

initial = len(leads)

JUNK_EMAILS = {
    "email@email.com", "ejemplo@gmail.com", "test@test.com",
    "example@example.com", "john.smith@gmail.com",
    "ejemplo@ejemplo.com", "correo@correo.com",
}

JUNK_NAMES = {
    "tiktok", "youtube", "facebook", "instagram", "twitter",
    "contacto", "contact us", "contáctanos", "author details",
    "opiniones", "resumen de opiniones", "fotos", "videos",
    "ponte en contacto", "acerca de nosotros", "ayuda",
    "como llegar", "directorio", "directorioempresarial",
}

def clean_name(n):
    n = n.lower().strip()
    # Remove HTML tags
    n = re.sub(r'<[^>]+>', '', n)
    n = re.sub(r'&[a-z]+;', '', n)
    n = n.strip()
    return n

def is_junk_lead(lead):
    nombre = clean_name(lead.get("nombre", ""))
    email = lead.get("email", "").strip().lower()
    
    # Junk name
    if nombre in JUNK_NAMES or len(nombre) < 3:
        return True
    
    # Junk email
    if email in JUNK_EMAILS:
        return True
    
    # Email is an image file
    if re.search(r'\.(png|jpg|gif|webp|svg|pdf)$', email):
        return True
    
    # Name contains HTML
    if '<' in lead.get("nombre", "") or '&lt;' in lead.get("nombre", ""):
        return True
    
    # Name starts with number only (not a business)
    if re.match(r'^\d+$', nombre):
        return True
    
    # Name is a random string
    if len(nombre) > 40:
        return True
    
    # Email domain is a file/image
    if email and email.split("@")[1] in ("4x-300x199.png", "example.com"):
        return True
    
    return False

cleaned = []
seen_emails = set()
seen_names = set()

for lead in leads:
    # Fix name
    lead["nombre"] = clean_name(lead.get("nombre", ""))
    
    # Fix email
    email = lead.get("email", "").strip().lower()
    lead["email"] = email
    
    # Skip junk
    if is_junk_lead(lead):
        continue
    
    # Dedup by email
    if email and email in seen_emails:
        continue
    if email:
        seen_emails.add(email)
    
    # Dedup by name
    if lead["nombre"] in seen_names:
        continue
    seen_names.add(lead["nombre"])
    
    cleaned.append(lead)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

con_email = sum(1 for l in cleaned if l.get("email","").strip())
con_tel = sum(1 for l in cleaned if l.get("telefono","").strip())
con_ambos = sum(1 for l in cleaned if l.get("email","").strip() and l.get("telefono","").strip())

print(f"Antes: {initial}")
print(f"Despues: {len(cleaned)}")
print(f"  Con email: {con_email}")
print(f"  Con telefono: {con_tel}")
print(f"  Con ambos: {con_ambos}")
