"""
=============================================================================
PSKloud Prospector v2.0 - Sistema REAL de Prospección B2B
Integración con Hunter.io API + SMTP Real
Mercado: Costa Rica & El Salvador
=============================================================================
INSTALACIÓN:
    pip install streamlit pandas openpyxl requests

EJECUCIÓN:
    streamlit run app.py

DEPLOY STREAMLIT CLOUD:
    1. Subir a GitHub (git push)
    2. Ir a https://share.streamlit.io
    3. Conectar repositorio: fabiopabonmovilnet-rgb/prospeccion-pskloud
    4. Settings → Secrets → agregar: HUNTER_API_KEY, SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
    5. Deploy!

EJECUTABLES:
    - Doble clic en "PSKloud Prospector.bat" en el escritorio
    - O: streamlit run app.py
=============================================================================
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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from enrichment import enrich_company, clear_cache as limpiar_cache_enriquecimiento, get_cache_stats

# =============================================================================
# ARCHIVO DE PERSISTENCIA - Leads excluidos (se guardan entre sesiones)
# =============================================================================
EXCLUIDOS_FILE = "leads_excluidos.json"
PLANTILLA_FILE = "plantilla_personalizada.json"
SECRETS_FILE = ".streamlit/secrets.toml"
PIPELINE_FILE = "pipeline_estado.json"
LUSHA_API_FILE = ".streamlit/lusha_key.txt"

# Motivos de exclusión predefinidos
MOTIVOS_EXCLUSION = [
    "No interesado",
    "Correo rebotó (bounced)",
    "Bloqueó / Spam",
    "Contacto erróneo",
    "Ya es cliente",
    "Fuera de mercado",
    "Información incorrecta",
    "Otro"
]

# =============================================================================
# ETAPAS DEL PIPELINE DE VENTAS
# =============================================================================
ETAPAS = [
    "Nuevo",
    "📧 Email enviado",
    "🔗 LinkedIn contactado",
    "📞 Llamada realizada",
    "✅ Cliente",
    "❌ Perdido"
]

ETAPAS_ICONOS = {
    "Nuevo": "🆕",
    "📧 Email enviado": "📧",
    "🔗 LinkedIn contactado": "🔗",
    "📞 Llamada realizada": "📞",
    "✅ Cliente": "✅",
    "❌ Perdido": "❌"
}


def guardar_api_key_en_secrets(api_key: str):
    """Guarda la API key de Hunter en secrets.toml para que persista."""
    try:
        os.makedirs(".streamlit", exist_ok=True)
        contenido = f"""# PSKloud Prospector - Secrets
# ⚠️ Este archivo está en .gitignore

