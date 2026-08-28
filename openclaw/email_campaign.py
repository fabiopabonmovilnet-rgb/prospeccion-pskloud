"""
Módulo de campañas de correo SMTP (migrado desde Streamlit app.py al entorno :9000).
- Configuración SMTP persistente en /app/data/email_config.json
- Plantillas con variables {{nombre}}, {{empresa}}, {{pais}}, {{cargo}}, {{email}}
- Envío individual y masivo con límite diario y log en envios_realizados.json
"""
from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import ssl
import time
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger("openclaw.email_campaign")

BASE_DIR = "/app/data"
CONFIG_FILE = os.path.join(BASE_DIR, "email_config.json")
PLANTILLA_FILE = os.path.join(BASE_DIR, "plantilla_correo.json")
ENVIOS_FILE = os.path.join(BASE_DIR, "envios_realizados.json")
CONTACTADOS_FILE = os.path.join(BASE_DIR, "contactos_tocados.json")

DEFAULT_PLANTILLA = {
    "asunto": "Alianza estratégica en {{pais}} para distribución de software / Oportunidad Operativa",
    "cuerpo": """Hola {{nombre}},

Me dirigí a usted porque vi que en {{empresa}} están liderando el sector. Como Consultor de Ventas Internacionales de PSKloud, estamos expandiendo nuestro ecosistema de soluciones administrativas y facturación electrónica nativa en {{pais}}.

Me gustaría evaluar si hace sentido una sinergia con ustedes. ¿Tendrás 10 minutos esta semana para una conversación rápida?

Saludos cordiales,
Equipo PSKloud
Ventas Internacionales""",
}

DAILY_LIMIT = int(os.getenv("EMAIL_DAILY_LIMIT", "40"))
DELAY_BETWEEN = int(os.getenv("EMAIL_DELAY_SECONDS", "5"))


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_config() -> dict:
    return _load(CONFIG_FILE, {})


def save_config(cfg: dict) -> dict:
    data = get_config()
    data.update(cfg)
    _save(CONFIG_FILE, data)
    return data


def test_smtp(cfg: Optional[dict] = None) -> dict:
    cfg = cfg or get_config()
    host = cfg.get("host") or cfg.get("smtp_host")
    port = int(cfg.get("port") or cfg.get("smtp_port") or 587)
    user = cfg.get("user") or cfg.get("smtp_user") or cfg.get("smtp_email") or ""
    password = cfg.get("password") or cfg.get("smtp_password") or ""
    from_email = cfg.get("from_email") or user
    if not host or not user or not password:
        return {"ok": False, "error": "SMTP incompleto: faltan host, usuario o contraseña"}
    try:
        ctx = ssl._create_unverified_context()
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=ctx)
            server.login(user, password)
        return {"ok": True, "from_email": from_email, "host": host, "port": port}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Error de autenticación. Verifica usuario/contraseña."}
    except smtplib.SMTPConnectError:
        return {"ok": False, "error": "Error al conectar con el servidor SMTP."}
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"Error SMTP: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"Error inesperado: {str(e)}"}


def renderizar_plantilla(plantilla: str, nombre: str = "", empresa: str = "", pais: str = "", cargo: str = "", email: str = "") -> str:
    def _s(val):
        return "" if val is None or str(val) == "nan" else str(val)

    resultado = plantilla
    nombre_s = _s(nombre)
    empresa_s = _s(empresa)
    resultado = resultado.replace("{{nombre}}", nombre_s.split()[0] if nombre_s else "")
    resultado = resultado.replace("{{empresa}}", empresa_s)
    resultado = resultado.replace("{{company_name}}", empresa_s)
    resultado = resultado.replace("{{pais}}", _s(pais))
    resultado = resultado.replace("{{cargo}}", _s(cargo))
    resultado = resultado.replace("{{email}}", _s(email))
    return resultado


def get_plantilla() -> dict:
    return _load(PLANTILLA_FILE, DEFAULT_PLANTILLA)


def save_plantilla(asunto: str, cuerpo: str) -> None:
    _save(PLANTILLA_FILE, {"asunto": asunto, "cuerpo": cuerpo})


