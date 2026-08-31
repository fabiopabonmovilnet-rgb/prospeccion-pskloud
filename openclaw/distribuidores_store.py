"""
Distribuidores Store — SQLite persistence for the Distribuidores/Partners module.
Separate from the OpenClaw/WhatsApp Cliente Final flow.
Database: ./data/prospeccion.db
"""
import os
import json
import sqlite3
from datetime import datetime, date, timedelta
from contextlib import contextmanager

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "prospeccion.db")

# ─── Constants ───
PAISES = {
    "COLOMBIA": {"moneda": "COP", "ciudades": ["Bogota", "Medellin", "Cali", "Barranquilla", "Cartagena"]},
    "EL_SALVADOR": {"moneda": "USD", "ciudades": ["San Salvador", "Santa Ana", "San Miguel"]},
    "COSTA_RICA": {"moneda": "CRC", "ciudades": ["San Jose", "Cartago", "Alajuela", "Heredia"]},
    "NICARAGUA": {"moneda": "NIO", "ciudades": ["Managua", "Leon", "Masaya", "Esteli"]},
    "HONDURAS": {"moneda": "HNL", "ciudades": ["Tegucigalpa", "San Pedro Sula", "La Ceiba", "Choloma", "Comayagua"]},
    "PANAMA": {"moneda": "USD", "ciudades": ["Ciudad de Panamá", "San Miguelito", "Colón", "David", "La Chorrera"]},
}

RUBROS_CONFIG = {
    "Firmas Contables": {
        "queries": [
            "contadores publicos y firmas contables",
            "firma de contadores auditoria",
            "servicios contables tributarios",
            "despacho contable empresas",
        ],
        "keywords": ["contabl", "contador", "auditor", "impuest", "tributar", "firma contable"],
        "cargo": "Socio Contador | Gerente de la Firma",
        "descripcion": "Firmas contables, despachos de auditoría y tributación",
    },
    "Soporte TI": {
        "queries": [
            "soporte tecnico informatico empresas",
            "empresa de soporte tecnico computacion",
            "servicio tecnico outsourcing ti",
            "soporte it infraestructura redes",
        ],
        "keywords": ["soporte tecnico", "soporte it", "informatic", "computacion", "help desk", "outsourcing ti", "servicio tecnico"],
        "cargo": "Gerente de TI | CEO",
        "descripcion": "Empresas de soporte técnico, mantenimiento e infraestructura TI",
    },
    "Integradores POS": {
        "queries": [
            "sistemas punto de venta",
            "software pos restaurantes empresas",
            "integradores facturacion electronica",
            "sistemas de facturacion datafono",
        ],
        "keywords": ["punto de venta", "sistemas pt", "facturacion", "software pt", "integrador comercial"],
        "cargo": "Gerente Comercial | Director de Canal",
        "descripcion": "Integradores de punto de venta, facturación y datafonos",
    },
    "Consultores Fiscales": {
        "queries": [
            "consultoria fiscal tributaria",
            "consultores tributarios impuestos",
            "asesoria fiscal empresas",
            "planificacion fiscal tributaria",
        ],
        "keywords": ["fiscal", "tributar", "impuest", "consultoria fiscal", "auditoria fiscal"],
        "cargo": "Socio Consultor | Director Fiscal",
        "descripcion": "Consultorías fiscales, tributarias y de planificación",
    },
    "Revendedores ERP": {
        "queries": [
            "software erp empresarial",
            "revendedores e implementadores erp",
            "soluciones erp gestion",
            "sistemas de gestion contable empresas",
        ],
        "keywords": ["erp", "gestion empresarial", "software contable", "sistemas de gestion", "automatizacion empresarial", "implementadores"],
        "cargo": "Partner Manager | Gerente Comercial",
        "descripcion": "Revendedores e implementadores de ERP / software de gestión",
    },
}

RUBROS_DISTRIBUIDORES = list(RUBROS_CONFIG.keys())

# Tope global semanal en modo "Todos los países": reparto entre países activos
META_TOTAL_SEMANAL = 40

