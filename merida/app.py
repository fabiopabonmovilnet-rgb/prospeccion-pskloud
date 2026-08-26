"""
PSKloud Prospector v1.0 — Mérida, Venezuela
Sistema de prospección de negocios: scraping OSM+DDG/Google Maps,
normalización de teléfonos VE (+58), enriquecimiento email,
campaña de correo SMTP con delay configurable, WhatsApp links,
exportación para OpenClaw, y analítica.
"""

import streamlit as st
import pandas as pd
import requests
import smtplib
import ssl
import time
import re
import json
import os
import io
import sys
import hashlib
from collections import Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_search
from phone_utils import (
    normalizar_telefono_ve, es_telefono_ve, formato_whatsapp,
    extraer_telefonos, extraer_emails, enriquecer_leads,
)
from import_utils import importar_leads, generar_plantilla_csv_ejemplo, generar_plantilla_excel_ejemplo
from whatsapp_export import (
    exportar_openclaw_json, exportar_openclaw_csv,
    exportar_wa_links_csv, estadisticas_exportacion,
)
from templates_default import TEMPLATES_DEFAULT, get_template_by_name
from fast_scraper import (
    scrape_fast as scrape_fast_v2,
    scrape_barrido_total,
    MATRIZ_TARGET_SOFTWARE,
    UBICACIONES_PRECISAS_MERIDA,
    CATEGORIAS_COMERCIALES_MERIDA,
    MUNICIPIOS,
)
from hunter_api import (
    enrich_leads_hunter,
    verificar_api_key_hunter,
    extraer_dominio,
)
from directorio_ve import buscar_directorio
from email_finder import buscar_email_completo, enrich_leads_batch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "leads.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SEND_LOG_FILE = os.path.join(BASE_DIR, "send_log.json")
EMAIL_TEMPLATES_FILE = os.path.join(BASE_DIR, "email_templates.json")
WA_SEND_LOG_FILE = os.path.join(BASE_DIR, "wa_send_log.json")

st.set_page_config(
    page_title="PSKloud Prospector | Mérida, Venezuela",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CONSTANTS
# =============================================================================

RUBROS = MATRIZ_TARGET_SOFTWARE

MUNICIPIOS = list(UBICACIONES_PRECISAS_MERIDA.keys())

MUNICIPIOS_LABELS = {
    k: f"{v.split(',')[0]} ({k})"
    for k, v in UBICACIONES_PRECISAS_MERIDA.items()
}

ESTADOS_CONTACTO = [
    "No Contactado", "Contactado", "Interesado", "No Interesado", "Cliente"
]

DEFAULT_EMAIL_TEMPLATE = {
    "asunto": "Oportunidad de negocio en Mérida — PSKloud Export",
    "cuerpo": """<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;background:#ffffff;">
<div style="background:#0B2138;padding:24px;text-align:center;">
<h1 style="color:#8FC54B;font-size:22px;margin:0;">PSKloud Export</h1>
<p style="color:#8FA8C8;font-size:12px;margin:4px 0 0;">Trabajo y Business Consulting</p>
</div>
<div style="padding:32px 24px;">
<p style="color:#333;font-size:15px;line-height:1.6;">Estimado/a <strong>{{nombre}}</strong>,</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
Identificamos su negocio <strong>{{rubro}}</strong> en <strong>{{municipio}}, Mérida</strong> como una excelente oportunidad para formar parte de nuestra red de aliados estratégicos en Venezuela.
</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
<strong>PSKloud Export</strong> ofrece soluciones de <em>business consulting</em>, gestión administrativa y conexiones internacionales diseñadas para empresas que buscan crecer de forma sostenible.
</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
Le invitamos a completar nuestro formulario de participación para conocer más sobre esta alianza:
</p>
<div style="text-align:center;margin:28px 0;">
<a href="{{enlace}}" style="background:#8FC54B;color:#0B2138;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">Completar Formulario</a>
</div>
<p style="color:#333;font-size:15px;line-height:1.6;">
Si tiene alguna consulta, responda a este correo o escríbanos.
</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
Saludos cordiales,<br>
<strong>Equipo PSKloud Export</strong><br>
<span style="color:#5A7A9B;font-size:13px;">Ventas Internacionales</span>
</p>
</div>
<div style="background:#f5f5f5;padding:16px 24px;text-align:center;">
<p style="color:#999;font-size:11px;margin:0;">© 2025 PSKloud Export — Business Consulting</p>
</div>
</div>""",
}

PSKLOUD_CSS = """
<style>
    .stApp { background: #0B2138; }
    .main > div { background: #0B2138; }
    section[data-testid="stSidebar"] {
        background: #081B2F !important;
        border-right: 1px solid #081B2F;
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #f8fafc;
    }
    section[data-testid="stSidebar"] .stCaption { color: #94a3b8; }
    h1, h2, h3, h4, h5, h6 {
        color: #f8fafc !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }
    h1 { font-size: 2rem !important; }
    h2 { font-size: 1.5rem !important; color: #FFFFFF !important; }
    h3 { font-size: 1.125rem !important; color: #cbd5e1 !important; }
    .stCard, div[data-testid="stMetric"] {
        background: #081B2F !important;
        border: 1px solid #1E3A5F !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetric"] { padding: 1.25rem !important; }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] p {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #f8fafc !important;
        font-size: 1.75rem !important;
        font-weight: 700 !important;
    }
    .stButton button {
        background: linear-gradient(135deg, #8FC54B, #A3D15E) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 8px rgba(143,197,75,0.3) !important;
    }
    .stButton button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(143,197,75,0.4) !important;
    }
    .stButton button:active { transform: translateY(0) !important; }
    .stButton button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid #1E3A5F !important;
        box-shadow: none !important;
        color: #cbd5e1 !important;
    }
    .stButton button[kind="secondary"]:hover {
        border-color: #8FC54B !important;
        color: #f8fafc !important;
    }
    .stTextInput input, .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"],
    .stMultiSelect div[data-baseweb="select"] {
        background: #081B2F !important;
        border: 1px solid #1E3A5F !important;
        border-radius: 8px !important;
        color: #f8fafc !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #8FC54B !important;
        box-shadow: 0 0 0 2px rgba(143,197,75,0.2) !important;
    }
    .stTextInput label, .stTextArea label,
    .stSelectbox label, .stMultiSelect label {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
    }
    .streamlit-expanderHeader {
        background: #081B2F !important;
        border: 1px solid #1E3A5F !important;
        border-radius: 10px !important;
        color: #f8fafc !important;
        font-weight: 600 !important;
        padding: 0.75rem 1rem !important;
    }
    .streamlit-expanderHeader:hover { border-color: #8FC54B !important; }
    .streamlit-expanderContent {
        border: 1px solid #081B2F !important;
        border-top: none !important;
        border-radius: 0 0 10px 10px !important;
        padding: 1rem !important;
        background: #081B2F !important;
    }
    hr { border-color: #081B2F !important; margin: 1.5rem 0 !important; }
    .stDataFrame { border: 1px solid #081B2F !important; border-radius: 10px !important; overflow: hidden; }
    .stDataFrame thead tr th {
        background: #081B2F !important;
        color: #94a3b8 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 0.75rem !important;
        border-bottom: 1px solid #1E3A5F !important;
    }
    .stDataFrame tbody tr td {
        background: #081B2F !important;
        color: #FFFFFF !important;
        padding: 0.6rem !important;
        border-bottom: 1px solid #081B2F !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        background: #081B2F !important;
        border-bottom: 1px solid #081B2F !important;
        gap: 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #94a3b8 !important;
        padding: 0.75rem 1.25rem !important;
        font-weight: 500 !important;
        border-bottom: 2px solid transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #8FC54B !important;
        border-bottom-color: #8FC54B !important;
        background: transparent !important;
    }
    .stAlert {
        background: #081B2F !important;
        border: 1px solid #1E3A5F !important;
        border-radius: 10px !important;
        color: #FFFFFF !important;
    }
    .stAlert [data-testid="stAlert"] p { color: #FFFFFF !important; }
    .stAlert p, .stAlert li { color: #FFFFFF !important; }
    div[data-baseweb="notification"] { color: #FFFFFF !important; }
    div[data-baseweb="notification"] p { color: #FFFFFF !important; }
    .stProgress > div > div { background: #8FC54B !important; }
    .stCheckbox label { color: #cbd5e1 !important; }
    .stSpinner > div { border-color: #8FC54B !important; }
    code {
        background: #081B2F !important;
        color: #a5b4fc !important;
        padding: 0.2em 0.4em !important;
        border-radius: 4px !important;
    }
    .stImage caption, .stCaption { color: #94a3b8 !important; }
    .stMarkdown p, .stMarkdown li { color: #e2e8f0 !important; }
    .stMarkdown strong { color: #f8fafc !important; }
    .stMarkdown a { color: #8FC54B !important; }
    .stRadio label, .stRadio p { color: #cbd5e1 !important; }
    .stRadio [data-baseweb="radio"] { color: #cbd5e1 !important; }
    .stRadio div[role="radiogroup"] label { color: #cbd5e1 !important; }
    div[data-baseweb="select"] { color: #f8fafc !important; }
    div[data-baseweb="select"] span { color: #f8fafc !important; }
    .stMultiSelect div[data-baseweb="tag"] { background: #1E3A5F !important; }
    .stMultiSelect div[data-baseweb="tag"] span { color: #f8fafc !important; }
    .stSlider label { color: #94a3b8 !important; }
    .stSlider [data-baseweb="thumb"] { color: #8FC54B !important; }
    .stNumberInput label { color: #94a3b8 !important; }
    .stFileUploader label { color: #94a3b8 !important; }
    .stDownloadButton a { color: #8FC54B !important; }
    .stForm { border: 1px solid #1E3A5F !important; }
    .streamlit-expanderContent p { color: #e2e8f0 !important; }
    .streamlit-expanderContent li { color: #e2e8f0 !important; }
    .streamlit-expanderContent strong { color: #f8fafc !important; }
    div[data-testid="stVerticalBlock"] p { color: #e2e8f0 !important; }
    footer { opacity: 0.4; }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #081B2F; }
    ::-webkit-scrollbar-thumb { background: #1E3A5F; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #2E5185; }
    .lead-card {
        background: #081B2F;
        border: 1px solid #1E3A5F;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    .lead-card h4 { color: #8FC54B !important; margin: 0 0 0.5rem 0 !important; font-size: 1rem !important; }
    .whatsapp-btn {
        display: inline-block;
        background: #25D366;
        color: white !important;
        padding: 6px 14px;
        border-radius: 6px;
        text-decoration: none !important;
        font-weight: 500;
        font-size: 0.85rem;
    }
    .email-badge {
        display: inline-block;
        background: #1E3A5F;
        color: #8FC54B;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
    }
    .phone-badge {
        display: inline-block;
        background: #1E3A5F;
        color: #60A5FA;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
    }
    .section-divider {
        border-top: 1px solid #1E3A5F;
        margin: 1.5rem 0;
    }
</style>
"""

DEFAULT_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_email": "pskloud.fpabon@gmail.com",
    "smtp_password": "",
    "hunter_api_key": "",
    "daily_send_limit": 50,
    "default_country": "Venezuela",
}