def enviar_correo_real(cfg: dict, correo_receptor: str, asunto: str, cuerpo: str) -> tuple[bool, str]:
    """Envía un correo real por SMTP/TLS (o SendGrid si el host es sendgrid)."""
    host = cfg.get("host") or cfg.get("smtp_host")
    port = int(cfg.get("port") or cfg.get("smtp_port") or 587)
    user = cfg.get("user") or cfg.get("smtp_user") or cfg.get("smtp_email") or ""
    password = cfg.get("password") or cfg.get("smtp_password") or ""
    from_addr = cfg.get("from_email") or user
    try:
        if host and "sendgrid" in str(host).lower():
            import httpx
            headers = {"Authorization": f"Bearer {password}", "Content-Type": "application/json"}
            data = {
                "personalizations": [{"to": [{"email": correo_receptor}]}],
                "from": {"email": from_addr},
                "subject": asunto,
                "content": [{"type": "text/plain", "value": cuerpo}],
            }
            r = httpx.post("https://api.sendgrid.com/v3/mail/send", headers=headers, json=data, timeout=20)
            if r.status_code == 202:
                return True, "Correo enviado exitosamente"
            return False, f"Error SendGrid: {r.status_code} {r.text[:200]}"

        mensaje = MIMEMultipart()
        mensaje["From"] = from_addr
        mensaje["To"] = correo_receptor
        mensaje["Subject"] = asunto
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

        ctx = ssl._create_unverified_context()
        with smtplib.SMTP(host, port, timeout=30) as servidor_smtp:
            servidor_smtp.starttls(context=ctx)
            servidor_smtp.login(user, password)
            servidor_smtp.sendmail(from_addr, correo_receptor, mensaje.as_string())
        return True, "Correo enviado exitosamente"
    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación. Verifica usuario/contraseña."
    except smtplib.SMTPConnectError:
        return False, "Error al conectar con el servidor SMTP."
    except smtplib.SMTPException as e:
        return False, f"Error SMTP: {str(e)}"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"


def registrar_envio(email: str, nombre: str, empresa: str, asunto: str, status: str, mensaje: str = ""):
    envios = _load(ENVIOS_FILE, [])
    envios.append({
        "fecha": date.today().isoformat(),
        "ts": time.time(),
        "email": email,
        "nombre": nombre,
        "empresa": empresa,
        "asunto": asunto,
        "status": status,
        "mensaje": mensaje,
    })
    _save(ENVIOS_FILE, envios[-1000:])


def get_envios(dias: int = 30) -> dict:
    envios = _load(ENVIOS_FILE, [])
    desde = time.time() - dias * 86400
    recientes = [e for e in envios if e.get("ts", 0) >= desde]
    ok = [e for e in recientes if e.get("status") == "ok"]
    return {
        "total": len(envios),
        "hoy": sum(1 for e in envios if e.get("fecha") == date.today().isoformat()),
        "recientes": len(recientes),
        "exitosos": len(ok),
        "ultimos": envios[-50:][::-1],
    }


def _email_contactado(email: str) -> bool:
    envios = _load(ENVIOS_FILE, [])
    norm = email.strip().lower()
    return any(e.get("email", "").strip().lower() == norm for e in envios)


def enviar_masivo(leads: list[dict], cfg: Optional[dict] = None, plantilla: Optional[dict] = None, max_enviar: int = 40) -> dict:
    cfg = cfg or get_config()
    plantilla = plantilla or get_plantilla()
    try:
        import distribuidores_store as dstore
        paises_activos = set(dstore.get_paises_activos())
    except Exception:
        paises_activos = None
    resultados = []
    ok = 0
    fail = 0
    saltados = 0
    for lead in leads:
        pais = (lead.get("País") or lead.get("pais") or "").strip().upper()
        if paises_activos is not None:
            if not pais:
                saltados += 1
                continue
            if pais in dstore.PAISES and pais not in paises_activos:
                saltados += 1
                continue
        email = (lead.get("Correo") or lead.get("email") or "").strip()
        if not email:
            continue
        if _email_contactado(email):
            saltados += 1
            continue
        nombre = lead.get("Contacto Clabe") or lead.get("Contacto") or lead.get("nombre") or ""
        empresa = lead.get("Empresa") or lead.get("empresa") or lead.get("nombre_empresa") or ""
        cargo = lead.get("Cargo") or lead.get("cargo") or ""
        asunto = renderizar_plantilla(plantilla.get("asunto", ""), nombre, empresa, pais, cargo, email)
        cuerpo = renderizar_plantilla(plantilla.get("cuerpo", ""), nombre, empresa, pais, cargo, email)
        exito, msg = enviar_correo_real(cfg, email, asunto, cuerpo)
        registrar_envio(email, nombre, empresa, asunto, "ok" if exito else "error", msg)
        if exito:
            ok += 1
        else:
            fail += 1
        resultados.append({"email": email, "empresa": empresa, "ok": exito, "mensaje": msg})
        if ok + fail >= max_enviar:
            break
        time.sleep(DELAY_BETWEEN)
    return {"enviados": ok, "fallidos": fail, "saltados": saltados, "resultados": resultados}