# Plantillas de correo por rubro (Contexto + Encaje). Variables {{nombre}}, {{empresa}}, {{pais}}.
PLANTILLAS_DISTRIBUIDOR = {
    "CTX_DISTRIBUIDOR_Firma_Contable": {
        "rubro": "Firmas Contables",
        "asunto": "Alianza PSKloud para distribuir software contable en {{pais}}",
        "cuerpo": """Hola {{nombre}},

Vi que en {{empresa}} ofrecen servicios contables y tributarios en {{pais}}. Como parte del ecosistema PSKloud, buscamos socios comerciales que ya atiendan empresas con necesidades de software administrativo, contable y de facturación electrónica.

Creemos que nuestra suite (que cumple las normativas locales y automatiza facturación, inventario y reportes financieros) encaja bien con la cartera de clientes de una firma contable como la suya. Trabajamos con modelos de co-marketing y comisiones por venta.

¿Tendrías 10 minutos esta semana para una llamada corta y evaluamos el encaje?

Saludos cordiales,
Equipo PSKloud — Ventas Internacionales""",
    },
    "CTX_DISTRIBUIDOR_SOporte_TI": {
        "rubro": "Soporte TI",
        "asunto": "Alianza PSKloud para soporte TI y software administrativo en {{pais}}",
        "cuerpo": """Hola {{nombre}},

Me puse en contacto porque en {{empresa}} prestan servicios de soporte técnico e infraestructura en {{pais}}. En PSKloud desarrollamos software administrativo, contable y de facturación electrónica que requiere implementación, migración y soporte continuo por parte de aliados técnicos.

Su perfil de soporte TI encaja perfecto para sumar ingresos recurrentes: nuestros clientes necesitan exactamente el acompañamiento local que ustedes proveen, y nosotros entregamos la licencia del producto y la capacitación de base.

¿Tendrías 10 minutos esta semana para que conversemos y evaluemos una alianza?

Saludos cordiales,
Equipo PSKloud — Ventas Internacionales""",
    },
    "CTX_DISTRIBUIDOR_POS": {
        "rubro": "Integradores POS",
        "asunto": "Alianza PSKloud para integradores POS en {{pais}}",
        "cuerpo": """Hola {{nombre}},

Veo que en {{empresa}} integran sistemas de punto de venta en {{pais}}. En PSKloud tenemos una suite administrativa y de facturación electrónica que complementa el POS: control de inventario, contabilidad y facturación que cumple las normativas locales.

Para un integrador como ustedes, representa una ampliación natural de su portafolio y una fuente de margen recurrente, porque nuestros clientes necesitan el mismo tipo de implantación y soporte que ustedes ya hacen.

¿Tendrías 10 minutos esta semana para conversar y ver si hay fit?

Saludos cordiales,
Equipo PSKloud — Ventas Internacionales""",
    },
    "CTX_DISTRIBUIDOR_ERP": {
        "rubro": "Revendedores ERP",
        "asunto": "Alianza PSKloud para revendedor ERP en {{pais}}",
        "cuerpo": """Hola {{nombre}},

Me contacté con ustedes porque en {{empresa}} implementan soluciones ERP y de gestión en {{pais}}. PSKloud ofrece una suite administrativa-contable con facturación electrónica nativa, pensada para las pymes de la región y con canal de revendedores.

Su experiencia en implantación de ERP encaja con nuestro modelo: nosotros aportamos el producto y la habilitación técnica, y ustedes la venta, implementación y soporte local con unidades recurrentes.

¿Tendrías 10 minutos esta semana para evaluar una alianza comercial?

Saludos cordiales,
Equipo PSKloud — Ventas Internacionales""",
    },
    "CTX_DISTRIBUIDOR_Consultor": {
        "rubro": "Consultores Fiscales",
        "asunto": "Alianza PSKloud con consultoría fiscal en {{pais}}",
        "cuerpo": """Hola {{nombre}},

Vi que en {{empresa}} brindan consultoría fiscal y tributaria en {{pais}}. En PSKloud desarrollamos software administrativo y de facturación electrónica que cumple las exigencias fiscales locales, y buscamos consultores aliados que recomienden la suite a sus clientes.

Para un consultor fiscal, es una herramienta que les facilita el trabajo: reportes financieros confiables, facturación a la norma y control de inventario, con un modelo de contraprestación por cada cliente referido o en co-marketing.

¿Tendrías 10 minutos esta semana para conversar sobre un acuerdo?

Saludos cordiales,
Equipo PSKloud — Ventas Internacionales""",
    },
}

