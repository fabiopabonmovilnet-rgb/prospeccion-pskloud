"""
=============================================================================
SISTEMA DE PROSPECCIÓN Y AUTOMATIZACIÓN DE CORREOS EN FRÍO - PSKLOUD
Estilo Apollo.io | Mercado Latinoamérica (Costa Rica & El Salvador)
=============================================================================
Autor: Ingeniero de Software Senior / Growth Hacker
Versión: 1.0.0
Descripción: Sistema modular de generación de leads, configuración de
             campañas y envío masivo de correos de prospección B2B.

INSTALACIÓN:
    pip install streamlit pandas openpyxl

EJECUCIÓN:
    streamlit run app.py
=============================================================================
"""

import streamlit as st
import pandas as pd
import smtplib
import ssl
import time
import random
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional

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
# BASE DE DATOS SIMULADA - DIRECTORIO REALISTA DE EMPRESAS
# Costa Rica y El Salvador - Sectores tecnológicos y comerciales
# =============================================================================
BASE_EMPRESAS: Dict[str, List[Dict]] = {
    "Costa Rica": [
        # -- Canales / Distribuidores --
        {"empresa": "TechDistribution CR", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Carlos", "apellido": "Mendoza", "cargo": "Gerente General", "telefono": "+506 2201-4500"},
             {"nombre": "Laura", "apellido": "Vargas", "cargo": "Director de Ventas", "telefono": "+506 2201-4501"}
         ], "linkedin": "https://linkedin.com/company/techdistribution-cr"},
        {"empresa": "Distribuidora Digital Centroamérica", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Roberto", "apellido": "Quiros", "cargo": "CEO", "telefono": "+506 2220-8800"},
             {"nombre": "María", "apellido": "Fernández", "cargo": "Gerente de Operaciones", "telefono": "+506 2220-8801"}
         ], "linkedin": "https://linkedin.com/company/distribuidora-digital-ca"},
        {"empresa": "Softsol Costa Rica", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Andrés", "apellido": "Calderón", "cargo": "Director Comercial", "telefono": "+506 2256-1100"},
             {"nombre": "Patricia", "apellido": "Solís", "cargo": "Gerente de Canal", "telefono": "+506 2256-1102"}
         ], "linkedin": "https://linkedin.com/company/softsol-cr"},
        {"empresa": "Innovatech Solutions", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Eduardo", "apellido": "Rojas", "cargo": "Gerente General", "telefono": "+506 2290-3300"},
             {"nombre": "Valentina", "apellido": "Arce", "cargo": "Directora de Negocios", "telefono": "+506 2290-3301"}
         ], "linkedin": "https://linkedin.com/company/innovatech-cr"},
        {"empresa": "ConexionTech CR", "sector": "Retail", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Jorge", "apellido": "Castro", "cargo": "CEO", "telefono": "+506 2215-6600"},
             {"nombre": "Daniela", "apellido": "Mora", "cargo": "Gerente de Ventas", "telefono": "+506 2215-6601"}
         ], "linkedin": "https://linkedin.com/company/conexiontech-cr"},
        {"empresa": "Distribuidora Mesoamericana", "sector": "Contadores", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Fernando", "apellido": "Ureña", "cargo": "Director General", "telefono": "+506 2242-7700"},
             {"nombre": "Ana", "apellido": "Campos", "cargo": "Gerente de Producto", "telefono": "+506 2242-7701"}
         ], "linkedin": "https://linkedin.com/company/distribuidora-mesoamericana"},
        # -- Clientes Finales --
        {"empresa": "Retail Corp Costa Rica", "sector": "Retail", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Sergio", "apellido": "Ramírez", "cargo": "Gerente de TI", "telefono": "+506 2234-5500"},
             {"nombre": "Claudia", "apellido": "Villatoro", "cargo": "Directora de Sistemas", "telefono": "+506 2234-5501"}
         ], "linkedin": "https://linkedin.com/company/retail-corp-cr"},
        {"empresa": "Grupo Financiero Centroamericano", "sector": "Finanzas", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Ricardo", "apellido": "Barrantes", "cargo": "Director de Tecnología", "telefono": "+506 2212-9900"},
             {"nombre": "Isabel", "apellido": "Chaves", "cargo": "Gerente de Sistemas", "telefono": "+506 2212-9901"}
         ], "linkedin": "https://linkedin.com/company/grupo-financiero-ca"},
        {"empresa": "Agroindustrias del Valle", "sector": "Agricultura", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Mauricio", "apellido": "Herrera", "cargo": "CEO", "telefono": "+506 2267-4400"},
             {"nombre": "Luciana", "apellido": "Pereira", "cargo": "Gerente Administrativa", "telefono": "+506 2267-4401"}
         ], "linkedin": "https://linkedin.com/company/agroindustrias-valle"},
        {"empresa": "Constructora Horizonte", "sector": "Construcción", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Alfredo", "apellido": "Mesén", "cargo": "Director General", "telefono": "+506 2223-8800"},
             {"nombre": "Gloria", "apellido": "Arias", "cargo": "Gerente de Proyectos", "telefono": "+506 2223-8801"}
         ], "linkedin": "https://linkedin.com/company/constructora-horizonte"},
        {"empresa": "Clínica Santa María", "sector": "Salud", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Dr. Pablo", "apellido": "León", "cargo": "Director Médico", "telefono": "+506 2246-2200"},
             {"nombre": "Karla", "apellido": "Brenes", "cargo": "Gerente Administrativa", "telefono": "+506 2246-2201"}
         ], "linkedin": "https://linkedin.com/company/clinica-santa-maria"},
        {"empresa": "Hotel Paradiso del Caribe", "sector": "Turismo", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Gonzalo", "apellido": "Tencio", "cargo": "Gerente General", "telefono": "+506 2670-1100"},
             {"nombre": "Verónica", "apellido": "Solano", "cargo": "Directora de Operaciones", "telefono": "+506 2670-1101"}
         ], "linkedin": "https://linkedin.com/company/hotel-paradiso-caribe"},
        {"empresa": "Importadora Central", "sector": "Retail", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Héctor", "apellido": "Zúñiga", "cargo": "Gerente de TI", "telefono": "+506 2220-3300"},
             {"nombre": "Natalia", "apellido": "Guillén", "cargo": "Subgerente de Sistemas", "telefono": "+506 2220-3301"}
         ], "linkedin": "https://linkedin.com/company/importadora-central"},
        {"empresa": "Empacadora Rápida", "sector": "Manufactura", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Ronaldo", "apellido": "Chacón", "cargo": "Director de Operaciones", "telefono": "+506 2258-7700"},
             {"nombre": "Melissa", "apellido": "Obando", "cargo": "Gerente de Producción", "telefono": "+506 2258-7701"}
         ], "linkedin": "https://linkedin.com/company/empacadora-rapida"},
        {"empresa": "Transportes Internacionales GT", "sector": "Logística", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Luis", "apellido": "Sandí", "cargo": "CEO", "telefono": "+506 2205-9900"},
             {"nombre": "Adriana", "apellido": "Monge", "cargo": "Gerente de Flota", "telefono": "+506 2205-9901"}
         ], "linkedin": "https://linkedin.com/company/transportes-internacionales"},
    ],
    "El Salvador": [
        # -- Canales / Distribuidores --
        {"empresa": "TecnoSalvador S.A.", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Miguel", "apellido": "Ávalos", "cargo": "Gerente General", "telefono": "+503 2243-5500"},
             {"nombre": "Cindy", "apellido": "Hernández", "cargo": "Directora Comercial", "telefono": "+503 2243-5501"}
         ], "linkedin": "https://linkedin.com/company/tecnosalvador"},
        {"empresa": "DigiCorp El Salvador", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Óscar", "apellido": "Martínez", "cargo": "CEO", "telefono": "+503 2280-1100"},
             {"nombre": "Sandra", "apellido": "Pineda", "cargo": "Gerente de Ventas", "telefono": "+503 2280-1101"}
         ], "linkedin": "https://linkedin.com/company/digicorp-sv"},
        {"empresa": "Red Distribuidora Centroamericana", "sector": "Retail", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Raúl", "apellido": "López", "cargo": "Director General", "telefono": "+503 2225-3300"},
             {"nombre": "Gabriela", "apellido": "Torres", "cargo": "Gerente de Producto", "telefono": "+503 2225-3301"}
         ], "linkedin": "https://linkedin.com/company/red-distribuidora-ca"},
        {"empresa": "Sysoft Solutions", "sector": "Tecnología", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Francisco", "apellido": "Guerrero", "cargo": "Director de Tecnología", "telefono": "+503 2279-8800"},
             {"nombre": "Tatiana", "apellido": "Reyes", "cargo": "Gerente de Implementación", "telefono": "+503 2279-8801"}
         ], "linkedin": "https://linkedin.com/company/sysoft-sv"},
        {"empresa": "MegaTech Distribuciones", "sector": "Contadores", "tipo": "Canales/Distribuidores",
         "contactos": [
             {"nombre": "Ernesto", "apellido": "Guevara", "cargo": "Gerente de Canal", "telefono": "+503 2266-2200"},
             {"nombre": "Ivonne", "apellido": "Cáceres", "cargo": "Directora de Negocios", "telefono": "+503 2266-2201"}
         ], "linkedin": "https://linkedin.com/company/megatech-distribuciones"},
        # -- Clientes Finales --
        {"empresa": "Super Selectos El Salvador", "sector": "Retail", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Juan", "apellido": "Pomata", "cargo": "Gerente de TI", "telefono": "+503 2209-4400"},
             {"nombre": "Beatriz", "apellido": "de López", "cargo": "Directora de Sistemas", "telefono": "+503 2209-4401"}
         ], "linkedin": "https://linkedin.com/company/super-selectos"},
        {"empresa": "Banco Cuscatlán", "sector": "Finanzas", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Alejandro", "apellido": "Díaz", "cargo": "Director de Innovación", "telefono": "+503 2281-6600"},
             {"nombre": "Nancy", "apellido": "Avalos", "cargo": "Gerente de Transformación Digital", "telefono": "+503 2281-6601"}
         ], "linkedin": "https://linkedin.com/company/banco-cuscatlan"},
        {"empresa": "Café Salvaexport", "sector": "Agricultura", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Víctor", "apellido": "Morán", "cargo": "Director General", "telefono": "+503 2275-1100"},
             {"nombre": "Mónica", "apellido": "Eguizabal", "cargo": "Gerente Administrativa", "telefono": "+503 2275-1101"}
         ], "linkedin": "https://linkedin.com/company/cafe-salvaexport"},
        {"empresa": "Constructora Plomo", "sector": "Construcción", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Rodrigo", "apellido": "Arias", "cargo": "CEO", "telefono": "+503 2243-9900"},
             {"nombre": "Lorena", "apellido": "Fuentes", "cargo": "Gerente de Proyectos", "telefono": "+503 2243-9901"}
         ], "linkedin": "https://linkedin.com/company/constructora-plomo"},
        {"empresa": "Hospital Nacional San Juan de Dios", "sector": "Salud", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Dr. Manuel", "apellido": "Aguilar", "cargo": "Director Médico", "telefono": "+503 2223-3300"},
             {"nombre": "Sonia", "apellido": "Velásquez", "cargo": "Gerente Administrativa", "telefono": "+503 2223-3301"}
         ], "linkedin": "https://linkedin.com/company/hospital-san-juan-dios"},
        {"empresa": "Hotel Marriott San Salvador", "sector": "Turismo", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Pedro", "apellido": "Barraza", "cargo": "Gerente General", "telefono": "+503 2278-5500"},
             {"nombre": "Daniela", "apellido": "Rivas", "cargo": "Directora de Operaciones", "telefono": "+503 2278-5501"}
         ], "linkedin": "https://linkedin.com/company/hotel-marriott-sv"},
        {"empresa": "Aeroman S.A.", "sector": "Manufactura", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Fidel", "apellido": "Álvarez", "cargo": "Director de Operaciones", "telefono": "+503 2366-7700"},
             {"nombre": "Karen", "apellido": "Bautista", "cargo": "Gerente de Producción", "telefono": "+503 2366-7701"}
         ], "linkedin": "https://linkedin.com/company/aeroman-sa"},
        {"empresa": "Transportes Pirineos", "sector": "Logística", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Agustín", "apellido": "Palencia", "cargo": "Gerente General", "telefono": "+503 2231-8800"},
             {"nombre": "Rosa", "apellido": "Abarca", "cargo": "Gerente de Flota", "telefono": "+503 2231-8801"}
         ], "linkedin": "https://linkedin.com/company/transportes-pirineos"},
        {"empresa": "Papelería Nacional", "sector": "Retail", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Marvin", "apellido": "Córdova", "cargo": "Gerente de TI", "telefono": "+503 2239-2200"},
             {"nombre": "Anabella", "apellido": "Tobar", "cargo": "Subgerente de Sistemas", "telefono": "+503 2239-2201"}
         ], "linkedin": "https://linkedin.com/company/papeleria-nacional"},
        {"empresa": "Cadena Farmatodo SV", "sector": "Salud", "tipo": "Clientes Finales",
         "contactos": [
             {"nombre": "Leonel", "apellido": "Vega", "cargo": "Director de TI", "telefono": "+503 2298-1100"},
             {"nombre": "Jacqueline", "apellido": "Portillo", "cargo": "Gerente de Sistemas", "telefono": "+503 2298-1101"}
         ], "linkedin": "https://linkedin.com/company/farmatodo-sv"},
    ]
}


