from __future__ import annotations

import logging
import sys
import threading
import asyncio
from contextlib import asynccontextmanager

import json
import os
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add /app/data to sys.path to load hot-replaced files from volume mount
if "/app/data" not in sys.path:
    sys.path.insert(0, "/app/data")

from models import Lead, EnqueueRequest
from config import settings
from queue_manager import enqueue_leads, get_queue_status, handle_incoming, process_next_batch, load_queue, start_queue_task, get_daily_summary, _ensure_ig_logins, pause_queue, resume_queue, replay_queue, is_queue_paused
from evolution_client import evolution_default
from assistant import chat as assistant_chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("openclaw.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_queue()
    start_queue_task()
    _start_prospector()
    _start_ig_bot()
    logger.info("OpenClaw started (auto-queue active, 20/pais/dia)")
    yield
    logger.info("OpenClaw shutting down")


def _start_prospector():
    """Start the autonomous prospector in a daemon thread."""
    try:
        import prospector
        t = threading.Thread(target=prospector.main, daemon=True)
        t.start()
        logger.info("Prospector worker started")
    except Exception as e:
        logger.error(f"Prospector failed to start: {e}")


def _start_ig_bot():
    """Start IG bot login in a daemon thread."""
    try:
        import asyncio
        from queue_manager import _ensure_ig_logins

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_ensure_ig_logins())
            logger.info("IG bot login initialized")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
    except Exception as e:
        logger.error(f"IG bot failed to start: {e}")


app = FastAPI(title="OpenClaw", version="1.0.0", lifespan=lifespan)

# Serve media files (images, etc.) from data/media/
_media_dir = os.path.join(settings.data_dir, "media")
os.makedirs(_media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_dir), name="media")

# Serve dashboard static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ─── Distribuidores Module ───
try:
    from distribuidores_api import router as dist_router
    app.include_router(dist_router)
    logging.getLogger("distribuidores").info("Distribuidores module loaded")
except Exception as e:
    logging.getLogger("distribuidores").warning(f"Distribuidores module not loaded: {e}")


@app.get("/health")
async def health():
    status = await evolution_default().connection_state()
    return {
        "status": "ok",
        "whatsapp_connected": status is not None and "open" in str(status).lower(),
        "queue": get_queue_status(),
    }


@app.post("/enqueue")
async def enqueue(request: EnqueueRequest):
    count = enqueue_leads(request.leads)
    return {"queued": count, "queue_status": get_queue_status()}


@app.get("/queue")
async def queue_status():
    return get_queue_status()


@app.post("/process-sending")
async def process_sending(count: int = 5):
    result = await process_next_batch(count=count)
    result["queue_status"] = get_queue_status()
    return result


@app.get("/daily-summary")
async def daily_summary():
    return get_daily_summary()


@app.get("/ig/status")
@app.get("/api/ig/status")
async def ig_status():
    from ig_sender import remaining_today
    return {
        "remaining_today": remaining_today(),
        "senders_initialized": len([s for s in _ig_senders_cache()]),
    }


@app.post("/ig/login")
@app.post("/api/ig/login")
async def ig_login():
    await _ensure_ig_logins()
    return {"status": "ok"}


@app.post("/ig/search-and-enqueue")
@app.post("/api/ig/search-and-enqueue")
async def ig_search_enqueue(data: dict):
    """Search IG for leads matching hashtags and enqueue them."""
    client_id = data.get("client_id", "")
    hashtags = data.get("hashtags", [])
    limit = data.get("limit", 5)

    if not client_id or not hashtags:
        return {"error": "client_id and hashtags required", "enqueued": 0}

    from client_store import get_client
    from models import Lead
    from queue_manager import enqueue_leads
    from ig_sender import InstagramSender

    client = get_client(client_id)
    if not client:
        return {"error": "client not found", "enqueued": 0}

    sender = InstagramSender(
        username=client.instagram.instagram_username,
        password=client.instagram.instagram_password,
    )
    if not await sender.ensure_login():
        return {"error": "IG login failed", "enqueued": 0}

    ig_leads = await sender.search_leads(hashtags, max_per_tag=limit)

    leads = []
    for l in ig_leads[:limit]:
        leads.append(Lead(
            nombre=l["username"],
            empresa="",
            rubro=hashtags[0] if hashtags else "",
            pais="",
            ciudad="",
            fuente=f"instagram_{l.get('source', 'hashtag')}",
            client_id=client_id,
        ))

    count = enqueue_leads(leads)
    await sender.close()

    return {"found": len(ig_leads), "enqueued": count}