PAISES_ACTIVOS_FILE = os.path.join(os.path.dirname(__file__), "data", "dist_paises_activos.json")


def get_paises_activos() -> list:
    try:
        with open(PAISES_ACTIVOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            paises = data.get("paises", [])
            if paises:
                return paises
    except Exception:
        pass
    return list(PAISES.keys())


def set_paises_activos(paises: list) -> dict:
    validos = [str(p) for p in paises if str(p) in PAISES]
    if not validos:
        validos = list(PAISES.keys())
    with open(PAISES_ACTIVOS_FILE, "w", encoding="utf-8") as f:
        json.dump({"paises": validos}, f, ensure_ascii=False, indent=2)
    return {"paises": validos}


def is_pais_activo(pais: str) -> bool:
    return str(pais) in get_paises_activos()


CLASIFICACION_SEMAFORO = ["VERDE", "AMARILLO", "ROJO"]
ESTADO_CONVERSION = [
    "INVESTIGADO",
    "PRECALIFICADO",
    "CONTACTADO",
    "CONVERSACION",
    "REUNION_AGENDADA",
]
CANAL_CONTACTO = ["EMAIL_SMTP", "LINKEDIN", "WHATSAPP_DIRECTO", "LLAMADA"]

# Metas semanales por país (Documento Maestro)
METAS_SEMANALES = {
    "investigados": 40,
    "precalificados": 20,
    "contactados": 20,
    "reuniones": 5,
}


@contextmanager
def _get_conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS distribuidores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa TEXT NOT NULL,
                contacto_nombre TEXT,
                contacto_email TEXT,
                contacto_telefono TEXT,
                pais_target TEXT NOT NULL,
                ciudad TEXT,
                moneda_operativa TEXT NOT NULL,
                tipo_prospecto TEXT NOT NULL DEFAULT 'DISTRIBUIDOR',
                rubro TEXT,
                clasificacion_semaforo TEXT DEFAULT 'AMARILLO',
                canal_contacto TEXT,
                estado_conversion TEXT DEFAULT 'INVESTIGADO',
                notas TEXT,
                website TEXT,
                maps_url TEXT,
                rating TEXT,
                total_reviews TEXT,
                fuente TEXT DEFAULT 'manual',
                client_id TEXT DEFAULT '254eee6c',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(empresa, pais_target)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS distribuidores_actividad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distribuidor_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                accion TEXT NOT NULL,
                detalle TEXT,
                canal TEXT,
                plantilla TEXT,
                usuario TEXT DEFAULT 'sistema',
                created_at TEXT NOT NULL,
                FOREIGN KEY (distribuidor_id) REFERENCES distribuidores(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS distribuidores_cuotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pais_target TEXT NOT NULL,
                semana_iso TEXT NOT NULL,
                meta_investigados INTEGER DEFAULT 40,
                meta_precalificados INTEGER DEFAULT 20,
                meta_contactados INTEGER DEFAULT 20,
                meta_reuniones INTEGER DEFAULT 5,
                log_investigados INTEGER DEFAULT 0,
                log_precalificados INTEGER DEFAULT 0,
                log_contactados INTEGER DEFAULT 0,
                log_reuniones INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(pais_target, semana_iso)
            )
        """)


# ─── CRUD Distribuidores ───

def _now():
    return datetime.now().isoformat()


def _semana_iso():
    return date.today().isocalendar()[:2]  # (year, week)


def _validar_lead(data: dict) -> list:
    """Validate minimum required fields for a real lead. Returns list of errors."""
    errors = []
    empresa = (data.get("empresa") or "").strip()
    pais = (data.get("pais_target") or "").strip()
    if not empresa:
        errors.append("empresa es obligatoria")
    if not pais:
        errors.append("pais_target es obligatorio")
    has_contact = any([
        (data.get("contacto_email") or "").strip(),
        (data.get("contacto_telefono") or "").strip(),
        (data.get("website") or "").strip(),
    ])
    if not has_contact:
        errors.append("Se requiere al menos un medio de contacto (email, teléfono o website)")
    return errors


def crear_distribuidor(data: dict) -> dict:
    errors = _validar_lead(data)
    if errors:
        return {"status": "validation_error", "errors": errors}
    with _get_conn() as conn:
        now = _now()
        pais = data.get("pais_target", "").upper()
        moneda = PAISES.get(pais, {}).get("moneda", "USD")
        cursor = conn.execute("""
            INSERT OR IGNORE INTO distribuidores
            (empresa, contacto_nombre, contacto_email, contacto_telefono,
             pais_target, ciudad, moneda_operativa, tipo_prospecto, rubro,
             clasificacion_semaforo, canal_contacto, estado_conversion,
             notas, website, maps_url, rating, total_reviews, fuente,
             client_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("empresa", ""),
            data.get("contacto_nombre", ""),
            data.get("contacto_email", ""),
            data.get("contacto_telefono", ""),
            pais,
            data.get("ciudad", ""),
            moneda,
            data.get("tipo_prospecto", "DISTRIBUIDOR"),
            data.get("rubro", ""),
            data.get("clasificacion_semaforo", "AMARILLO"),
            data.get("canal_contacto", ""),
            data.get("estado_conversion", "INVESTIGADO"),
            data.get("notas", ""),
            data.get("website", ""),
            data.get("maps_url", ""),
            data.get("rating", ""),
            data.get("total_reviews", ""),
            data.get("fuente", "manual"),
            data.get("client_id", "254eee6c"),
            now, now,
        ))
        if cursor.rowcount > 0:
            _registrar_actividad(conn, cursor.lastrowid, "CREADO", f"Prospecto creado: {data.get('empresa', '')}")
            _actualizar_cuota(conn, pais)
            return {"id": cursor.lastrowid, "status": "created"}
        return {"id": None, "status": "exists"}


