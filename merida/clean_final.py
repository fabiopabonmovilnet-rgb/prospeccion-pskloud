"""Limpieza final de leads - quita emails rotos y duplicados por email"""
import json, re

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"

with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)

initial = len(leads)

def email_valido(e):
    e = e.lower().strip()
    if not e or "@" not in e or "." not in e:
        return False
    if len(e) < 6 or len(e) > 70:
        return False
    # Junk patterns
    junk = ["4x-300","ejemplo","test@","noreply","example","example.com",
            "recursos-2@","recurso-2@",".png",".jpg",".gif",".webp",
            "root@","admin@","user@"]
    for j in junk:
        if j in e:
            return False
    user, domain = e.split("@")
    if len(user) > 25:
        return False
    bad_domains = {"sentry.io","wixpress.com","localhost","schema.org","w3.org",
                   "wordpress.org","squarespace.com","wix.com","godaddy.com"}
    if domain in bad_domains:
        return False
    return True

def tel_valido(t):
    d = re.sub(r"[^\d]", "", t)
    if len(d) < 10:
        return False
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417",
                "0274","0271","0275","0276","412","414","416","424","426",
                "274","271","275","276","58")
    if d.startswith("0"):
        return d[:4] in prefixes[:8]
    if d.startswith("58"):
        return True
    return False

cleaned = []
seen_emails = set()
seen_names = set()
removed = 0

for lead in leads:
    email = lead.get("email", "").strip()
    tel = lead.get("telefono", "").strip()
    nombre = lead.get("nombre", "").strip()
    
    # Fix email
    if email and not email_valido(email):
        lead["email"] = ""
        email = ""
    
    # Fix phone
    if tel and not tel_valido(tel):
        lead["telefono"] = ""
        tel = ""
    
    # Skip if no data
    if not email and not tel:
        removed += 1
        continue
    
    # Dedup by email
    if email and email.lower() in seen_emails:
        removed += 1
        continue
    if email:
        seen_emails.add(email.lower())
    
    # Dedup by name
    norm_name = nombre.lower().strip()
    if norm_name in seen_names:
        removed += 1
        continue
    seen_names.add(norm_name)
    
    cleaned.append(lead)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

con_email = sum(1 for l in cleaned if l.get("email","").strip())
con_tel = sum(1 for l in cleaned if l.get("telefono","").strip())
con_ambos = sum(1 for l in cleaned if l.get("email","").strip() and l.get("telefono","").strip())

print(f"Antes: {initial}")
print(f"Eliminados: {removed}")
print(f"Despues: {len(cleaned)}")
print(f"  Con email: {con_email}")
print(f"  Con telefono: {con_tel}")
print(f"  Con ambos: {con_ambos}")