def _ig_senders_cache():
    try:
        from queue_manager import _ig_senders
        return list(_ig_senders.values())
    except Exception:
        return []


# ─── Dashboard API ───


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard loading...</h1><p>Run setup first.</p>")


@app.get("/assistant", response_class=HTMLResponse)
async def assistant_page():
    html_path = os.path.join(_static_dir, "assistant.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Assistant</h1><p>assistant.html not found.</p>")


@app.get("/campaign", response_class=HTMLResponse)
async def campaign_page():
    html_path = os.path.join(_static_dir, "campaign.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Campaign Center</h1><p>campaign.html not found.</p>")


# ─── CAMPAIGN CENTER ───


@app.get("/api/campaigns")
async def api_campaigns():
    import campaign_store
    return campaign_store.list_campaigns()


@app.post("/api/campaigns")
async def api_campaign_create(data: dict):
    import campaign_store
    client_id = str(data.get("client_id", "")).strip()
    rubro = str(data.get("rubro", "")).strip()
    paises = data.get("paises_objetivo") or []
    if not client_id:
        return JSONResponse(status_code=400, content={"error": "client_id es requerido"})
    if not rubro:
        return JSONResponse(status_code=400, content={"error": "rubro es requerido"})
    if not isinstance(paises, list) or not paises:
        return JSONResponse(status_code=400, content={"error": "paises_objetivo debe ser una lista no vacía"})
    mensajes = data.get("mensajes") or []
    meta = int(data.get("meta_diaria_total", 25) or 25)
    try:
        c = campaign_store.create_campaign(client_id, rubro, paises, mensajes, meta, data.get("image_media"))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"no pude crear la campaña: {e}"})
    return {"status": "ok", "campaign": c}


@app.get("/api/campaigns/{key}")
async def api_campaign(key: str):
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return c


@app.put("/api/campaigns/{key}")
async def api_campaign_save(key: str, data: dict):
    import campaign_store
    st = campaign_store.save_state(key, data)
    return {"status": "ok", "campaign": campaign_store.get_campaign(key)}


@app.post("/api/campaigns/{key}/reset")
async def api_campaign_reset(key: str):
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return campaign_store.reset_campaign(key)


@app.get("/api/campaigns/{key}/messages")
async def api_campaign_messages(key: str):
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return {"messages": c["messages"], "media": c["media"]}


@app.put("/api/campaigns/{key}/messages")
async def api_campaign_save_messages(key: str, data: dict):
    import campaign_store
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return JSONResponse(status_code=400, content={"error": "messages must be a non-empty list"})
    result = campaign_store.save_messages(key, messages)
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=404, content=result)
    return {"status": "ok", "campaign": result}


@app.post("/api/campaigns/{key}/media")
async def api_campaign_media(key: str, file: UploadFile = File(...)):
    import campaign_store
    raw = await file.read()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "empty file"})
    ext = (file.filename or "jpg").rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    result = campaign_store.upload_media(key, raw, ext)
    return {"status": "ok", "url": result["url"], "bytes": result["bytes"]}


@app.delete("/api/campaigns/{key}/media")
async def api_campaign_media_delete(key: str):
    """Elimina la imagen de la campaña: el paso 3 pasa a enviarse solo como texto."""
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return campaign_store.remove_media(key)


@app.get("/api/campaigns/{key}/queue")
async def api_campaign_queue(key: str):
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return campaign_store.queue_by_country(key)


@app.get("/api/campaigns/{key}/activity")
async def api_campaign_activity(key: str, limit: int = 40):
    import campaign_store
    c = campaign_store.get_campaign(key)
    if not c:
        return JSONResponse(status_code=404, content={"error": "campaign not found"})
    return {"activity": campaign_store.recent_activity(limit)}


# ─── UNIFIED DATA (Prospectos + Distribuidores) ───


