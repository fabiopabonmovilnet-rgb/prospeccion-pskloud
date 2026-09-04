"""
Importa un CSV de empresas (directorios / Cámara de Comercio / Páginas Amarillas / Apollo web)
como distribuidores contactables (por email y/o teléfono).

Uso dentro del contenedor:
    python /tmp/importar_csv.py /tmp/mi_archivo.csv

El CSV debe tener columnas con nombres reconocibles; se mapean automáticamente.
Los distribuidores se crean con estado INVESTIGADO y canal según email/teléfono.
"""
import sys, csv, json, re

sys.path.insert(0, "/app")
import distribuidores_store as store

PAIS_SINONIMOS = {
    "colombia": "COLOMBIA", "col": "COLOMBIA", "co": "COLOMBIA",
    "el salvador": "EL_SALVADOR", "elsalvador": "EL_SALVADOR", "salvador": "EL_SALVADOR", "sv": "EL_SALVADOR",
    "costa rica": "COSTA_RICA", "costarica": "COSTA_RICA", "cr": "COSTA_RICA",
    "nicaragua": "NICARAGUA", "ni": "NICARAGUA",
    "honduras": "HONDURAS", "hn": "HONDURAS",
    "panama": "PANAMA", "panamá": "PANAMA", "pa": "PANAMA",
}

RUBROS = ["Firmas Contables", "Soporte TI", "Integradores POS", "Consultores Fiscales", "Revendedores ERP"]

RUBRO_KEYWORDS = {
    "Firmas Contables": ["contable", "contador", "contabilidad", "auditor", "contadores", "firma contable", "tributaria"],
    "Soporte TI": ["soporte ti", "soporte tecnico", "soporte it", "informatic", "tecnolog", "help desk", "outsourcing ti", "ti"],
    "Integradores POS": ["punto de venta", "pos", "facturacion", "datafono", "integrador", "cajas registradoras", "sistemas pt"],
    "Consultores Fiscales": ["fiscal", "tributar", "impuest", "consultoria fiscal", "auditoria fiscal", "asesoria fiscal"],
    "Revendedores ERP": ["erp", "gestion empresarial", "software de gestion", "software contable", "implementador", "revendedor", "automatizacion"],
}

def norm_pais(v):
    s = (v or "").strip().lower()
    return PAIS_SINONIMOS.get(s, "")

def norm_rubro(v, empresa=""):
    s = f"{v or ''} {empresa}".lower()
    mejor, mejor_score = "", 0
    for rubro, kws in RUBRO_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in s)
        if score > mejor_score:
            mejor, mejor_score = rubro, score
    return mejor

def clean_email(v):
    e = (v or "").strip().strip("'\"")
    return e

def clean_tel(v):
    t = (v or "").strip().strip("'\" ")
    if not t:
        return ""
    return t

def find_col(header, keys):
    hl = [h.strip().lower() for h in header]
    for k in keys:
        for i, h in enumerate(hl):
            if k in h:
                return i
    return -1

def main(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        raw = list(reader)
    header = raw[0]
    rows = raw[1:]

    idx = {
        "empresa": find_col(header, ["empresa", "nombre", "razon social", "company", "name", "comercial", "negocio"]),
        "email": find_col(header, ["email", "correo", "e-mail", "mail"]),
        "telefono": find_col(header, ["telefono", "tel", "phone", "contacto", "celular", "movil", "cel"]),
        "pais": find_col(header, ["pais", "país", "country"]),
        "ciudad": find_col(header, ["ciudad", "city", "ubicacion"]),
        "rubro": find_col(header, ["rubro", "rubro2", "sector", "industry", "actividad", "giro", "categoria"]),
        "web": find_col(header, ["web", "website", "sitio", "url", "dominio", "pagina"]),
    }
    missing = [k for k, i in idx.items() if i < 0]
    if missing:
        print("AVISO: columnas no encontradas:", missing)
    if idx["empresa"] < 0:
        print("ERROR: falta columna de empresa/nombre")
        return

    created = skipped = invalid = 0
    for r in rows:
        if not any(c.strip() for c in r):
            continue
        def val(key):
            i = idx[key]
            return r[i].strip() if 0 <= i < len(r) else ""
        empresa = val("empresa")
        email = clean_email(val("email"))
        telefono = clean_tel(val("telefono"))
        pais = norm_pais(val("pais"))
        rubro = norm_rubro(val("rubro"), empresa)
        ciudad = val("ciudad")
        web = val("web")

        lead = {
            "empresa": empresa,
            "contacto_email": email,
            "contacto_telefono": telefono,
            "pais_target": pais,
            "ciudad": ciudad,
            "rubro": rubro,
            "website": web,
            "canal_contacto": "EMAIL_SMTP" if email else ("WHATSAPP_DIRECTO" if telefono else ""),
            "estado_conversion": "INVESTIGADO",
            "tipo_prospecto": "DISTRIBUIDOR",
            "fuente": "import_csv",
            "clasificacion_semaforo": "AMARILLO",
            "notas": f"Importado por CSV ({path.split('/')[-1]})",
        }
        res = store.crear_distribuidor(lead)
        if res.get("status") == "created":
            created += 1
        elif res.get("status") == "external":
            skipped += 1
        else:
            invalid += 1
            print(f"  rechazado: {empresa} -> {res}")

    print(f"\n=== RESULTADO IMPORT ===")
    print(f"  creados: {created}")
    print(f"  duplicados/existentes: {skipped}")
    print(f"  inválidos: {invalid}")
    print(f"  total filas: {len(rows)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python importar_csv.py /tmp/archivo.csv")
        sys.exit(1)
    main(sys.argv[1])