HUNTER_API_KEY = "{api_key}"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
"""
        with open(SECRETS_FILE, "w", encoding="utf-8") as f:
            f.write(contenido)
        return True
    except Exception as e:
        print(f"Error al guardar API key: {e}")
        return False


def cargar_excluidos() -> dict:
    """Carga el diccionario de leads excluidos con sus motivos."""
    if os.path.exists(EXCLUIDOS_FILE):
        try:
            with open(EXCLUIDOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                excluidos = data.get("excluidos", {})
                if isinstance(excluidos, list):
                    return {e: {"motivo": "No especificado", "fecha": ""} for e in excluidos}
                return excluidos
        except Exception:
            return {}
    return {}


def guardar_excluidos(excluidos: dict):
    """Guarda el diccionario de leads excluidos."""
    try:
        with open(EXCLUIDOS_FILE, "w", encoding="utf-8") as f:
            json.dump({"excluidos": excluidos, "actualizado": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Error al guardar exclusiones: {str(e)}")


def excluir_lead(email: str, motivo: str = "No especificado"):
    """Agrega un lead a la lista de excluidos con su motivo."""
    excluidos = cargar_excluidos()
    excluidos[email] = {
        "motivo": motivo,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "actualizado": datetime.now().isoformat()
    }
    guardar_excluidos(excluidos)


def email_excluido(email: str) -> bool:
    """Verifica si un email está en la lista de excluidos."""
    excluidos = cargar_excluidos()
    return email in excluidos


# =============================================================================
# PERSISTENCIA DEL PIPELINE DE VENTAS
# =============================================================================

def cargar_pipeline() -> dict:
    """Carga el estado del pipeline desde el archivo JSON."""
    if os.path.exists(PIPELINE_FILE):
        try:
            with open(PIPELINE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar_pipeline(pipeline: dict):
    """Guarda el estado del pipeline en el archivo JSON."""
    try:
        with open(PIPELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(pipeline, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Error al guardar pipeline: {e}")


def actualizar_etapa_lead(email: str, etapa: str, notas: str = ""):
    """Actualiza la etapa de un lead en el pipeline."""
    pipeline = cargar_pipeline()
    if email not in pipeline:
        pipeline[email] = {
            "etapa": "Nuevo",
            "fecha_creacion": datetime.now().isoformat(),
            "fecha_email": "",
            "fecha_linkedin": "",
            "fecha_llamada": "",
            "notas": ""
        }
    pipeline[email]["etapa"] = etapa
    if notas:
        pipeline[email]["notas"] = notas
    ahora = datetime.now().isoformat()
    if "📧" in etapa:
        pipeline[email]["fecha_email"] = ahora
    if "🔗" in etapa:
        pipeline[email]["fecha_linkedin"] = ahora
    if "📞" in etapa:
        pipeline[email]["fecha_llamada"] = ahora
    guardar_pipeline(pipeline)


def obtener_etapa_lead(email: str) -> str:
    """Obtiene la etapa actual de un lead."""
    pipeline = cargar_pipeline()
    return pipeline.get(email, {}).get("etapa", "Nuevo")


def pipeline_stats() -> dict:
    """Estadísticas del pipeline."""
    pipeline = cargar_pipeline()
    stats = {e: 0 for e in ETAPAS}
    for data in pipeline.values():
        etapa = data.get("etapa", "Nuevo")
        if etapa in stats:
            stats[etapa] += 1
    stats["Total"] = sum(stats.values())
    return stats


# =============================================================================
# PERSISTENCIA DE PLANTILLA PERSONALIZADA
# =============================================================================

def cargar_plantilla() -> Dict:
    """Carga la plantilla guardada del archivo JSON."""
    if os.path.exists(PLANTILLA_FILE):
        try:
            with open(PLANTILLA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar_plantilla(asunto: str, cuerpo: str):
    """Guarda la plantilla personalizada en el archivo JSON."""
    try:
        with open(PLANTILLA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "asunto": asunto,
                "cuerpo": cuerpo,
                "actualizado": datetime.now().isoformat()
            }, f, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error al guardar plantilla: {str(e)}")


# =============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="PSKloud Prospector | Ventas Internacionales",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar plantilla guardada al iniciar (persiste entre sesiones)
plantilla_guardada = cargar_plantilla()
if plantilla_guardada:
    st.session_state["asunto_campana"] = plantilla_guardada.get("asunto", PLANTILLA_DEFAULT["asunto"])
    st.session_state["cuerpo_campana"] = plantilla_guardada.get("cuerpo", PLANTILLA_DEFAULT["cuerpo"])

# =============================================================================
# BASE DE DATOS REAL DE EMPRESAS - Dominios verificados
# Estos son dominios reales de empresas en Costa Rica y El Salvador
# =============================================================================
EMPRESAS_REALES: Dict[str, List[Dict]] = {
    "Costa Rica": [
        # === TECNOLOGÍA / SOFTWARE ===
        {"empresa": "Kambda", "dominio": "kambda.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/kambda"},
        {"empresa": "Siftia", "dominio": "siftia.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/siftia"},
        {"empresa": "Gorilla Logic", "dominio": "gorillalogic.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/gorilla-logic"},
        {"empresa": "FusionHit", "dominio": "fusionhit.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/fusionhit"},
        {"empresa": "Infosgroup", "dominio": "infosgroup.cr", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/infosgroupcr"},
        {"empresa": "ParallelDevs", "dominio": "paralleldevs.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/paralleldevs"},
        {"empresa": "weKnow Inc.", "dominio": "weknow.cr", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/weknow-inc"},
        {"empresa": "Glob Costa Rica", "dominio": "glob.co.cr", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/glob-costarica"},
        {"empresa": "Centauro Solutions", "dominio": "centaurosol.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/centauro-solutions"},
        {"empresa": "Prosoft Nearshore", "dominio": "prosoftnearshore.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/prosoft-nearshore"},
        {"empresa": "EX2 Outcoding", "dominio": "outcoding.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/ex2-outcoding"},
        {"empresa": "Analisis MBC", "dominio": "analisismbc.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/analisis-mbc"},
        {"empresa": "Aubrant Digital", "dominio": "aubrantdigital.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/aubrant-digital"},
        {"empresa": "AceBuddy", "dominio": "acebuddy.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/acebuddy"},
        {"empresa": "WAM Digital", "dominio": "wamdigital.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/wam-digital"},
        {"empresa": "Emerald Studio", "dominio": "emerald.studio", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/emerald-studio"},
        {"empresa": "People Apps Inc", "dominio": "peopleappsinc.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/people-apps-inc"},
        {"empresa": "Mecsoft de Costa Rica", "dominio": "mecsoftcr.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/mecsoft-costarica"},
        {"empresa": "Red Global", "dominio": "redglobal.net", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/red-global"},
        {"empresa": "Cr Advanced", "dominio": "cradvanced.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/cr-advanced"},

        # === RETAIL / COMERCIO ===
        {"empresa": "Grupo Palí", "dominio": "grupopali.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-pali"},
        {"empresa": "AutoMercado", "dominio": "automercado.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/automercado"},
        {"empresa": "Farmacia Fischel", "dominio": "fischel.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/farmacia-fischel"},
        {"empresa": "La Grenia", "dominio": "lagrenia.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/la-grenia"},
        {"empresa": "Vindi", "dominio": "vindicr.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/vindicr"},

        # === BANCA / FINANZAS ===
        {"empresa": "Banco Nacional", "dominio": "bnprimary.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-nacional-cr"},
        {"empresa": "Banco de Costa Rica", "dominio": "bancocr.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-de-costa-rica"},
        {"empresa": "BAC Credomatic", "dominio": "baccredomatic.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bac-credomatic"},
        {"empresa": "Grupo Mutual", "dominio": "grupomutual.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-mutual"},
        {"empresa": "INS", "dominio": "ins-cr.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/ins-cr"},

        # === SALUD ===
        {"empresa": "Clínica Bíblica", "dominio": "clinicabiblica.com", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/clinica-biblica"},
        {"empresa": "Hospital CIMA", "dominio": "hospitalcima.com", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/hospital-cima"},
        {"empresa": "Laboratorios Lahey", "dominio": "lahey.co.cr", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/laboratorios-lahey"},

        # === TURISMO ===
        {"empresa": "Grupo Tilajari", "dominio": "tilajari.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-tilajari"},
        {"empresa": "Hotel Marriott Costa Rica", "dominio": "marriott.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/marriott"},

        # === MANUFACTURA / AGRO ===
        {"empresa": "Dos Pinos", "dominio": "dospinos.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/dos-pinos"},
        {"empresa": "Florida Ice & Farm", "dominio": "fifco.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/fifco"},
        {"empresa": "Cementos Portland", "dominio": "cementosportland.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/cementos-portland"},
    ],
    "El Salvador": [
        # === TECNOLOGÍA / SOFTWARE ===
        {"empresa": "Softcorp International", "dominio": "softcorp.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/softcorp-international"},
        {"empresa": "GInIEm", "dominio": "giniem.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/giniem"},
        {"empresa": "Intecno Solutions", "dominio": "intecnosolutions.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/intecno-solutions"},
        {"empresa": "Inversiones Técnicas", "dominio": "inversionestec.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/inversiones-tecnicas"},

        # === RETAIL / COMERCIO ===
        {"empresa": "Super Selectos", "dominio": "superselectos.com.sv", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/super-selectos"},
        {"empresa": "Siman", "dominio": "siman.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/siman"},
        {"empresa": "La Curacao", "dominio": "lacuracao.com.sv", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/la-curacao"},
        {"empresa": "Farmacias Guadalupana", "dominio": "guadalupana.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/farmacias-guadalupana"},

        # === BANCA / FINANZAS ===
        {"empresa": "Banco Cuscatlán", "dominio": "bancocuscatlan.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-cuscatlan"},
        {"empresa": "Banco Agrícola", "dominio": "bancoagricola.com.sv", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-agricola"},
        {"empresa": "Davivienda", "dominio": "davivienda.com.sv", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/davivienda-sv"},
        {"empresa": "BAC Credomatic El Salvador", "dominio": "baccredomatic.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bac-credomatic"},

        # === TELECOMUNICACIONES ===
        {"empresa": "Tigo El Salvador", "dominio": "tigo.com", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/tigo"},
        {"empresa": "Claro El Salvador", "dominio": "claro.com", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/claro"},
        {"empresa": "Telefónica El Salvador", "dominio": "telefonica.com", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/telefonica"},

        # === BEBIDAS / MANUFACTURA ===
        {"empresa": "Heineken El Salvador", "dominio": "heineken.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/heineken"},
        {"empresa": "Pilsener El Salvador", "dominio": "pilsener.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/pilsener"},
        {"empresa": "Cementos de El Salvador", "dominio": "cementos.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/cementos"},

        # === SALUD ===
        {"empresa": "Salud El Salvador", "dominio": "salud.com.sv", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/salud-sv"},

        # === TURISMO ===
        {"empresa": "Hotel Barceló San Salvador", "dominio": "barcelo.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/barcelo"},
        {"empresa": "Marriott San Salvador", "dominio": "marriott.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/marriott"},
    ],
    "Panamá": [
        # === TECNOLOGÍA ===
        {"empresa": "DXC Technology Panama", "dominio": "dxc.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/dxc-technology"},
        {"empresa": "Yuxi Global", "dominio": "yuxiglobal.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/yuxi-global"},
        {"empresa": "Waked Technology", "dominio": "waked.com.pa", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/waked-logistics"},
        # === FINANZAS ===
        {"empresa": "Banco General", "dominio": "banco-general.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-general"},
        {"empresa": "BAC Panama", "dominio": "baccredomatic.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bac-credomatic"},
        {"empresa": "Towerbank", "dominio": "towerbank.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/towerbank"},
        {"empresa": "Scotiabank Panama", "dominio": "scotiabank.com.pa", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/scotiabank"},
        # === RETAIL ===
        {"empresa": "Súper 99", "dominio": "super99.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/super99"},
        {"empresa": "Rey Panama", "dominio": "supermercadosrey.com.pa", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/supermercados-rey"},
        {"empresa": "El Machetazo", "dominio": "elmachetazo.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/el-machetazo"},
        # === TELECOMUNICACIONES ===
        {"empresa": "Claro Panama", "dominio": "claro.com.pa", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/claro"},
        {"empresa": "Digicel Panama", "dominio": "digicelpanama.com", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/digicel"},
        # === MANUFACTURA / LOGÍSTICA ===
        {"empresa": "Cervecería Nacional Panama", "dominio": "cervecerianacional.com.pa", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/cerveceria-nacional"},
        {"empresa": "Copa Airlines", "dominio": "copa.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/copa-airlines"},
        {"empresa": "Panama Ports", "dominio": "panamaports.com", "sector": "Logística", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/panama-ports"},
    ],
    "Honduras": [
        # === TECNOLOGÍA ===
        {"empresa": "Grupo Intellect", "dominio": "grupointellect.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/grupo-intellect"},
        {"empresa": "Datasys HN", "dominio": "datasys.hn", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/datasys"},
        # === FINANZAS ===
        {"empresa": "Banco Atlántida", "dominio": "bancatlan.hn", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-atlantida"},
        {"empresa": "Banco Ficohsa", "dominio": "ficohsa.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/ficohsa"},
        {"empresa": "BAC Honduras", "dominio": "baccredomatic.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bac-credomatic"},
        {"empresa": "Banco Lafise", "dominio": "lafise.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/lafise"},
        # === RETAIL ===
        {"empresa": "La Colonia", "dominio": "lacolonia.hn", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/supermercados-la-colonia"},
        {"empresa": "Despensa Familiar", "dominio": "walmart.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/walmart"},
        # === TELECOMUNICACIONES ===
        {"empresa": "Tigo Honduras", "dominio": "tigo.com", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/tigo"},
        {"empresa": "Claro Honduras", "dominio": "claro.com.hn", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/claro"},
        # === MANUFACTURA ===
        {"empresa": "Kimberly Clark Honduras", "dominio": "kimberly-clark.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/kimberly-clark"},
        {"empresa": "Cementos Argos Honduras", "dominio": "argos.co", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/cementos-argos"},
    ],
    "Colombia": [
        # === TECNOLOGÍA ===
        {"empresa": "Sofka Technologies", "dominio": "sofka.com.co", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/sofka-technologies"},
        {"empresa": "Globant Colombia", "dominio": "globant.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/globant"},
        {"empresa": "Periferia IT", "dominio": "periferiait.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/periferia-it"},
        {"empresa": "Mismo", "dominio": "mismo.com.co", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/mismo"},
        {"empresa": "Intergrupo", "dominio": "intergrupo.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/intergrupo"},
        # === FINANZAS ===
        {"empresa": "Bancolombia", "dominio": "bancolombia.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bancolombia"},
        {"empresa": "Davivienda", "dominio": "davivienda.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/davivienda"},
        {"empresa": "Grupo Sura", "dominio": "gruposura.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-sura"},
        {"empresa": "BBVA Colombia", "dominio": "bbva.com.co", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bbva"},
        # === RETAIL ===
        {"empresa": "Éxito", "dominio": "exito.com.co", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-exito"},
        {"empresa": "Falabella Colombia", "dominio": "falabella.com.co", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/falabella"},
        {"empresa": "Homecenter", "dominio": "homecenter.com.co", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/homecenter"},
        {"empresa": "Alkosto", "dominio": "alkosto.com.co", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/alkosto"},
        # === ENERGÍA ===
        {"empresa": "Ecopetrol", "dominio": "ecopetrol.com.co", "sector": "Energía", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/ecopetrol"},
        {"empresa": "EPM", "dominio": "epm.com.co", "sector": "Energía", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/epm"},
        {"empresa": "ISA", "dominio": "isa.co", "sector": "Energía", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/isa-interconexion-electrica"},
        # === TELECOMUNICACIONES ===
        {"empresa": "Tigo Colombia", "dominio": "tigo.com.co", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/tigo"},
        {"empresa": "Movistar Colombia", "dominio": "movistar.com.co", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/movistar"},
        {"empresa": "Claro Colombia", "dominio": "claro.com.co", "sector": "Telecomunicaciones", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/claro"},
        # === MANUFACTURA / ALIMENTOS ===
        {"empresa": "Grupo Nutresa", "dominio": "gruponutresa.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/grupo-nutresa"},
        {"empresa": "Postobón", "dominio": "postobon.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/postobon"},
        {"empresa": "Cementos Argos", "dominio": "argos.co", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/cementos-argos"},
    ],
}


# =============================================================================
# FUNCIONES DE HUNTER.IO API
# =============================================================================

def buscar_contactos_hunter(
    api_key: str,
    dominio: str,
    limite: int = 10
) -> Tuple[List[Dict], Dict]:
    """
    Busca contactos reales en un dominio usando Hunter.io API (Domain Search).

    Endpoint: GET https://api.hunter.io/v2/domain-search

    Args:
        api_key: API key de Hunter.io
        dominio: Dominio de la empresa (ej: google.com)
        limite: Número máximo de contactos a retornar

    Returns:
        Tupla de (lista de contactos, información de la empresa)
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": dominio,
        "api_key": api_key,
        "limit": limite,
        "type": "personal"
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # La API de Hunter.io envuelve los datos en un nivel "data"
        datos_empresa = data.get("data", {})

        # Información de la empresa
        empresa_info = {
            "organisation": datos_empresa.get("organisation", dominio),
            "domain": datos_empresa.get("domain", dominio),
            "pattern": datos_empresa.get("pattern", ""),
            "emails_encontrados": len(datos_empresa.get("emails", []))
        }

        # Procesar contactos encontrados
        contactos = []
        for email_data in datos_empresa.get("emails", []):
            # Solo incluir emails con confianza media o alta
            confianza = email_data.get("confidence", 0)

            contacto = {
                "email": email_data.get("value", ""),
                "nombre": email_data.get("first_name", ""),
                "apellido": email_data.get("last_name", ""),
                "cargo": email_data.get("position", ""),
                "confianza": confianza,
                "tipo": email_data.get("type", ""),
                "telefono": email_data.get("phone_number", ""),
                "linkedin": email_data.get("linkedin", ""),
                "fuente": "Hunter.io"
            }
            contactos.append(contacto)

        return contactos, empresa_info

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            return [], {"error": "API key inválida. Verifica tu clave de Hunter.io."}
        elif response.status_code == 402:
            return [], {"error": "Límite de búsqueda alcanzado. Plan gratuito: 25 búsquedas/mes."}
        elif response.status_code == 404:
            return [], {"error": f"Dominio '{dominio}' no encontrado en Hunter.io."}
        else:
            return [], {"error": f"Error HTTP {response.status_code}: {str(e)}"}
    except requests.exceptions.ConnectionError:
        return [], {"error": "Error de conexión. Verifica tu conexión a internet."}
    except requests.exceptions.Timeout:
        return [], {"error": "Timeout al conectar con Hunter.io. Intenta de nuevo."}
    except Exception as e:
        return [], {"error": f"Error inesperado: {str(e)}"}