@app.get("/api/data/all")
async def api_data_all(q: str = ""):
    """Prospectos (conversaciones.db) + distribuidores (prospeccion.db) unificados."""
    import sqlite3
    query = (q or "").strip().lower()
    prospectos = []
    db_path = os.path.join(settings.data_dir, "conversaciones.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT phone, lead_json, status, current_step, classification, started_at, last_reply_at "
                "FROM conversations ORDER BY started_at DESC LIMIT 2000"
            ).fetchall()
            conn.close()
            for r in rows:
                try:
                    lead = json.loads(r["lead_json"])
                except Exception:
                    continue
                item = {
                    "origen": "prospecto",
                    "nombre": lead.get("nombre", ""),
                    "empresa": lead.get("empresa", ""),
                    "pais": lead.get("pais", ""),
                    "ciudad": lead.get("ciudad", ""),
                    "rubro": lead.get("rubro", ""),
                    "telefono": r["phone"],
                    "email": lead.get("email", ""),
                    "canal": "whatsapp" if lead.get("telefono") else "instagram",
                    "estado": r["status"] or "",
                    "clasificacion": r["classification"] or "",
                    "paso": r["current_step"] or 0,
                    "enviado": r["started_at"] or "",
                    "respondio": r["last_reply_at"] or "",
                }
                if not query or any(query in str(v).lower() for v in item.values()):
                    prospectos.append(item)
        except Exception as e:
            logger.error(f"Error reading conversations: {e}")

    distribuidores = []
    try:
        from distribuidores_store import listar_distribuidores as listar_dist
        for d in listar_dist(pais=None, estado=None, semaforo=None, limit=2000):
            item = {
                "origen": "distribuidor",
                "nombre": d.get("nombre", ""),
                "empresa": d.get("empresa", ""),
                "pais": d.get("pais", ""),
                "ciudad": d.get("ciudad", ""),
                "rubro": d.get("rubro", ""),
                "telefono": d.get("telefono", "") or str(d.get("whatsapp", "")) or "",
                "email": d.get("email", ""),
                "canal": "distribuidores",
                "estado": d.get("estado", ""),
                "clasificacion": "",
                "paso": 0,
                "enviado": d.get("created_at", ""),
                "respondio": d.get("last_activity_at", ""),
            }
            if not query or any(query in str(v).lower() for v in item.values()):
                distribuidores.append(item)
    except Exception as e:
        logger.warning(f"distribuidores unavailable: {e}")

    return {
        "prospectos": prospectos,
        "distribuidores": distribuidores,
        "total": len(prospectos) + len(distribuidores),
    }


@app.get("/api/analytics")
async def api_analytics():
    """Unified 365 analytics: daily series, hourly distribution, by country/rubro/city, conversations, corrections."""
    import analytics
    return analytics.build_analytics()


