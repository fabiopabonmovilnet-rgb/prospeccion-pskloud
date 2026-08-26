"""
Limpieza de leads.json - elimina basura:
- Emails genéricos (ejemplo, test, noreply)
- Emails de dominios no venezolanos sin contexto VE
- Teléfonos que no son de Venezuela (02xx sin prefijo celular)
- Leads sin email Y sin teléfono válido
- Leads con nombres que parecen páginas web, no negocios
"""
import json, re

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"

with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)

initial = len(leads)

# BAD email patterns
BAD_EMAILS = {
    "ejemplo@gmail.com", "test@test.com", "noreply@", "no-reply@",
    "john.smith@gmail.com", "example@example.com",
}

BAD_DOMAINS = {
    "sentry.io", "wixpress.com", "google.com", "localhost", "schema.org",
    "w3.org", "wordpress.org", "squarespace.com", "wix.com", "godaddy.com",
    "apple.com", "microsoft.com", "tiktok.com", "meneame.es", "redalyc.org",
    "unmejorempleo.com", "prodigy.net.mx", "comalsa.com", "cafrimx.com",
    "odoo.com", "overtimeve.com",
}

# Non-Venezuelan domains that appear with Merida Mexico
MEXICO_DOMAINS = {
    "hotmail.com", "gmail.com", "yahoo.com", "outlook.com", "live.com",
}

def es_tel_ve(t):
    d = re.sub(r'[^\d]', '', t)
    if not d:
        return False
    prefixes_ve = ("0412","0414","0416","0424","0426","0413","0415","0417",
                   "0274","0271","0275","0276","0273","0278","0279")
    prefixes_int_ve = ("412","414","416","424","426","413","415","417",
                       "274","271","275","276","273","278","279")
    if len(d) == 11 and d.startswith("0"):
        return d[:4] in prefixes_ve
    if len(d) == 12 and d.startswith("58"):
        return d[2:6] in prefixes_int_ve
    if len(d) == 10 and d.startswith("58"):
        return d[2:6] in prefixes_int_ve
    return False

def clean_email(email):
    email = email.lower().strip()
    if len(email) < 5 or len(email) > 80:
        return ""
    parts = email.split("@")
    if len(parts) != 2:
        return ""
    user, domain = parts
    if domain in BAD_DOMAINS:
        return ""
    if any(bad in email for bad in BAD_EMAILS):
        return ""
    # Skip emails that are clearly not business
    if user.startswith(("test", "example", "noreply", "no-reply", "abuse", "postmaster")):
        return ""
    # Skip super long usernames (likely scraped junk)
    if len(user) > 30:
        return ""
    return email

def es_nombre_junk(nombre):
    """Check if a name looks like junk, not a real business."""
    nombre = nombre.lower().strip()
    # Too short or too generic
    if len(nombre) < 4:
        return True
    # Looks like a page title, not a business name
    junk_patterns = [
        "opiniones", "resumen", "fotos", "videos", "imagenes",
        "como llegar", "direccion", "telefono de contacto",
        "email &", "emails &", "author details", "contact us",
        "contáctanos", "acerca de", "ponte en contacto",
        "directorio", "empresas en", "79 empresas",
        "mejores", "lista de", "transporte y",
        "ves%", "http", "www.", ".com", ".ve",
        "agregar la", "en este lugar",
    ]
    for p in junk_patterns:
        if p in nombre:
            return True
    return False

cleaned = []
removed = 0
for lead in leads:
    email = lead.get("email", "").strip()
    tel = lead.get("telefono", "").strip()
    nombre = lead.get("nombre", "")
    
    # Clean email
    email_clean = clean_email(email) if email else ""
    if email_clean != email:
        lead["email"] = email_clean
    
    # Validate phone
    if tel and not es_tel_ve(tel):
        lead["telefono"] = ""
        tel = ""
    
    # Remove junk names
    if es_nombre_junk(nombre):
        removed += 1
        continue
    
    # Remove leads with no useful data
    if not lead.get("email", "").strip() and not lead.get("telefono", "").strip():
        removed += 1
        continue
    
    cleaned.append(lead)

# Deduplicate by name
seen = set()
deduped = []
dupes = 0
for lead in cleaned:
    norm = lead.get("nombre", "").lower().strip()
    if norm in seen:
        dupes += 1
        continue
    seen.add(norm)
    deduped.append(lead)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

con_email = sum(1 for l in deduped if l.get("email", "").strip())
con_tel = sum(1 for l in deduped if l.get("telefono", "").strip())
con_ambos = sum(1 for l in deduped if l.get("email", "").strip() and l.get("telefono", "").strip())

print(f"Antes: {initial}")
print(f"Eliminados (basura): {removed}")
print(f"Duplicados: {dupes}")
print(f"Despues: {len(deduped)}")
print(f"  Con email: {con_email}")
print(f"  Con telefono: {con_tel}")
print(f"  Con ambos: {con_ambos}")