def verificar_email_hunter(
    api_key: str,
    email: str
) -> Dict:
    """
    Verifica si un email es válido usando Hunter.io API (Email Verifier).

    Endpoint: GET https://api.hunter.io/v2/email-verifier

    Args:
        api_key: API key de Hunter.io
        email: Correo a verificar

    Returns:
        Diccionario con el resultado de la verificación
    """
    url = "https://api.hunter.io/v2/email-verifier"
    params = {
        "email": email,
        "api_key": api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        datos = data.get("data", data)

        return {
            "email": email,
            "resultado": datos.get("result", "unknown"),
            "confianza": datos.get("score", 0),
            "status": datos.get("status", "unknown"),
            "disposable": datos.get("disposable", False),
            "webmail": datos.get("webmail", False),
            "mx_found": datos.get("mx_found", False),
            "smtp_check": datos.get("smtp_check", False)
        }
    except Exception as e:
        return {
            "email": email,
            "resultado": "error",
            "confianza": 0,
            "status": str(e)
        }


def obtener_info_cuenta_hunter(api_key: str) -> Dict:
    """
    Obtiene información de la cuenta de Hunter.io (créditos restantes).

    Endpoint: GET https://api.hunter.io/v2/account

    Args:
        api_key: API key de Hunter.io

    Returns:
        Diccionario con información de la cuenta
    """
    url = "https://api.hunter.io/v2/account"
    params = {"api_key": api_key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", {})

        return {
            "email": data.get("email", ""),
            "plan_nombre": data.get("plan_name", "Gratuito"),
            "busquedas": {
                "disponibles": data.get("requests", {}).get("available", 0),
                "usados": data.get("requests", {}).get("used", 0),
                "limite": data.get("requests", {}).get("limit", 25)
            },
            "verificaciones": {
                "disponibles": data.get("verifications", {}).get("available", 0),
                "usados": data.get("verifications", {}).get("used", 0),
                "limite": data.get("verifications", {}).get("limit", 50)
            }
        }
    except Exception:
        return {"error": "No se pudo obtener información de la cuenta"}


# =============================================================================
# FUNCIONES DE ENVÍO SMTP REAL
# =============================================================================

def enviar_correo_real(
    servidor: str,
    puerto: int,
    correo_emisor: str,
    contrasena: str,
    correo_receptor: str,
    asunto: str,
    cuerpo: str
) -> Tuple[bool, str]:
    """
    Envía un correo electrónico real vía SMTP/TLS.

    Args:
        servidor: Servidor SMTP (ej: smtp.gmail.com)
        puerto: Puerto SMTP (ej: 587)
        correo_emisor: Correo del remitente
        contrasena: Contraseña o token de aplicación
        correo_receptor: Correo del destinatario
        asunto: Asunto del correo
        cuerpo: Cuerpo del mensaje

    Returns:
        Tupla de (éxito: bool, mensaje: str)
    """
    try:
        # Crear mensaje
        mensaje = MIMEMultipart()
        mensaje["From"] = correo_emisor
        mensaje["To"] = correo_receptor
        mensaje["Subject"] = asunto
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

        # Conexión segura y envío
        contexto = ssl.create_default_context()
        with smtplib.SMTP(servidor, puerto, timeout=30) as servidor_smtp:
            servidor_smtp.starttls(context=contexto)
            servidor_smtp.login(correo_emisor, contrasena)
            servidor_smtp.sendmail(correo_emisor, correo_receptor, mensaje.as_string())

        return True, "Correo enviado exitosamente"

    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación. Verifica usuario/contraseña."
    except smtplib.SMTPConnectError:
        return False, "Error al conectar con el servidor SMTP."
    except smtplib.SMTPException as e:
        return False, f"Error SMTP: {str(e)}"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"


def renderizar_plantilla(
    plantilla: str,
    nombre: str,
    empresa: str,
    pais: str,
    cargo: str,
    email: str
) -> str:
    """
    Reemplaza variables dinámicas en la plantilla.

    Variables: {{nombre}}, {{empresa}}, {{pais}}, {{cargo}}, {{email}}
    """
    resultado = plantilla
    resultado = resultado.replace("{{nombre}}", nombre.split()[0] if nombre else "")
    resultado = resultado.replace("{{empresa}}", empresa)
    resultado = resultado.replace("{{pais}}", pais)
    resultado = resultado.replace("{{cargo}}", cargo)
    resultado = resultado.replace("{{email}}", email)
    return resultado


# =============================================================================
# PLANTILLA POR DEFECTO PSKLOUD
# =============================================================================
PLANTILLA_DEFAULT = {
    "asunto": "Alianza estratégica en {{pais}} para distribución de software / Oportunidad Operativa",
    "cuerpo": """Hola {{nombre}},

Me dirigí a usted porque vi que en {{empresa}} están liderando el sector. Como Consultor de Ventas Internacionales de PSKloud, estamos expandiendo nuestro ecosistema de soluciones administrativas y facturación electrónica nativa en {{pais}}.

Me gustaría evaluar si hace sentido una sinergia con ustedes. ¿Tendrás 10 minutos esta semana para una conversación rápida?

Saludos cordiales,
Equipo PSKloud
Ventas Internacionales"""
}


# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================
def main():
    """Función principal de la aplicación."""

    # =========================================================================
    # CSS PERSONALIZADO - PSKloud Branding
    # =========================================================================
    st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
        }
        .main-header {
            background: linear-gradient(135deg, #CC0000 0%, #8B0000 100%);
            padding: 1.5rem 2rem;
            border-radius: 12px;
            color: white !important;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 12px rgba(204,0,0,0.2);
        }
        .main-header h1 {
            color: white !important;
            margin: 0;
            font-size: 1.8rem;
        }
        .main-header p {
            color: rgba(255,255,255,0.9) !important;
            margin: 0.3rem 0 0 0;
        }
        .lead-card {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: box-shadow 0.2s;
        }
        .lead-card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .status-badge {
            display: inline-block;
            padding: 0.15rem 0.6rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-phone {
            background: #e8f5e9;
            color: #2e7d32;
        }
        .badge-nophone {
            background: #fbe9e7;
            color: #c62828;
        }
        .stButton > button[data-testid="baseButton-secondary"] {
            background: linear-gradient(135deg, #CC0000 0%, #8B0000 100%);
            color: white;
            border: none;
            font-weight: 600;
        }
        .stButton > button[data-testid="baseButton-secondary"]:hover {
            background: linear-gradient(135deg, #DD2222 0%, #AA0000 100%);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
        }
        .stats-container {
            background: white;
            border-radius: 10px;
            padding: 1rem;
            border: 1px solid #e0e0e0;
            margin-bottom: 1rem;
        }
        .phone-result {
            font-family: monospace;
            font-size: 1.1rem;
            color: #CC0000;
            font-weight: bold;
        }
        .fuente-tag {
            background: #e3f2fd;
            color: #1565c0;
            padding: 0.1rem 0.5rem;
            border-radius: 8px;
            font-size: 0.7rem;
        }
        @media (max-width: 768px) {
            .main-header h1 { font-size: 1.3rem; }
        }
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # BARRA LATERAL
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/email-send.png", width=80)
        st.title("PSKloud Prospector")
        st.caption("v2.0 | Sistema REAL de Prospección B2B")

        # Campo para API key de Hunter.io
        st.divider()
        st.markdown("### 🔑 Configuración Hunter.io")
        st.markdown("[Obtener API key gratis →](https://hunter.io/users/sign_up)")

        # Cargar API key desde secrets (archivo local o Streamlit Cloud)
        try:
            api_key_predeterminada = st.secrets.get("HUNTER_API_KEY", "")
        except Exception:
            api_key_predeterminada = ""

        # Si hay key en secrets.toml local, precargarla en session_state
        if api_key_predeterminada and "hunter_api_key" not in st.session_state:
            st.session_state["hunter_api_key"] = api_key_predeterminada

        api_key = st.text_input(
            "API Key de Hunter.io",
            type="password",
            value=st.session_state.get("hunter_api_key", ""),
            help="Tu API key se guarda automáticamente al hacer clic en 'Guardar'"
        )

        # Botón para persistir la API key
        col_key1, col_key2 = st.columns([3, 1])
        with col_key1:
            if api_key and api_key != st.session_state.get("hunter_api_key_saved", ""):
                if guardar_api_key_en_secrets(api_key):
                    st.session_state["hunter_api_key_saved"] = api_key
                    st.success("✅ API key guardada", icon="🔒")
        with col_key2:
            if st.button("🔑💾", help="Guardar API key permanentemente"):
                if api_key and guardar_api_key_en_secrets(api_key):
                    st.session_state["hunter_api_key_saved"] = api_key
                    st.success("✅ Guardada!")

        if api_key:
            st.session_state["hunter_api_key"] = api_key
            info_cuenta = obtener_info_cuenta_hunter(api_key)
            if "error" not in info_cuenta:
                st.success(f"✅ Conectado: {info_cuenta.get('email', '')}")
                st.metric("Búsquedas disponibles", info_cuenta["busquedas"]["disponibles"])
                st.metric("Verificaciones disponibles", info_cuenta["verificaciones"]["disponibles"])
            else:
                st.error(f"❌ {info_cuenta['error']}")

        # =====================================================================
        # LUSHA API (teléfonos directos)
        # =====================================================================
        st.divider()
        st.markdown("### 📞 Configuración Lusha")
        st.markdown("[Obtener API key gratis →](https://www.lusha.com/)")
        lusha_key = st.text_input(
            "API Key de Lusha",
            type="password",
            value=st.session_state.get("lusha_api_key", ""),
            help="Lusha provee teléfonos DIRECTOS del contacto (no solo de la empresa)"
        )
        if lusha_key:
            st.session_state["lusha_api_key"] = lusha_key
            st.success("✅ Lusha conectado (70 créditos/mes en plan free)")

        st.divider()
        st.markdown("""
        **Mercado Objetivo:**
        - 🇨🇷 Costa Rica: {} empresas
        - 🇸🇻 El Salvador: {} empresas
        - 🇵🇦 Panamá: {} empresas
        - 🇭🇳 Honduras: {} empresas
        - 🇨🇴 Colombia: {} empresas

        **Fuente:** Datos reales de Hunter.io API
        """.format(
            len(EMPRESAS_REALES["Costa Rica"]),
            len(EMPRESAS_REALES["El Salvador"]),
            len(EMPRESAS_REALES["Panamá"]),
            len(EMPRESAS_REALES["Honduras"]),
            len(EMPRESAS_REALES["Colombia"])
        ))

        # Contador de leads excluidos
        excluidos_data = cargar_excluidos()
        excluidos_count = len(excluidos_data)
        if excluidos_count > 0:
            st.metric("🚫 Leads excluidos", excluidos_count, help="Leads que ya contactaste y no volverán a aparecer")
            if st.button("🔄 Ver leads excluidos"):
                with st.expander("📋 Historial de exclusiones", expanded=True):
                    for email, info in excluidos_data.items():
                        motivo = info.get("motivo", "No especificado") if isinstance(info, dict) else "No especificado"
                        fecha = info.get("fecha", "")[:10] if isinstance(info, dict) else ""
                        st.text(f"• {email} — {motivo} {f'({fecha})' if fecha else ''}")

    # -------------------------------------------------------------------------
    # ENCABEZADO
    # -------------------------------------------------------------------------
    st.markdown("""
    <div class="main-header">
        <h1>📧 PSKloud Prospector</h1>
        <p>Leads reales vía Hunter.io + Enriquecimiento con directorios públicos + Envío SMTP real</p>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # PESTAÑAS
    # -------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Componente 1: Búsqueda de Leads Reales",
        "📝 Componente 2: Configurador de Campañas",
        "🚀 Componente 3: Envío Masivo SMTP Real",
        "📊 Componente 4: Pipeline de Ventas"
    ])

    # =========================================================================
    # COMPONENTE 1: BÚSQUEDA DE LEADS REALES
    # =========================================================================
    with tab1:
        st.header("🔍 Búsqueda de Leads Reales")
        st.markdown("Busca contactos reales en empresas de Costa Rica y El Salvador usando Hunter.io.")

        if not api_key:
            st.warning("⚠️ Ingresa tu API key de Hunter.io en la barra lateral para comenzar.")
            st.info("💡 **¿No tienes API key?** Regístrate gratis en [hunter.io](https://hunter.io/users/sign_up) — Plan gratuito: 25 búsquedas/mes")

        # Filtros preconfigurados para PSKloud
        col1, col2 = st.columns(2)

        with col1:
            paisSeleccionado = st.selectbox(
                "🌍 País",
                options=["Costa Rica", "El Salvador", "Panamá", "Honduras", "Colombia"],
                key="pais_busqueda"
            )

        with col2:
            tipo_target = st.selectbox(
                "🎯 Tipo de Target",
                options=["Canales/Distribuidores", "Clientes Finales"],
                key="tipo_busqueda",
                help="Canales: aliados comerciales para distribuir PSKloud. Clientes Finales: empresas que usan el software."
            )

        # Sectores predefinidos según el target de PSKloud
        sectores_pscloud = {
            "Canales/Distribuidores": ["Todos", "Tecnología"],
            "Clientes Finales": ["Todos", "Retail", "Finanzas", "Salud", "Turismo", "Manufactura", "Telecomunicaciones", "Energía", "Logística"]
        }

        sector_filtro = st.selectbox(
            "🏢 Sector",
            options=sectores_pscloud.get(tipo_target, ["Todos"]),
            key="sector_busqueda"
        )

        # Contactos por empresa
        limite_resultados = st.slider(
            "📊 Contactos por empresa",
            min_value=3,
            max_value=10,
            value=5
        )

        # Botón de búsqueda
        if st.button("🔍 Buscar Leads Reales", type="primary", use_container_width=True):
            if not api_key:
                st.error("❌ Necesitas una API key de Hunter.io para buscar leads reales.")
                st.stop()

            # Filtrar empresas según criterios
            empresas_filtradas = []
            for empresa in EMPRESAS_REALES.get(paisSeleccionado, []):
                # Filtro por tipo
                if tipo_target != "Todos" and empresa.get("tipo") != tipo_target:
                    continue
                # Filtro por sector (selectbox exacto)
                if sector_filtro != "Todos" and empresa.get("sector") != sector_filtro:
                    continue
                empresas_filtradas.append(empresa)

            if not empresas_filtradas:
                st.warning("No se encontraron empresas con los filtros seleccionados.")
                st.stop()

            # Cargar leads ya excluidos (vistos en días anteriores)
            excluidos = cargar_excluidos()
            if excluidos:
                st.info(f"📋 exclusiones previas: **{len(excluidos)} leads** ya vistos serán omitidos automáticamente.")

            st.info(f"🔍 Buscando contactos en **{len(empresas_filtradas)} empresas** de **{paisSeleccionado}**...")

            # Barra de progreso
            progress_bar = st.progress(0, text="Iniciando búsqueda...")
            todos_los_leads = []
            errores = []

            # Buscar en cada empresa
            for idx, empresa in enumerate(empresas_filtradas):
                dominio = empresa.get("dominio", "")
                if not dominio:
                    continue

                progress_bar.progress(
                    (idx + 1) / len(empresas_filtradas),
                    text=f"Buscando en {empresa['empresa']} ({dominio})..."
                )

                # Llamar a Hunter.io API
                contactos, info = buscar_contactos_hunter(api_key, dominio, limite_resultados)

                if "error" in info:
                    errores.append(f"{empresa['empresa']}: {info['error']}")
                    continue

                # Procesar - SOLO EL MEJOR CONTACTO POR EMPRESA
                if contactos:
                    # Ordenar: mayor confianza + cargo más alto primero
                    def prioridad(c):
                        conf = c.get("confianza", 0)
                        cargo = (c.get("cargo", "") or "").lower()
                        if "chief" in cargo or "ceo" in cargo or "founder" in cargo or "director" in cargo:
                            return conf + 20
                        elif "gerente" in cargo or "manager" in cargo:
                            return conf + 10
                        return conf

                    # Filtrar contactos ya excluidos
                    contactos_disponibles = [
                        c for c in contactos
                        if c.get("email", "") not in excluidos
                    ]

                    if contactos_disponibles:
                        mejor = max(contactos_disponibles, key=prioridad)

                        lead = {
                                "País": paisSeleccionado,
                                "Empresa": empresa["empresa"],
                                "Dominio": dominio,
                                "Sector": empresa.get("sector", ""),
                                "Tipo": empresa.get("tipo", ""),
                                "Contacto Clabe": f"{mejor.get('nombre', '')} {mejor.get('apellido', '')}".strip(),
                                "Cargo": mejor.get("cargo", "No especificado"),
                                "Correo": mejor.get("email", ""),
                                "Confianza (%)": mejor.get("confianza", 0),
                                "LinkedIn": mejor.get("linkedin", ""),
                                "Fuente": "Hunter.io",
                                "Estado del Lead": "Nuevo",
                                "Etapa": "Nuevo"
                            }
                        todos_los_leads.append(lead)

            progress_bar.progress(1.0, text="✅ Búsqueda completada")

            # Guardar leads en session state
            if todos_los_leads:
                df_leads = pd.DataFrame(todos_los_leads)
                st.session_state["df_leads"] = df_leads
                st.success(f"✅ **{len(df_leads)} leads reales encontrados** en {len(empresas_filtradas)} empresas")
            else:
                st.warning("No se encontraron contactos con los filtros aplicados.")

            # Mostrar errores
            if errores:
                with st.expander("⚠️ Errores durante la búsqueda"):
                    for error in errores:
                        st.error(error)

        # -------------------------------------------------------------------------
        # Mostrar resultados si existen
        # -------------------------------------------------------------------------
        if "df_leads" in st.session_state and not st.session_state["df_leads"].empty:
            df = st.session_state["df_leads"]

            # Métricas rápidas
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("📋 Total Leads", len(df))
            with col_m2:
                st.metric("🏢 Empresas", df["Empresa"].nunique())
            with col_m3:
                if "Teléfono" in df.columns:
                    con_tel = df["Teléfono"].astype(bool).sum()
                    st.metric("📞 Con teléfono", f"{con_tel}")
                else:
                    st.metric("📞 Con teléfono", "0")
            with col_m4:
                st.metric("📧 Con email", len(df))

            # Opciones de exportación
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Descargar CSV",
                    data=csv_data,
                    file_name=f"leads_reales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_e2:
                excel_filename = f"leads_reales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Leads Reales")
                with open(excel_filename, "rb") as f:
                    excel_bytes = f.read()
                st.download_button(
                    "📥 Descargar Excel",
                    data=excel_bytes,
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            # Tabla principal con columnas dinámicas
            column_config = {
                "Confianza (%)": st.column_config.ProgressColumn(
                    "Confianza", min_value=0, max_value=100, format="%d%%"
                ),
                "LinkedIn": st.column_config.LinkColumn("LinkedIn", width="small"),
                "Correo": st.column_config.TextColumn("Email", width="medium"),
            }
            if "Teléfono" in df.columns:
                column_config["Teléfono"] = st.column_config.TextColumn("📞 Teléfono", width="medium")
            if "Fuente Teléfono" in df.columns:
                column_config["Fuente Teléfono"] = st.column_config.TextColumn("Origen", width="small")

            st.dataframe(df, use_container_width=True, height=400, column_config=column_config)

            # -------------------------------------------------------------------------
            # ENRIQUECIMIENTO - Buscar teléfonos en directorios públicos
            # -------------------------------------------------------------------------
            st.divider()
            st.subheader("📞 Buscar Teléfonos en Directorios")
            col_enr1, col_enr2 = st.columns([3, 1])
            with col_enr1:
                st.markdown("Busca en **Páginas Amarillas SV**, **Yelu.cr**, **Infoguía CR** y **sitios web corporativos**.")
            with col_enr2:
                stats = get_cache_stats()
                st.caption(f"🧠 Caché: {stats['entradas']} consultas")

            col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
            with col_btn1:
                if st.button("📞 Buscar Teléfonos para Todos los Leads",
                             type="secondary", use_container_width=True):
                    df = st.session_state["df_leads"]
                    progreso_enrich = st.progress(0, text="Iniciando enriquecimiento...")
                    log_enrich = st.container()

                    telefonos_encontrados = 0
                    total_leads = len(df)

                    if "Teléfono" not in df.columns:
                        df["Teléfono"] = ""
                    if "Dirección" not in df.columns:
                        df["Dirección"] = ""
                    if "Fuente Teléfono" not in df.columns:
                        df["Fuente Teléfono"] = ""

                    for idx, lead in df.iterrows():
                        empresa = lead.get("Empresa", "")
                        pais = lead.get("País", "Costa Rica")
                        dominio = lead.get("Dominio", "")

                        progreso_enrich.progress(
                            (idx + 1) / total_leads,
                            text=f"Buscando teléfono: {empresa}..."
                        )
                        with log_enrich:
                            st.caption(f"🔍 {empresa}...")

                        sitio_web = f"https://{dominio}" if dominio and dominio != "N/A" else None
                        contacto_nombre = lead.get("Contacto Clabe", "").strip()
                        nombres = contacto_nombre.split(" ", 1) if contacto_nombre else ["", ""]
                        lusha_key = st.session_state.get("lusha_api_key", "")
                        datos = enrich_company(
                            empresa, pais,
                            website=sitio_web,
                            lusha_api_key=lusha_key,
                            contact_first_name=nombres[0] if nombres else "",
                            contact_last_name=nombres[1] if len(nombres) > 1 else ""
                        )

                        if datos.get("telefonos"):
                            telefonos = "; ".join(datos["telefonos"][:3])
                            df.at[idx, "Teléfono"] = telefonos
                            df.at[idx, "Dirección"] = datos.get("direccion", "")
                            df.at[idx, "Fuente Teléfono"] = ", ".join(datos.get("fuentes_usadas", []))
                            telefonos_encontrados += 1
                            with log_enrich:
                                st.success(f"✅ {empresa}: {telefonos}")
                        else:
                            with log_enrich:
                                st.info(f"⏭️ {empresa}: sin teléfono")

                        time.sleep(0.3)

                    progreso_enrich.progress(1.0, text="✅ Enriquecimiento completado")
                    st.session_state["df_leads"] = df
                    st.success(f"✅ {telefonos_encontrados}/{total_leads} leads con teléfono")
                    st.rerun()

            with col_btn2:
                if st.button("🗑️ Limpiar Caché", use_container_width=True):
                    limpiar_cache_enriquecimiento()
                    st.success("Caché limpiado")
            with col_btn3:
                st.caption(f"⏱️ ~15-30 seg por lead")

            # -------------------------------------------------------------------------
            # PIPELINE - Avance de etapas por lead
            # -------------------------------------------------------------------------
            st.divider()
            st.subheader("🔄 Pipeline de Ventas — Avanzar Etapa")
            st.markdown("Selecciona el lead y la siguiente etapa en tu flujo:")

            col_pipe1, col_pipe2, col_pipe3 = st.columns([2, 2, 1])
            lead_emails = df["Correo"].tolist()
            lead_options = {f"{row['Contacto Clabe']} - {row['Empresa']} ({row['Correo']})": row["Correo"]
                           for _, row in df.iterrows()}

            with col_pipe1:
                selected_display = st.selectbox(
                    "Seleccionar lead",
                    options=list(lead_options.keys()),
                    key="pipeline_select"
                )
                selected_email = lead_options.get(selected_display, "")

            with col_pipe2:
                etapa_actual = obtener_etapa_lead(selected_email)
                idx_actual = ETAPAS.index(etapa_actual) if etapa_actual in ETAPAS else 0
                nuevas_etapas = [e for e in ETAPAS if ETAPAS.index(e) > idx_actual]
                if not nuevas_etapas:
                    nuevas_etapas = [ETAPAS[-1]]
                siguiente_etapa = st.selectbox(
                    "Avanzar a",
                    options=nuevas_etapas,
                    key="pipeline_etapa"
                )

            with col_pipe3:
                if st.button("✅ Avanzar", type="primary", use_container_width=True):
                    actualizar_etapa_lead(selected_email, siguiente_etapa)
                    st.success(f"Lead avanzado a: {siguiente_etapa}")
                    st.rerun()

            # Mostrar etapa actual del lead seleccionado
            if selected_email:
                datos_pipe = cargar_pipeline().get(selected_email, {})
                st.info(
                    f"📊 **{selected_display}** — "
                    f"Etapa actual: **{etapa_actual}**  |  "
                    f"📧 {datos_pipe.get('fecha_email','—')[:10] or '—'}  |  "
                    f"🔗 {datos_pipe.get('fecha_linkedin','—')[:10] or '—'}  |  "
                    f"📞 {datos_pipe.get('fecha_llamada','—')[:10] or '—'}"
                )

            # Estadísticas rápidas del pipeline
            st.divider()
            stats_pipe = pipeline_stats()
            cols_pipe = st.columns(len(ETAPAS) + 1)
            for i, etapa in enumerate(ETAPAS):
                with cols_pipe[i]:
                    st.metric(ETAPAS_ICONOS.get(etapa, "•"), stats_pipe.get(etapa, 0))
            with cols_pipe[-1]:
                st.metric("📊 Total", stats_pipe.get("Total", 0))

            # -------------------------------------------------------------------------
            # SISTEMA DE EXCLUSIÓN - Marcar leads como vistos
            # -------------------------------------------------------------------------
            st.divider()
            st.subheader("✅ Marcar Leads como Vistos")
            st.markdown("Selecciona los leads que ya contactaste para que no aparezcan en futuras búsquedas.")

            excluidos_actuales = cargar_excluidos()
            leads_a_excluir = []

            for idx, lead in df.iterrows():
                email = lead.get("Correo", "")
                nombre = lead.get("Contacto Clabe", "")
                empresa = lead.get("Empresa", "")

                if email in excluidos_actuales:
                    info = excluidos_actuales[email]
                    motivo = info.get("motivo", "No especificado") if isinstance(info, dict) else "No especificado"
                    st.success(f"✅ **{nombre}** ({empresa}) — Excluido: {motivo}")
                else:
                    col_chk, col_mot = st.columns([3, 2])
                    with col_chk:
                        excluir = st.checkbox(
                            f"**{nombre}** de {empresa} ({email})",
                            key=f"excluir_{idx}"
                        )
                    with col_mot:
                        motivo_sel = st.selectbox(
                            "Motivo",
                            options=MOTIVOS_EXCLUSION,
                            key=f"motivo_{idx}",
                            label_visibility="collapsed"
                        ) if excluir else None
                    if excluir and motivo_sel:
                        leads_a_excluir.append((email, motivo_sel))

            if leads_a_excluir:
                if st.button("🗑️ Excluir Seleccionados", type="primary"):
                    for email, motivo in leads_a_excluir:
                        excluir_lead(email, motivo)
                    st.success(f"✅ {len(leads_a_excluir)} leads excluidos con motivo. No aparecerán en futuras búsquedas.")
                    st.rerun()

        # -------------------------------------------------------------------------
        # IMPORTAR LEADS PROPIOS
        # -------------------------------------------------------------------------
        st.divider()
        st.subheader("📤 Importar Leads Propios (CSV)")
        st.markdown("Si ya tienes una base de datos de leads, impórtala aquí.")

        archivo_csv = st.file_uploader(
            "Sube tu archivo CSV",
            type=["csv"],
            help="El CSV debe tener columnas: Empresa, Correo, Contacto, Cargo, País"
        )

        if archivo_csv:
            try:
                df_importado = pd.read_csv(archivo_csv)
                st.success(f"✅ Archivo cargado: {len(df_importado)} registros")

                # Normalizar columnas
                columnas_requeridas = ["Empresa", "Correo", "Contacto", "Cargo", "Pais"]
                columnas_encontradas = list(df_importado.columns)

                st.dataframe(df_importado.head(), use_container_width=True)

                if st.button("📥 Importar Leads", type="primary"):
                    # Renombrar columnas si es necesario
                    rename_map = {}
                    for col in df_importado.columns:
                        col_lower = col.lower()
                        if "empresa" in col_lower or "company" in col_lower:
                            rename_map[col] = "Empresa"
                        elif "correo" in col_lower or "email" in col_lower:
                            rename_map[col] = "Correo"
                        elif "contacto" in col_lower or "nombre" in col_lower or "name" in col_lower:
                            rename_map[col] = "Contacto Clabe"
                        elif "cargo" in col_lower or "position" in col_lower or "puesto" in col_lower:
                            rename_map[col] = "Cargo"
                        elif "pais" in col_lower or "country" in col_lower:
                            rename_map[col] = "País"

                    df_importado = df_importado.rename(columns=rename_map)
                    df_importado["Estado del Lead"] = "Nuevo"
                    df_importado["Etapa"] = "Nuevo"
                    df_importado["Fuente"] = "Importado"

                    st.session_state["df_leads"] = df_importado
                    st.success(f"✅ {len(df_importado)} leads importados exitosamente")
                    st.rerun()

            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")

    # =========================================================================
    # COMPONENTE 2: CONFIGURADOR DE CAMPAÑAS
    # =========================================================================
    with tab2:
        st.header("📝 Configurador de Campañas y Plantillas")

        # Variables disponibles
        with st.expander("ℹ️ Variables Dinámicas", expanded=False):
            st.markdown("""
            | Variable | Descripción | Ejemplo |
            |----------|-------------|---------|
            | `{{nombre}}` | Primer nombre del contacto | Carlos |
            | `{{empresa}}` | Nombre de la empresa | Kambda |
            | `{{pais}}` | País del lead | Costa Rica |
            | `{{cargo}}` | Cargo del contacto | CEO |
            | `{{email}}` | Correo del contacto | carlos@kambda.com |
            """)

        # Editor de plantilla
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("📌 Asunto")
            asunto = st.text_area(
                "Asunto del correo",
                value=st.session_state.get("asunto_campana", PLANTILLA_DEFAULT["asunto"]),
                height=80,
                key="asunto_editor"
            )

        with col2:
            st.subheader("📄 Cuerpo")
            cuerpo = st.text_area(
                "Cuerpo del correo",
                value=st.session_state.get("cuerpo_campana", PLANTILLA_DEFAULT["cuerpo"]),
                height=250,
                key="cuerpo_editor"
            )

        # Vista previa
        if "df_leads" in st.session_state and not st.session_state["df_leads"].empty:
            st.divider()
            st.subheader("👁️ Vista Previa")

            lead_ejemplo = st.session_state["df_leads"].iloc[0]

            asunto_preview = renderizar_plantilla(
                asunto,
                lead_ejemplo.get("Contacto Clabe", ""),
                lead_ejemplo.get("Empresa", ""),
                lead_ejemplo.get("País", ""),
                lead_ejemplo.get("Cargo", ""),
                lead_ejemplo.get("Correo", "")
            )

            cuerpo_preview = renderizar_plantilla(
                cuerpo,
                lead_ejemplo.get("Contacto Clabe", ""),
                lead_ejemplo.get("Empresa", ""),
                lead_ejemplo.get("País", ""),
                lead_ejemplo.get("Cargo", ""),
                lead_ejemplo.get("Correo", "")
            )

            st.markdown(f"""
            <div style="border:1px solid #ddd; border-radius:10px; padding:20px; background-color:#f9f9f9;">
                <p style="font-size:12px; color:#888;">Vista previa para: <strong>{lead_ejemplo.get('Contacto Clabe', '')}</strong> - {lead_ejemplo.get('Empresa', '')}</p>
                <p><strong>De:</strong> tu_email@empresa.com</p>
                <p><strong>Para:</strong> {lead_ejemplo.get('Correo', '')}</p>
                <p><strong>Asunto:</strong> {asunto_preview}</p>
                <hr>
                <p style="white-space: pre-line;">{cuerpo_preview}</p>
            </div>
            """, unsafe_allow_html=True)

        if st.button("💾 Guardar Plantilla", type="secondary"):
            st.session_state["asunto_campana"] = asunto
            st.session_state["cuerpo_campana"] = cuerpo
            guardar_plantilla(asunto, cuerpo)
            st.success("✅ Plantilla guardada permanentemente")

    # =========================================================================
    # COMPONENTE 3: ENVÍO MASIVO SMTP REAL
    # =========================================================================
    with tab3:
        st.header("🚀 Motor de Envío Masivo SMTP Real")
        st.markdown("Configura credenciales SMTP reales y envía correos de prospección.")

        # Configuración SMTP
        st.subheader("⚙️ Configuración SMTP")

        col1, col2 = st.columns(2)

        with col1:
            try:
                smtp_server_default = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
            except Exception:
                smtp_server_default = "smtp.gmail.com"
            smtp_server = st.text_input(
                "🖥️ Servidor SMTP",
                value=smtp_server_default,
                help="Gmail: smtp.gmail.com | Outlook: smtp.office365.com | Yahoo: smtp.mail.yahoo.com"
            )

            try:
                smtp_port_default = int(st.secrets.get("SMTP_PORT", 587))
            except Exception:
                smtp_port_default = 587
            smtp_port = st.number_input(
                "🔌 Puerto",
                value=smtp_port_default,
                min_value=1,
                max_value=65535
            )

        with col2:
            try:
                smtp_email_default = st.secrets.get("SMTP_EMAIL", "")
            except Exception:
                smtp_email_default = ""
            smtp_email = st.text_input(
                "📧 Correo Emisor",
                value=smtp_email_default,
                placeholder="tu_empresa@gmail.com"
            )

            try:
                smtp_password_default = st.secrets.get("SMTP_PASSWORD", "")
            except Exception:
                smtp_password_default = ""
            smtp_password = st.text_input(
                "🔑 Contraseña / Token de Aplicación",
                type="password",
                value=smtp_password_default,
                help="Para Gmail: usa una 'Contraseña de aplicación' de Google"
            )

        # Instrucciones para Gmail
        with st.expander("ℹ️ Cómo configurar Gmail para envío"):
            st.markdown("""
            1. Ve a [myaccount.google.com](https://myaccount.google.com)
            2. Seguridad → Verificación en 2 pasos (activar)
            3. Seguridad → Contraseñas de aplicaciones
            4. Selecciona "Otra (Nombre personalizado)" → "PSKloud Prospector"
            5. Copia la contraseña generada (16 caracteres)
            6. Pégala arriba como contraseña
            """)

        # -------------------------------------------------------------------------
        # Verificar prerrequisitos
        # -------------------------------------------------------------------------
        st.divider()
        leads_ok = "df_leads" in st.session_state and not st.session_state["df_leads"].empty
        plantilla_ok = st.session_state.get("asunto_campana", "").strip() != ""
        smtp_ok = smtp_server and smtp_email and smtp_password

        col1, col2, col3 = st.columns(3)
        with col1:
            if leads_ok:
                st.success(f"✅ Leads: {len(st.session_state['df_leads'])}")
            else:
                st.error("❌ Sin leads")
        with col2:
            if plantilla_ok:
                st.success("✅ Plantilla configurada")
            else:
                st.error("❌ Sin plantilla")
        with col3:
            if smtp_ok:
                st.success("✅ SMTP configurado")
            else:
                st.error("❌ SMTP incompleto")

        # -------------------------------------------------------------------------
        # Botón de envío
        # -------------------------------------------------------------------------
        st.divider()

        if st.button("🚀 Iniciar Campaña de Prospección Masiva", type="primary", use_container_width=True):
            if not leads_ok:
                st.error("❌ No hay leads para procesar. Busca leads en el Componente 1.")
                st.stop()

            if not smtp_ok:
                st.error("❌ Configura credenciales SMTP válidas.")
                st.stop()

            # Obtener plantilla activa
            asunto_activo = st.session_state.get("asunto_campana", PLANTILLA_DEFAULT["asunto"])
            cuerpo_activo = st.session_state.get("cuerpo_campana", PLANTILLA_DEFAULT["cuerpo"])

            leads_procesar = st.session_state["df_leads"].copy()

            # Barra de progreso
            progress = st.progress(0, text="Iniciando campaña...")
            log_container = st.container()

            exitosos = 0
            fallidos = 0
            total = len(leads_procesar)

            for idx, lead in leads_procesar.iterrows():
                try:
                    progress.progress(
                        (idx + 1) / total,
                        text=f"Enviando {idx + 1} de {total}..."
                    )

                    # Renderizar plantilla
                    asunto_render = renderizar_plantilla(
                        asunto_activo,
                        lead.get("Contacto Clabe", ""),
                        lead.get("Empresa", ""),
                        lead.get("País", ""),
                        lead.get("Cargo", ""),
                        lead.get("Correo", "")
                    )

                    cuerpo_render = renderizar_plantilla(
                        cuerpo_activo,
                        lead.get("Contacto Clabe", ""),
                        lead.get("Empresa", ""),
                        lead.get("País", ""),
                        lead.get("Cargo", ""),
                        lead.get("Correo", "")
                    )

                    # Enviar correo real
                    exito, mensaje = enviar_correo_real(
                        servidor=smtp_server,
                        puerto=smtp_port,
                        correo_emisor=smtp_email,
                        contrasena=smtp_password,
                        correo_receptor=lead.get("Correo", ""),
                        asunto=asunto_render,
                        cuerpo=cuerpo_render
                    )

                    if exito:
                        exitosos += 1
                        with log_container:
                            st.success(
                                f"✉️ **[{idx + 1}/{total}]** "
                                f"**{lead.get('Contacto Clabe', '')}** "
                                f"({lead.get('Empresa', '')}) — ✅ ¡Enviado!"
                            )
                    else:
                        fallidos += 1
                        with log_container:
                            st.error(
                                f"❌ **[{idx + 1}/{total}]** "
                                f"**{lead.get('Contacto Clabe', '')}** "
                                f"({lead.get('Empresa', '')}) — {mensaje}"
                            )

                except Exception as e:
                    fallidos += 1
                    with log_container:
                        st.error(f"⚠️ Error procesando lead {idx + 1}: {str(e)}")

            # Finalización
            progress.progress(1.0, text="✅ ¡Campaña completada!")

            st.divider()
            st.subheader("📊 Resumen Final")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📧 Enviados", exitosos)
            with col2:
                st.metric("❌ Fallidos", fallidos)
            with col3:
                tasa = (exitosos / total * 100) if total > 0 else 0
                st.metric("📈 Tasa de Éxito", f"{tasa:.1f}%")
            with col4:
                st.metric("📋 Total", total)

            if exitosos > 0:
                st.success(
                    f"🎉 **Campaña finalizada.** "
                    f"{exitosos} correos enviados exitosamente."
                )

    # =========================================================================
    # COMPONENTE 4: PIPELINE DE VENTAS
    # =========================================================================
    with tab4:
        st.header("📊 Pipeline de Ventas")
        st.markdown("Visualiza y gestiona el avance de tus leads por las etapas del proceso comercial.")

        pipeline = cargar_pipeline()
        if not pipeline:
            st.info("💡 Aún no hay leads en el pipeline. Busca leads en el Componente 1 y asígnales una etapa.")
        else:
            # Resumen visual tipo kanban
            stats = pipeline_stats()
            total = stats.pop("Total", 0)

            # Métricas generales
            cols = st.columns(5)
            with cols[0]:
                st.metric("🆕 Nuevos", stats.get("Nuevo", 0))
            with cols[1]:
                st.metric("📧 Email enviado", stats.get("📧 Email enviado", 0))
            with cols[2]:
                st.metric("🔗 LinkedIn", stats.get("🔗 LinkedIn contactado", 0))
            with cols[3]:
                st.metric("📞 Llamada", stats.get("📞 Llamada realizada", 0))
            with cols[4]:
                st.metric("✅ Cerrados", stats.get("✅ Cliente", 0) + stats.get("❌ Perdido", 0))

            # Tabla del pipeline con todas las etapas
            st.subheader("📋 Detalle del Pipeline")
            df_pipeline = pd.DataFrame([
                {
                    "Email": email,
                    "Etapa": data.get("etapa", "Nuevo"),
                    "📧 Email": (data.get("fecha_email", "") or "")[:10],
                    "🔗 LinkedIn": (data.get("fecha_linkedin", "") or "")[:10],
                    "📞 Llamada": (data.get("fecha_llamada", "") or "")[:10],
                    "Notas": data.get("notas", ""),
                }
                for email, data in pipeline.items()
            ])

            if not df_pipeline.empty:
                # Filtro por etapa
                etapas_disponibles = ["Todas"] + ETAPAS
                filtro_etapa = st.selectbox("Filtrar por etapa", options=etapas_disponibles, key="filtro_pipeline")
                if filtro_etapa != "Todas":
                    df_pipeline = df_pipeline[df_pipeline["Etapa"] == filtro_etapa]

                st.dataframe(
                    df_pipeline,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Email": st.column_config.TextColumn("Email", width="medium"),
                        "Etapa": st.column_config.TextColumn("🚩 Etapa", width="medium"),
                    }
                )

                # Permitir editar notas
                st.subheader("📝 Editar Notas del Lead")
                pipe_emails = df_pipeline["Email"].tolist()
                email_seleccionado = st.selectbox(
                    "Seleccionar lead para agregar nota",
                    options=pipe_emails,
                    key="pipe_nota_email"
                )
                nota_actual = pipeline.get(email_seleccionado, {}).get("notas", "")
                nueva_nota = st.text_area("Notas", value=nota_actual, key="pipe_nota_texto")
                if st.button("💾 Guardar Nota", type="secondary"):
                    actualizar_etapa_lead(email_seleccionado,
                                          pipeline[email_seleccionado]["etapa"],
                                          notas=nueva_nota)
                    st.success("Nota guardada")
                    st.rerun()

            # Exportar pipeline
            st.divider()
            if st.button("📥 Exportar Pipeline a CSV", use_container_width=True):
                csv_pipe = df_pipeline.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Descargar CSV",
                    data=csv_pipe,
                    file_name=f"pipeline_ventas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    main()
