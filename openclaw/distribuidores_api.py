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


class EnviarCorreosBody(BaseModel):
    ids: list
    plantilla: Optional[str] = ""
    force: Optional[bool] = False


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


@router.post("/enviar-correos")
def api_dist_enviar_correos(body: EnviarCorreosBody):
    """Envía correos SMTP reales a los distribuidores seleccionados (plantilla por rubro).
    force=True re-envía aunque el lead ya haya recibido correo antes."""
    from distribuidores_engine import enviar_correos_distribuidores
    return enviar_correos_distribuidores(body.ids, body.plantilla, body.force)


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


# ─── Pool Clasificado Endpoints ───

@router.get("/pool")
def api_pool_list(pais: str = None, rubro: str = None, tipo: str = None, estado: str = None, limit: int = 200):
    """Lista leads del pool clasificado con filtros opcionales."""
    from distribuidores_store import listar_pool
    return {"leads": listar_pool(pais, rubro, tipo, estado, limit)}


@router.get("/pool/stats")
def api_pool_stats():
    """Estadísticas del pool clasificado."""
    from distribuidores_store import estadisticas_pool
    return estadisticas_pool()


@router.post("/pool/clean")
def api_pool_clean():
    """Ejecuta limpieza y clasificación del pool desde prospectos_locales.json."""
    from clean_pool import clean_and_classify
    clean_and_classify()
    from distribuidores_store import estadisticas_pool
    return {"status": "ok", "stats": estadisticas_pool()}


@router.post("/pool/enviar-emails")
def api_pool_enviar_emails():
    """Envía emails a todos los leads pendientes del pool (distribuidores + clientes finales)."""
    from distribuidores_store import pendientes_email_pool, actualizar_estado_pool, PLANTILLAS_DISTRIBUIDOR, PLANTILLAS_CLIENTE_FINAL
    import email_campaign

    leads = pendientes_email_pool()
    cfg = email_campaign.get_config()
    if not (cfg.get("host") and cfg.get("user") and cfg.get("password")):
        return {"error": "SMTP no configurado"}

    resultados = {"enviados": 0, "fallidos": 0, "detalles": []}

    for lead in leads:
        nombre = lead.get("nombre", "")
        empresa = lead.get("nombre", "")
        pais = lead.get("pais", "")
        email = lead.get("email", "")

        # Seleccionar plantilla según tipo
        if lead["tipo"] == "DISTRIBUIDOR":
            rubro = lead.get("rubro", "")
            tpl_map = {
                "Firmas Contables": "CTX_DISTRIBUIDOR_Firma_Contable",
                "Soporte TI": "CTX_DISTRIBUIDOR_SOporte_TI",
                "Integradores POS": "CTX_DISTRIBUIDOR_POS",
                "Consultores Fiscales": "CTX_DISTRIBUIDOR_Consultor",
                "Revendedores ERP": "CTX_DISTRIBUIDOR_ERP",
            }
            tpl_key = tpl_map.get(rubro, "CTX_DISTRIBUIDOR_Firma_Contable")
            plantilla = PLANTILLAS_DISTRIBUIDOR.get(tpl_key, {})
        else:
            rubro = lead.get("rubro", "")
            tpl_map = {
                "Restaurantes": "CTX_CLIENTE_Restaurante",
                "Ferreterias": "CTX_CLIENTE_Ferreteria",
            }
            tpl_key = tpl_map.get(rubro, "CTX_CLIENTE_Restaurante")
            plantilla = PLANTILLAS_CLIENTE_FINAL.get(tpl_key, {})

        if not plantilla:
            resultados["fallidos"] += 1
            resultados["detalles"].append({"id": lead["id"], "error": "Sin plantilla"})
            continue

        # Renderizar con parámetros individuales
        asunto = email_campaign.renderizar_plantilla(plantilla.get("asunto", ""), nombre, empresa, pais, "", email)
        cuerpo = email_campaign.renderizar_plantilla(plantilla.get("cuerpo", ""), nombre, empresa, pais, "", email)

        # Enviar
        ok, msg = email_campaign.enviar_correo_real(cfg, email, asunto, cuerpo)
        if ok:
            actualizar_estado_pool(lead["id"], "EMAIL_ENVIADO", "fecha_envio_email")
            resultados["enviados"] += 1
        else:
            actualizar_estado_pool(lead["id"], "EMAIL_FALLIDO")
            resultados["fallidos"] += 1
            resultados["detalles"].append({"id": lead["id"], "error": msg})

    return resultados


@router.post("/pool/encolar-wa")
def api_pool_encolar_wa():
    """Marca leads pendientes de WA (email enviado + tiene teléfono) para cola WhatsApp."""
    from distribuidores_store import pendientes_wa_pool, actualizar_estado_pool

    leads = pendientes_wa_pool()
    for lead in leads:
        actualizar_estado_pool(lead["id"], "ENCOLADO_WA", "fecha_envio_wa")

    return {"encolados": len(leads)}


@router.put("/pool/{pool_id}/estado")
def api_pool_update_estado(pool_id: int, body: dict):
    """Actualiza estado de un lead del pool."""
    from distribuidores_store import actualizar_estado_pool
    estado = body.get("estado", "")
    actualizar_estado_pool(pool_id, estado)
    return {"ok": True}


@router.post("/pool/reset")
def api_pool_reset():
    """Limpia todo el pool y re-clasifica desde prospectos_locales.json."""
    from distribuidores_store import limpiar_pool
    from clean_pool import clean_and_classify
    limpiar_pool()
    clean_and_classify()
    from distribuidores_store import estadisticas_pool
    return {"status": "reset_ok", "stats": estadisticas_pool()}
