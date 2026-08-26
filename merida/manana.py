"""
MAÑANA TEMPRANO - Script único: busca empresas nuevas + envía correos y WhatsApp.
Solo ejecutar: python manana.py
"""
import sys, os, json, time, random, re, smtplib, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE = r"C:\Users\fabio\prospeccion-pskloud\merida"

# ==================== FUNCIONES ====================
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_FULL = re.compile(r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|\d{4}[\s.-]\d{3,4}[\s.-]\d{4})')
BAD_DOMAINS = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com","meneame.es","redalyc.org"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 6: return False
    p = e.split("@")
    if len(p) != 2: return False
    if p[1] in BAD_DOMAINS: return False
    if p[0] in ("noreply","no-reply","test","example","abuse","postmaster","support"): return False
    if len(p[0]) > 25: return False
    return True

def es_tel_ve(t):
    d = re.sub(r'[^\d]', '', t)
    if not d: return False
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276")
    if len(d) == 11 and d.startswith("0"): return d[:4] in prefixes
    if len(d) == 12 and d.startswith("58"): return d[2:6] in prefixes
    if len(d) == 10 and d.startswith("58"): return d[2:6] in prefixes
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
        if es_tel_ve(t):
            tel = t
            break
    return email, tel

def preparar_html(body):
    body = body.strip()
    if not body.startswith("<"):
        body = body.replace("\n", "<br>")
        body = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body style='font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#333;'>{body}</body></html>"
    return body

# ==================== RUBROS NUEVOS (NO EN LA BD) ====================
# Estos rubros son DIFERENTES a los que ya tenemos
RUBROS_NUEVOS = [
    ("abogado_despacho_legal", [
        "abogado Merida Venezuela email contacto",
        "despacho legal Merida Venezuela email",
        "firma abogados Merida Venezuela email",
        "juridico Merida Venezuela empresa email",
        "asesoria legal Merida Venezuela email",
    ]),
    ("seguros", [
        "aseguradora Merida Venezuela email",
        "empresa de seguros Merida Venezuela email",
        "agente de seguros Merida Venezuela email",
        "seguros Merida Venezuela contacto email",
    ]),
    ("contabilidad_auditoria", [
        "empresa contabilidad Merida Venezuela email",
        "auditoria Merida Venezuela email",
        "consultoria contable Merida Venezuela email",
        "firma contable Merida Venezuela email",
    ]),
    ("imprenta Papeleria", [
        "imprenta Merida Venezuela email",
        "papeleria Merida Venezuela email",
        "impresion Merida Venezuela empresa email",
        "estampados Merida Venezuela email",
    ]),
    ("materiales_construccion", [
        "materiales de construccion Merida Venezuela email",
        "ferreteria grande Merida Venezuela email",
        "ceramicos Merida Venezuela email",
        "sanitarios Merida Venezuela email",
        "pintura Merida Venezuela empresa email",
    ]),
    ("electrodomesticos", [
        "electrodomesticos Merida Venezuela email",
        "tienda de electrodomesticos Merida email",
        "materiales electricos Merida Venezuela email",
        "iluminacion Merida Venezuela email",
    ]),
    ("moda_ropa", [
        "tienda de ropa Merida Venezuela email",
        "boutique Merida Venezuela email",
        "moda Merida Venezuela empresa email",
        "confecciones Merida Venezuela email",
    ]),
    ("joyeria_relojeria", [
        "joyeria Merida Venezuela email",
        "relojeria Merida Venezuela email",
        "bisuteria Merida Venezuela email",
    ]),
    ("mascotas", [
        "veterinaria grande Merida Venezuela email",
        "pet shop Merida Venezuela email",
        "empresa de mascotas Merida Venezuela email",
    ]),
    ("deportes_gimnasio", [
        "gimnasio grande Merida Venezuela email",
        "centro deportivo Merida Venezuela email",
        "crossfit Merida Venezuela email",
        "academia de deportes Merida Venezuela email",
    ]),
    ("belleza_cosmeticos", [
        "salon de belleza grande Merida Venezuela email",
        "spa Merida Venezuela email",
        "cosmeticos Merida Venezuela empresa email",
        "estetica Merida Venezuela email",
    ]),
    ("eventos_fiestas", [
        "empresa de eventos Merida Venezuela email",
        "salon de fiestas Merida Venezuela email",
        "decoracion de eventos Merida Venezuela email",
        "catering Merida Venezuela email",
    ]),
    ("fotografia_video", [
        "estudio de fotografia Merida Venezuela email",
        "empresa de video Merida Venezuela email",
        "productora audiovisual Merida Venezuela email",
    ]),
    ("farmacia_grande", [
        "farmacia grande Merida Venezuela email",
        "cadena de farmacias Merida Venezuela email",
        "drogueria Merida Venezuela email",
    ]),
    ("supermercado_bodega", [
        "supermercado grande Merida Venezuela email",
        "bodega grande Merida Venezuela email",
        "abastos Merida Venezuela email",
    ]),
    ("gasolina_estacion", [
        "estacion de servicio Merida Venezuela email",
        "gasolinera Merida Venezuela email",
    ]),
    ("mudanza_almacenamiento", [
        "empresa de mudanza Merida Venezuela email",
        "bodega de almacenamiento Merida Venezuela email",
    ]),
    ("reciclaje", [
        "empresa de reciclaje Merida Venezuela email",
        "recuperacion de residuos Merida Venezuela email",
    ]),
    ("publicidad_impresion", [
        "empresa de publicidad Merida Venezuela email",
        "rotulacion Merida Venezuela email",
        "vinil Merida Venezuela empresa email",
    ]),
    ("gastronomia_catering", [
        "catering Merida Venezuela email",
        "servicio de comida Merida Venezuela email",
        "restaurante grande Merida Venezuela email",
    ]),
]