@app.post("/api/assistant/chat")
async def api_assistant_chat(data: dict):
    message = (data.get("message") or "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "message required"})
    session_id = data.get("session_id") or "default"
    try:
        result = await assistant_chat(message, session_id=session_id)
        return result
    except Exception as e:
        logger.error(f"assistant chat error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/assistant/history")
async def api_assistant_history(session_id: str = "default"):
    import assistant
    history = assistant._load_history()
    return [m for m in history if m.get("session", "default") == session_id][-30:]


@app.get("/api/prospector/status")
async def api_prospector_status():
    import prospector
    return prospector.get_status()


@app.post("/api/prospector/pause")
async def api_prospector_pause():
    import prospector
    prospector.pause()
    return {"status": "paused"}


@app.post("/api/prospector/resume")
async def api_prospector_resume():
    import prospector
    prospector.resume()
    return {"status": "resumed"}


@app.post("/api/prospector/rubro")
async def api_prospector_rubro(data: dict):
    rubros = data.get("rubros")
    if not rubros or not isinstance(rubros, list):
        return JSONResponse(status_code=400, content={"error": "rubros must be a non-empty list"})
    import prospector
    prospector.set_rubro(rubros)
    return {"status": "ok", "rubros": rubros}


@app.get("/api/prospector/paises")
async def api_prospector_paises():
    """Retorna países disponibles, activos y la distribución diaria equitativa."""
    import prospector
    cfg = prospector.load_config()
    disponibles = cfg.get("paises_disponibles", {})
    activos = cfg.get("paises_activos") or []
    max_diario = int(cfg.get("max_por_pais_diario", 25))
    distribucion = prospector._distribuir_cupo(activos, max_diario)
    return {
        "disponibles": disponibles,
        "activos": activos,
        "max_diario": max_diario,
        "distribucion": distribucion,
    }


@app.post("/api/prospector/paises")
async def api_prospector_paises_update(data: dict):
    """Actualiza los países activos de prospección en la config."""
    import prospector
    activos = data.get("activos") or []
    validos = set(prospector.load_config().get("paises_disponibles", {}).keys())
    activos = [a for a in activos if a in validos]
    cfg = prospector.load_config()
    cfg["paises_activos"] = activos
    result = prospector.save_config(cfg)
    if not result.get("ok"):
        return JSONResponse(status_code=500, content={"error": result.get("error", "error")})
    max_diario = int(cfg.get("max_por_pais_diario", 25))
    distribucion = prospector._distribuir_cupo(activos, max_diario)
    return {"status": "ok", "activos": activos, "max_diario": max_diario, "distribucion": distribucion}


# ─── Queue Play / Stop / Replay controls ───

@app.post("/api/queue/play")
async def api_queue_play():
    """Resume queue processing (Play button)."""
    resume_queue()
    return {"status": "resumed", "queue_status": get_queue_status()}


@app.post("/api/queue/stop")
async def api_queue_stop():
    """Stop queue processing immediately (Stop button)."""
    pause_queue()
    return {"status": "stopped", "queue_status": get_queue_status()}


@app.post("/api/queue/replay")
async def api_queue_replay():
    """Reload queue from disk and resume (Replay button)."""
    count = replay_queue()
    return {"status": "reloaded", "leads_loaded": count, "queue_status": get_queue_status()}


@app.get("/api/activity-log")
async def api_activity_log(limit: int = 100):
    """Return recent prospector activity log entries."""
    import prospector
    entries = []
    if os.path.exists(prospector.ACTIVITY_LOG):
        try:
            with open(prospector.ACTIVITY_LOG, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
    return entries[-limit:]


@app.get("/api/historical")
async def api_historical(days: int = 7):
    """Return aggregated historical data from reports + real per-day activity."""
    import prospector
    from datetime import date, timedelta
    reports = []
    report_path = prospector.REPORT_PATH
    if report_path.exists():
        try:
            with open(report_path) as f:
                rpt = json.load(f)
                if rpt.get("total_found") or rpt.get("total_enqueued") or rpt.get("ciclo"):
                    reports.append(rpt)
        except Exception:
            pass
    # Also try to load historical report files
    data_dir = settings.data_dir
    pattern = os.path.join(data_dir, "reporte_prospector_*.json")
    import glob
    for fpath in sorted(glob.glob(pattern))[-30:]:
        try:
            with open(fpath) as f:
                rpt = json.load(f)
                if rpt.get("total_found") or rpt.get("total_enqueued") or rpt.get("ciclo"):
                    reports.append(rpt)
        except Exception:
            pass
    # Real per-day activity (la fuente de verdad del scraping de hoy)
    by_day = prospector._activity_by_day()
    if by_day:
        today = date.today().isoformat()
        ciclo = []
        grand_found = 0
        grand_enq = 0
        for d in sorted(by_day, reverse=True):
            r = by_day[d]
            grand_found += r["encontrados"]
            grand_enq += r["encolados"]
            ciclo.append({
                "timestamp": f"{d}T00:00:00",
                "cliente": r["cliente"] or "—",
                "rubro": r["rubro"] or "—",
                "ubicacion": r["ubicacion"] or "—",
                "encontrados": r["encontrados"],
                "con_telefono": r["encontrados"],
                "encolados": r["encolados"],
            })
        ciclo = ciclo[: max(days, 30)]
        reports.insert(0, {
            "timestamp": f"{today}T00:00:00",
            "total_found": grand_found,
            "total_enqueued": grand_enq,
            "ciclo": ciclo,
            "completados": [],
            "fuente": "actividad",
        })
    return {"reports": reports}


@app.get("/api/queue/detail")
async def api_queue_detail():
    """Return detailed queue info for dashboard."""
    from queue_manager import get_queue_status, load_queue
    qs = get_queue_status()
    daily = {}
    try:
        from store import DailyCounter
        daily = DailyCounter.get_all() if hasattr(DailyCounter, 'get_all') else {}
    except Exception:
        pass
    return {
        "queue": qs,
        "daily": daily,
    }


@app.post("/api/contacto/excluir")
async def api_contacto_excluir(data: dict):
    """Mark a phone as wrong contact and remove it from the queue (never re-contact)."""
    from store import exclude_phone
    from queue_manager import remove_from_queue
    phone = (data.get("phone") or "").strip()
    if not phone:
        return JSONResponse(status_code=400, content={"error": "phone required"})
    motivo = (data.get("motivo") or "Contacto equivocado").strip()
    p = exclude_phone(phone, motivo)
    removed = remove_from_queue(p)
    return {"status": "ok", "phone": p, "removed_from_queue": removed}


@app.post("/api/contacto/renombrar")
async def api_contacto_renombrar(data: dict):
    """Fix a contact's name/company in conversations DB and pending queue."""
    from store import rename_contact
    from queue_manager import rename_in_queue
    phone = (data.get("phone") or "").strip()
    if not phone:
        return JSONResponse(status_code=400, content={"error": "phone required"})
    nombre = (data.get("nombre") or "").strip()
    empresa = (data.get("empresa") or "").strip()
    lead = rename_contact(phone, nombre=nombre, empresa=empresa)
    updated = rename_in_queue(phone, nombre=nombre, empresa=empresa)
    return {"status": "ok", "phone": phone, "conversation": lead, "queue_updated": updated}


@app.get("/api/contactos/incorrectos")
async def api_contactos_incorrectos(limit: int = 100):
    """Contactos que el bot detectó como equivocados (disculpa + exclusión automática)."""
    import sqlite3
    from store import get_contactos_excluidos
    db_path = os.path.join(settings.data_dir, "conversaciones.db")
    excluidos = get_contactos_excluidos() or {}
    rows = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            data_rows = conn.execute(
                "SELECT phone, lead_json, status, classification, started_at, last_reply_at "
                "FROM conversations WHERE status = 'excluido' OR classification IN ('contacto_equivocado','excluido') "
                "ORDER BY last_reply_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            conn.close()
            for r in data_rows:
                try:
                    lead = json.loads(r["lead_json"])
                except Exception:
                    lead = {}
                inc = excluidos.get(r["phone"]) or {}
                rows.append({
                    "phone": r["phone"],
                    "nombre": lead.get("nombre") or "",
                    "empresa": lead.get("empresa") or "",
                    "pais": lead.get("pais") or "",
                    "rubro": lead.get("rubro") or "",
                    "ciudad": lead.get("ciudad") or "",
                    "status": r["status"],
                    "classification": r["classification"],
                    "motivo": inc.get("motivo") or "Contacto equivocado",
                    "excluido_en": inc.get("fecha") or r["last_reply_at"] or r["started_at"],
                })
        except Exception as e:
            logger.error(f"Error reading incorrectos: {e}")
    return {"contactos": rows, "count": len(rows)}


# ─── Sent leads API (who was contacted) ───


@app.get("/api/sent")
async def api_sent(limit: int = 500, pais: str = "", estado: str = "", canal: str = ""):
    """Return leads that were contacted (from conversations DB) with reply/classification info."""
    import sqlite3
    db_path = os.path.join(settings.data_dir, "conversaciones.db")
    results = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT phone, lead_json, status, current_step, classification, started_at, last_reply_at "
                "FROM conversations ORDER BY started_at DESC"
            ).fetchall()
            conn.close()
            for r in rows:
                try:
                    lead = json.loads(r["lead_json"])
                except Exception:
                    continue
                p = lead.get("pais", "") or ""
                if pais and p != pais:
                    continue
                st = r["status"] or ""
                if estado and st != estado:
                    continue
                if canal:
                    if canal == "whatsapp" and not lead.get("telefono"):
                        continue
                    if canal == "instagram" and not lead.get("instagram_username"):
                        continue
                results.append({
                    "nombre": lead.get("nombre", ""),
                    "empresa": lead.get("empresa", ""),
                    "telefono": r["phone"],
                    "pais": p,
                    "rubro": lead.get("rubro", ""),
                    "canal": lead.get("fuente", "").startswith("instagram") and "instagram" or "whatsapp",
                    "estado": st,
                    "classification": r["classification"] or "",
                    "current_step": r["current_step"] or 0,
                    "enviado": r["started_at"] or "",
                    "respondio": r["last_reply_at"] or "",
                })
        except Exception as e:
            logger.error(f"Error reading conversations: {e}")
    return results[-limit:]


@app.get("/api/sent/stats")
async def api_sent_stats():
    """Aggregated stats of who was contacted."""
    import sqlite3
    db_path = os.path.join(settings.data_dir, "conversaciones.db")
    stats = {"total": 0, "por_pais": {}, "por_estado": {}, "por_clasificacion": {}}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT lead_json, status, classification FROM conversations").fetchall()
            conn.close()
            for r in rows:
                try:
                    lead = json.loads(r["lead_json"])
                except Exception:
                    continue
                stats["total"] += 1
                p = lead.get("pais", "") or "Sin país"
                stats["por_pais"][p] = stats["por_pais"].get(p, 0) + 1
                st = r["status"] or "unknown"
                stats["por_estado"][st] = stats["por_estado"].get(st, 0) + 1
                cl = r["classification"] or "sin_reply"
                stats["por_clasificacion"][cl] = stats["por_clasificacion"].get(cl, 0) + 1
        except Exception as e:
            logger.error(f"Error reading conversations stats: {e}")
    return stats


@app.get("/api/messages/latest")
async def api_messages_latest(limit: int = 15):
    """Últimos mensajes OUT enviados por WhatsApp (visual en vivo del panel)."""
    import sqlite3
    db_path = os.path.join(settings.data_dir, "conversaciones.db")
    rows = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            for r in cur.execute(
                "SELECT m.phone, m.text, m.timestamp, m.classification, c.lead_json, c.status, c.current_step "
                "FROM messages m LEFT JOIN conversations c ON c.phone = m.phone "
                "WHERE m.direction='out' ORDER BY m.timestamp DESC LIMIT ?",
                (max(1, min(int(limit), 100),),),
            ):
                try:
                    lead = json.loads(r["lead_json"] or "{}")
                except Exception:
                    lead = {}
                rows.append({
                    "phone": r["phone"],
                    "text": (r["text"] or "").strip()[:600],
                    "timestamp": r["timestamp"],
                    "classification": r["classification"],
                    "status": r["status"],
                    "step": r["current_step"],
                    "nombre": lead.get("nombre") or "",
                    "pais": lead.get("pais") or "",
                    "rubro": lead.get("rubro") or "",
                    "ciudad": lead.get("ciudad") or "",
                })
            conn.close()
        except Exception as e:
            logger.error(f"Error reading latest messages: {e}")
    return {"mensajes": rows, "count": len(rows)}


@app.get("/api/queue/reorder")
async def api_queue_reorder():
    """Reorder the queue by priority order. Focus countries first (Panamá, El Salvador,
    Nicaragua, Costa Rica, Honduras, Colombia), then limited-presence countries
    (Argentina, Chile, Ecuador, Perú, México)."""
    from queue_manager import load_queue, save_queue
    load_queue(force_reload=True)
    country_order = [
        "Panamá", "El Salvador", "Nicaragua", "Costa Rica", "Honduras", "Colombia",
        "Argentina", "Chile", "Ecuador", "Perú", "México",
    ]
    try:
        # Stable sort by the order above; unknown countries go after Panamá
        rank = {c: i for i, c in enumerate(country_order)}
        import queue_manager as qm
        qm._queue.sort(key=lambda e: (
            -qm._rubro_conversion_score(e.get("rubro", "")),  # funnel: rubro que más convierte primero
            rank.get(e.get("pais", ""), len(country_order)),   # y país prioritario dentro del mismo rubro
        ))
        save_queue(force=True)
        return {"status": "ok", "pending": len(qm._queue)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Clients API ───


@app.get("/api/clients")
async def api_list_clients():
    from client_store import list_clients
    clients = list_clients()
    return [c.model_dump() for c in clients]


@app.get("/api/clients/{client_id}")
async def api_get_client(client_id: str):
    from client_store import get_client
    client = get_client(client_id)
    if not client:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return client.model_dump()


@app.put("/api/clients/{client_id}/ig-hashtags")
async def api_update_ig_hashtags(client_id: str, data: dict):
    from client_store import get_client, save_client
    hashtags = data.get("hashtags")
    if not hashtags or not isinstance(hashtags, list):
        return JSONResponse(status_code=400, content={"error": "hashtags must be a non-empty list"})
    client = get_client(client_id)
    if not client:
        return JSONResponse(status_code=404, content={"error": "client not found"})
    client.instagram.ig_hashtags = hashtags
    save_client(client)
    return {"status": "ok", "client_id": client_id, "hashtags": hashtags}


@app.put("/api/clients/{client_id}/ig-dm-config")
async def api_update_ig_dm_config(client_id: str, data: dict):
    """Guardar el mensaje del DM y/o la imagen de presentación de Instagram."""
    from client_store import get_client, save_client, get_template, save_template
    from models import TemplateMessage, MessageTemplateSet

    client = get_client(client_id)
    if not client:
        return JSONResponse(status_code=404, content={"error": "client not found"})

    mensaje = data.get("mensaje", "")
    imagen = data.get("imagen", "")

    # Guardar la imagen en el canal IG del cliente (ruta dentro del contenedor)
    if imagen is not None:
        client.instagram.ig_imagen = imagen
        save_client(client)

    # Guardar el mensaje como template IG (un solo paso de presentación)
    if mensaje is not None and mensaje.strip():
        tpl = get_template(client_id, "instagram")
        new_tpl = TemplateMessage(step=1, text=mensaje.strip(), enabled=True)
        if tpl:
            tpl.messages = [new_tpl]
            save_template(tpl)
        else:
            save_template(MessageTemplateSet(client_id=client_id, channel="instagram", messages=[new_tpl]))

    return {
        "status": "ok",
        "client_id": client_id,
        "mensaje": mensaje,
        "imagen": client.instagram.ig_imagen,
    }


_webhook_msg_ids: set[str] = set()


@app.post("/webhook/evolution")
@app.post("/webhook/evolution/{event_path:path}")
async def webhook_evolution(request: Request, event_path: str = ""):
    """Recibe webhooks de evolution-api, incluyendo sub-rutas de eventos."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    event = body.get("event", event_path.replace("/", ".") if event_path else "")

    if event == "messages.upsert":
        data = body.get("data", {})
        key = data.get("key", {})

        if key.get("fromMe", True):
            return {"ignored": True}

        # Dedup by message id
        msg_id = key.get("id", "")
        if msg_id:
            if msg_id in _webhook_msg_ids:
                return {"ignored": "duplicate"}
            _webhook_msg_ids.add(msg_id)
            if len(_webhook_msg_ids) > 500:
                _webhook_msg_ids.clear()

        remote_jid = key.get("remoteJid", "")
        phone = remote_jid.replace("@s.whatsapp.net", "").replace("@lid", "")

        message_obj = data.get("message", {})
        text = ""
        if "conversation" in message_obj:
            text = message_obj["conversation"]
        elif "extendedTextMessage" in message_obj:
            text = message_obj["extendedTextMessage"].get("text", "")

        sender_name = data.get("pushName", "")

        if text and phone:
            logger.info(f"Incoming from {sender_name} ({phone}): {text[:80]}")
            await handle_incoming(phone, sender_name, text)

    return {"received": True}


# ─── EMAIL CAMPAIGN (migrado desde Streamlit) ───
@app.get("/api/email/config")
async def api_email_config():
    import email_campaign
    cfg = email_campaign.get_config()
    return {k: v for k, v in cfg.items() if k != "password"}


@app.post("/api/email/config")
async def api_email_save(data: dict):
    import email_campaign
    email_campaign.save_config(data)
    return {"status": "ok"}


@app.post("/api/email/test")
async def api_email_test(data: dict):
    import email_campaign
    return email_campaign.test_smtp(data or None)


@app.get("/api/email/plantilla")
async def api_email_plantilla():
    import email_campaign
    return email_campaign.get_plantilla()


@app.post("/api/email/plantilla")
async def api_email_save_plantilla(data: dict):
    import email_campaign
    email_campaign.save_plantilla(data.get("asunto", ""), data.get("cuerpo", ""))
    return {"status": "ok"}


@app.get("/api/email/envios")
async def api_email_envios(dias: int = 30):
    import email_campaign
    return email_campaign.get_envios(dias)


@app.post("/api/email/enviar")
async def api_email_enviar(data: dict):
    """Enviar correo a un solo lead: {email, nombre, empresa, pais, cargo}"""
    import email_campaign
    cfg = email_campaign.get_config()
    plantilla = email_campaign.get_plantilla()
    nombre = data.get("nombre", "")
    empresa = data.get("empresa", "")
    pais = data.get("pais", "")
    cargo = data.get("cargo", "")
    email = data.get("email", "")
    if not email:
        return JSONResponse(status_code=400, content={"error": "email required"})
    asunto = email_campaign.renderizar_plantilla(plantilla.get("asunto", ""), nombre, empresa, pais, cargo, email)
    cuerpo = email_campaign.renderizar_plantilla(plantilla.get("cuerpo", ""), nombre, empresa, pais, cargo, email)
    ok, msg = email_campaign.enviar_correo_real(cfg, email, asunto, cuerpo)
    email_campaign.registrar_envio(email, nombre, empresa, asunto, "ok" if ok else "error", msg)
    return {"ok": ok, "mensaje": msg}


@app.post("/api/email/masivo")
async def api_email_masivo(data: dict):
    """Enviar campaña masiva: {leads: [...], max_enviar: n}"""
    import email_campaign
    leads = data.get("leads", [])
    max_enviar = int(data.get("max_enviar", email_campaign.DAILY_LIMIT))
    if not leads:
        return JSONResponse(status_code=400, content={"error": "leads required"})
    result = email_campaign.enviar_masivo(leads, max_enviar=max_enviar)
    return result


# ─── API SEARCH (migrado desde Streamlit) ───
@app.get("/api/search/keys")
async def api_search_keys():
    import api_search
    keys = api_search.get_keys()
    secretas = ("apollo",)
    return {k: (v if ("key" not in k.lower() or k.endswith("_set")) and k.lower() not in secretas else ("***" if v else "")) for k, v in keys.items()}


@app.post("/api/search/keys")
async def api_search_save_keys(data: dict):
    import api_search
    api_search.save_keys(data)
    return {"status": "ok"}


@app.post("/api/search/apollo/test")
async def api_search_apollo_test(data: dict = None):
    """Valida la key de Apollo.io con una búsqueda de prueba (1 resultado)."""
    import api_search
    data = data or {}
    key = (data.get("api_key") or "").strip()
    if not key:
        keys = api_search.get_keys()
        key = keys.get("apollo") or keys.get("APOLLO_API_KEY") or ""
    if not key:
        return JSONResponse(status_code=400, content={"error": "guarda primero la API key de Apollo o pásala en la petición"})
    res, info = await asyncio.to_thread(api_search.buscar_contactos_apollo, key, "PSKloud", "", "", 1)
    if info.get("error"):
        return {"ok": False, "mensaje": info["error"]}
    extra = info.get("nota", "") or (" (plan con people search)" if not info.get("solo_orgs") else "")
    return {"ok": True, "mensaje": f"Apollo conectado: {info.get('total', 0)} resultado(s){extra}", "info": info}


@app.post("/api/search/empresa")
async def api_search_empresa(data: dict):
    """Buscar contactos por empresa usando fuentes API."""
    import api_search
    empresa = data.get("empresa", "")
    pais = data.get("pais", "")
    cargo = data.get("cargo", "")
    limite = int(data.get("limite", 10))
    fuentes = data.get("fuentes")
    if not empresa:
        return JSONResponse(status_code=400, content={"error": "empresa required"})
    result = await asyncio.to_thread(api_search.buscar_por_empresa, empresa, pais, cargo, limite, fuentes)
    return result


@app.post("/api/search/guardar")
async def api_search_guardar(data: dict):
    import api_search
    leads = data.get("leads", [])
    n = api_search.guardar_resultados(leads)
    return {"status": "ok", "guardados": n}


@app.get("/api/search/resultados")
async def api_search_resultados():
    import api_search
    return {"leads": api_search.cargar_resultados()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