DEFAULT_TEMPLATE_MERIDA = {
    "asunto": "Alianza estratégica en Mérida — PSKloud Export",
    "cuerpo": """<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;background:#ffffff;">
<div style="background:#0B2138;padding:24px;text-align:center;">
<h1 style="color:#8FC54B;font-size:22px;margin:0;">PSKloud Export</h1>
<p style="color:#8FA8C8;font-size:12px;margin:4px 0 0;">Trabajo y Business Consulting</p>
</div>
<div style="padding:32px 24px;">
<p style="color:#333;font-size:15px;line-height:1.6;">Estimado/a <strong>{{nombre}}</strong>,</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
Su negocio <strong>{{rubro}}</strong> en <strong>{{municipio}}, Mérida</strong> fue seleccionado como potencial aliado estratégico para nuestra red de empresas asociadas.
</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
En <strong>PSKloud Export</strong> ayudamos a negocios venezolanos a conectarse con oportunidades internacionales, ofreciendo herramientas de gestión, consulting y desarrollo empresarial.
</p>
<p style="color:#333;font-size:15px;line-height:1.6;">
Completando nuestro formulario de participación podrá acceder a:
</p>
<ul style="color:#333;font-size:15px;line-height:1.8;margin:0 0 16px 20px;">
<li>Asesoría empresarial personalizada</li>
<li>Conexiones con mercados internacionales</li>
<li>Herramientas de gestión y facturación</li>
<li>Red de aliados estratégicos</li>
</ul>
<div style="text-align:center;margin:28px 0;">
<a href="{{enlace}}" style="background:#8FC54B;color:#0B2138;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">Unirse a la Red PSKloud</a>
</div>
<p style="color:#333;font-size:15px;line-height:1.6;">
Saludos cordiales,<br>
<strong>Equipo PSKloud Export</strong><br>
<span style="color:#5A7A9B;font-size:13px;">Ventas Internacionales</span>
</p>
</div>
<div style="background:#f5f5f5;padding:16px 24px;text-align:center;">
<p style="color:#999;font-size:11px;margin:0;">© 2025 PSKloud Export — Business Consulting</p>
</div>
</div>""",
}

# =============================================================================
# PERSISTENCE
# =============================================================================


def _load_json(path: str, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_leads() -> List[Dict]:
    return _load_json(DATA_FILE, [])


def save_leads(leads: List[Dict]):
    _save_json(DATA_FILE, leads)


def load_config() -> Dict:
    cfg = _load_json(CONFIG_FILE, {})
    merged = {**DEFAULT_CONFIG, **cfg}
    return merged


def save_config(cfg: Dict):
    _save_json(CONFIG_FILE, cfg)


def is_phone_blocked(phone: str) -> bool:
    """Verifica si un teléfono está bloqueado (nunca enviar mensajes)."""
    if not phone:
        return False
    cfg = load_config()
    blocked = [re.sub(r"[^\d]", "", b) for b in cfg.get("blocked_phones", [])]
    clean = re.sub(r"[^\d]", "", phone)
    return clean in blocked or phone in cfg.get("blocked_phones", [])


def load_send_log() -> List[Dict]:
    return _load_json(SEND_LOG_FILE, [])


def save_send_log(log: List[Dict]):
    _save_json(SEND_LOG_FILE, log)


def load_email_templates() -> List[Dict]:
    data = _load_json(EMAIL_TEMPLATES_FILE, [])
    if not data:
        data = [t.copy() for t in TEMPLATES_DEFAULT]
        _save_json(EMAIL_TEMPLATES_FILE, data)
    return data


def save_email_templates(templates: List[Dict]):
    _save_json(EMAIL_TEMPLATES_FILE, templates)


def load_wa_log() -> List[Dict]:
    return _load_json(WA_SEND_LOG_FILE, [])


def save_wa_log(data: List[Dict]):
    _save_json(WA_SEND_LOG_FILE, data)


# =============================================================================
# EMAIL ENRICHMENT (scrape website + DDG for emails)
# =============================================================================

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
GENERIC_PREFIXES = {
    "info", "contact", "contacto", "ventas", "sales", "support", "soporte",
    "admin", "help", "hola", "hello", "mail", "office", "comercial",
    "general", "servicio", "customer", "service", "webmaster", "postmaster",
    "marketing", "press", "media", "jobs", "careers", "empleo", "recruitment",
    "rrhh", "legal", "privacy", "abuse", "noc", "billing", "accounts",
    "finance", "partner", "editor", "web", "newsletter", "no-reply",
    "noreply", "donotreply", "example", "test", "prueba",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
}


def _is_valid_email(email: str) -> bool:
    local = email.split("@")[0].lower().strip()
    domain = email.split("@")[1].lower().strip()
    if local in GENERIC_PREFIXES:
        return False
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js")):
        return False
    if len(domain.split(".")) < 2:
        return False
    return True


def _extract_emails_from_text(text: str) -> List[str]:
    candidates = set(EMAIL_REGEX.findall(text))
    return [e for e in candidates if _is_valid_email(e)]


def scrape_website_emails(website_url: str) -> List[str]:
    if not website_url:
        return []
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    pages = [
        website_url,
        website_url.rstrip("/") + "/contacto",
        website_url.rstrip("/") + "/contact",
        website_url.rstrip("/") + "/contactenos",
        website_url.rstrip("/") + "/nosotros",
        website_url.rstrip("/") + "/about",
        website_url.rstrip("/") + "/about-us",
        website_url.rstrip("/") + "/equipo",
        website_url.rstrip("/") + "/team",
    ]
    all_text = ""
    for page_url in pages:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                all_text += resp.text + "\n"
        except Exception:
            continue

    return _extract_emails_from_text(all_text)


def ddg_search_email(nombre: str, municipio: str) -> List[str]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []

    queries = [
        f'"{nombre}" {municipio} email contacto',
        f'"{nombre}" {municipio} correo electrónico',
        f'"{nombre}" Venezuela email',
    ]
    emails_found = []
    try:
        with DDGS() as d:
            for q in queries:
                for r in d.text(q, region="ve-ve", max_results=5, backend="mojeek,yahoo,startpage"):
                    text = f"{r.get('title', '')} {r.get('body', '')} {r.get('href', '')}"
                    emails_found.extend(_extract_emails_from_text(text))
                    if len(emails_found) >= 3:
                        break
                if len(emails_found) >= 3:
                    break
    except Exception:
        pass
    return list(dict.fromkeys(emails_found))[:3]


def enrich_lead_email(lead: Dict) -> Dict:
    emails = []
    website = lead.get("website", "")
    if website:
        emails.extend(scrape_website_emails(website))
    if not emails:
        emails.extend(ddg_search_email(lead.get("nombre", ""), lead.get("ciudad", "")))
    if emails:
        lead["email"] = emails[0]
        lead["emails_extra"] = emails
        lead["fuente_email"] = "website" if website else "ddg"
    return lead


# =============================================================================
# WHATSAPP HELPERS
# =============================================================================


def build_wa_link(phone: str, message: str = "") -> str:
    clean = re.sub(r"[^\d]", "", phone)
    if not clean or len(clean) < 8:
        return ""
    if not message:
        message = "Hola, buenos días. Me comunico desde PSKloud."
    return f"https://wa.me/{clean}?text={quote(message)}"


def build_wa_link_business(nombre: str) -> str:
    return f"https://wa.me/?text={quote(f'Interesado en: {nombre}')}"


# =============================================================================
# WHATSAPP BUSINESS — Evolution API
# =============================================================================

EVO_API_URL = os.environ.get("EVOLUTION_API_URL", "http://localhost:8080")
EVO_API_KEY = os.environ.get("EVOLUTION_API_KEY", "psk-evo-a7f3k9m2x5p8q1w4")
EVO_INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "pskloud-merida")