if __name__ == "__main__":
    leads_file = f"{BASE}\\leads.json"
    send_log_file = f"{BASE}\\send_log.json"
    wa_log_file = f"{BASE}\\wa_send_log.json"
    template_file = f"{BASE}\\email_templates.json"
    config_file = f"{BASE}\\config.json"

    leads = json.load(open(leads_file, encoding="utf-8"))
    send_log = json.load(open(send_log_file, encoding="utf-8"))
    wa_log = json.load(open(wa_log_file, encoding="utf-8"))
    templates = json.load(open(template_file, encoding="utf-8"))
    config = json.load(open(config_file, encoding="utf-8"))

    existing = set(l.get("nombre","").lower().strip() for l in leads)
    
    SMTP_SERVER = config.get("smtp_server", "smtp.gmail.com")
    SMTP_PORT = int(config.get("smtp_port", 587))
    SMTP_USER = config.get("smtp_email", "")
    SMTP_PASS = config.get("smtp_password", "")
    DELAY = int(config.get("delay_seconds", 60))
    DAILY_LIMIT = int(config.get("daily_send_limit", 100))
    EVO_URL = config.get("evo_api_url", "http://localhost:8080")
    EVO_KEY = config.get("evo_api_key", "")
    EVO_INST = config.get("evo_instance", "pskloud-merida")
    blocked = set(re.sub(r"[^\d]","", b) for b in config.get("blocked_phones", []))

    template = templates[0] if templates else {}
    enlace_consultoria = template.get("enlace_consultoria", "")
    enlace_expotrabajo = template.get("enlace_expotrabajo", "")
    asunto_tpl = template.get("asunto", "")
    cuerpo_tpl = template.get("cuerpo", "")

    emails_enviados = set(s.get("email","").lower().strip() for s in send_log if s.get("exitoso"))
    wa_enviados = set(re.sub(r"[^\d]","", s.get("telefono","")) for s in wa_log if s.get("exitoso"))
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    sent_today = sum(1 for s in send_log if s.get("exitoso") and s.get("fecha","").startswith(today_str))

    # ==================== PASO 1: SCRAPING ====================
    print("="*60, flush=True)
    print(f"PASO 1: SCRAPING DE EMPRESAS NUEVAS - {today_str}", flush=True)
    print("="*60, flush=True)

    total_nuevos = 0
    for rubro, queries in RUBROS_NUEVOS:
        print(f"\n  {rubro.upper()}", flush=True)
        all_results = []
        for q in queries:
            results = ddg(q, 10)
            all_results.extend(results)
            time.sleep(random.uniform(2, 4))
        
        seen_local = set()
        nuevos_rubro = 0
        for r in all_results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            texto = f"{title} {body}"
            email, tel = extract(texto)
            
            partes = re.split(r'[\-|–—:]', title)
            for p in partes:
                p = p.strip()
                skip = ["merida","venezuela","google","maps","opiniones","facebook","instagram","gov","twitter","wikipedia","buscar","directorio"]
                if any(x.lower() in p.lower() for x in skip):
                    continue
                if len(p) > 4 and len(p) < 60 and not p.startswith("http"):
                    norm = p.lower().strip()
                    if norm not in seen_local and norm not in existing:
                        seen_local.add(norm)
                        if email or tel:
                            lead = {
                                "nombre": p,
                                "rubro": rubro,
                                "municipio": "Libertador",
                                "estado_contacto": "No Contactado",
                                "fecha_creacion": today_str,
                            }
                            if email: lead["email"] = email
                            if tel: lead["telefono"] = tel
                            if href: lead["fuente_contacto"] = "ddg"
                            leads.append(lead)
                            existing.add(norm)
                            nuevos_rubro += 1
                            total_nuevos += 1
        print(f"    +{nuevos_rubro} nuevos", flush=True)
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)

    con_email_nuevos = sum(1 for l in leads if l.get("email","").strip() and l.get("email","").lower().strip() not in emails_enviados)
    print(f"\nScraping completo: +{total_nuevos} leads nuevos", flush=True)
    print(f"Correos pendientes de envio: {con_email_nuevos}", flush=True)

    # ==================== PASO 2: ENVIAR CORREOS ====================
    print("\n" + "="*60, flush=True)
    print("PASO 2: ENVIANDO CORREOS", flush=True)
    print("="*60, flush=True)

    pendientes_email = [l for l in leads if l.get("email","").strip() and l.get("email","").lower().strip() not in emails_enviados]
    email_enviados_hoy = 0

    def render(t, l):
        t = t.replace("{{nombre}}", l.get("nombre", ""))
        t = t.replace("{{rubro}}", l.get("rubro", ""))
        t = t.replace("{{municipio}}", l.get("municipio", ""))
        return t

    for i, lead in enumerate(pendientes_email):
        if sent_today + email_enviados_hoy >= DAILY_LIMIT:
            print(f"  Limite diario alcanzado ({DAILY_LIMIT})", flush=True)
            break
        email = lead["email"].strip()
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = email
        msg["Subject"] = render(asunto_tpl, lead)
        msg.attach(MIMEText(preparar_html(render(cuerpo_tpl, lead)), "html", "utf-8"))
        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email, msg.as_string())
            server.quit()
            email_enviados_hoy += 1
            print(f"  [{email_enviados_hoy}] OK  {lead.get('nombre','')[:30]}  {email[:35]}", flush=True)
        except Exception as ex:
            print(f"  FAIL  {lead.get('nombre','')[:30]}  {email[:35]}  {str(ex)[:50]}", flush=True)
        
        send_log.append({"email": email, "nombre": lead.get("nombre",""), "fecha": datetime.now().isoformat(), "exitoso": True, "mensaje": "OK"})
        with open(send_log_file, "w", encoding="utf-8") as f:
            json.dump(send_log, f, ensure_ascii=False, indent=2)
        if i < len(pendientes_email) - 1:
            time.sleep(DELAY)

    print(f"Correos enviados: {email_enviados_hoy}", flush=True)

    # ==================== PASO 3: ENVIAR WHATSAPP ====================
    print("\n" + "="*60, flush=True)
    print("PASO 3: ENVIANDO WHATSAPP", flush=True)
    print("="*60, flush=True)

    pendientes_wa = [l for l in leads if l.get("telefono","").strip() and re.sub(r"[^\d]","", l.get("telefono","")) not in wa_enviados and re.sub(r"[^\d]","", l.get("telefono","")) not in blocked]
    wa_enviados_nuevos = 0

    for lead in pendientes_wa:
        nombre = lead.get("nombre", "")
        tel = lead.get("telefono", "").strip()
        clean = re.sub(r"[^\d]", "", tel)
        if clean.startswith("0") and len(clean) == 11:
            evo_number = "58" + clean[1:]
        elif clean.startswith("58"):
            evo_number = clean
        else:
            evo_number = "58" + clean

        msg = f"Hola {nombre}!\n\nSomos Premium Soft en alianza con la Camara de Comercio de Merida.\n\n1 Business Consulting Day - 27 de Agosto\nSesion de consultoria GRATUITA.\nRESERVAR: {enlace_consultoria}\n\n2 ExpoTrabajo Merida 2026 - 28 de Agosto\nStand empresarial + recepcion de HV.\nREGISTRAR: {enlace_expotrabajo}\n\nCupos limitados. Equipo Premium Soft & Camara de Comercio"
        try:
            url = f"{EVO_URL}/message/sendText/{EVO_INST}"
            payload = {"number": evo_number, "text": msg}
            headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            ok = resp.status_code in (200, 201)
            if ok:
                wa_enviados_nuevos += 1
                print(f"  OK  {nombre[:30]}  {tel}", flush=True)
            else:
                print(f"  FAIL  {nombre[:30]}  {tel}  {resp.status_code}", flush=True)
        except Exception as ex:
            print(f"  FAIL  {nombre[:30]}  {tel}  {str(ex)[:50]}", flush=True)
        
        wa_log.append({"telefono": evo_number, "nombre": nombre, "fecha": datetime.now().isoformat(), "exitoso": ok, "mensaje": "OK" if ok else "FAIL"})
        with open(wa_log_file, "w", encoding="utf-8") as f:
            json.dump(wa_log, f, ensure_ascii=False, indent=2)
        time.sleep(15)

    print(f"WA enviados: {wa_enviados_nuevos}", flush=True)

    # ==================== RESUMEN ====================
    print("\n" + "="*60, flush=True)
    print("RESUMEN FINAL", flush=True)
    print("="*60, flush=True)
    con_email = sum(1 for l in leads if l.get("email","").strip())
    con_tel = sum(1 for l in leads if l.get("telefono","").strip())
    print(f"  Leads totales: {len(leads)}", flush=True)
    print(f"  Con email: {con_email}", flush=True)
    print(f"  Con telefono: {con_tel}", flush=True)
    print(f"  Correos enviados hoy: {email_enviados_hoy}", flush=True)
    print(f"  WA enviados hoy: {wa_enviados_nuevos}", flush=True)
    print(f"\n  Descarga el Excel desde Analitica en la app.", flush=True)
