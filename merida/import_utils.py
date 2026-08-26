"""
PSKloud Prospector — Utilidades de importación de leads
Soporte para CSV, Excel (XLSX), y mapeo automático de columnas.
"""
import pandas as pd
import json
import os
from typing import List, Dict, Tuple, Optional
from datetime import datetime


# Mapeo de columnas comunes en español/inglés a nuestros campos
COLUMN_MAP = {
    # Nombre
    "nombre": "nombre", "name": "nombre", "business_name": "nombre",
    "negocio": "nombre", "empresa": "nombre", "company": "nombre",
    "razon_social": "nombre", "razonsocial": "nombre",
    
    # Rubro
    "rubro": "rubro", "sector": "rubro", "category": "rubro",
    "categoria": "rubro", "industry": "rubro", "giro": "rubro",
    "tipo": "rubro", "type": "rubro", "business_type": "rubro",
    
    # Municipio
    "municipio": "municipio", "municipality": "municipio",
    "city": "municipio", "ciudad": "municipio", "location": "municipio",
    "ubicacion": "municipio", "lugar": "municipio",
    
    # Dirección
    "direccion": "direccion", "address": "direccion",
    "domicilio": "direccion", "ubicación": "direccion",
    
    # Teléfono
    "telefono": "telefono", "phone": "telefono", "tel": "telefono",
    "celular": "telefono", "mobile": "telefono", "whatsapp": "telefono",
    "teléfono": "telefono", "cel": "telefono", "movil": "telefono",
    "phone_number": "telefono", "telefono1": "telefono",
    
    # Email
    "email": "email", "correo": "email", "mail": "email",
    "e-mail": "email", "email1": "email", "correo_electronico": "email",
    
    # Website
    "website": "website", "sitio_web": "website", "web": "website",
    "url": "website", "pagina_web": "website", "site": "website",
    "sitio": "website",
    
    # Estado contacto
    "estado": "estado_contacto", "status": "estado_contacto",
    "estado_contacto": "estado_contacto", "contact_status": "estado_contacto",
    
    # Notas
    "notas": "notas", "notes": "notas", "observaciones": "notas",
    "comentarios": "notas", "comments": "notas",
    
    # Maps URL
    "maps_url": "maps_url", "google_maps": "maps_url",
    "googlemaps": "maps_url", "ubicacion_maps": "maps_url",
    
    # Facebook
    "facebook": "facebook", "fb": "facebook", "pagina_facebook": "facebook",
    
    # Instagram
    "instagram": "instagram", "ig": "instagram",
}


def detectar_formato(filename: str) -> str:
    """Detecta el formato del archivo por extensión."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return "csv"
    elif ext in [".xlsx", ".xls"]:
        return "excel"
    elif ext == ".json":
        return "json"
    return "unknown"


def leer_archivo(file_obj, filename: str) -> pd.DataFrame:
    """Lee un archivo CSV, Excel o JSON y retorna un DataFrame."""
    fmt = detectar_formato(filename)
    
    if fmt == "csv":
        # Intentar diferentes encodings
        for encoding in ["utf-8", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                file_obj.seek(0)
                return pd.read_csv(file_obj, encoding=encoding)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        raise ValueError("No se pudo leer el archivo CSV con ningún encoding estándar")
    
    elif fmt == "excel":
        file_obj.seek(0)
        return pd.read_excel(file_obj, engine="openpyxl")
    
    elif fmt == "json":
        file_obj.seek(0)
        data = json.load(file_obj)
        if isinstance(data, list):
            return pd.DataFrame(data)
        elif isinstance(data, dict):
            return pd.DataFrame([data])
        raise ValueError("El JSON debe contener una lista de objetos")
    
    else:
        raise ValueError(f"Formato no soportado: {filename}")


def mapear_columnas(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Mapea columnas del DataFrame a nuestros campos estándar.
    Soporta mapeo exacto y por substrings (ej: "nombre de la empresa" → "nombre").
    Retorna (DataFrame mapeado, diccionario de mapeo aplicado).
    """
    mapeo_aplicado = {}
    columnas_mapeadas = {}

    # Substring matching: si la columna contiene estas palabras clave → campo destino
    SUBSTR_MAP = [
        ("nombre", "nombre"), ("empresa", "nombre"), ("negocio", "nombre"),
        ("razon", "nombre"), ("business", "nombre"), ("company", "nombre"),
        ("correo", "email"), ("email", "email"), ("e-mail", "email"),
        ("mail", "email"), ("correo_electronico", "email"),
        ("telefono", "telefono"), ("tel", "telefono"), ("celular", "telefono"),
        ("movil", "telefono"), ("whatsapp", "telefono"), ("wa", "telefono"),
        ("numero", "telefono"), ("num", "telefono"),
        ("rubro", "rubro"), ("sector", "rubro"), ("categoria", "rubro"),
        ("giro", "rubro"), ("industry", "rubro"), ("business_type", "rubro"),
        ("municipio", "municipio"), ("ciudad", "municipio"), ("city", "municipio"),
        ("localidad", "municipio"), ("location", "municipio"),
        ("direccion", "direccion"), ("address", "direccion"), ("domicilio", "direccion"),
        ("website", "website"), ("sitio", "website"), ("web", "website"),
        ("url", "website"),
        ("instagram", "instagram"), ("facebook", "facebook"),
        ("notas", "notas"), ("observaciones", "notas"), ("comentarios", "notas"),
    ]

    for col in df.columns:
        col_lower = col.lower().strip().replace(" ", "_").replace("-", "_").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")

        # 1) Exact match first
        if col_lower in COLUMN_MAP:
            target = COLUMN_MAP[col_lower]
            columnas_mapeadas[col] = target
            mapeo_aplicado[col] = target
            continue

        # 2) Substring match
        for keyword, target in SUBSTR_MAP:
            if keyword in col_lower and target not in columnas_mapeadas.values():
                columnas_mapeadas[col] = target
                mapeo_aplicado[col] = target
                break

    # Renombrar columnas mapeadas
    df_mapeado = df.rename(columns=columnas_mapeadas)

    return df_mapeado, mapeo_aplicado