# =============================================================================
# FUNCIONES DEL COMPONENTE 1: MOTOR DE BÚSQUEDA Y EXTRACCIÓN DE LEADS
# =============================================================================

def generar_leads(
    pais: str,
    tipo_target: str,
    sector: str,
    cargo_filtro: str
) -> pd.DataFrame:
    """
    Genera una lista de leads basada en los filtros del usuario.
    Utiliza la base de datos simulada para crear registros realistas.

    Args:
        pais: País seleccionado (Costa Rica o El Salvador)
        tipo_target: Tipo de target (Canales/Distribuidores o Clientes Finales)
        sector: Vertical o sector de interés
        cargo_filtro: Cargo del contacto a filtrar

    Returns:
        DataFrame de pandas con los leads generados
    """
    leads = []

    # Obtener empresas del país seleccionado
    empresas_pais = BASE_EMPRESAS.get(pais, [])

    for empresa_data in empresas_pais:
        # Filtrar por tipo de target
        if empresa_data["tipo"] != tipo_target:
            continue

        # Filtrar por sector (búsqueda parcial, insensible a mayúsculas)
        if sector and sector.lower() not in empresa_data["sector"].lower():
            continue

        # Iterar sobre los contactos de cada empresa
        for contacto in empresa_data["contactos"]:
            # Filtrar por cargo si se especifica
            if cargo_filtro and cargo_filtro.lower() not in contacto["cargo"].lower():
                continue

            # Generar correo corporativo (formato: nombre.apellido@empresa.com)
            dominio = empresa_data["empresa"].lower().replace(" ", "").replace(".", "")
            # Limpiar caracteres especiales del dominio
            dominio = re.sub(r'[^a-z0-9]', '', dominio)
            correo = f"{contacto['nombre'].lower()}.{contacto['apellido'].lower()}@{dominio}.com"

            # Construir el lead completo
            lead = {
                "País": pais,
                "Empresa": empresa_data["empresa"],
                "Sector": empresa_data["sector"],
                "Contacto Clave": f"{contacto['nombre']} {contacto['apellido']}",
                "Cargo": contacto["cargo"],
                "Correo Corporativo": correo,
                "Teléfono": contacto["telefono"],
                "LinkedIn Empresa": empresa_data["linkedin"],
                "Estado del Lead": "Nuevo"
            }
            leads.append(lead)

    # Crear DataFrame y retornar
    if not leads:
        return pd.DataFrame(columns=[
            "País", "Empresa", "Sector", "Contacto Clave", "Cargo",
            "Correo Corporativo", "Teléfono", "LinkedIn Empresa", "Estado del Lead"
        ])

    df_leads = pd.DataFrame(leads)
    return df_leads