def send_wa_business(phone: str, message: str, evo_url: str = None, evo_key: str = None, evo_instance: str = None) -> Tuple[bool, str]:
    """Envía mensaje WhatsApp Business vía Evolution API."""
    try:
        if is_phone_blocked(phone):
            return False, f"BLOQUEADO: {phone} está en lista de bloqueados"
        url = evo_url or EVO_API_URL
        key = evo_key or EVO_API_KEY
        inst = evo_instance or EVO_INSTANCE
        clean = re.sub(r"[^\d]", "", phone)
        if not clean or len(clean) < 10:
            return False, f"Teléfono inválido: {phone}"
        if clean.startswith("0"):
            clean = "58" + clean[1:]
        elif not clean.startswith("58"):
            clean = "58" + clean

        api_url = f"{url}/message/sendText/{inst}"
        payload = {"number": clean, "text": message}
        headers = {"apikey": key, "Content-Type": "application/json"}
        resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return True, "WhatsApp enviado"
        return False, f"Error {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def send_wa_business_template(phone: str, message: str, button_text: str = "Ver más") -> Tuple[bool, str]:
    """Envía mensaje WhatsApp Business con botón clickable vía Evolution API."""
    try:
        if is_phone_blocked(phone):
            return False, f"BLOQUEADO: {phone} está en lista de bloqueados"
        clean = re.sub(r"[^\d]", "", phone)
        if not clean or len(clean) < 10:
            return False, f"Teléfono inválido: {phone}"
        if clean.startswith("0"):
            clean = "58" + clean[1:]
        elif not clean.startswith("58"):
            clean = "58" + clean

        url = f"{EVO_API_URL}/message/sendText/{EVO_INSTANCE}"
        payload = {
            "number": clean,
            "text": message,
            "presence": "composing",
        }
        headers = {"apikey": EVO_API_KEY, "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return True, "WhatsApp enviado"
        return False, f"Error {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_wa_connection(evo_url: str = None, evo_key: str = None, evo_instance: str = None) -> Tuple[bool, str]:
    """Verifica conexión con Evolution API."""
    try:
        url = evo_url or EVO_API_URL
        key = evo_key or EVO_API_KEY
        inst = evo_instance or EVO_INSTANCE
        api_url = f"{url}/instance/connectionState/{inst}"
        headers = {"apikey": key}
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            instance_data = data.get("instance", {})
            state = instance_data.get("state", "unknown")
            owner = instance_data.get("owner", "")
            if state == "open":
                phone_display = f" — Tel: {owner}" if owner else ""
                return True, f"Conexión WhatsApp activa — Instancia: {inst}{phone_display}"
            return False, f"WhatsApp desconectado — Instancia: {inst} (estado: {state})"
        return False, f"Error {resp.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


# =============================================================================
# SMTP HELPERS
# =============================================================================


def preparar_cuerpo_html(body: str) -> str:
    if "<br>" not in body and "</p>" not in body and "<div" not in body and "<html" not in body:
        body = body.replace("\n", "<br>")
    html_final = f"""<!DOCTYPE html>
<html>
  <head><meta charset="utf-8"></head>
  <body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#333;">
    {body}
  </body>
</html>"""
    return html_final


def send_smtp_email(
    server: str, port: int, email: str, password: str,
    to_email: str, subject: str, body: str, html: bool = True,
    attachments: Optional[List[Dict]] = None,
    inline_images: Optional[List[Dict]] = None,
) -> Tuple[bool, str]:
    """
    Envía email con soporte para adjuntos e imágenes inline (CID).
    
    inline_images: [{"filename": "logo.png", "content": bytes, "cid": "logo_cid"}]
    En el HTML se referencia con: <img src="cid:logo_cid">
    """
    try:
        if html:
            body = preparar_cuerpo_html(body)

        msg = MIMEMultipart("related" if inline_images else "alternative")
        msg["From"] = email
        msg["To"] = to_email
        msg["Subject"] = subject

        if inline_images:
            alt_part = MIMEMultipart("alternative")
            if html:
                alt_part.attach(MIMEText(body, "html", "utf-8"))
            else:
                alt_part.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(alt_part)
        else:
            if html:
                msg.attach(MIMEText(body, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

        if inline_images:
            for img in inline_images:
                part = MIMEBase("image", "png" if img["filename"].endswith(".png") else "jpeg")
                part.set_payload(img["content"])
                encoders.encode_base64(part)
                part.add_header("Content-ID", f"<{img['cid']}>")
                part.add_header("Content-Disposition", "inline", filename=img["filename"])
                msg.attach(part)

        if attachments:
            for att in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(att["content"])
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={att['filename']}",
                )
                msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(server, port) as server_obj:
            server_obj.starttls(context=context)
            server_obj.login(email, password)
            server_obj.sendmail(email, to_email, msg.as_string())
        return True, "Enviado correctamente"
    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación SMTP. Verifique credenciales."
    except smtplib.SMTPRecipientsRefused:
        return False, "Destinatario rechazado."
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_smtp_connection(server: str, port: int, email: str, password: str) -> Tuple[bool, str]:
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(server, port, timeout=10) as s:
            s.starttls(context=context)
            s.login(email, password)
        return True, "Conexión SMTP exitosa"
    except smtplib.SMTPAuthenticationError:
        return False, "Credenciales incorrectas"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def send_daily_summary(
    server: str, port: int, email: str, password: str,
    to_email: str, sent_count: int, limit: int,
):
    subject = f"Resumen diario Prospector Mérida — {sent_count}/{limit} emails enviados"
    body = f"""
    <html><body style="font-family: Arial; color: #333;">
    <h2 style="color: #0B2138;">PSKloud Prospector — Mérida</h2>
    <p>Resumen de actividad del día:</p>
    <ul>
        <li>Emails enviados hoy: <strong>{sent_count}</strong></li>
        <li>Límite diario: <strong>{limit}</strong></li>
        <li>Restantes: <strong>{max(0, limit - sent_count)}</strong></li>
    </ul>
    <p style="color: #8FC54B;">Equipo PSKloud</p>
    </body></html>
    """
    return send_smtp_email(server, port, email, password, to_email, subject, body)


# =============================================================================
# CSS + PAGE CONFIG
# =============================================================================

st.markdown(PSKLOUD_CSS, unsafe_allow_html=True)

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0;">
        <h1 style="color:#8FC54B; font-size:1.8rem; margin:0;">PSKloud</h1>
        <p style="color:#94a3b8; font-size:0.8rem; margin:0;">Prospector v1.0 — Mérida</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("#### 📊 Resumen rápido")
    leads = load_leads()
    total = len(leads)
    con_tel = sum(1 for l in leads if l.get("telefono"))
    con_email = sum(1 for l in leads if l.get("email"))
    con_ambos = sum(1 for l in leads if l.get("telefono") and l.get("email"))

    col1, col2 = st.columns(2)
    col1.metric("Total", total)
    col2.metric("Con teléfono", con_tel)
    col1.metric("Con email", con_email)
    col2.metric("Con ambos", con_ambos)

    st.markdown("---")
    st.caption("PSKloud Prospector © 2026")

# =============================================================================
# MAIN TABS
# =============================================================================

tabs = st.tabs(["Prospección", "Correo", "WhatsApp", "Analítica", "Configuración"])
tab_prospeccion, tab_correo, tab_whatsapp, tab_analitica, tab_config = tabs

# =============================================================================
# HELPER: build variables dict for template substitution
# =============================================================================


def _build_template_vars(lead: Dict, links: Dict = None) -> Dict:
    links = links or {}
    return {
        "nombre": lead.get("nombre", ""),
        "rubro": lead.get("rubro", ""),
        "municipio": lead.get("municipio", ""),
        "telefono": lead.get("telefono", ""),
        "email": lead.get("email", ""),
        "enlace": links.get("enlace_consultoria", ""),
        "enlace_consultoria": links.get("enlace_consultoria", ""),
        "enlace_expotrabajo": links.get("enlace_expotrabajo", ""),
    }


def _substitute_vars(text: str, variables: Dict) -> str:
    for k, v in variables.items():
        text = text.replace("{{" + k + "}}", v)
    return text


# =============================================================================
# TAB 1: PROSPECCIÓN (SCRAPING)
# =============================================================================

with tab_prospeccion:
    st.header("🔍 Scraping de Negocios — Mérida, Venezuela")

    # --- BUSCADOR RÁPIDO POR RUBRO (ARRIBA) ---
    st.subheader("🔎 Buscar un Rubro Ahora")
    st.markdown("Escribe cualquier rubro. El sistema busca negocios en Mérida y extrae email/teléfono de snippets sin navegador — rápido.")
    rcol1, rcol2 = st.columns([3, 1])
    with rcol1:
        custom_rubro = st.text_input(
            "Rubro a buscar",
            placeholder="ej: agencias de vehiculos, clínica dental, ventas de motos, abogado...",
            key="custom_rubro_input",
        )
    with rcol2:
        custom_mun = st.selectbox(
            "Municipio",
            options=MUNICIPIOS,
            format_func=lambda x: MUNICIPIOS_LABELS.get(x, x),
            key="custom_rubro_mun",
            index=0,
        )

    if st.button("🔍 Buscar este rubro", key="search_custom_rubro"):
        if not custom_rubro.strip():
            st.warning("Escribe un rubro.")
        else:
            st.info(f"Buscando **{custom_rubro}** en {custom_mun}...")
            with st.spinner("Ejecutando scraper DDG... esto toma ~1-2 minutos"):
                import subprocess
                result = subprocess.run(
                    ["python", r"C:\Users\fabio\prospeccion-pskloud\merida\scrape_batch.py", custom_rubro.strip()],
                    capture_output=True, text=True, timeout=300,
                    cwd=r"C:\Users\fabio\prospeccion-pskloud\merida",
                )
            st.code(result.stdout[-2000:] if result.stdout else "Sin salida")
            if result.returncode != 0 and result.stderr:
                st.error(f"Error: {result.stderr[-500:]}")
            else:
                st.success("Scraping completado. Recargando leads...")
                st.rerun()

    st.markdown("---")

    # --- IMPORTAR EXCEL ---
    st.subheader("📥 Importar tu Base de Datos (Excel/CSV)")
    st.markdown("Sube un Excel con **nombre de empresa**, **correo** y **número de teléfono**. El sistema detecta las columnas automáticamente.")
    with st.expander("📥 Cargar archivo Excel/CSV", expanded=True):
        upcol1, upcol2 = st.columns(2)
        with upcol1:
            csv_ejemplo = generar_plantilla_csv_ejemplo()
            st.download_button(
                "📥 Descargar plantilla CSV",
                csv_ejemplo.encode("utf-8"),
                file_name="plantilla_leads.csv",
                mime="text/csv",
                key="dl_csv_prosp",
            )
        with upcol2:
            xlsx_ejemplo = generar_plantilla_excel_ejemplo()
            st.download_button(
                "📥 Descargar plantilla Excel",
                xlsx_ejemplo,
                file_name="plantilla_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx_prosp",
            )

        uploaded_file = st.file_uploader(
            "Seleccionar archivo (CSV, Excel, JSON)",
            type=["csv", "xlsx", "xls", "json"],
            key="import_file_prosp",
        )

        if uploaded_file:
            st.info(f"📄 {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")
            if st.button("📥 Importar leads desde archivo", key="do_import_prosp"):
                try:
                    existing = load_leads()
                    leads_actualizados, num_nuevos, info = importar_leads(
                        uploaded_file, uploaded_file.name, existing
                    )
                    save_leads(leads_actualizados)
                    st.success(f"✅ Importados **{num_nuevos}** leads nuevos de **{info['total_archivo']}** totales")
                    with st.expander("Detalles"):
                        st.write(f"**Nuevos:** {info['nuevos_agregados']}")
                        st.write(f"**Duplicados omitidos:** {info['duplicados_omitidos']}")
                        st.write(f"**Columnas:** {', '.join(info['columnas_originales'])}")
                        if info['mapeo_columnas']:
                            for orig, mapped in info['mapeo_columnas'].items():
                                st.write(f"  `{orig}` → `{mapped}`")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    st.markdown("---")

    # --- RE-BUSCAR CONTACTOS FALTANTES ---
    sin_email = sum(1 for l in leads if not l.get("email", "").strip())
    sin_tel = sum(1 for l in leads if not es_telefono_ve(l.get("telefono", "")))
    st.subheader("🔄 Re-buscar Contactos Faltantes")
    st.markdown(f"De **{len(leads)}** leads actuales:")
    rbc1, rbc2, rbc3 = st.columns(3)
    rbc1.metric("Sin email", sin_email)
    rbc2.metric("Sin teléfono válido", sin_tel)
    rbc3.metric("Sin ambos", sum(1 for l in leads if not l.get("email", "").strip() and not es_telefono_ve(l.get("telefono", ""))))

    st.markdown("Este proceso visita Instagram, Facebook, websites y más para encontrar los datos faltantes. Tarda varios minutos dependiendo de cuántos falten.")

    if st.button("🔄 Re-buscar contactos faltantes (cascada completa)", key="rescrape_contacts"):
        with st.spinner("Rebuscando contactos... esto puede tardar varios minutos"):
            import subprocess
            result = subprocess.run(
                ["python", r"C:\Users\fabio\prospeccion-pskloud\merida\rescrape_contacts.py"],
                capture_output=True, text=True, timeout=1200,
                cwd=r"C:\Users\fabio\prospeccion-pskloud\merida",
            )
        st.code(result.stdout[-3000:] if result.stdout else "Sin salida")
        if result.returncode != 0 and result.stderr:
            st.error(f"Error: {result.stderr[-500:]}")
        else:
            st.success("Re-búsqueda completada. Recargando...")
            st.rerun()

    st.markdown("---")

    # --- EXTRACCIÓN DE TELÉFONOS DESDE INSTAGRAM ---
    sin_tel_ig = sum(1 for l in leads if not l.get("telefono", "").strip())
    con_ig_url = sum(1 for l in leads if "instagram.com" in l.get("website", ""))
    st.subheader("📱 Extraer Teléfonos desde Instagram")
    st.markdown(f"De **{len(leads)}** leads, **{sin_tel_ig}** no tienen teléfono. El sistema busca cada perfil de Instagram vía DuckDuckGo, visita la página pública del perfil con un navegador y extrae el teléfono del bio.")
    igc1, igc2 = st.columns(2)
    igc1.metric("Sin teléfono", sin_tel_ig)
    igc2.metric("Con URL Instagram", con_ig_url)

    if st.button("📱 Buscar teléfonos en Instagram (leads sin teléfono)", key="ig_phone_extract"):
        with st.spinner("Extrayendo teléfonos desde Instagram... esto puede tardar varios minutos"):
            import subprocess
            result = subprocess.run(
                ["python", r"C:\Users\fabio\prospeccion-pskloud\merida\ig_phone_extractor.py"],
                capture_output=True, text=True, timeout=1800,
                cwd=r"C:\Users\fabio\prospeccion-pskloud\merida",
            )
        st.code(result.stdout[-3000:] if result.stdout else "Sin salida")
        if result.returncode != 0 and result.stderr:
            st.error(f"Error: {result.stderr[-500:]}")
        else:
            st.success("Extracción completada. Recargando...")
            st.rerun()

    st.markdown("---")

    # --- EXPORTAR ---
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        df_export = pd.DataFrame(leads)
        cols_keep = [
            "nombre", "rubro", "municipio", "direccion", "telefono",
            "email", "website", "whatsapp_url", "estado_contacto",
            "notas", "fuente_telefono", "fuente_email", "maps_url",
            "fecha_creacion", "fecha_contacto",
        ]
        cols_present = [c for c in cols_keep if c in df_export.columns]
        csv_data = df_export[cols_present].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Descargar CSV",
            csv_data,
            file_name=f"leads_merida_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
    with export_col2:
        buffer = io.BytesIO()
        df_export[cols_present].to_excel(buffer, index=False, engine="openpyxl")
        st.download_button(
            "📥 Descargar Excel",
            buffer.getvalue(),
            file_name=f"leads_merida_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("---")

    st.subheader("📋 Modo de búsqueda")

    barrido_total = st.checkbox(
        "🎯 BARRIDO TOTAL B2B — Todas las empresas susceptibles de usar software/POS",
        value=False,
        key="barrido_total",
        help="Busca en TODAS las categorías comerciales reales (supermercados, farmacias, restaurantes, ferreterías, etc.) en vez de un solo rubro.",
    )

    if barrido_total:
        st.info(f"📊 **Modo Barrido Total activado:** Se buscarán **{len(CATEGORIAS_COMERCIALES_MERIDA)} categorías** en cada municipio seleccionado.")
        with st.expander("Ver todas las categorías de búsqueda", expanded=False):
            cat_grupos = {
                "Comercio & Retail": ["supermercado", "ferreteria", "farmacia", "bodegon", "tienda de repuestos", "venta de pintura", "tienda de electronica", "zapateria", "tienda de ropa"],
                "Gastronomía": ["restaurante", "panaderia", "pizzeria", "cafe", "cafeteria", "heladeria", "reposteria", "bar"],
                "Mayoristas & Distribución": ["distribuidora de alimentos", "mayorista", "encomiendas", "transporte de carga"],
                "Servicios & Salud": ["clinica", "laboratorio clinico", "taller mecanico", "hotel", "colegio privado", "constructora"],
            }
            for grupo, cats in cat_grupos.items():
                st.markdown(f"**{grupo}:** {', '.join(cats)}")
    else:
        metodo = st.radio(
            "Método de búsqueda",
            [
                "📚 Directorios VE (guías locales, recomendado)",
                "📡 OSM + DuckDuckGo",
                "⚡ Búsqueda Google (rápido)",
                "🗺️ Google Maps",
            ],
            horizontal=True,
        )

    st.subheader("🎯 Filtros de búsqueda")
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        municipios_selected = st.multiselect(
            "Municipios",
            options=MUNICIPIOS,
            default=MUNICIPIOS,
            format_func=lambda x: MUNICIPIOS_LABELS.get(x, x),
            key="municipios_selected",
        )
    with fcol2:
        rubros_selected = st.multiselect(
            "Rubros",
            options=list(RUBROS.keys()),
            default=list(RUBROS.keys()),
            key="rubros_selected",
        )
    with fcol3:
        max_results_per_rubro = st.slider(
            "Resultados por rubro",
            min_value=10,
            max_value=100,
            value=20,
            step=5,
        )

    if st.button("🚀 Iniciar Scraping", key="start_scraping"):
        if not municipios_selected:
            st.warning("Selecciona al menos un municipio.")
        elif not barrido_total and not rubros_selected:
            st.warning("Selecciona al menos un rubro (o activa el Barrido Total).")
        else:
            existing = load_leads()
            seen_ids = {l.get("place_id", "") for l in existing}
            new_leads = []

            if barrido_total:
                total_categorias = len(CATEGORIAS_COMERCIALES_MERIDA)
                total_combos = total_categorias * len(municipios_selected)
                est_seconds = total_combos * 0.5
                est_min = est_seconds // 60

                st.caption(f"⏱ Tiempo estimado: ~{est_min} min ({total_combos} búsquedas × 0.5s)")

                visit_sites = st.checkbox(
                    "🔍 Visitar sitios web para más contactos",
                    value=False,
                    key="visit_sites_barrido",
                )

                progress = st.progress(0, text="Iniciando Barrido Total con OSM+DDG...")
                status_text = st.empty()

                raw_leads = []
                seen_barrido = set()
                total_categorias = len(CATEGORIAS_COMERCIALES_MERIDA)
                combo_actual = 0

                for municipio in municipios_selected:
                    ubicacion = f"{municipio}, Mérida, Venezuela"
                    for segmento, categorias in MATRIZ_TARGET_SOFTWARE.items():
                        for categoria in categorias:
                            combo_actual += 1
                            progress.progress(
                                combo_actual / (total_categorias * len(municipios_selected)),
                                text=f"OSM+DDG: {categoria} en {municipio}... ({combo_actual}/{total_categorias * len(municipios_selected)})",
                            )

                            raw = []
                            seen_local = set()

                            osm_results = local_search._buscar_overpass(categoria, ubicacion)
                            for r in osm_results:
                                k = r["nombre"].lower().strip()
                                if k not in seen_local:
                                    raw.append(r)
                                    seen_local.add(k)

                            ddg_results = local_search._buscar_ddg_batch(categoria, ubicacion, min(max_results_per_rubro, 20))
                            for r in ddg_results:
                                k = r["nombre"].lower().strip()
                                if k not in seen_local:
                                    raw.append(r)
                                    seen_local.add(k)

                            phones_found = 0
                            emails_found = 0
                            for r in raw:
                                pid = r.get("nombre", "").lower().strip()
                                if pid in seen_barrido:
                                    continue
                                r["rubro"] = categoria
                                r["segmento"] = segmento
                                r["municipio"] = municipio
                                r["ciudad"] = municipio
                                r["fecha_creacion"] = datetime.now().isoformat()
                                r.setdefault("email", "")
                                r.setdefault("fuente_email", "")
                                if r.get("telefono"):
                                    r["telefono"] = normalizar_telefono_ve(r["telefono"])
                                    if r["telefono"]:
                                        phones_found += 1
                                        r["whatsapp_url"] = build_wa_link(
                                            r["telefono"],
                                            f"Hola, buenos días. Un gusto saludarle de {r.get('nombre', '')}.",
                                        )
                                if r.get("email"):
                                    emails_found += 1
                                raw_leads.append(r)
                                seen_barrido.add(pid)

                            status_text.info(
                                f"✅ {categoria} en {municipio}: {len(raw)} encontrados, "
                                f"{phones_found} con teléfono, {emails_found} con email"
                            )

                for r in raw_leads:
                    pid = r.get("nombre", "").lower().strip()
                    if pid in seen_ids:
                        continue
                    new_leads.append(r)
                    seen_ids.add(pid)

                progress.progress(1.0, text="Barrido Total completado")
                st.success(
                    f"✅ **Barrido Total completado:** {len(new_leads)} nuevos leads, "
                    f"{sum(1 for r in new_leads if r.get('telefono'))} con teléfono, "
                    f"{sum(1 for r in new_leads if r.get('email'))} con email"
                )

            else:
                total_combos = len(municipios_selected) * len(rubros_selected)

                if "Directorios VE" in metodo:
                    est_seconds = total_combos * 2
                    est_min = est_seconds // 60
                    progress = st.progress(0, text="Buscando en directorios venezolanos...")
                    status_text = st.empty()
                    st.caption(f"⏱ Tiempo estimado: ~{est_min} min ({total_combos} combinaciones × ~2s)")

                    idx = 0
                    for municipio in municipios_selected:
                        for rubro in rubros_selected:
                            idx += 1
                            progress.progress(
                                idx / total_combos,
                                text=f"Directorios: {rubro} en {municipio}... ({idx}/{total_combos})",
                            )
                            ubicacion = f"{municipio}, Mérida, Venezuela"

                            raw = buscar_directorio(rubro, ubicacion, max_results=max_results_per_rubro)

                            phones_found = 0
                            emails_found = 0
                            for r in raw:
                                pid = r.get("nombre", "").lower().strip()
                                if pid in seen_ids:
                                    continue
                                r["rubro"] = rubro
                                r["municipio"] = municipio
                                r["ciudad"] = municipio
                                r["fecha_creacion"] = datetime.now().isoformat()
                                r.setdefault("email", "")
                                r.setdefault("fuente_email", "")
                                if r.get("telefono"):
                                    r["telefono"] = normalizar_telefono_ve(r["telefono"])
                                    if r["telefono"]:
                                        phones_found += 1
                                        r["whatsapp_url"] = build_wa_link(
                                            r["telefono"],
                                            f"Hola, buenos días. Un gusto saludarle de {r.get('nombre', '')}.",
                                        )
                                if r.get("email"):
                                    emails_found += 1
                                new_leads.append(r)
                                seen_ids.add(pid)

                            status_text.info(
                                f"✅ {rubro} en {municipio}: {len(raw)} encontrados, "
                                f"{phones_found} con teléfono, {emails_found} con email"
                            )

                elif "Búsqueda Google" in metodo:
                    est_seconds = total_combos * 5
                    est_min = est_seconds // 60
                    progress = st.progress(0, text="Iniciando búsqueda rápida en Google...")
                    status_text = st.empty()
                    st.caption(f"⏱ Tiempo estimado: ~{est_min} min ({total_combos} combinaciones × ~5s)")

                    visit_sites = st.checkbox(
                        "🔍 Visitar sitios web para más contactos (lento pero más datos)",
                        value=False,
                        key="visit_sites",
                    )

                    idx = 0
                    for municipio in municipios_selected:
                        for rubro in rubros_selected:
                            idx += 1
                            progress.progress(
                                idx / total_combos,
                                text=f"Google: {rubro} en {municipio}... ({idx}/{total_combos})",
                            )
                            ciudad = DICCIONARIO_UBICACIONES.get(municipio, {}).get("ciudad", municipio)
                            raw = scrape_fast_v2(rubro, municipio, max_results=max_results_per_rubro, visit_sites=visit_sites)
                            phones_found = 0
                            emails_found = 0
                            for r in raw:
                                pid = r.get("nombre", "").lower().strip()
                                if pid in seen_ids:
                                    continue
                                r["rubro"] = rubro
                                r["municipio"] = municipio
                                r["ciudad"] = ciudad
                                r["fecha_creacion"] = datetime.now().isoformat()
                                r.setdefault("email", "")
                                r.setdefault("fuente_email", "")
                                if r.get("telefono"):
                                    phones_found += 1
                                    r["whatsapp_url"] = build_wa_link(
                                        r["telefono"],
                                        f"Hola, buenos días. Un gusto saludarle de {r.get('nombre', '')}.",
                                    )
                                if r.get("email"):
                                    emails_found += 1
                                new_leads.append(r)
                                seen_ids.add(pid)

                            status_text.info(
                                f"✅ {rubro} en {ciudad}: {len(raw)} encontrados, "
                                f"{phones_found} con teléfono, {emails_found} con email"
                            )

                elif "Google Maps" in metodo:
                    from gmaps_scraper import scrape_google_maps
                    est_seconds = total_combos * 15
                    est_min = est_seconds // 60
                    progress = st.progress(0, text="Iniciando Google Maps scraping...")
                    status_text = st.empty()
                    st.caption(f"⏱ Tiempo estimado: ~{est_min} min ({total_combos} combinaciones × ~15s)")

                    idx = 0
                    for municipio in municipios_selected:
                        for rubro in rubros_selected:
                            idx += 1
                            progress.progress(
                                idx / total_combos,
                                text=f"Google Maps: {rubro} en {municipio}... ({idx}/{total_combos})",
                            )
                            raw = scrape_google_maps(rubro, municipio, max_results=max_results_per_rubro)
                            phones_found = 0
                            for r in raw:
                                pid = r.get("place_id", r.get("nombre", "")).lower().strip()
                                if pid in seen_ids:
                                    continue
                                r["rubro"] = rubro
                                r["municipio"] = municipio
                                r["fecha_creacion"] = datetime.now().isoformat()
                                r.setdefault("email", "")
                                r.setdefault("fuente_email", "")
                                if r.get("telefono"):
                                    r["telefono"] = normalizar_telefono_ve(r["telefono"])
                                    if r["telefono"]:
                                        phones_found += 1
                                        r["whatsapp_url"] = build_wa_link(
                                            r["telefono"],
                                            f"Hola, buenos días. Un gusto saludarle de {r.get('nombre', '')}.",
                                        )
                                new_leads.append(r)
                                seen_ids.add(pid)

                            status_text.info(
                                f"✅ {rubro} en {municipio}: {len(raw)} encontrados, "
                                f"{phones_found} con teléfono"
                            )

                else:
                    est_seconds = total_combos * 8
                    est_min = est_seconds // 60
                    progress = st.progress(0, text="Iniciando scraping OSM + DDG...")
                    status_text = st.empty()
                    st.caption(f"⏱ Tiempo estimado: ~{est_min} min ({total_combos} combinaciones × ~8s)")

                    idx = 0
                    for municipio in municipios_selected:
                        for rubro in rubros_selected:
                            idx += 1
                            progress.progress(
                                idx / total_combos,
                                text=f"Scraping {rubro} en {municipio}... ({idx}/{total_combos})",
                            )
                            ubicacion = f"{municipio}, Mérida, Venezuela"

                            raw = []
                            seen_local = set()

                            osm_results = local_search._buscar_overpass(rubro, ubicacion)
                            for r in osm_results:
                                k = r["nombre"].lower().strip()
                                if k not in seen_local:
                                    raw.append(r)
                                    seen_local.add(k)

                            ddg_results = local_search._buscar_ddg_batch(rubro, ubicacion, min(max_results_per_rubro, 20))
                            for r in ddg_results:
                                k = r["nombre"].lower().strip()
                                if k not in seen_local:
                                    raw.append(r)
                                    seen_local.add(k)

                            phones_found = 0
                            emails_found = 0
                            for r in raw:
                                pid = r.get("place_id", "")
                                if pid and pid in seen_ids:
                                    continue
                                r["rubro"] = rubro
                                r["municipio"] = municipio
                                r["ciudad"] = municipio
                                r["fecha_creacion"] = datetime.now().isoformat()
                                r.setdefault("email", "")
                                r.setdefault("fuente_email", "")
                                if r.get("telefono"):
                                    r["telefono"] = normalizar_telefono_ve(r["telefono"])
                                    if r["telefono"]:
                                        phones_found += 1
                                        r["whatsapp_url"] = build_wa_link(
                                            r["telefono"],
                                            f"Hola, buenos días. Un gusto saludarle de {r.get('nombre', '')}.",
                                        )
                                if r.get("email"):
                                    emails_found += 1
                                new_leads.append(r)
                                if pid:
                                    seen_ids.add(pid)

                            status_text.info(
                                f"✅ {rubro} en {municipio}: {len(raw)} encontrados, "
                                f"{phones_found} con teléfono, {emails_found} con email"
                            )

            if new_leads:
                existing.extend(new_leads)
                save_leads(existing)
                leads = existing

                st.success(
                    f"Scraping completado: **{len(new_leads)}** nuevos leads guardados"
                )

                with st.expander("📧 Enriquecimiento de emails (opcional — puede tardar)", expanded=True):
                    st.write(
                        "Busca emails automáticamente usando: scraping web, DuckDuckGo y Hunter.io."
                    )

                    leads_sin_email = [l for l in new_leads if not l.get("email")]
                    leads_con_website = [l for l in leads_sin_email if l.get("website")]
                    leads_sin_website = [l for l in leads_sin_email if not l.get("website")]

                    st.write(f"**{len(leads_sin_email)}** leads sin email "
                             f"({len(leads_con_website)} con website, {len(leads_sin_website)} sin website)")

                    config = load_config()
                    hunter_api_key = config.get("hunter_api_key", "")

                    enrich_cols = st.columns(3)
                    with enrich_cols[0]:
                        use_website = st.checkbox("🌐 Scraping web", value=True, key="enrich_web")
                    with enrich_cols[1]:
                        use_ddg = st.checkbox("🔍 DuckDuckGo", value=True, key="enrich_ddg")
                    with enrich_cols[2]:
                        use_hunter = st.checkbox("🔑 Hunter.io", value=bool(hunter_api_key), key="enrich_hunter",
                                                  disabled=not hunter_api_key)

                    if not hunter_api_key:
                        st.caption("💡 Para usar Hunter.io, configura tu API key en Configuración → API Keys.")

                    max_to_enrich = st.slider("Máximo a enriquecer", 10, 500, min(100, len(leads_sin_email)),
                                               key="max_enrich")

                    if st.button("🔍 Buscar emails", key="enrich_emails"):
                        if not leads_sin_email:
                            st.info("Todos los leads ya tienen email.")
                        else:
                            enrich_progress = st.progress(0, text="Iniciando búsqueda de emails...")
                            status_area = st.empty()

                            def enrich_callback(current, total, name):
                                enrich_progress.progress(
                                    current / total,
                                    text=f"📧 Buscando email: {name[:35]}... ({current}/{total})",
                                )

                            leads_actualizados, found_count = enrich_leads_batch(
                                leads=new_leads,
                                hunter_api_key=hunter_api_key if use_hunter else "",
                                max_leads=max_to_enrich,
                                delay=0.8,
                                progress_callback=enrich_callback,
                            )

                            existing = load_leads()
                            for lead in leads_actualizados:
                                for i, e in enumerate(existing):
                                    if e.get("nombre", "").lower() == lead.get("nombre", "").lower():
                                        if lead.get("email"):
                                            existing[i]["email"] = lead["email"]
                                            existing[i]["fuente_email"] = lead.get("fuente_email", "")
                                        break
                            save_leads(existing)

                            enrich_progress.progress(1.0, text="Búsqueda completada")
                            st.success(
                                f"✅ **Emails encontrados: {found_count}** de {max_to_enrich} revisados"
                            )

                            fuentes = {}
                            for l in leads_actualizados[:max_to_enrich]:
                                if l.get("email") and l.get("fuente_email"):
                                    f = l["fuente_email"]
                                    fuentes[f] = fuentes.get(f, 0) + 1
                            if fuentes:
                                st.write("**Por fuente:**")
                                for fuente, count in fuentes.items():
                                    st.write(f"  - {fuente}: {count} emails")
            else:
                st.info("No se encontraron nuevos leads en esta búsqueda.")

    st.markdown("---")
    st.subheader("📋 Leads actuales")

    leads = load_leads()

    if leads:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_rubro = st.multiselect(
                "Filtrar por rubro",
                options=sorted(set(l.get("rubro", "") for l in leads)),
                key="filter_rubro_1",
            )
        with col_f2:
            filter_municipio = st.multiselect(
                "Filtrar por municipio",
                options=sorted(set(l.get("municipio", "") for l in leads)),
                key="filter_mun_1",
            )
        with col_f3:
            filter_estado = st.multiselect(
                "Filtrar por estado",
                options=ESTADOS_CONTACTO,
                key="filter_estado_1",
            )

        filtered = leads
        if filter_rubro:
            filtered = [l for l in filtered if l.get("rubro", "") in filter_rubro]
        if filter_municipio:
            filtered = [l for l in filtered if l.get("municipio", "") in filter_municipio]
        if filter_estado:
            filtered = [l for l in filtered if l.get("estado_contacto", "No Contactado") in filter_estado]

        st.write(f"Mostrando **{len(filtered)}** de **{len(leads)}** leads")

        for i, lead in enumerate(filtered):
            idx_in_all = next(
                (j for j, l in enumerate(leads) if l.get("place_id") == lead.get("place_id") and l.get("place_id") is not None),
                None,
            )
            if idx_in_all is None:
                idx_in_all = next(
                    (j for j, l in enumerate(leads) if l.get("nombre") == lead.get("nombre") and l.get("rubro") == lead.get("rubro")),
                    None,
                )
            if idx_in_all is None:
                continue

            nombre = lead.get("nombre", "Sin nombre")
            rubro = lead.get("rubro", "")
            municipio = lead.get("municipio", "")
            telefono = lead.get("telefono", "")
            email = lead.get("email", "")
            website = lead.get("website", "")
            estado = lead.get("estado_contacto", "No Contactado")
            notas = lead.get("notas", "")
            fuente = lead.get("fuente_telefono", "")

            with st.expander(f"{'📞 ' if telefono else ''}{'📧 ' if email else ''}{nombre} — {rubro} | {municipio}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Rubro:** {rubro}")
                    st.markdown(f"**Municipio:** {municipio}")
                    st.markdown(f"**Dirección:** {lead.get('direccion', 'N/A')}")
                with c2:
                    if telefono:
                        st.markdown(f"**Teléfono:** {telefono}")
                        wa_url = lead.get("whatsapp_url", build_wa_link(telefono, f"Hola, {nombre}."))
                        if wa_url:
                            st.markdown(
                                f'<a href="{wa_url}" target="_blank" class="whatsapp-btn">💬 WhatsApp</a>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown("**Teléfono:** No encontrado")
                    if email:
                        st.markdown(f"**Email:** {email}")
                    else:
                        st.markdown("**Email:** No encontrado")
                with c3:
                    if website:
                        st.markdown(f"**Website:** [{website}]({website})")
                    st.markdown(f"**Fuente:** {fuente or 'N/A'}")
                    st.markdown(f"**Maps:** [Ver ubicación]({lead.get('maps_url', '#')})")

                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

                ec1, ec2 = st.columns([1, 2])
                with ec1:
                    new_estado = st.selectbox(
                        "Estado",
                        ESTADOS_CONTACTO,
                        index=ESTADOS_CONTACTO.index(estado) if estado in ESTADOS_CONTACTO else 0,
                        key=f"estado_{i}",
                    )
                with ec2:
                    new_notas = st.text_input(
                        "Notas",
                        value=notas,
                        key=f"notas_{i}",
                    )

                b1, b2, b3 = st.columns([1, 1, 1])
                with b1:
                    if st.button("💾 Guardar", key=f"save_{i}"):
                        leads[idx_in_all]["estado_contacto"] = new_estado
                        leads[idx_in_all]["notas"] = new_notas
                        if new_estado != "No Contactado":
                            leads[idx_in_all]["fecha_contacto"] = datetime.now().isoformat()
                        save_leads(leads)
                        st.success("Guardado")
                        st.rerun()
                with b2:
                    if not email and telefono:
                        if st.button("📧 Buscar email", key=f"enrich_{i}"):
                            with st.spinner("Buscando email..."):
                                leads[idx_in_all] = enrich_lead_email(leads[idx_in_all])
                                save_leads(leads)
                            if leads[idx_in_all].get("email"):
                                st.success(f"Email encontrado: {leads[idx_in_all]['email']}")
                            else:
                                st.info("No se encontró email")
                            st.rerun()
                with b3:
                    if st.button("🗑️ Eliminar", key=f"del_{i}"):
                        leads.pop(idx_in_all)
                        save_leads(leads)
                        st.rerun()

        st.markdown("---")

        # --- RESUMEN DEL SCRAPING ---
        st.subheader("📊 Resumen del Scraping Actual")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("📋 Total", len(leads))
        s2.metric("📧 Con Email", sum(1 for l in leads if l.get("email", "").strip()))
        s3.metric("📱 Con Tel", sum(1 for l in leads if es_telefono_ve(l.get("telefono", ""))))
        s4.metric("⚠️ Sin Datos", sum(1 for l in leads if not l.get("email", "").strip() and not es_telefono_ve(l.get("telefono", ""))))

        # --- DETALLE DE LEADS ---
        with st.expander("📋 Ver todos los leads", expanded=False):
            if leads:
                df_show = pd.DataFrame(leads)
                cols_show = ["nombre", "rubro", "municipio", "email", "telefono", "estado_contacto"]
                cols_avail = [c for c in cols_show if c in df_show.columns]
                st.dataframe(df_show[cols_avail], use_container_width=True, height=400)
            else:
                st.info("No hay leads aún.")

    else:
        st.info("No hay leads aún. Usa el botón de scraping para empezar.")

# =============================================================================
# TAB 2: CORREO
# =============================================================================

with tab_correo:
    st.header("📧 Enviar Correos")

    leads = load_leads()
    leads_con_email = [l for l in leads if l.get("email", "").strip()]
    config = load_config()
    smtp_server = config.get("smtp_server", "smtp.gmail.com")
    smtp_port = int(config.get("smtp_port", 587))
    smtp_email = config.get("smtp_email", "")
    smtp_password = config.get("smtp_password", "")

    templates = load_email_templates()
    tpl = templates[0] if templates else {"nombre": "Default", "asunto": "", "cuerpo": ""}
    asunto = tpl.get("asunto", "")
    cuerpo = re.sub('<[^<]+?>', '', tpl.get("cuerpo", ""))
    form_link_consultoria = tpl.get("form_link_consultoria", tpl.get("form_link", ""))
    form_link_expotrabajo = tpl.get("form_link_expotrabajo", "")

    send_log = load_send_log()
    today_str = datetime.now().strftime("%Y-%m-%d")
    sent_today = sum(1 for s in send_log if s.get("fecha", "").startswith(today_str) and s.get("exitoso"))
    daily_limit = config.get("daily_send_limit", 100)
    remaining = max(0, daily_limit - sent_today)

    emails_sent_set = set(s.get("email", "").lower() for s in send_log if s.get("exitoso"))
    leads_pendientes = [l for l in leads_con_email if l.get("email", "").lower() not in emails_sent_set]

    c1, c2, c3 = st.columns(3)
    c1.metric("📧 Con email", len(leads_con_email))
    c2.metric("⏳ Pendientes", len(leads_pendientes))
    c3.metric("✅ Enviados hoy", f"{sent_today}/{daily_limit}")

    if not leads_con_email:
        st.info("No hay leads con email. Importa tu Excel en Prospección.")
    elif len(leads_pendientes) == 0:
        st.success("Todos los leads con email ya fueron contactados hoy.")
    else:
        st.markdown(f"### {len(leads_pendientes)} correos pendientes")

        with st.expander("✏️ Ver/editar plantilla", expanded=False):
            asunto = st.text_input("Asunto", value=asunto, key="correo_asunto")
            cuerpo = st.text_area("Mensaje", value=cuerpo, height=200, key="correo_cuerpo")
            fl1, fl2 = st.columns(2)
            with fl1:
                form_link_consultoria = st.text_input("Enlace Consultoría", value=form_link_consultoria, key="correo_link1")
            with fl2:
                form_link_expotrabajo = st.text_input("Enlace ExpoTrabajo", value=form_link_expotrabajo, key="correo_link2")
            if st.button("Guardar plantilla", key="save_correo_tpl"):
                templates[0]["asunto"] = asunto
                templates[0]["cuerpo"] = cuerpo
                templates[0]["form_link_consultoria"] = form_link_consultoria
                templates[0]["form_link_expotrabajo"] = form_link_expotrabajo
                save_email_templates(templates)
                st.success("Plantilla guardada")

        if st.button("🚀 ENVIAR TODOS LOS CORREOS", key="send_all_email", type="primary", use_container_width=True):
            if not smtp_password:
                st.error("Configura SMTP en Configuración.")
            else:
                delay_seconds = config.get("delay_seconds", 30)
                sent_count = 0
                fail_count = 0
                log = load_send_log()
                total = len(leads_pendientes)
                results_container = st.container()

                for i, lead in enumerate(leads_pendientes):
                    email_body = cuerpo
                    email_subject = asunto
                    for k, v in {
                        "nombre": lead.get("nombre", ""),
                        "rubro": lead.get("rubro", ""),
                        "municipio": lead.get("municipio", ""),
                        "enlace": form_link_consultoria or "",
                        "enlace_consultoria": form_link_consultoria or "",
                        "enlace_expotrabajo": form_link_expotrabajo or "",
                    }.items():
                        email_body = email_body.replace("{{" + k + "}}", v)
                        email_subject = email_subject.replace("{{" + k + "}}", v)

                    ok, msg = send_smtp_email(
                        smtp_server, int(smtp_port), smtp_email, smtp_password,
                        lead.get("email", ""), email_subject, email_body,
                    )
                    log.append({"email": lead.get("email", ""), "nombre": lead.get("nombre", ""), "fecha": datetime.now().isoformat(), "exitoso": ok, "mensaje": msg})
                    if ok:
                        sent_count += 1
                        results_container.success(f"[{i+1}/{total}] {lead.get('nombre', '')} — OK")
                    else:
                        fail_count += 1
                        results_container.warning(f"[{i+1}/{total}] {lead.get('nombre', '')} — {msg}")
                    save_send_log(log)
                    if i < total - 1:
                        time.sleep(delay_seconds)

                save_leads(leads)
                st.success(f"Completado: {sent_count} enviados, {fail_count} fallidos de {total} pendientes")

    st.markdown("---")
    st.subheader("📋 Últimos envíos")
    if send_log:
        log_df = pd.DataFrame(send_log)
        cols = [c for c in ["nombre", "email", "fecha", "exitoso"] if c in log_df.columns]
        st.dataframe(log_df[cols].tail(20), use_container_width=True)
    else:
        st.info("No hay envíos registrados.")

# =============================================================================
# TAB 3: WHATSAPP
# =============================================================================

with tab_whatsapp:
    st.header("💬 Enviar WhatsApp")

    leads = load_leads()
    leads_con_tel = [l for l in leads if l.get("telefono") and es_telefono_ve(l.get("telefono", ""))]
    config = load_config()

    templates_wa = load_email_templates()
    tpl_wa = templates_wa[0] if templates_wa else {}

    evo_url = EVO_API_URL
    evo_key = EVO_API_KEY
    evo_instance = EVO_INSTANCE

    wa_log = load_wa_log()
    wa_today_str = datetime.now().strftime("%Y-%m-%d")
    wa_today = sum(1 for s in wa_log if s.get("fecha", "").startswith(wa_today_str) and s.get("exitoso"))
    wa_daily_limit = config.get("wa_daily_limit", 30)
    wa_remaining = max(0, wa_daily_limit - wa_today)

    wa_already_sent = set(re.sub(r"[^\d]", "", s.get("telefono", "")) for s in wa_log if s.get("exitoso"))
    leads_wa_pending = [l for l in leads_con_tel if re.sub(r"[^\d]", "", l.get("telefono", "")) not in wa_already_sent and not is_phone_blocked(l.get("telefono", ""))]

    c1, c2, c3 = st.columns(3)
    c1.metric("📱 Con teléfono", len(leads_con_tel))
    c2.metric("⏳ Pendientes", len(leads_wa_pending))
    c3.metric("✅ Enviados hoy", f"{wa_today}/{wa_daily_limit}")

    if not leads_con_tel:
        st.info("No hay leads con teléfono válido. Importa tu Excel en Prospección.")
    elif len(leads_wa_pending) == 0:
        st.success("Todos los leads con teléfono ya fueron contactados por WhatsApp.")
    else:
        st.markdown(f"### {len(leads_wa_pending)} WhatsApp pendientes")

        with st.expander("✏️ Ver/editar plantilla", expanded=False):
            default_wa = tpl_wa.get("cuerpo_wa", """Estimado(a) Director/Gerente,

En nombre de Premium Soft, con el respaldo de la Cámara de Comercio del Estado Mérida, lo invitamos a participar en dos eventos estratégicos:

1️⃣ Business Consulting Day | 27 Agosto 2026
📍 C.C. Las Tapias, Piso 2
💰 Sin Costo (con reservación)
👉 RESERVAR: {{enlace_consultoria}}

2️⃣ ExpoTrabajo Mérida 2026 | 28 Agosto 2026
📍 C.C. Las Tapias, Piso 2
👉 REGISTRAR MI EMPRESA: {{enlace_expotrabajo}}

Cupos limitados. - Equipo Premium Soft & Cámara de Comercio""")
            wa_message = st.text_area("Mensaje WhatsApp", value=default_wa, height=250, key="wa_msg_simple")
            st.caption("Variables: `{{nombre}}` `{{rubro}}` `{{municipio}}` `{{enlace_consultoria}}` `{{enlace_expotrabajo}}`")
            wl1, wl2 = st.columns(2)
            with wl1:
                enlace_consultoria = st.text_input("Enlace Consultoría", value="", key="wa_link1_simple")
            with wl2:
                enlace_expotrabajo = st.text_input("Enlace ExpoTrabajo", value="", key="wa_link2_simple")
            if st.button("Guardar plantilla WA", key="save_wa_tpl"):
                templates_wa[0]["cuerpo_wa"] = wa_message
                save_email_templates(templates_wa)
                st.success("Plantilla guardada")

        if st.button("🚀 ENVIAR TODOS LOS WHATSAPP", key="send_all_wa", type="primary", use_container_width=True):
            if not (enlace_consultoria or enlace_expotrabajo):
                st.warning("Ingresa al menos un enlace de formulario en la plantilla.")
            else:
                wa_delay = 60
                wa_sent = 0
                wa_fail = 0
                wa_log_batch = load_wa_log()
                total = len(leads_wa_pending)
                results_container = st.container()

                for idx, lead in enumerate(leads_wa_pending):
                    nombre = lead.get("nombre", "")
                    telefono = formato_whatsapp(lead.get("telefono", ""))

                    msg = _substitute_vars(wa_message, {
                        "nombre": nombre,
                        "rubro": lead.get("rubro", ""),
                        "municipio": lead.get("municipio", ""),
                        "telefono": telefono,
                        "email": lead.get("email", ""),
                        "enlace_consultoria": enlace_consultoria or "",
                        "enlace_expotrabajo": enlace_expotrabajo or "",
                    })

                    ok, resp = send_wa_business(telefono, msg, evo_url, evo_key, evo_instance)
                    wa_log_batch.append({
                        "telefono": telefono,
                        "nombre": nombre,
                        "fecha": datetime.now().isoformat(),
                        "exitoso": ok,
                        "mensaje": resp,
                    })

                    if ok:
                        wa_sent += 1
                        results_container.success(f"[{idx+1}/{total}] {nombre} ({telefono}) — OK")
                    else:
                        wa_fail += 1
                        results_container.warning(f"[{idx+1}/{total}] {nombre} ({telefono}) — {resp}")

                    save_wa_log(wa_log_batch)
                    if idx < total - 1:
                        time.sleep(wa_delay)

                st.success(f"Completado: {wa_sent} enviados, {wa_fail} fallidos de {total} pendientes")

    st.markdown("---")
    st.subheader("📋 Últimos envíos WA")
    wa_log = load_wa_log()
    if wa_log:
        wa_log_df = pd.DataFrame(wa_log)
        wa_cols = [c for c in ["nombre", "telefono", "fecha", "exitoso"] if c in wa_log_df.columns]
        st.dataframe(wa_log_df[wa_cols].tail(20), use_container_width=True)
    else:
        st.info("No hay envíos WA registrados.")

# =============================================================================
# TAB 4: ANALÍTICA
# =============================================================================

with tab_analitica:
    st.header("📊 Analítica — Mérida, Venezuela")

    leads = load_leads()
    send_log = load_send_log()
    wa_log = load_wa_log()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not leads:
        st.info("No hay datos para analizar.")
    else:
        emails_ok = [s for s in send_log if s.get("exitoso")]
        emails_fail = [s for s in send_log if not s.get("exitoso")]
        wa_ok = [s for s in wa_log if s.get("exitoso")]
        wa_fail = [s for s in wa_log if not s.get("exitoso")]

        emails_ok_set = set(s.get("email", "").lower().strip() for s in emails_ok)
        wa_ok_set = set()
        for s in wa_ok:
            wa_ok_set.add(re.sub(r"[^\d]", "", s.get("telefono", "")))

        con_email = [l for l in leads if l.get("email", "").strip()]
        con_tel = [l for l in leads if l.get("telefono") and es_telefono_ve(l.get("telefono", ""))]

        enviados_correo = [l for l in leads if l.get("email", "").lower().strip() in emails_ok_set]
        enviados_wa = [l for l in leads if l.get("telefono") and re.sub(r"[^\d]", "", l.get("telefono", "")) in wa_ok_set]
        sin_datos = [l for l in leads if not l.get("email", "").strip() and not (l.get("telefono") and es_telefono_ve(l.get("telefono", "")))]
        no_contactados = [l for l in leads if l not in enviados_correo and l not in enviados_wa]

        # --- PANEL GENERAL ---
        st.subheader("Panel General")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("📋 Total Leads", len(leads))
        r2.metric("📧 Con Email", len(con_email))
        r3.metric("📱 Con Tel Válido", len(con_tel))
        r4.metric("⚠️ Sin Datos", len(sin_datos))

        # --- CONTACTO POR CANAL ---
        st.markdown("---")
        st.subheader("Estado de Contacto por Canal")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📧 Contactados por Correo", len(enviados_correo))
        c2.metric("💬 Contactados por WhatsApp", len(enviados_wa))
        c3.metric("📞 Líneas fijas (para llamada)", sum(1 for l in leads if l.get("telefono") and not es_telefono_ve(l.get("telefono", "")) and l.get("email", "").lower().strip() not in emails_ok_set))
        c4.metric("⏳ Sin contacto aún", len(no_contactados))

        # --- DETALLE: QUIÉN FUE CONTACTADO ---
        st.markdown("---")
        st.subheader("Detalle de Contactos por Canal")

        # Build contact status for each lead
        detalle = []
        for l in leads:
            email = l.get("email", "").strip()
            tel = l.get("telefono", "").strip()
            nombre = l.get("nombre", "")
            rubro = l.get("rubro", "")
            municipio = l.get("municipio", "")

            en_correo = email.lower() in emails_ok_set if email else False
            tel_digits = re.sub(r"[^\d]", "", tel) if tel else ""
            en_wa = tel_digits in wa_ok_set if tel_digits else False
            es_fijo = not es_telefono_ve(tel) if tel else False
            tiene_email = bool(email)
            tiene_tel = es_telefono_ve(tel) if tel else False

            if en_correo and en_wa:
                canal = "📧💬 Correo + WA"
            elif en_correo:
                canal = "📧 Correo"
            elif en_wa:
                canal = "💬 WhatsApp"
            elif tiene_email and not en_correo:
                canal = "⏳ Email pendiente"
            elif tiene_tel and not en_wa:
                canal = "⏳ WA pendiente"
            elif es_fijo and tiene_email:
                canal = "📞 Línea fija + Email"
            elif es_fijo:
                canal = "📞 Línea fija (llamada)"
            else:
                canal = "❌ Sin datos"

            fecha_email = ""
            fecha_wa = ""
            for s in send_log:
                if s.get("exitoso") and s.get("email","").lower().strip() == email.lower().strip():
                    fecha_email = s.get("fecha","")[:16]
                    break
            if tel:
                for s in wa_log:
                    if s.get("exitoso") and re.sub(r"[^\d]","",s.get("telefono","")) == tel_digits:
                        fecha_wa = s.get("fecha","")[:16]
                        break

            detalle.append({
                "Nombre": nombre,
                "Rubro": rubro,
                "Municipio": municipio,
                "Email": email,
                "Teléfono": tel,
                "Canal Contacto": canal,
                "Fecha Prospección": l.get("fecha_creacion", "")[:10] or today_str,
                "Fecha Envío Email": fecha_email,
                "Fecha Envío WA": fecha_wa,
                "Estado": l.get("estado_contacto", "No Contactado"),
                "Website": l.get("website", ""),
                "Notas": l.get("notas", ""),
            })

        df_detalle = pd.DataFrame(detalle)

        # Filter options
        filtros = st.multiselect(
            "Filtrar por canal de contacto",
            options=sorted(df_detalle["Canal Contacto"].unique()),
            default=[],
            key="analitica_filtro_canal",
        )
        if filtros:
            df_filtrado = df_detalle[df_detalle["Canal Contacto"].isin(filtros)]
        else:
            df_filtrado = df_detalle

        st.dataframe(df_filtrado, use_container_width=True)
        st.caption(f"Mostrando {len(df_filtrado)} de {len(df_detalle)} leads")

        # --- RESUMEN CONTABLE ---
        st.markdown("---")
        st.subheader("Resumen Contable")
        resumen_data = []
        for canal, grupo in df_detalle.groupby("Canal Contacto"):
            resumen_data.append({"Canal de Contacto": canal, "Cantidad": len(grupo)})
        resumen_df = pd.DataFrame(resumen_data).sort_values("Cantidad", ascending=False)
        st.dataframe(resumen_df, use_container_width=True)

        # --- GRÁFICAS ---
        st.markdown("---")
        st.subheader("Distribución")
        ac1, ac2 = st.columns(2)
        with ac1:
            st.markdown("**Por Rubro**")
            rubro_counts = Counter(l.get("rubro", "N/A") for l in leads)
            rubro_df = pd.DataFrame(list(rubro_counts.items()), columns=["Rubro", "Total"]).sort_values("Total", ascending=False)
            st.bar_chart(rubro_df.set_index("Rubro"))
        with ac2:
            st.markdown("**Por Municipio**")
            mun_counts = Counter(l.get("municipio", "N/A") for l in leads)
            mun_df = pd.DataFrame(list(mun_counts.items()), columns=["Municipio", "Total"]).sort_values("Total", ascending=False)
            st.bar_chart(mun_df.set_index("Municipio"))

        # --- EXPORTAR ---
        st.markdown("---")
        st.subheader("📥 Descargar Reporte")

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
                df_detalle.to_excel(writer, sheet_name="Detalle Contactos", index=False)
                resumen_df.to_excel(writer, sheet_name="Resumen", index=False)
                pd.DataFrame([{
                    "Total Leads": len(leads),
                    "Con Email": len(con_email),
                    "Con Tel Válido": len(con_tel),
                    "Sin Datos": len(sin_datos),
                    "Contactados Correo": len(enviados_correo),
                    "Contactados WA": len(enviados_wa),
                    "Pendientes": len(no_contactados),
                }]).to_excel(writer, sheet_name="Panel General", index=False)
            st.download_button(
                "📥 Descargar Excel completo",
                buf_xlsx.getvalue(),
                file_name=f"analitica_merida_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel_full",
            )
        with col_dl2:
            csv_detalle = df_detalle.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Descargar CSV", csv_detalle, file_name=f"contactos_merida_{today_str}.csv", mime="text/csv", key="dl_csv_full")

        st.markdown("---")
        st.subheader("📥 Descargar por Día")

        all_dates = set()
        for s in send_log:
            if s.get("fecha"):
                all_dates.add(s["fecha"][:10])
        for s in wa_log:
            if s.get("fecha"):
                all_dates.add(s["fecha"][:10])
        for l in leads:
            if l.get("fecha_creacion"):
                all_dates.add(l["fecha_creacion"][:10])

        if all_dates:
            selected_day = st.selectbox("Seleccionar día", options=sorted(all_dates, reverse=True), key="day_select")
            if selected_day:
                day_email_logs = [s for s in send_log if s.get("fecha", "").startswith(selected_day)]
                day_wa_logs = [s for s in wa_log if s.get("fecha", "").startswith(selected_day)]
                day_emails_ok = [s for s in day_email_logs if s.get("exitoso")]
                day_wa_ok = [s for s in day_wa_logs if s.get("exitoso")]

                day_names_map = {
                    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
                    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
                }
                from datetime import datetime as dt
                day_date = dt.strptime(selected_day, "%Y-%m-%d")
                day_name_es = day_names_map.get(day_date.strftime("%A"), day_date.strftime("%A"))
                sheet_label = f"{day_name_es} {day_date.day} {day_date.strftime('%b')}"

                buf_day = io.BytesIO()
                with pd.ExcelWriter(buf_day, engine="openpyxl") as writer:
                    if day_emails_ok:
                        day_df = pd.DataFrame(day_emails_ok)
                        day_cols = [c for c in ["nombre", "email", "fecha", "template"] if c in day_df.columns]
                        day_df[day_cols].to_excel(writer, sheet_name="Correos Enviados", index=False)
                    if day_wa_ok:
                        wdf = pd.DataFrame(day_wa_ok)
                        w_cols = [c for c in ["nombre", "telefono", "fecha"] if c in wdf.columns]
                        wdf[w_cols].to_excel(writer, sheet_name="WhatsApp Enviados", index=False)

                    summary_data = []
                    for l in leads:
                        email = l.get("email", "").strip()
                        tel = l.get("telefono", "").strip()
                        nombre = l.get("nombre", "")
                        rubro = l.get("rubro", "")
                        municipio = l.get("municipio", "")

                        fue_email = any(s.get("exitoso") and s.get("email", "").lower() == email.lower() for s in day_emails_ok) if email else False
                        tel_digits = re.sub(r"[^\d]", "", tel) if tel else ""
                        fue_wa = any(s.get("exitoso") and re.sub(r"[^\d]", "", s.get("telefono", "")) == tel_digits for s in day_wa_ok) if tel_digits else False

                        if fue_email or fue_wa:
                            summary_data.append({
                                "Nombre": nombre,
                                "Rubro": rubro,
                                "Municipio": municipio,
                                "Email": email,
                                "Telefono": tel,
                                "Canal": "Correo + WA" if fue_email and fue_wa else ("Correo" if fue_email else "WhatsApp"),
                            })
                    if summary_data:
                        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Resumen del Dia", index=False)

                    pd.DataFrame([{
                        "Fecha": selected_day,
                        "Dia": sheet_label,
                        "Correos Enviados": len(day_emails_ok),
                        "WhatsApp Enviados": len(day_wa_ok),
                        "Total Contactados": len(day_emails_ok) + len(day_wa_ok),
                    }]).to_excel(writer, sheet_name="Estadisticas", index=False)

                st.download_button(
                    f"📥 Descargar reporte del {sheet_label}",
                    buf_day.getvalue(),
                    file_name=f"reporte_merida_{selected_day}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_day",
                )
                d1, d2, d3 = st.columns(3)
                d1.metric("📧 Correos enviados", len(day_emails_ok))
                d2.metric("💬 WA enviados", len(day_wa_ok))
                d3.metric("📊 Total contactados", len(day_emails_ok) + len(day_wa_ok))
        else:
            st.info("Aún no hay envíos registrados.")

# =============================================================================
# TAB 5: CONFIGURACIÓN
# =============================================================================

with tab_config:
    st.header("⚙️ Configuración — Mérida, Venezuela")

    config = load_config()

    # --- SMTP ---
    st.subheader("📧 Configuración SMTP (Gmail)")
    with st.expander("Configuración SMTP", expanded=True):
        st.info("**IMPORTANTE:** Gmail NO acepta tu contraseña normal. Necesitas una **Contraseña de Aplicación**.\n\n"
                "Pasos:\n"
                "1. Ve a https://myaccount.google.com/security\n"
                "2. Activa **Verificación en 2 pasos** (si no la tienes)\n"
                "3. Ve a https://myaccount.google.com/apppasswords\n"
                "4. Selecciona 'Correo' → 'Otra (nombre personalizado)' → escribe 'Prospector'\n"
                "5. Copia la contraseña de 16 caracteres (ej: `abcdefghijklmnop`)\n"
                "6. Pégala abajo en 'Contraseña'")
        cfg_col1, cfg_col2 = st.columns(2)
        with cfg_col1:
            new_smtp_server = st.text_input("Servidor", value=config.get("smtp_server", "smtp.gmail.com"), key="cfg_server")
            new_smtp_port = st.number_input("Puerto", value=int(config.get("smtp_port", 587)), key="cfg_port")
        with cfg_col2:
            new_smtp_email = st.text_input("Email remitente", value=config.get("smtp_email", "pskloud.fpabon@gmail.com"), key="cfg_email")
            new_smtp_pass = st.text_input("Contraseña de aplicación (16 caracteres)", value=config.get("smtp_password", ""), type="password", key="cfg_pass")

        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("💾 Guardar configuración SMTP"):
                config["smtp_server"] = new_smtp_server
                config["smtp_port"] = new_smtp_port
                config["smtp_email"] = new_smtp_email
                config["smtp_password"] = new_smtp_pass
                save_config(config)
                st.success("Configuración SMTP guardada")
        with sc2:
            if st.button("🔌 Probar conexión SMTP"):
                with st.spinner("Probando conexión..."):
                    ok, msg = test_smtp_connection(
                        new_smtp_server, int(new_smtp_port), new_smtp_email, new_smtp_pass,
                    )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    st.markdown("---")

    # --- API KEYS ---
    st.subheader("🔑 API Keys")
    with st.expander("API Keys (opcional)"):
        hunter_key = st.text_input(
            "Hunter.io API Key",
            value=config.get("hunter_api_key", ""),
            type="password",
            key="cfg_hunter",
        )
        if st.button("Guardar API Keys"):
            config["hunter_api_key"] = hunter_key
            save_config(config)
            st.success("API Keys guardadas")

    st.markdown("---")

    # --- WHATSAPP EVOLUTION API ---
    st.subheader("💬 WhatsApp Evolution API")
    with st.expander("Configuración WhatsApp", expanded=True):
        cfg_wa_url = st.text_input("URL Evolution API", value=config.get("evo_api_url", EVO_API_URL), key="cfg_wa_url")
        cfg_wa_key = st.text_input("API Key", value=config.get("evo_api_key", EVO_API_KEY), type="password", key="cfg_wa_key")
        cfg_wa_instance = st.text_input("Nombre de instancia", value=config.get("evo_instance", EVO_INSTANCE), key="cfg_wa_instance")

        wac1, wac2 = st.columns(2)
        with wac1:
            if st.button("💾 Guardar config WA (Global)"):
                config["evo_api_url"] = cfg_wa_url
                config["evo_api_key"] = cfg_wa_key
                config["evo_instance"] = cfg_wa_instance
                save_config(config)
                st.success("Configuración WA guardada")
        with wac2:
            if st.button("🔌 Probar conexión WA (Global)"):
                with st.spinner("Probando conexión..."):
                    ok, msg = test_wa_connection(cfg_wa_url, cfg_wa_key, cfg_wa_instance)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("**QR para escanear:**")
        qr_url = f"{cfg_wa_url}/instance/connect/{cfg_wa_instance}"
        st.code(f"Abre en tu navegador para escanear QR:\n{qr_url}", language=None)

    st.markdown("---")

    # --- LÍMITES DIARIOS ---
    st.subheader("🔄 Límites diarios")
    with st.expander("Control de envíos", expanded=True):
        lcol1, lcol2, lcol3 = st.columns(3)
        with lcol1:
            daily_limit = st.number_input(
                "Límite diario de emails",
                min_value=10,
                max_value=500,
                value=config.get("daily_send_limit", 50),
                key="cfg_daily_limit",
            )
        with lcol2:
            wa_daily_limit = st.number_input(
                "Límite diario de WhatsApp",
                min_value=5,
                max_value=200,
                value=config.get("wa_daily_limit", 30),
                key="cfg_wa_daily_limit",
            )
        with lcol3:
            delay_seconds = st.number_input(
                "Delay entre emails (segundos)",
                min_value=5,
                max_value=120,
                value=config.get("delay_seconds", 15),
                step=5,
                key="cfg_delay",
            )
        if st.button("Guardar límites"):
            config["daily_send_limit"] = int(daily_limit)
            config["wa_daily_limit"] = int(wa_daily_limit)
            config["delay_seconds"] = int(delay_seconds)
            save_config(config)
            st.success("Límites actualizados")

    st.markdown("---")

    # --- IMPORTAR LEADS ---
    st.subheader("📥 Importar Leads")
    with st.expander("Importar leads desde CSV, Excel o JSON", expanded=False):
        st.markdown("""
        **Formatos soportados:**
        - **CSV:** Archivos `.csv` con encoding UTF-8, Latin-1 o CP1252
        - **Excel:** Archivos `.xlsx` o `.xls`
        - **JSON:** Archivos `.json` con lista de leads

        **Columnas reconocidas** (español o inglés):
        `nombre`, `rubro`, `municipio`, `direccion`, `telefono`, `email`, `website`, `notas`
        """)

        tcol1, tcol2 = st.columns(2)
        with tcol1:
            csv_ejemplo = generar_plantilla_csv_ejemplo()
            st.download_button(
                "📥 Descargar plantilla CSV de ejemplo",
                csv_ejemplo.encode("utf-8"),
                file_name="plantilla_leads_ejemplo.csv",
                mime="text/csv",
            )
        with tcol2:
            xlsx_ejemplo = generar_plantilla_excel_ejemplo()
            st.download_button(
                "📥 Descargar plantilla Excel de ejemplo",
                xlsx_ejemplo,
                file_name="plantilla_leads_ejemplo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.markdown("---")

        uploaded_file = st.file_uploader(
            "Seleccionar archivo de leads",
            type=["csv", "xlsx", "xls", "json"],
            key="import_file",
        )

        if uploaded_file:
            st.info(f"📄 Archivo: {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")

            if st.button("📥 Importar leads", key="do_import"):
                try:
                    existing = load_leads()
                    leads_actualizados, num_nuevos, info = importar_leads(
                        uploaded_file, uploaded_file.name, existing
                    )
                    save_leads(leads_actualizados)

                    st.success(f"✅ Importados **{num_nuevos}** leads nuevos")

                    with st.expander("Detalles de la importación"):
                        st.write(f"**Total en archivo:** {info['total_archivo']}")
                        st.write(f"**Nuevos agregados:** {info['nuevos_agregados']}")
                        st.write(f"**Duplicados omitidos:** {info['duplicados_omitidos']}")
                        st.write(f"**Columnas originales:** {', '.join(info['columnas_originales'])}")
                        if info['mapeo_columnas']:
                            st.write("**Mapeo de columnas aplicado:**")
                            for orig, mapped in info['mapeo_columnas'].items():
                                st.write(f"  - `{orig}` → `{mapped}`")

                    st.rerun()
                except Exception as e:
                    st.error(f"Error al importar: {str(e)}")

    st.markdown("---")

    # --- SINCRONIZAR RESULTADOS DEL SCRAPPER ---
    st.subheader("🔄 Sincronizar Scraping")
    completos_path = os.path.join(BASE_DIR, "leads_completos.json")
    parciales_path = os.path.join(BASE_DIR, "leads_parciales.json")

    archivos = []
    if os.path.exists(completos_path):
        with open(completos_path, encoding="utf-8") as f:
            archivos.append(("leads_completos.json", json.load(f)))
    if os.path.exists(parciales_path):
        with open(parciales_path, encoding="utf-8") as f:
            archivos.append(("leads_parciales.json", json.load(f)))

    if archivos:
        for fname, data in archivos:
            st.write(f"📄 **{fname}**: {len(data)} leads")
        if st.button("🔄 Sincronizar con leads.json", key="sync_scraper"):
            leads = load_leads()
            existing_names = {l.get("nombre", "").lower().strip(): l for l in leads}
            nuevos = 0
            enriquecidos = 0
            for fname, scraped in archivos:
                for sl in scraped:
                    sname = sl.get("nombre", "").lower().strip()
                    if sname in existing_names:
                        existing = existing_names[sname]
                        if sl.get("email") and not existing.get("email"):
                            existing["email"] = sl["email"]
                            enriquecidos += 1
                        if sl.get("telefono") and not existing.get("telefono"):
                            existing["telefono"] = sl["telefono"]
                            enriquecidos += 1
                        if sl.get("website") and not existing.get("website"):
                            existing["website"] = sl["website"]
                    else:
                        leads.append(sl)
                        existing_names[sname] = sl
                        nuevos += 1
            save_leads(leads)
            st.success(f"✅ Enriquecidos: **{enriquecidos}** datos nuevos, **{nuevos}** leads nuevos")
            st.rerun()
    else:
        st.info("No se encontraron archivos de scraping (leads_completos.json / leads_parciales.json). Ejecuta el scraper primero.")

    st.markdown("---")

    # --- PLANTILLAS DE EMAIL ---
    st.subheader("📋 Plantillas de Email")
    with st.expander("Gestionar plantillas"):
        templates = load_email_templates()
        for i, tpl in enumerate(templates):
            st.markdown(f"**{tpl.get('nombre', f'Plantilla {i+1}')}**")
            st.text(f"Asunto: {tpl.get('asunto', 'N/A')[:80]}")
            if tpl.get('evento'):
                st.caption(f"📅 Evento: {tpl['evento']}")
            st.caption(f"Cuerpo: {re.sub('<[^<]+?>', '', tpl.get('cuerpo', ''))[:120]}...")
            st.markdown("---")

        new_tpl_name = st.text_input("Nombre nueva plantilla", key="new_tpl_name")
        new_tpl_subject = st.text_input("Asunto", key="new_tpl_subject")
        new_tpl_body = st.text_area("Cuerpo (HTML)", key="new_tpl_body", height=150)
        if st.button("➕ Crear plantilla"):
            if new_tpl_name and new_tpl_subject:
                templates.append({
                    "nombre": new_tpl_name,
                    "asunto": new_tpl_subject,
                    "cuerpo": new_tpl_body,
                })
                save_email_templates(templates)
                st.success(f"Plantilla '{new_tpl_name}' creada")
                st.rerun()
            else:
                st.warning("Nombre y asunto son requeridos")

    st.markdown("---")

    # --- GESTIÓN DE DATOS ---
    st.subheader("🗄️ Gestión de Datos")

    leads = load_leads()

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.metric("Total leads", len(leads))
    with dc2:
        st.metric("Con teléfono", sum(1 for l in leads if l.get("telefono")))
    with dc3:
        st.metric("Con email", sum(1 for l in leads if l.get("email")))

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        if st.button("📥 Exportar todos los leads (JSON)"):
            json_data = json.dumps(leads, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button(
                "Descargar JSON",
                json_data,
                file_name=f"leads_merida_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
            )
    with mc2:
        if st.button("📥 Exportar historial de envíos"):
            log = load_send_log()
            if log:
                log_df = pd.DataFrame(log)
                log_csv = log_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Descargar CSV",
                    log_csv,
                    file_name=f"send_log_merida_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("No hay historial de envíos")
    with mc3:
        if st.button("🗑️ Limpiar todos los leads", type="secondary"):
            st.session_state["confirm_clear"] = True

    if st.session_state.get("confirm_clear"):
        st.warning("⚠️ ¿Estás seguro? Esta acción eliminará todos los leads permanentemente.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("✅ Sí, eliminar todo", type="primary"):
                save_leads([])
                st.session_state["confirm_clear"] = False
                st.success("Todos los leads han sido eliminados")
                st.rerun()
        with cc2:
            if st.button("❌ Cancelar"):
                st.session_state["confirm_clear"] = False
                st.rerun()

    st.markdown("---")

    # --- DICCIONARIOS DE BÚSQUEDA ---
    st.subheader("📚 Diccionarios de Búsqueda")
    with st.expander("Ver matriz de búsqueda B2B", expanded=False):
        st.markdown("**Ubicaciones geográficas:**")
        for mun, query in UBICACIONES_PRECISAS_MERIDA.items():
            st.markdown(f"  - **{mun}** → {query}")

        st.markdown("---")
        st.markdown(f"**🎯 Matriz Target Software:** {len(CATEGORIAS_COMERCIALES_MERIDA)} categorías en {len(MATRIZ_TARGET_SOFTWARE)} segmentos")
        
        for segmento, categorias in MATRIZ_TARGET_SOFTWARE.items():
            with st.expander(f"📊 {segmento} ({len(categorias)} términos)"):
                st.caption(", ".join(categorias))

    st.markdown("---")

    # --- INFORMACIÓN DEL SISTEMA ---
    st.subheader("ℹ️ Información del Sistema")
    with st.expander("Detalles técnicos"):
        st.markdown(f"""
        - **Aplicación:** PSKloud Prospector v1.0 — Mérida
        - **Ubicación:** `{BASE_DIR}`
        - **Archivo de leads:** `{DATA_FILE}`
        - **Configuración:** `{CONFIG_FILE}`
        - **Log de envíos:** `{SEND_LOG_FILE}`
        - **Log WA:** `{WA_SEND_LOG_FILE}`
        - **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
        - **Módulo local_search:** {local_search.__file__ if hasattr(local_search, '__file__') else 'N/A'}
        - **Módulo phone_utils:** OK
        - **Módulo import_utils:** OK
        - **Módulo whatsapp_export:** OK
        - **Módulo templates_default:** OK
        """)

# =============================================================================
# FOOTER
# =============================================================================

st.markdown("---")
st.markdown(
    """
    <div style="text-align:center; padding:1rem; color:#64748b; font-size:0.8rem;">
        PSKloud Prospector v1.0 — Mérida, Venezuela | © 2026 PSKloud
    </div>
    """,
    unsafe_allow_html=True,
)