def normalizar_leads_importados(df: pd.DataFrame) -> List[Dict]:
    """
    Normaliza un DataFrame de leads importados al formato estándar.
    """
    from phone_utils import normalizar_telefono_ve
    
    leads = []
    
    for _, row in df.iterrows():
        lead = {}
        
        # Copiar todas las columnas mapeadas
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                val = ""
            else:
                val = str(val).strip()
            lead[col] = val
        
        # Normalizar teléfono
        if lead.get("telefono"):
            lead["telefono"] = normalizar_telefono_ve(lead["telefono"])
        
        # Asegurar campos obligatorios
        lead.setdefault("nombre", "")
        lead.setdefault("rubro", "")
        lead.setdefault("municipio", "")
        lead.setdefault("direccion", "")
        lead.setdefault("telefono", "")
        lead.setdefault("email", "")
        lead.setdefault("website", "")
        lead.setdefault("notas", "")
        lead.setdefault("estado_contacto", "No Contactado")
        lead.setdefault("fuente", "importacion_manual")
        lead.setdefault("fecha_creacion", datetime.now().isoformat())
        
        # Generar ID único basado en nombre + ubicación
        if not lead.get("place_id"):
            key = f"{lead['nombre']}_{lead.get('municipio', '')}".lower().strip()
            lead["place_id"] = f"import_{hash(key) & 0xFFFFFFFF:08x}"
        
        # Agregar WhatsApp URL si hay teléfono
        if lead.get("telefono") and len(lead["telefono"]) >= 12:
            from urllib.parse import quote
            msg = f"Hola, buenos días. Me comunico desde PSKloud."
            lead["whatsapp_url"] = f"https://wa.me/{lead['telefono'][1:]}?text={quote(msg)}"
        
        leads.append(lead)
    
    return leads


def importar_leads(file_obj, filename: str, existing_leads: List[Dict]) -> Tuple[List[Dict], int, Dict]:
    """
    Importa leads desde un archivo.
    
    Retorna: (leads_actualizados, cantidad_nuevos, info_mapeo)
    """
    # Leer archivo
    df = leer_archivo(file_obj, filename)
    
    if df.empty:
        raise ValueError("El archivo está vacío")
    
    # Mapear columnas
    df_mapeado, mapeo = mapear_columnas(df)
    
    # Normalizar leads
    nuevos_leads = normalizar_leads_importados(df_mapeado)
    
    # Dedup contra existentes
    existing_ids = {l.get("place_id", "") for l in existing_leads}
    leads_nuevos = []
    
    for lead in nuevos_leads:
        pid = lead.get("place_id", "")
        if pid and pid not in existing_ids:
            leads_nuevos.append(lead)
            existing_ids.add(pid)
    
    # Combinar
    leads_actualizados = existing_leads + leads_nuevos
    
    info = {
        "total_archivo": len(df),
        "mapeo_columnas": mapeo,
        "nuevos_agregados": len(leads_nuevos),
        "duplicados_omitidos": len(nuevos_leads) - len(leads_nuevos),
        "columnas_originales": list(df.columns),
    }
    
    return leads_actualizados, len(leads_nuevos), info


def generar_plantilla_csv_ejemplo() -> str:
    """Genera un CSV de ejemplo para importación."""
    ejemplo = {
        "nombre": ["Restaurante El Buen Sabor", "Farmacia La Salud", "Hotel Montaña"],
        "rubro": ["Alimentos y bebidas", "Salud", "Turismo"],
        "municipio": ["Libertador", "Alberto Adriani", "Campo Elías"],
        "direccion": ["Av. Principal, Mérida", "Calle 5, Mérida", "Av. Libertador, Mérida"],
        "telefono": ["04141234567", "02742630000", "04241234567"],
        "email": ["info@elbuen.com.ve", "ventas@fasalud.com", "reservas@hotel.com"],
        "website": ["www.elbuen.com.ve", "", "www.hotel.com"],
    }
    df = pd.DataFrame(ejemplo)
    return df.to_csv(index=False)


def generar_plantilla_excel_ejemplo() -> bytes:
    """Genera un Excel de ejemplo para importación."""
    ejemplo = {
        "nombre": ["Restaurante El Buen Sabor", "Farmacia La Salud", "Hotel Montaña"],
        "rubro": ["Alimentos y bebidas", "Salud", "Turismo"],
        "municipio": ["Libertador", "Alberto Adriani", "Campo Elías"],
        "direccion": ["Av. Principal, Mérida", "Calle 5, Mérida", "Av. Libertador, Mérida"],
        "telefono": ["04141234567", "02742630000", "04241234567"],
        "email": ["info@elbuen.com.ve", "ventas@fasalud.com", "reservas@hotel.com"],
        "website": ["www.elbuen.com.ve", "", "www.hotel.com"],
    }
    df = pd.DataFrame(ejemplo)
    import io
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()