# =============================================================================
# FUNCIONES DEL COMPONENTE 2: CONFIGURADOR DE CAMPAÑAS Y PLANTILLAS
# =============================================================================

PLANTILLA_POR_DEFECTO = {
    "asunto": "Alianza estratégica en {{pais}} para distribución de software / Oportunidad Operativa",
    "cuerpo": """Hola {{nombre}}, veo que en {{empresa}} lideran el sector. Como Consultor de Ventas Internacionales de PSKloud, estamos expandiendo nuestro ecosistema de soluciones administrativas y facturación electrónica nativa en {{pais}}. Me gustaría evaluar si hace sentido una sinergia con ustedes. ¿Tendrás 10 minutos esta semana?

Saludos cordiales,
Equipo PSKloud
Ventas Internacionales"""
}


def renderizar_plantilla(
    plantilla: str,
    contacto: str,
    empresa: str,
    pais: str,
    cargo: str
) -> str:
    """
    Reemplaza las variables dinámicas en la plantilla con los datos reales del lead.

    Variables disponibles:
        {{nombre}}   -> Nombre del contacto
        {{empresa}}  -> Nombre de la empresa
        {{pais}}     -> País del lead
        {{cargo}}    -> Cargo del contacto

    Args:
        plantilla: Texto de la plantilla con variables
        contacto: Nombre completo del contacto
        empresa: Nombre de la empresa
        pais: País del lead
        cargo: Cargo del contacto

    Returns:
        Texto con las variables reemplazadas
    """
    # Extraer solo el nombre (sin apellido) para un tono más personal
    nombre_solo = contacto.split()[0] if contacto else ""

    resultado = plantilla
    resultado = resultado.replace("{{nombre}}", nombre_solo)
    resultado = resultado.replace("{{empresa}}", empresa)
    resultado = resultado.replace("{{pais}}", pais)
    resultado = resultado.replace("{{cargo}}", cargo)

    return resultado


