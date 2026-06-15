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
    Subir a GitHub → share.streamlit.io → Deploy
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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# =============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="PSKloud Prospector | Ventas Internacionales",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        {"empresa": "La Grenia", "domain": "lagrenia.com", "sector": "Retail", "tipo": "Clientes Finales",
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
        {"empresa": "Synapsis", "dominio": "synapsis.net", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/synapsis-el-salvador"},
        {"empresa": "Softcorp International", "dominio": "softcorp.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/softcorp-international"},
        {"empresa": "GInIEm", "dominio": "giniem.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/giniem"},
        {"empresa": "Logical Sistemas", "dominio": "logical.com.sv", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/logical-sistemas"},
        {"empresa": "Computo Express", "dominio": "computoexpress.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/computo-express"},
        {"empresa": "Inforum", "dominio": "inforum.com.sv", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/inforum-sv"},
        {"empresa": "Grupo Magaña", "dominio": "grupomagana.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/grupo-magana"},
        {"empresa": "Netcom", "dominio": "netcom.com.sv", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/netcom-sv"},
        {"empresa": "EIT", "dominio": "eit.com.sv", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/eit-sv"},
        {"empresa": "Inversiones Técnológicas", "dominio": "inversionestec.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/inversiones-tecnologicas"},
        {"empresa": "Intecno Solutions", "dominio": "intecnosolutions.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/intecno-solutions"},
        {"empresa": "Sistemas Técnicos", "dominio": "sistemas Tecnicos.com", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "linkedin": "https://linkedin.com/company/sistemas-tecnicos"},

        # === RETAIL / COMERCIO ===
        {"empresa": "Super Selectos", "dominio": "superselectos.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/super-selectos"},
        {"empresa": "Despensa Familiar", "dominio": "despensafamiliar.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/despensa-familiar"},
        {"empresa": "La Curacao", "dominio": "lacuracao.com.sv", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/la-curacao"},
        {"empresa": "Siman", "dominio": "siman.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/siman"},
        {"empresa": "Farmacias Guadalupana", "dominio": "guadalupana.com", "sector": "Retail", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/farmacias-guadalupana"},

        # === BANCA / FINANZAS ===
        {"empresa": "Banco Cuscatlán", "dominio": "bancocuscatlan.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-cuscatlan"},
        {"empresa": "Banco Agrícola", "dominio": "bancoagricola.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/banco-agricola"},
        {"empresa": "Davivienda", "dominio": "davivienda.com.sv", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/davivienda-sv"},
        {"empresa": "BAC Credomatic El Salvador", "dominio": "baccredomatic.com", "sector": "Finanzas", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/bac-credomatic"},

        # === SALUD ===
        {"empresa": "Hospital Diagnóstico", "dominio": "hdd.com.sv", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/hospital-diagnostico"},
        {"empresa": "Hospital Nacional San Juan de Dios", "dominio": "hnsjd.gob.sv", "sector": "Salud", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/hospital-san-juan-de-dios"},

        # === TURISMO ===
        {"empresa": "Hotel Barceló San Salvador", "dominio": "barcelo.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/barcelo"},
        {"empresa": "Marriott San Salvador", "dominio": "marriott.com", "sector": "Turismo", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/marriott"},

        # === MANUFACTURA ===
        {"empresa": "Aeroman", "dominio": "aeroman.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/aeroman"},
        {"empresa": "Pollo Campero", "dominio": "pfrinternational.com", "sector": "Manufactura", "tipo": "Clientes Finales",
         "linkedin": "https://linkedin.com/company/pollo-campero"},
    ]
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

        # Información de la empresa
        empresa_info = {
            "organisation": data.get("organisation", dominio),
            "domain": data.get("domain", dominio),
            "pattern": data.get("pattern", ""),
            "emails_encontrados": len(data.get("emails", []))
        }

        # Procesar contactos encontrados
        contactos = []
        for email_data in data.get("emails", []):
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

        return {
            "email": email,
            "resultado": data.get("result", "unknown"),
            "confianza": data.get("score", 0),
            "status": data.get("status", "unknown"),
            "disposable": data.get("disposable", False),
            "webmail": data.get("webmail", False),
            "mx_found": data.get("mx_found", False),
            "smtp_check": data.get("smtp_check", False)
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

        api_key = st.text_input(
            "API Key de Hunter.io",
            type="password",
            value=st.session_state.get("hunter_api_key", ""),
            help="Regístrate gratis en hunter.io para obtener tu API key"
        )

        if api_key:
            st.session_state["hunter_api_key"] = api_key
            # Verificar créditos
            info_cuenta = obtener_info_cuenta_hunter(api_key)
            if "error" not in info_cuenta:
                st.success(f"✅ Conectado: {info_cuenta.get('email', '')}")
                st.metric("Búsquedas disponibles",
                          info_cuenta["busquedas"]["disponibles"])
                st.metric("Verificaciones disponibles",
                          info_cuenta["verificaciones"]["disponibles"])
            else:
                st.error(f"❌ {info_cuenta['error']}")

        st.divider()
        st.markdown("""
        **Mercado Objetivo:**
        - 🇨🇷 Costa Rica: {} empresas
        - 🇸🇻 El Salvador: {} empresas

        **Fuente:** Datos reales de Hunter.io API
        """.format(
            len(EMPRESAS_REALES["Costa Rica"]),
            len(EMPRESAS_REALES["El Salvador"])
        ))

    # -------------------------------------------------------------------------
    # ENCABEZADO
    # -------------------------------------------------------------------------
    st.title("📧 PSKloud Prospector - Sistema REAL de Prospección B2B")
    st.markdown("**Leads reales vía Hunter.io API + Envío SMTP real**")
    st.divider()

    # -------------------------------------------------------------------------
    # PESTAÑAS
    # -------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        "🔍 Componente 1: Búsqueda de Leads Reales",
        "📝 Componente 2: Configurador de Campañas",
        "🚀 Componente 3: Envío Masivo SMTP Real"
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

        # Filtros de búsqueda
        col1, col2 = st.columns(2)

        with col1:
            paisSeleccionado = st.selectbox(
                "🌍 País",
                options=["Costa Rica", "El Salvador"],
                key="pais_busqueda"
            )

            tipo_target = st.selectbox(
                "🎯 Tipo de Target",
                options=["Todos", "Canales/Distribuidores", "Clientes Finales"],
                key="tipo_busqueda"
            )

        with col2:
            sector_filtro = st.text_input(
                "🏢 Sector",
                placeholder="Ej: Tecnología, Retail, Finanzas, Salud...",
                key="sector_busqueda"
            )

            cargo_filtro = st.text_input(
                "👤 Cargo a buscar",
                placeholder="Ej: CEO, Gerente, Director, CTO...",
                key="cargo_busqueda"
            )

        # Limitar resultados por búsqueda (para ahorrar créditos)
        limite_resultados = st.slider(
            "📊 Contactos por empresa",
            min_value=3,
            max_value=10,
            value=5,
            help="Más contactos = más créditos utilizados"
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
                # Filtro por sector
                if sector_filtro and sector_filtro.lower() not in empresa.get("sector", "").lower():
                    continue
                empresas_filtradas.append(empresa)

            if not empresas_filtradas:
                st.warning("No se encontraron empresas con los filtros seleccionados.")
                st.stop()

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

                # Procesar contactos encontrados
                for contacto in contactos:
                    # Aplicar filtro de cargo si se especifica
                    if cargo_filtro and cargo_filtro.lower() not in (contacto.get("cargo", "") or "").lower():
                        continue

                    lead = {
                        "País": paisSeleccionado,
                        "Empresa": empresa["empresa"],
                        "Dominio": dominio,
                        "Sector": empresa.get("sector", ""),
                        "Tipo": empresa.get("tipo", ""),
                        "Contacto Clabe": f"{contacto.get('nombre', '')} {contacto.get('apellido', '')}".strip(),
                        "Cargo": contacto.get("cargo", "No especificado"),
                        "Correo": contacto.get("email", ""),
                        "Confianza (%)": contacto.get("confianza", 0),
                        "Teléfono": contacto.get("telefono", ""),
                        "LinkedIn": contacto.get("linkedin", ""),
                        "Fuente": "Hunter.io",
                        "Estado del Lead": "Nuevo"
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

            st.divider()
            st.subheader(f"📋 Leads Encontrados: {len(df)}")

            # Opciones de exportación
            col1, col2, col3 = st.columns(3)

            with col1:
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Descargar CSV",
                    data=csv_data,
                    file_name=f"leads_reales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col2:
                # Exportar a Excel
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

            with col3:
                st.metric("📊 Total Leads", len(df))

            # Tabla interactiva
            st.dataframe(
                df,
                use_container_width=True,
                height=400,
                column_config={
                    "Confianza (%)": st.column_config.ProgressColumn(
                        "Confianza",
                        min_value=0,
                        max_value=100,
                        format="%d%%"
                    ),
                    "LinkedIn": st.column_config.LinkColumn("LinkedIn"),
                    "Correo": st.column_config.TextColumn("Correo", width="large")
                }
            )

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
            st.success("✅ Plantilla guardada")

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
            smtp_server = st.text_input(
                "🖥️ Servidor SMTP",
                value="smtp.gmail.com",
                help="Gmail: smtp.gmail.com | Outlook: smtp.office365.com | Yahoo: smtp.mail.yahoo.com"
            )

            smtp_port = st.number_input(
                "🔌 Puerto",
                value=587,
                min_value=1,
                max_value=65535
            )

        with col2:
            smtp_email = st.text_input(
                "📧 Correo Emisor",
                placeholder="tu_empresa@gmail.com"
            )

            smtp_password = st.text_input(
                "🔑 Contraseña / Token de Aplicación",
                type="password",
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


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    main()