def listar_distribuidores(pais: str = None, estado: str = None, semaforo: str = None, limit: int = 200) -> list:
    with _get_conn() as conn:
        query = "SELECT * FROM distribuidores WHERE 1=1"
        params = []
        if pais:
            query += " AND pais_target = ?"
            params.append(pais.upper())
        if estado:
            query += " AND estado_conversion = ?"
            params.append(estado)
        if semaforo:
            query += " AND clasificacion_semaforo = ?"
            params.append(semaforo)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def actualizar_distribuidor(dist_id: int, data: dict) -> dict:
    with _get_conn() as conn:
        # Fetch current state for comparison
        current = conn.execute("SELECT estado_conversion, canal_contacto, clasificacion_semaforo FROM distribuidores WHERE id = ?", (dist_id,)).fetchone()
        if not current:
            return {"status": "not_found"}
        old_estado = current["estado_conversion"]
        old_semaforo = current["clasificacion_semaforo"]

        sets = []
        params = []
        allowed = [
            "empresa", "contacto_nombre", "contacto_email", "contacto_telefono",
            "pais_target", "ciudad", "rubro", "clasificacion_semaforo",
            "canal_contacto", "estado_conversion", "notas", "website",
        ]
        for k in allowed:
            if k in data:
                sets.append(f"{k} = ?")
                params.append(data[k])
        if not sets:
            return {"status": "no_changes"}
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(dist_id)
        conn.execute(f"UPDATE distribuidores SET {', '.join(sets)} WHERE id = ?", params)

        # Trace state changes with specific activity
        new_estado = data.get("estado_conversion", old_estado)
        new_semaforo = data.get("clasificacion_semaforo", old_semaforo)
        new_canal = data.get("canal_contacto", current["canal_contacto"])

        if new_estado != old_estado:
            detail = f"{old_estado} → {new_estado}"
            if new_canal:
                detail += f" (canal: {new_canal})"
            _registrar_actividad(conn, dist_id, new_estado, detail, new_canal or "")
            # Update cuota counters
            row = conn.execute("SELECT pais_target FROM distribuidores WHERE id = ?", (dist_id,)).fetchone()
            if row:
                _actualizar_cuota(conn, row["pais_target"])
        elif new_semaforo != old_semaforo:
            _registrar_actividad(conn, dist_id, f"SEMAFORO_{new_semaforo}", f"Semáforo cambiado: {old_semaforo} → {new_semaforo}")
        else:
            _registrar_actividad(conn, dist_id, "ACTUALIZADO", json.dumps(data, ensure_ascii=False))

        return {"status": "updated"}