# =============================================================================
# FUNCIONES DEL COMPONENTE 3: MOTOR DE ENVÍO MASIVO
# =============================================================================

def enviar_correo_smtp(
    servidor: str,
    puerto: int,
    correo_emisor: str,
    contrasena: str,
    correo_receptor: str,
    asunto: str,
    cuerpo: str
) -> bool:
    """
    Envía un correo electrónico utilizando SMTP/TLS.

    Args:
        servidor: Dirección del servidor SMTP
        puerto: Puerto del servidor SMTP
        correo_emisor: Correo electrónico del remitente
        contrasena: Contraseña o token de aplicación
        correo_receptor: Correo del destinatario
        asunto: Asunto del correo
        cuerpo: Cuerpo del mensaje

    Returns:
        True si el envío fue exitoso, False en caso contrario
    """
    try:
        # Crear el mensaje
        mensaje = MIMEMultipart()
        mensaje["From"] = correo_emisor
        mensaje["To"] = correo_receptor
        mensaje["Subject"] = asunto

        # Adjuntar el cuerpo del mensaje
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

        # Establecer conexión segura y enviar
        contexto = ssl.create_default_context()
        with smtplib.SMTP(servidor, puerto) as servidor_smtp:
            servidor_smtp.starttls(context=contexto)
            servidor_smtp.login(correo_emisor, contrasena)
            servidor_smtp.sendmail(correo_emisor, correo_receptor, mensaje.as_string())

        return True

    except Exception as e:
        st.error(f"Error al enviar correo a {correo_receptor}: {str(e)}")
        return False


def simular_envio(
    contacto: str,
    empresa: str,
    asunto: str,
    cuerpo: str
) -> bool:
    """
    Simula el envío de un correo (modo demostración sin conexión SMTP).
    Agrega un tiempo de espera realista para simular el proceso.

    Args:
        contacto: Nombre del contacto
        empresa: Nombre de la empresa
        asunto: Asunto del correo
        cuerpo: Cuerpo del mensaje

    Returns:
        True siempre (simulación exitosa)
    """
    # Simular latencia de red aleatoria (0.5 - 1.5 segundos)
    time.sleep(random.uniform(0.5, 1.5))
    return True


