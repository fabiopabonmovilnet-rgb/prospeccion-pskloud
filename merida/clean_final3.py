"""Limpieza final - quita basura obvia y deja solo leads útiles"""
import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

leads_file = r"C:\Users\fabio\prospeccion-pskloud\merida\leads.json"
with open(leads_file, encoding="utf-8") as f:
    leads = json.load(f)

JUNK_EMAILS = {
    "merida@gmail.com", "ejemplo@gmail.com", "test@test.com",
    "email@email.com", "last_initial@shmerida.com",
    "rrhhclinicamerida@info.com", "john.smith@gmail.com",
    "sketkar@gmail.com", "usoyestilo@gmail.com",
    "candidatos@unmejorempleo.com", "cardenasma60@gmail.com",
}

def is_junk(lead):
    email = lead.get("email", "").strip().lower()
    nombre = lead.get("nombre", "").strip().lower()
    if email in JUNK_EMAILS:
        return True
    if re.search(r'[\u0400-\u04FF]', nombre):
        return True
    if '<' in lead.get("nombre", ""):
        return True
    if len(nombre) < 3:
        return True
    return False

cleaned = []
seen_emails = set()
seen_names = set()

for lead in leads:
    if is_junk(lead):
        continue
    email = lead.get("email", "").lower().strip()
    nombre = lead.get("nombre", "").strip().lower()
    if email and email in seen_emails:
        continue
    if email:
        seen_emails.add(email)
    if nombre in seen_names:
        continue
    seen_names.add(nombre)
    cleaned.append(lead)

with open(leads_file, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

con_email = sum(1 for l in cleaned if l.get("email","").strip())
con_tel = sum(1 for l in cleaned if l.get("telefono","").strip())
from collections import Counter
rubros = Counter(l.get("rubro","") for l in cleaned)

print(f"Antes: {len(leads)} -> Despues: {len(cleaned)}")
print(f"Email: {con_email} | Tel: {con_tel}")
for r, c in rubros.most_common():
    print(f"  {r}: {c}")