def eliminar_distribuidor(dist_id: int) -> dict:
    with _get_conn() as conn:
        conn.execute("DELETE FROM distribuidores WHERE id = ?", (dist_id,))
        return {"status": "deleted"}


def estadisticas_pais(pais: str = None) -> dict:
    with _get_conn() as conn:
        where = ""
        params = []
        if pais:
            where = "WHERE pais_target = ?"
            params = [pais.upper()]

        total = conn.execute(f"SELECT COUNT(*) as c FROM distribuidores {where}", params).fetchone()["c"]

        by_estado = {}
        for row in conn.execute(
            f"SELECT estado_conversion, COUNT(*) as c FROM distribuidores {where} GROUP BY estado_conversion", params
        ):
            by_estado[row["estado_conversion"]] = row["c"]

        by_semaforo = {}
        for row in conn.execute(
            f"SELECT clasificacion_semaforo, COUNT(*) as c FROM distribuidores {where} GROUP BY clasificacion_semaforo", params
        ):
            by_semaforo[row["clasificacion_semaforo"]] = row["c"]

        by_pais = {}
        for row in conn.execute("SELECT pais_target, COUNT(*) as c FROM distribuidores GROUP BY pais_target"):
            by_pais[row["pais_target"]] = row["c"]

        return {
            "total": total,
            "by_estado": by_estado,
            "by_semaforo": by_semaforo,
            "by_pais": by_pais,
        }


# ─── Cuotas semanales ───

def _actualizar_cuota(conn, pais: str):
    y, w = _semana_iso()
    semana = f"{y}-W{w:02d}"
    now = _now()
    conn.execute("""
        INSERT INTO distribuidores_cuotas (pais_target, semana_iso, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(pais_target, semana_iso) DO UPDATE SET updated_at = ?
    """, (pais, semana, now, now, now))

    # Update counts
    for campo, estado in [
        ("log_investigados", "INVESTIGADO"),
        ("log_precalificados", "PRECALIFICADO"),
        ("log_contactados", "CONTACTADO"),
        ("log_reuniones", "REUNION_AGENDADA"),
    ]:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM distribuidores WHERE pais_target = ? AND estado_conversion = ?",
            (pais, estado)
        ).fetchone()["c"]
        conn.execute(
            f"UPDATE distribuidores_cuotas SET {campo} = ?, updated_at = ? WHERE pais_target = ? AND semana_iso = ?",
            (count, now, pais, semana)
        )


def obtener_cuotas(pais: str = None) -> list:
    with _get_conn() as conn:
        y, w = _semana_iso()
        semana = f"{y}-W{w:02d}"
        if pais:
            rows = conn.execute(
                "SELECT * FROM distribuidores_cuotas WHERE pais_target = ? AND semana_iso = ?",
                (pais.upper(), semana)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM distribuidores_cuotas WHERE semana_iso = ?", (semana,)
            ).fetchall()
        return [dict(r) for r in rows]


def obtener_cuota_con_progreso(pais: str = None) -> dict:
    cuotas = obtener_cuotas(pais)
    resultado = {}
    for c in cuotas:
        p = c["pais_target"]
        resultado[p] = {
            "semana": c["semana_iso"],
            "investigados": {"meta": c["meta_investigados"], "actual": c["log_investigados"]},
            "precalificados": {"meta": c["meta_precalificados"], "actual": c["log_precalificados"]},
            "contactados": {"meta": c["meta_contactados"], "actual": c["log_contactados"]},
            "reuniones": {"meta": c["meta_reuniones"], "actual": c["log_reuniones"]},
        }
    return resultado


