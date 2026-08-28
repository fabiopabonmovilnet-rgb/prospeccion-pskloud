"""
Distribuidores API — FastAPI router for the Distribuidores/Partners module.
Import in main.py and include_router() to mount all /api/dist/* endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import distribuidores_store as store

router = APIRouter(prefix="/api/dist", tags=["distribuidores"])


# ─── Request models ───

class DistribuidorCreate(BaseModel):
    empresa: str
    contacto_nombre: Optional[str] = ""
    contacto_email: Optional[str] = ""
    contacto_telefono: Optional[str] = ""
    pais_target: str
    ciudad: Optional[str] = ""
    rubro: Optional[str] = ""
    clasificacion_semaforo: Optional[str] = "AMARILLO"
    canal_contacto: Optional[str] = ""
    estado_conversion: Optional[str] = "INVESTIGADO"
    notas: Optional[str] = ""
    website: Optional[str] = ""
    maps_url: Optional[str] = ""
    rating: Optional[str] = ""
    total_reviews: Optional[str] = ""
    fuente: Optional[str] = "manual"


class DistribuidorUpdate(BaseModel):
    empresa: Optional[str] = None
    contacto_nombre: Optional[str] = None
    contacto_email: Optional[str] = None
    contacto_telefono: Optional[str] = None
    pais_target: Optional[str] = None
    ciudad: Optional[str] = None
    rubro: Optional[str] = None
    clasificacion_semaforo: Optional[str] = None
    canal_contacto: Optional[str] = None
    estado_conversion: Optional[str] = None
    notas: Optional[str] = None
    website: Optional[str] = None


class ActividadCreate(BaseModel):
    accion: str
    detalle: Optional[str] = ""
    canal: Optional[str] = ""
    plantilla: Optional[str] = ""


class BulkImport(BaseModel):
    leads: list


# ─── Endpoints ───

@router.get("/stats")
def api_dist_stats(pais: str = None):
    stats = store.estadisticas_pais(pais)
    cuotas = store.obtener_cuota_con_progreso(pais)
    return {"stats": stats, "cuotas": cuotas, "metas": store.METAS_SEMANALES}


@router.get("/cuotas")
def api_dist_cuotas(pais: str = None):
    return {"cuotas": store.obtener_cuota_con_progreso(pais)}


@router.get("/cuotas/check")
def api_dist_check_cuota(pais: str, tipo: str = "investigados"):
    return store.puede_encolar(pais, tipo)


@router.get("/list")
def api_dist_list(pais: str = None, estado: str = None, semaforo: str = None, limit: int = 200):
    rows = store.listar_distribuidores(pais, estado, semaforo, limit)
    return {"distribuidores": rows, "count": len(rows)}


@router.post("/create")
def api_dist_create(body: DistribuidorCreate):
    result = store.crear_distribuidor(body.model_dump())
    return result


@router.put("/{dist_id}")
def api_dist_update(dist_id: int, body: DistribuidorUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return store.actualizar_distribuidor(dist_id, data)


@router.delete("/{dist_id}")
def api_dist_delete(dist_id: int):
    return store.eliminar_distribuidor(dist_id)


@router.post("/{dist_id}/actividad")
def api_dist_add_actividad(dist_id: int, body: ActividadCreate):
    store.registrar_actividad(dist_id, body.accion, body.detalle, body.canal, body.plantilla)
    return {"status": "ok"}


@router.get("/actividad")
def api_dist_actividad(pais: str = None, limit: int = 100):
    rows = store.listar_actividad(pais, limit)
    return {"actividad": rows, "count": len(rows)}


@router.get("/analytics")
def api_dist_analytics():
    return store.analytics_distribuidores()


@router.get("/paises")
def api_dist_paises():
    return {"paises": store.PAISES, "rubros": store.RUBROS_DISTRIBUIDORES,
            "rubros_config": store.RUBROS_CONFIG,
            "meta_total_semanal": store.META_TOTAL_SEMANAL,
            "paises_activos": store.get_paises_activos()}


class PaisesActivosBody(BaseModel):
    paises: list


@router.get("/paises/activos")
def api_dist_paises_activos():
    return {"paises_activos": store.get_paises_activos(), "todos": list(store.PAISES.keys())}


@router.post("/paises/activos")
def api_dist_paises_activos_save(body: PaisesActivosBody):
    return store.set_paises_activos(body.paises)


@router.post("/bulk-import")
def api_dist_bulk_import(body: BulkImport):
    created = 0
    skipped = 0
    for lead in body.leads:
        result = store.crear_distribuidor(lead)
        if result.get("status") == "created":
            created += 1
        else:
            skipped += 1
    return {"created": created, "skipped": skipped, "total": len(body.leads)}


# ─── Engine: Auto-Prospecting ───

class EngineStart(BaseModel):
    pais: str = ""  # "" = TODOS los países activos (reparto de META_TOTAL_SEMANAL)
    rubros: Optional[list] = None
    ciudades: Optional[list] = None


@router.post("/engine/start")
def api_engine_start(body: EngineStart):
    from distribuidores_engine import start_engine
    return start_engine(body.pais, body.rubros, body.ciudades)


@router.post("/engine/stop")
def api_engine_stop():
    from distribuidores_engine import stop_engine
    return stop_engine()


@router.get("/engine/status")
def api_engine_status():
    from distribuidores_engine import engine_status
    return engine_status()


@router.get("/engine/log")
def api_engine_log(limit: int = 50):
    from distribuidores_engine import engine_log
    return {"log": engine_log(limit)}