# =============================================================================
# INTERFAZ PRINCIPAL - STREAMLIT
# =============================================================================

def main():
    """
    Función principal que renderiza la interfaz de Streamlit.
    Organiza los 3 componentes en pestañas (tabs).
    """

    # -------------------------------------------------------------------------
    # BARRA LATERAL - Información del sistema
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/email-send.png", width=80)
        st.title("PSKloud Prospector")
        st.caption("Sistema de Prospección B2B | v1.0.0")
        st.divider()
        st.markdown("""
        **Mercado Objetivo:**
        - 🇨🇷 Costa Rica
        - 🇸🇻 El Salvador

        **Sector:** Software Administrativo y Facturación Electrónica

        **Desarrollado por:** PSKloud Ventas Internacionales
        """)
        st.divider()
        st.markdown("### 📊 Estadísticas Rápidas")
        if "df_leads" in st.session_state and not st.session_state.df_leads.empty:
            total = len(st.session_state.df_leads)
            st.metric("Leads Generados", total)
            paises = st.session_state.df_leads["País"].nunique()
            st.metric("Países Activos", paises)
        else:
            st.metric("Leads Generados", 0)
            st.metric("Países Activos", 0)

    # -------------------------------------------------------------------------
    # ENCABEZADO PRINCIPAL
    # -------------------------------------------------------------------------
    st.title("📧 PSKloud Prospector - Sistema de Prospección B2B")
    st.markdown("**Automatización de ventas estilo Apollo.io para Latinoamérica**")
    st.divider()

    # -------------------------------------------------------------------------
    # PESTAÑAS (TABS) - Los 3 Componentes Principales
    # -------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        "🔍 Componente 1: Motor de Búsqueda de Leads",
        "📝 Componente 2: Configurador de Campañas",
        "🚀 Componente 3: Motor de Envío Masivo"
    ])

    # =========================================================================
    # COMPONENTE 1: MOTOR DE BÚSQUEDA Y EXTRACCIÓN DE LEADS
    # =========================================================================
    with tab1:
        st.header("🔍 Motor de Búsqueda y Extracción de Leads")
        st.markdown("Configure los filtros para generar una base de datos de prospectos.")

        # Inicializar session state para leads
        if "df_leads" not in st.session_state:
            st.session_state.df_leads = pd.DataFrame()

        # Filtros de búsqueda en columnas
        col1, col2 = st.columns(2)

        with col1:
            pais_seleccionado = st.selectbox(
                "🌍 País",
                options=["Costa Rica", "El Salvador"],
                index=0,
                help="Seleccione el país de destino para la prospección"
            )

            tipo_target = st.selectbox(
                "🎯 Tipo de Target",
                options=["Canales/Distribuidores", "Clientes Finales"],
                index=0,
                help="Canales: distribuidores y aliados comerciales. Clientes Finales: empresas que consumen software."
            )

        with col2:
            sector_busqueda = st.text_input(
                "🏢 Vertical / Sector",
                placeholder="Ej: Retail, Tecnología, Contadores, Salud...",
                help="Ingrese el sector de interés. Deje vacío para incluir todos los sectores."
            )

            cargo_filtro = st.text_input(
                "👤 Cargo del Contacto",
                placeholder="Ej: CEO, Gerente de TI, Director...",
                help="Filtre por cargo específico. Deje vacío para incluir todos los cargos."
            )

        # Botón de búsqueda
        st.divider()
        btn_buscar, btn_limpiar = st.columns(2)

        with btn_buscar:
            if st.button("🔍 Buscar Leads", type="primary", use_container_width=True):
                with st.spinner("Generando leads... Por favor espere."):
                    # Simular tiempo de procesamiento
                    time.sleep(1)

                    # Generar leads con los filtros aplicados
                    df_resultado = generar_leads(
                        pais=pais_seleccionado,
                        tipo_target=tipo_target,
                        sector=sector_busqueda,
                        cargo_filtro=cargo_filtro
                    )

                    # Guardar en session state
                    st.session_state.df_leads = df_resultado

                    # Mostrar resultado
                    if not df_resultado.empty:
                        st.success(f"✅ Se encontraron **{len(df_resultado)} leads** con los filtros seleccionados.")
                    else:
                        st.warning("⚠️ No se encontraron leads con los filtros seleccionados. Intente con otros parámetros.")

        with btn_limpiar:
            if st.button("🗑️ Limpiar Resultados", use_container_width=True):
                st.session_state.df_leads = pd.DataFrame()
                st.rerun()

        # Mostrar resultados si existen
        if not st.session_state.df_leads.empty:
            st.subheader("📋 Resultados de la Búsqueda")

            # Fila de opciones
            col_export1, col_export2, col_info = st.columns([1, 1, 2])

            with col_export1:
                # Botón de descarga CSV
                csv_data = st.session_state.df_leads.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv_data,
                    file_name=f"leads_pskloud_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col_export2:
                # Botón de descarga Excel
                excel_buffer = pd.ExcelWriter(
                    f"C:\\Users\\fabio\\prospeccion-pskloud\\temp_export.xlsx",
                    engine="openpyxl"
                )
                with excel_buffer:
                    st.session_state.df_leads.to_excel(excel_buffer, index=False, sheet_name="Leads")
                excel_buffer.close()

                with open("C:\\Users\\fabio\\prospeccion-pskloud\\temp_export.xlsx", "rb") as f:
                    excel_bytes = f.read()

                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_bytes,
                    file_name=f"leads_pskloud_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_info:
                st.info(f"📊 Total: **{len(st.session_state.df_leads)}** leads | "
                        f"País: **{pais_seleccionado}** | "
                        f"Target: **{tipo_target}**")

            # Tabla interactiva de leads
            st.dataframe(
                st.session_state.df_leads,
                use_container_width=True,
                height=400,
                column_config={
                    "País": st.column_config.TextColumn("País", width="small"),
                    "Empresa": st.column_config.TextColumn("Empresa", width="medium"),
                    "Sector": st.column_config.TextColumn("Sector", width="small"),
                    "Contacto Clave": st.column_config.TextColumn("Contacto Clave", width="medium"),
                    "Cargo": st.column_config.TextColumn("Cargo", width="medium"),
                    "Correo Corporativo": st.column_config.TextColumn("Correo Corporativo", width="large"),
                    "Teléfono": st.column_config.TextColumn("Teléfono", width="small"),
                    "LinkedIn Empresa": st.column_config.LinkColumn("LinkedIn Empresa", width="large"),
                    "Estado del Lead": st.column_config.TextColumn("Estado", width="small")
                }
            )

    # =========================================================================
    # COMPONENTE 2: CONFIGURADOR DE CAMPAÑAS Y PLANTILLAS
    # =========================================================================
    with tab2:
        st.header("📝 Configurador de Campañas y Plantillas")
        st.markdown("Cree y personalice las plantillas de correo para su campaña de prospección.")

        # Variables disponibles
        with st.expander("ℹ️ Variables Dinámicas Disponibles", expanded=False):
            st.markdown("""
            | Variable | Descripción | Ejemplo |
            |----------|-------------|---------|
            | `{{nombre}}` | Primer nombre del contacto | Carlos |
            | `{{empresa}}` | Nombre de la empresa | TechDistribution CR |
            | `{{pais}}` | País del lead | Costa Rica |
            | `{{cargo}}` | Cargo del contacto | Gerente General |
            """)

        # Configuración de la plantilla
        col_asunto, col_cuerpo = st.columns([1, 2])

        with col_asunto:
            st.subheader("📌 Asunto del Correo")
            asunto_plantilla = st.text_area(
                "Asunto",
                value=PLANTILLA_POR_DEFECTO["asunto"],
                height=80,
                key="asunto_plantilla",
                help="El asunto del correo. Use variables dinámicas para personalizar."
            )

        with col_cuerpo:
            st.subheader("📄 Cuerpo del Correo")
            cuerpo_plantilla = st.text_area(
                "Cuerpo",
                value=PLANTILLA_POR_DEFECTO["cuerpo"],
                height=200,
                key="cuerpo_plantilla",
                help="El cuerpo del correo. Use variables dinámicas para personalizar."
            )

        # Vista previa de la plantilla
        st.divider()
        st.subheader("👁️ Vista Previa de la Plantilla")

        if st.session_state.df_leads is not None and not st.session_state.df_leads.empty:
            # Tomar el primer lead como ejemplo
            primer_lead = st.session_state.df_leads.iloc[0]

            asunto_preview = renderizar_plantilla(
                asunto_plantilla,
                primer_lead["Contacto Clave"],
                primer_lead["Empresa"],
                primer_lead["País"],
                primer_lead["Cargo"]
            )

            cuerpo_preview = renderizar_plantilla(
                cuerpo_plantilla,
                primer_lead["Contacto Clave"],
                primer_lead["Empresa"],
                primer_lead["País"],
                primer_lead["Cargo"]
            )

            # Mostrar vista previa formateada
            with st.container():
                st.markdown(f"""
                <div style="border:1px solid #ddd; border-radius:10px; padding:20px; background-color:#f9f9f9;">
                    <p style="font-size:12px; color:#888;">Vista previa basada en: <strong>{primer_lead['Contacto Clave']}</strong> - {primer_lead['Empresa']}</p>
                    <p style="font-size:14px;"><strong>De:</strong> tu_email@empresa.com</p>
                    <p style="font-size:14px;"><strong>Para:</strong> {primer_lead['Correo Corporativo']}</p>
                    <p style="font-size:14px;"><strong>Asunto:</strong> {asunto_preview}</p>
                    <hr>
                    <p style="font-size:14px; white-space: pre-line;">{cuerpo_preview}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 Genere leads en el Componente 1 para ver la vista previa con datos reales.")

        # Guardar plantilla en session state
        if "plantilla_asunto" not in st.session_state:
            st.session_state.plantilla_asunto = asunto_plantilla
        if "plantilla_cuerpo" not in st.session_state:
            st.session_state.plantilla_cuerpo = cuerpo_plantilla

        if st.button("💾 Guardar Plantilla", type="secondary"):
            st.session_state.plantilla_asunto = asunto_plantilla
            st.session_state.plantilla_cuerpo = cuerpo_plantilla
            st.success("✅ Plantilla guardada exitosamente.")

    # =========================================================================
    # COMPONENTE 3: MOTOR DE ENVÍO MASIVO AUTOMATIZADO
    # =========================================================================
    with tab3:
        st.header("🚀 Motor de Envío Masivo Automatizado")
        st.markdown("Configure sus credenciales SMTP e inicie la campaña de prospección.")

        # -------------------------------------------------------------------------
        # Configuración SMTP
        # -------------------------------------------------------------------------
        st.subheader("⚙️ Configuración de Credenciales SMTP")

        col_smtp1, col_smtp2 = st.columns(2)

        with col_smtp1:
            servidor_smtp = st.text_input(
                "🖥️ Servidor SMTP",
                value="smtp.gmail.com",
                help="Servidor SMTP del proveedor de correo"
            )

            puerto_smtp = st.number_input(
                "🔌 Puerto",
                value=587,
                min_value=1,
                max_value=65535,
                help="Puerto del servidor SMTP (típicamente 587 para TLS)"
            )

        with col_smtp2:
            correo_emisor = st.text_input(
                "📧 Correo Emisor",
                placeholder="tu_empresa@gmail.com",
                help="Correo electrónico desde el cual se enviarán los mensajes"
            )

            contrasena_smtp = st.text_input(
                "🔑 Contraseña / Token de Aplicación",
                type="password",
                help="Contraseña del correo o token de aplicación (recomendado)"
            )

        # -------------------------------------------------------------------------
        # Modo de envío
        # -------------------------------------------------------------------------
        st.divider()
        st.subheader("🎛️ Modo de Envío")

        modo_envio = st.radio(
            "Seleccione el modo de envío:",
            options=["🟢 Simulación (No envía correos reales)", "🔴 Envío Real (SMTP)"],
            index=0,
            help="En modo simulación, el sistema muestra el proceso sin enviar correos reales."
        )

        usar_smtp = "🔴" in modo_envio

        # -------------------------------------------------------------------------
        # Verificación de prerrequisitos
        # -------------------------------------------------------------------------
        st.divider()
        leads_disponibles = (
            "df_leads" in st.session_state
            and not st.session_state.df_leads.empty
        )

        plantilla_configurada = (
            "plantilla_asunto" in st.session_state
            or asunto_plantilla.strip() != ""
        )

        # Mostrar estado de prerrequisitos
        col_check1, col_check2, col_check3 = st.columns(3)

        with col_check1:
            if leads_disponibles:
                st.success(f"✅ Leads: {len(st.session_state.df_leads)} disponibles")
            else:
                st.error("❌ Leads: No hay leads generados")

        with col_check2:
            if plantilla_configurada:
                st.success("✅ Plantilla: Configurada")
            else:
                st.error("❌ Plantilla: No configurada")

        with col_check3:
            if usar_smtp:
                if servidor_smtp and correo_emisor and contrasena_smtp:
                    st.success("✅ SMTP: Configurado")
                else:
                    st.error("❌ SMTP: Faltan credenciales")
            else:
                st.success("✅ Modo: Simulación (sin credenciales)")

        # -------------------------------------------------------------------------
        # Botón de inicio de campaña
        # -------------------------------------------------------------------------
        st.divider()

        if st.button("🚀 Iniciar Campaña de Prospección Masiva", type="primary", use_container_width=True):
            # Validar prerrequisitos
            if not leads_disponibles:
                st.error("⚠️ No hay leads para procesar. Por favor, genere leads en el Componente 1.")
                st.stop()

            # Obtener plantilla activa
            asunto_activo = st.session_state.get("plantilla_asunto", asunto_plantilla)
            cuerpo_activo = st.session_state.get("plantilla_cuerpo", cuerpo_plantilla)

            # Obtener leads
            leads_a_procesar = st.session_state.df_leads.copy()

            # -------------------------------------------------------------------------
            # Iniciar el proceso de envío
            # -------------------------------------------------------------------------
            st.subheader("📡 Progreso de la Campaña")

            # Barra de progreso
            progress_bar = st.progress(0, text="Iniciando campaña...")

            # Contenedor de logs
            log_container = st.container()

            # Estadísticas en tiempo real
            col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
            exitosos = 0
            fallidos = 0

            total_leads = len(leads_a_procesar)

            # Recorrer cada lead y procesar el envío
            for idx, lead in leads_a_procesar.iterrows():
                try:
                    # Actualizar barra de progreso
                    progreso = (idx + 1) / total_leads
                    progress_bar.progress(
                        progreso,
                        text=f"Procesando {idx + 1} de {total_leads}..."
                    )

                    # Renderizar plantilla con datos del lead
                    asunto_renderizado = renderizar_plantilla(
                        asunto_activo,
                        lead["Contacto Clave"],
                        lead["Empresa"],
                        lead["País"],
                        lead["Cargo"]
                    )

                    cuerpo_renderizado = renderizar_plantilla(
                        cuerpo_activo,
                        lead["Contacto Clave"],
                        lead["Empresa"],
                        lead["País"],
                        lead["Cargo"]
                    )

                    # Ejecutar envío según el modo seleccionado
                    if usar_smtp:
                        resultado = enviar_correo_smtp(
                            servidor=servidor_smtp,
                            puerto=puerto_smtp,
                            correo_emisor=correo_emisor,
                            contrasena=contrasena_smtp,
                            correo_receptor=lead["Correo Corporativo"],
                            asunto=asunto_renderizado,
                            cuerpo=cuerpo_renderizado
                        )
                    else:
                        # Modo simulación
                        resultado = simular_envio(
                            contacto=lead["Contacto Clave"],
                            empresa=lead["Empresa"],
                            asunto=asunto_renderizado,
                            cuerpo=cuerpo_renderizado
                        )

                    if resultado:
                        exitosos += 1
                        # Log de éxito
                        with log_container:
                            st.success(
                                f"✉️ **[{idx + 1}/{total_leads}]** Enviando correo a "
                                f"**{lead['Contacto Clave']}** de "
                                f"**{lead['Empresa']}**... "
                                f"{'🟢 ¡Éxito!' if not usar_smtp else '✅ Enviado!'}"
                            )
                    else:
                        fallidos += 1
                        with log_container:
                            st.error(
                                f"❌ **[{idx + 1}/{total_leads}]** Falló envío a "
                                f"**{lead['Contacto Clave']}** de "
                                f"**{lead['Empresa']}**"
                            )

                except Exception as e:
                    # Manejo de excepciones para evitar que el script se caiga
                    fallidos += 1
                    with log_container:
                        st.error(
                            f"⚠️ **[{idx + 1}/{total_leads}]** Error procesando "
                            f"**{lead['Contacto Clave']}**: {str(e)}"
                        )

                # Actualizar estadísticas en tiempo real
                with col_stats1:
                    st.metric("📧 Enviados", exitosos)
                with col_stats2:
                    st.metric("❌ Fallidos", fallidos)
                with col_stats3:
                    st.metric("📊 Tasa de Éxito",
                              f"{(exitosos / (exitosos + fallidos) * 100):.1f}%"
                              if (exitosos + fallidos) > 0 else "0%")
                with col_stats4:
                    st.metric("⏱️ Restantes",
                              max(0, total_leads - (exitosos + fallidos)))

            # -------------------------------------------------------------------------
            # Finalización de la campaña
            # -------------------------------------------------------------------------
            progress_bar.progress(1.0, text="✅ ¡Campaña completada!")

            st.divider()
            st.subheader("📊 Resumen Final de la Campaña")

            # Métricas finales
            col_res1, col_res2, col_res3, col_res4 = st.columns(4)

            with col_res1:
                st.metric("📧 Total Enviados", exitosos)
            with col_res2:
                st.metric("❌ Total Fallidos", fallidos)
            with col_res3:
                tasa_exito = (exitosos / total_leads * 100) if total_leads > 0 else 0
                st.metric("📈 Tasa de Éxito", f"{tasa_exito:.1f}%")
            with col_res4:
                st.metric("📋 Total Procesados", total_leads)

            # Resumen de la campaña
            if exitosos > 0:
                st.success(
                    f"🎉 **Campaña finalizada exitosamente.** "
                    f"Se procesaron **{total_leads}** correos: "
                    f"**{exitosos}** éxitos, **{fallidos}** fallidos."
                )
            else:
                st.warning(
                    f"⚠️ **Campaña finalizada con problemas.** "
                    f"Se procesaron **{total_leads}** correos con **{fallidos}** fallos."
                )

            # Guardar registro de la campaña
            registro_campana = {
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_procesados": total_leads,
                "exitosos": exitosos,
                "fallidos": fallidos,
                "tasa_exito": f"{tasa_exito:.1f}%",
                "modo": "Simulación" if not usar_smtp else "SMTP Real"
            }

            if "historial_campanas" not in st.session_state:
                st.session_state.historial_campanas = []

            st.session_state.historial_campanas.append(registro_campana)

    # -------------------------------------------------------------------------
    # HISTORIAL DE CAMPAÑAS (en la barra lateral)
    # -------------------------------------------------------------------------
    if "historial_campanas" in st.session_state and st.session_state.historial_campanas:
        with st.sidebar:
            st.divider()
            st.markdown("### 📜 Historial de Campañas")
            for i, campana in enumerate(reversed(st.session_state.historial_campanas), 1):
                st.markdown(f"""
                **Campaña #{i}** ({campana['fecha']})
                - Modo: {campana['modo']}
                - Éxitos: {campana['exitosos']}
                - Fallidos: {campana['fallidos']}
                - Tasa: {campana['tasa_exito']}
                """)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    main()