def puede_encolar(pais: str, tipo: str = "investigados") -> dict:
    """Check if we can enqueue more leads for this country/type."""
    with _get_conn() as conn:
        y, w = _semana_iso()
        semana = f"{y}-W{w:02d}"
        row = conn.execute(
            "SELECT * FROM distribuidores_cuotas WHERE pais_target = ? AND semana_iso = ?",
            (pais.upper(), semana)
        ).fetchone()
        if not row:
            return {"puede": True, "restantes": METAS_SEMANALES.get(tipo, 40)}
        campo_meta = f"meta_{tipo}"
        campo_log = f"log_{tipo}"
        meta = row[campo_meta] if campo_meta in row.keys() else METAS_SEMANALES.get(tipo, 40)
        actual = row[campo_log] if campo_log in row.keys() else 0
        restantes = max(0, meta - actual)
        return {"puede": restantes > 0, "restantes": restantes, "meta": meta, "actual": actual}


# ─── Actividad ───

def _registrar_actividad(conn, dist_id: int, accion: str, detalle: str = "", canal: str = "", plantilla: str = ""):
    conn.execute("""
        INSERT INTO distribuidores_actividad
        (distribuidor_id, fecha, accion, detalle, canal, plantilla, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (dist_id, date.today().isoformat(), accion, detalle, canal, plantilla, _now()))


def registrar_actividad(dist_id: int, accion: str, detalle: str = "", canal: str = "", plantilla: str = ""):
    with _get_conn() as conn:
        _registrar_actividad(conn, dist_id, accion, detalle, canal, plantilla)
        if accion in ("CONTACTADO", "PRECALIFICADO", "CONVERSACION", "REUNION_AGENDADA"):
            row = conn.execute("SELECT pais_target FROM distribuidores WHERE id = ?", (dist_id,)).fetchone()
            if row:
                _actualizar_cuota(conn, row["pais_target"])


def listar_actividad(pais: str = None, limit: int = 100) -> list:
    with _get_conn() as conn:
        query = """
            SELECT a.*, d.empresa, d.pais_target
            FROM distribuidores_actividad a
            JOIN distribuidores d ON a.distribuidor_id = d.id
            WHERE 1=1
        """
        params = []
        if pais:
            query += " AND d.pais_target = ?"
            params.append(pais.upper())
        query += " ORDER BY a.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ─── Analytics ───

def analytics_distribuidores() -> dict:
    with _get_conn() as conn:
        stats = estadisticas_pais()

        # Activity by day (last 14 days)
        by_day = []
        rows = conn.execute("""
            SELECT fecha, COUNT(*) as total,
                   SUM(CASE WHEN accion = 'CREADO' THEN 1 ELSE 0 END) as creados,
                   SUM(CASE WHEN accion = 'CONTACTADO' THEN 1 ELSE 0 END) as contactados,
                   SUM(CASE WHEN accion = 'REUNION_AGENDADA' THEN 1 ELSE 0 END) as reuniones
            FROM distribuidores_actividad
            WHERE fecha >= date('now', '-14 days')
            GROUP BY fecha ORDER BY fecha
        """).fetchall()
        by_day = [dict(r) for r in rows]

        # By country
        by_pais = conn.execute("""
            SELECT pais_target,
                   COUNT(*) as total,
                   SUM(CASE WHEN estado_conversion IN ('CONTACTADO','CONVERSACION','REUNION_AGENDADA') THEN 1 ELSE 0 END) as activos,
                   SUM(CASE WHEN clasificacion_semaforo = 'VERDE' THEN 1 ELSE 0 END) as verdes
            FROM distribuidores GROUP BY pais_target
        """).fetchall()

        # By rubro
        by_rubro = conn.execute("""
            SELECT rubro, COUNT(*) as total
            FROM distribuidores WHERE rubro != ''
            GROUP BY rubro ORDER BY total DESC
        """).fetchall()

        # Recent activity
        recent = conn.execute("""
            SELECT a.*, d.empresa, d.pais_target
            FROM distribuidores_actividad a
            JOIN distribuidores d ON a.distribuidor_id = d.id
            ORDER BY a.created_at DESC LIMIT 20
        """).fetchall()

        return {
            "totals": stats,
            "by_day": by_day,
            "by_pais": [dict(r) for r in by_pais],
            "by_rubro": [dict(r) for r in by_rubro],
            "recent_activity": [dict(r) for r in recent],
            "cuotas": obtener_cuota_con_progreso(),
            "metas": METAS_SEMANALES,
        }


# Initialize on import
ensure_db()
