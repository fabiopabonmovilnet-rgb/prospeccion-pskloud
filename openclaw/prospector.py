from __future__ import annotations

import json, logging, os, sys, time, traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import urllib.request, urllib.error

# Activity log for dashboard
ACTIVITY_LOG = "/app/data/actividad_prospector.jsonl"


def _log_activity(kind: str, message: str, data: dict = None):
    try:
        entry = {"ts": datetime.now().isoformat(), "kind": kind, "msg": message}
        if data:
            entry["data"] = data
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [prospector] %(levelname)s: %(message)s",
)
logger = logging.getLogger("prospector")

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
CONFIG_PATH = BASE_DIR / "prospector_config.json"
REPORT_PATH = Path("/app/data") / "reporte_prospector.json"

# Control flags
_prospector_paused = False
_prospector_rubro_override: list[str] | None = None  # None = use client rubros
_prospector_running = False

try:
    from local_search import scrape_local, agregar_prospectos_locales
    from client_store import list_clients
except ImportError as e:
    logger.error(f"Cannot import: {e}")
    sys.exit(1)


def load_config() -> dict:
    cfg = {
        "openclaw_url": "http://openclaw:9000",
        "interval_hours": 24,
        "max_leads_per_search": 20,
        "leads_por_tanda": 10,
        # País -> máximo de leads por rubro. Los países con presencia menor
        # (normativas más lentas) se limitan a ~2 por rubro.
        "limites_por_pais": {
            "Argentina": 2,
            "Chile": 2,
            "Ecuador": 2,
            "Perú": 2,
            "México": 2,
        },
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                file_cfg = json.load(f)
            if isinstance(file_cfg, dict):
                cfg.update({k: v for k, v in file_cfg.items() if k != "_comment"})
        except Exception as e:
            logger.warning(f"No pude leer {CONFIG_PATH}: {e}")
    return cfg


def _pais_de_ubicacion(ubicacion: str) -> str:
    """Extrae el país de una ubicación tipo 'Ciudad, País'."""
    return ubicacion.split(",")[-1].strip() if "," in ubicacion else ubicacion.strip()


def save_config(cfg: dict) -> dict:
    """Persiste la configuración del prospector en prospector_config.json."""
    try:
        existing = load_config()
        existing.update({k: v for k, v in cfg.items()})
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"ok": True, "config": existing}
    except Exception as e:
        logger.error(f"No pude guardar {CONFIG_PATH}: {e}")
        return {"ok": False, "error": str(e)}


def _distribuir_cupo(paises: list, total: int = 25) -> dict:
    """Reparte `total` leads diarios de forma equitativa entre países activos.
    Ej: 25/2 -> {A:13, B:12}; 25/3 -> {A:9, B:8, C:8}."""
    n = len(paises)
    if n == 0:
        return {}
    base = int(total // n)
    residuo = int(total % n)
    cupos = {}
    for i, pais in enumerate(paises):
        cupos[pais] = base + (1 if i < residuo else 0)
    return cupos


def enqueue_to_openclaw(leads: List[Dict], url: str, client_id: str = "",
                        campaign_key: str = "") -> int:
    if not leads:
        return 0
    try:
        from queue_manager import enqueue_leads as local_enqueue
        from models import Lead
        lead_objs = []
        for l in leads:
            l["fuente"] = l.get("fuente_telefono", l.get("fuente", ""))
            l["client_id"] = client_id
            if campaign_key:
                l["campaign_key"] = campaign_key
            lead_objs.append(Lead(**{k: v for k, v in l.items() if k in Lead.model_fields}))
        count = local_enqueue(lead_objs)
        logger.info(f"Direct-enqueued {count} leads to OpenClaw queue")
        return count
    except ImportError:
        pass
    # Fallback: HTTP POST
    payload = {"leads": leads}
    if campaign_key:
        payload["campaign_key"] = campaign_key
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/enqueue",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            queued = result.get("queued", 0)
            logger.info(f"HTTP-enqueued {queued} leads to OpenClaw")
            return queued
    except Exception as e:
        logger.error(f"Error enqueuing to OpenClaw: {e}")
        return 0


def _campaign_search_tasks(client) -> list:
    """Devuelve las tareas de prospección (rubro, ubicacion, campaign_key) para
    UN cliente: cada campaña activa aporta SOLO sus propios rubros en SOLO sus
    propios países/ciudades objetivo. Evita mezclar rubros entre campañas."""
    try:
        from campaign_store import list_campaigns, client_country_cities
    except Exception:
        return []
    tareas: list = []
    geo = client_country_cities()
    for camp in list_campaigns():
        if camp.get("channel") != "whatsapp":
            continue
        if camp.get("client_id") != client.id:
            continue
        if not camp.get("active", True):
            continue
        key = camp.get("key", "")
        paises = camp.get("paises_objetivo") or []
        n = max(1, int(camp.get("cities_per_country", 5)))
        for rubro in (camp.get("rubros") or [camp.get("rubro") or ""]):
            for pais in paises:
                cities = geo.get(pais) or []
                for ciudad in (cities or [pais])[:n]:
                    tareas.append((rubro, f"{ciudad}, {pais}", key))
    return tareas


def run_prospecting_cycle(config: dict, report: dict):
    max_results = config.get("max_leads_per_search", 50)
    openclaw_url = config.get("openclaw_url", "http://openclaw:9000")
    limites_por_pais = config.get("limites_por_pais", {})
    clients = list_clients()

    if not clients:
        logger.warning("No clients configured. Create a client in the dashboard first.")
        return {"timestamp": datetime.now().isoformat(), "total_enqueued": 0, "total_found": 0, "ciclo": [], "completados": []}

    # Cada campaña prospecta SOLO sus propios rubros en SOLO sus propios
    # países/ciudades. Nunca mezclamos rubros dentales con países de otra campaña.
    paises_activos = config.get("paises_activos") or []
    activos_set = set(paises_activos) if paises_activos else None
    limites_por_pais = config.get("limites_por_pais", {})
    if paises_activos:
        # Reparto equitativo del tope diario entre países activos
        cupos_pais = _distribuir_cupo(paises_activos, config.get("max_por_pais_diario", 25))
        limites_por_pais = cupos_pais
        logger.info(f"Países activos: {', '.join(paises_activos)}")
        logger.info(f"Cupo diario por país: {cupos_pais}")

    total_enqueued = 0
    total_found = 0
    ciclo = []
    completados_ok = []
    total_tareas = 0

    for client in clients:
        tareas = _campaign_search_tasks(client)
        if not tareas:
            # Sin campañas definidas: fallback al cliente heredado
            tareas = [(r, u, "") for r in client.rubros for u in client.ubicaciones]
        if activos_set:
            tareas = [t for t in tareas if _pais_de_ubicacion(t[1]) in activos_set]
        if _prospector_rubro_override is not None:
            tareas = [t for t in tareas if t[0] in _prospector_rubro_override]
        total_tareas += len(tareas)

        for rubro, ubicacion, campaign_key in tareas:
            key = f"{client.id}|{campaign_key}|{rubro}|{ubicacion}"
            if cycle_was_done(report, key):
                continue
            pais = _pais_de_ubicacion(ubicacion)
            limite_pais = limites_por_pais.get(pais)
            resultados = []
            try:
                logger.info(f"Buscando {rubro} en {ubicacion}")
                _log_activity("search", f"Buscando {rubro} en {ubicacion} (cliente: {client.name})",
                              {"rubro": rubro, "ubicacion": ubicacion, "cliente": client.name})
                resultados = scrape_local(rubro, ubicacion, max_results=max_results)
                con_telefono = [r for r in resultados if r.get("telefono")]
                if limite_pais:
                    con_telefono = con_telefono[:limite_pais]
                    logger.info(f"  Límite país {pais}: {limite_pais}/rubro -> {len(con_telefono)} leads")
                total_found += len(con_telefono)
                _log_activity("found", f"{len(con_telefono)} teléfonos en {len(resultados)} {rubro} de {ubicacion}",
                              {"encontrados": len(con_telefono), "rubro": rubro, "ubicacion": ubicacion})

                if resultados:
                    guardados = agregar_prospectos_locales(resultados)
                    logger.info(f"  -> {guardados} nuevos en prospectos_locales.json")

                fuentes = {}
                for r in con_telefono:
                    f = r.get("fuente_telefono", "unknown")
                    fuentes[f] = fuentes.get(f, 0) + 1
                src_detail = ", ".join(f"{k}={v}" for k, v in fuentes.items())
                logger.info(f"  {rubro} / {ubicacion}: {len(con_telefono)} con teléfono de {len(resultados)} [{src_detail}]")

                for i in range(0, len(con_telefono), config.get("leads_por_tanda", 20)):
                    tanda = con_telefono[i:i + config.get("leads_por_tanda", 20)]
                    cues = enqueue_to_openclaw(tanda, openclaw_url, client_id=client.id, campaign_key=campaign_key)
                    total_enqueued += cues
                    logger.info(f"  -> Enqueued batch {cues}")

                ciclo.append({
                    "cliente": client.name,
                    "rubro": rubro,
                    "ubicacion": ubicacion,
                    "campaign_key": campaign_key,
                    "encontrados": len(resultados),
                    "con_telefono": len(con_telefono),
                    "encolados": len([r for r in con_telefono if r.get("telefono")]),
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                logger.error(f"Error en {rubro}/{ubicacion}: {e}\n{traceback.format_exc()}")
            # Solo marcar como completado si realmente hubo un intento válido
            # con resultados (evita que un fallo de red/DNS bloquee el rubro 24h).
            if resultados:
                completados_ok.append(key)

    logger.info(f"=== Cycle complete: {total_enqueued} enqueued, {total_found} with phones ===")
    ciclo_data = {
        "timestamp": datetime.now().isoformat(),
        "total_enqueued": total_enqueued,
        "total_found": total_found,
        "ciclo": ciclo,
        "completados": completados_ok,
    }

    # Phase 2: Instagram prospecting for each client
    ig_total = 0
    for client in clients:
        if client.instagram.enabled and client.instagram.ig_hashtags:
            enc = _run_ig_prospecting(client, config, ciclo_data)
            ig_total += enc

    ciclo_data["ig_enqueued"] = ig_total
    logger.info(f"=== IG cycle: {ig_total} leads enqueued ===")
    return ciclo_data


def _normalize_hashtag(value: str) -> str:
    """Strip accents/spaces from a hashtag value for Instagram (IG has no accents)."""
    accented = "áéíóúüñÁÉÍÓÚÜÑ"
    plain = "aeiouunAEIOUUN"
    table = str.maketrans(accented, plain)
    return value.translate(table).replace(" ", "").lower()


def _run_ig_prospecting(client, config: dict, report: dict) -> int:
    """Busca clínicas dentales reales en Instagram, verifica su país visitando el perfil
    y encola 1 lead por país (hasta IG_DAILY_LIMIT DMs/día). El queue manager envía el DM
    (mensaje + imagen + wa.me) a cada lead encolado."""
    import asyncio
    from queue_manager import enqueue_leads
    from ig_sender import InstagramSender
    from models import Lead

    if not client.instagram.ig_hashtags:
        return 0

    # Consultas de búsqueda que devuelven clínicas dentales reales
    consultas = ["clinicas dentales", "clinica dental", "odontologia", "consultorio dental",
                 "dentista", "ortodoncia"]
    max_dm = int(os.getenv("IG_DAILY_LIMIT", "6"))
    orden_paises = ["Colombia", "Nicaragua", "Costa Rica", "Honduras", "Panamá", "El Salvador",
                    "Venezuela", "Ecuador", "Perú", "Guatemala", "México"]

    total = 0
    try:
        sender = InstagramSender(
            username=client.instagram.instagram_username,
            password=client.instagram.instagram_password,
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logged_in = loop.run_until_complete(sender.ensure_login())
        if not logged_in:
            logger.warning(f"IG login failed for {client.name}, skipping IG prospecting")
            return 0

        elegidos = {}  # pais -> lead elegido
        for consulta in consultas:
            if len(elegidos) >= max_dm:
                break
            logger.info(f"IG search: '{consulta}'")
            _log_activity("ig_search", f"Buscando '{consulta}'")
            try:
                leads = loop.run_until_complete(
                    sender.search_leads([consulta], max_per_tag=6)
                )
            except Exception as e:
                logger.error(f"IG search error for '{consulta}': {e}")
                continue

            for l in leads:
                if len(elegidos) >= max_dm:
                    break
                username = l.get("username", "")
                if not username:
                    continue
                if any(username == e.get("nombre") for e in elegidos.values()):
                    continue
                # Verificar país visitando el perfil
                pais = loop.run_until_complete(sender.profile_country(username))
                if not pais or pais in elegidos:
                    continue
                if pais not in orden_paises:
                    continue
                elegidos[pais] = {
                    "username": username,
                    "full_name": l.get("full_name", ""),
                    "pais": pais,
                }
                logger.info(f"  IG: {username} → {pais}")
                _log_activity("ig_found", f"Clínica {username} ({pais})")

        # Encolar 1 por país
        lead_objs = []
        for pais in orden_paises:
            if pais in elegidos:
                e = elegidos[pais]
                lead_objs.append(Lead(
                    nombre=e["username"],
                    empresa=e.get("full_name", ""),
                    rubro=client.instagram.ig_hashtags[0],
                    pais=pais,
                    ciudad=pais,
                    fuente="instagram_clinicas_dentales",
                    client_id=client.id,
                ))
        if lead_objs:
            enc = enqueue_leads(lead_objs)
            total = len(lead_objs)
            logger.info(f"IG prospecting: {enc} leads enqueued (1 por país): {[e['username'] for e in elegidos.values()]}")

        loop.run_until_complete(sender.close())
        logger.info(f"IG prospecting done: {total} lead(s) enqueued (1 por país)")
    except Exception as e:
        logger.error(f"IG prospecting error for {client.name}: {e}")

    return total


def cycle_was_done(report: dict, key: str) -> bool:
    return key in set(report.get("completados", []))


def _is_work_time() -> bool:
    work_days = [int(d.strip()) for d in os.getenv("WORK_DAYS", "0,1,2,3,4,5,6").split(",")]
    hour_start = int(os.getenv("HOUR_START", "8"))
    hour_end = int(os.getenv("HOUR_END", "18"))
    # Use earliest timezone (Costa Rica/El Salvador UTC-6) to ensure we don't miss any country
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Costa_Rica"))
    except Exception:
        now = datetime.now()
    if now.weekday() not in work_days:
        return False
    return hour_start <= now.hour < hour_end


def _sleep_until_work():
    """Sleep until next work time. Returns True if slept, False if already in work time."""
    if _is_work_time():
        return False
    logger.info("Outside work hours. Sleeping until next work period.")
    while not _is_work_time():
        time.sleep(300)
    logger.info("Work hours reached, resuming.")
    return True


# ─── Control functions (thread-safe via module-level flags) ───

def _prospector_pause_file() -> str:
    from config import settings
    return os.path.join(settings.data_dir, "prospector_pause.json")


def _save_prospector_pause():
    try:
        with open(_prospector_pause_file(), "w", encoding="utf-8") as f:
            json.dump({"paused": _prospector_paused}, f)
    except Exception as e:
        logger.error(f"prospector pause persist error: {e}")


def _restore_prospector_pause():
    global _prospector_paused
    try:
        p = _prospector_pause_file()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                _prospector_paused = bool(json.load(f).get("paused", False))
    except Exception as e:
        logger.error(f"prospector pause restore error: {e}")


def pause():
    global _prospector_paused
    _prospector_paused = True
    _save_prospector_pause()
    _log_activity("pause", "Prospector paused by user")
    logger.warning("PROSPECTOR PAUSED")

def resume():
    global _prospector_paused
    _prospector_paused = False
    _save_prospector_pause()
    _log_activity("resume", "Prospector resumed by user")
    logger.warning("PROSPECTOR RESUMED")


_restore_prospector_pause()

def set_rubro(rubros: list[str] | None):
    global _prospector_rubro_override
    # Mismo embudo ya activo: no tocar la cola en curso.
    if rubros == _prospector_rubro_override:
        return
    _prospector_rubro_override = rubros
    try:
        from queue_manager import clear_queue_with_backup
        n = clear_queue_with_backup()
        if n:
            logger.warning(f"NUEVO EMBUDO: cola anterior vaciada y respaldada ({n} leads)")
    except Exception as e:
        logger.error(f"set_rubro: no pude vaciar la cola: {e}")
    _log_activity("set_rubro", f"Rubro override: {rubros} (nuevo embudo)")
    logger.warning(f"RUBRO OVERRIDE: {rubros}")

def _activity_by_day() -> dict:
    """Agrupa la actividad real (búsquedas, encontrados, encolados) por día."""
    by_day: Dict[str, Dict] = {}
    try:
        with open(ACTIVITY_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                kind = m.get("kind", "")
                if kind not in ("search", "found", "enqueue"):
                    continue
                day = (m.get("ts") or "")[:10]
                if not day:
                    continue
                row = by_day.setdefault(day, {
                    "busquedas": 0, "encontrados": 0, "encolados": 0,
                    "rubro": "", "ubicacion": "", "cliente": "",
                })
                data = m.get("data") or {}
                msg = m.get("msg") or ""
                if kind == "search":
                    row["busquedas"] += 1
                    if data.get("rubro"):
                        row["rubro"] = data["rubro"]
                        row["ubicacion"] = data.get("ubicacion", "")
                        row["cliente"] = data.get("cliente", "")
                    elif " en " in msg:
                        try:
                            rb, resto = msg.split(" en ", 1)
                            if rb.startswith("Buscando "):
                                row["rubro"] = rb[len("Buscando "):]
                            row["ubicacion"] = resto.split(" (cliente:", 1)[0]
                        except Exception:
                            pass
                elif kind == "found":
                    n = data.get("encontrados")
                    if n is None:
                        try:
                            n = int(msg.split()[0])
                        except Exception:
                            n = 1
                    row["encontrados"] += n
                elif kind == "enqueue":
                    n = data.get("count", 0) if "count" in data else None
                    if not n:
                        try:
                            n = int(msg.split()[0])
                        except Exception:
                            n = 1
                    row["encolados"] += n
    except Exception:
        pass
    return by_day


def get_status() -> dict:
    from client_store import list_clients
    clients = list_clients()
    current_rubro = None
    for c in clients:
        if c.rubros:
            current_rubro = c.rubros
            break
    last_cycle = None
    if REPORT_PATH.exists():
        try:
            with open(REPORT_PATH) as f:
                rpt = json.load(f)
                last_cycle = rpt.get("timestamp")
        except Exception:
            pass
    today = datetime.now().date().isoformat()
    day = _activity_by_day().get(today, {})
    return {
        "paused": _prospector_paused,
        "running": _prospector_running,
        "rubro_override": _prospector_rubro_override,
        "current_rubro": current_rubro,
        "last_cycle": last_cycle,
        "ig_paused": False,
        "email_paused": False,
        "local_paused": _prospector_paused,
        "found_today": int(day.get("encontrados", 0)),
        "searches_today": int(day.get("busquedas", 0)),
        "enqueued_today": int(day.get("encolados", 0)),
    }


def main():
    config = load_config()
    logger.info(f"Prospector started. Interval: {config['interval_hours']}h, Schedule: {os.getenv('HOUR_START','9')}-{os.getenv('HOUR_END','22')} Mon-Sat")

    report = {}
    if REPORT_PATH.exists():
        try:
            with open(REPORT_PATH) as f:
                report = json.load(f)
        except Exception:
            report = {}

    first_run = True
    while True:
        _sleep_until_work()

        # Check pause
        if _prospector_paused:
            logger.info("Paused — waiting 60s")
            time.sleep(60)
            continue

        now = datetime.now()
        last_cycle = report.get("timestamp", "")
        if last_cycle and not first_run:
            last_dt = datetime.fromisoformat(last_cycle)
            elapsed = (now - last_dt).total_seconds() / 3600
            if elapsed < config["interval_hours"]:
                wait = (config["interval_hours"] - elapsed) * 3600
                logger.info(f"Waiting {wait/3600:.1f}h until next cycle (elapsed: {elapsed:.1f}h)")
                time.sleep(min(wait, 3600))
                continue

        _prospector_running = True
        try:
            result = run_prospecting_cycle(config, report)
            report = result
        finally:
            _prospector_running = False

        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        first_run = False

        # Si el ciclo no encontró nada (posible falta de red/DNS al arrancar),
        # reintentar en 30 min en lugar de esperar el intervalo completo.
        total_found = report.get("total_found", 0)
        total_enqueued = report.get("total_enqueued", 0)
        ig_enqueued = report.get("ig_enqueued", 0)
        ciclo_vacio = total_found == 0 and total_enqueued == 0 and ig_enqueued == 0
        if ciclo_vacio:
            logger.warning("Ciclo sin resultados (posible fallo de red/DNS). Reintentando en 30 min...")
            for _ in range(3):  # 10-min chunks
                if _prospector_paused:
                    break
                time.sleep(600)
            continue

        logger.info(f"Cycle complete. Waiting for next scheduled cycle.")
        # Sleep in chunks, checking work hours each time
        for _ in range(int(config['interval_hours'] * 6)):  # 10-min chunks
            if _prospector_paused:
                break
            if not _is_work_time():
                _sleep_until_work()
            time.sleep(600)
            if _is_work_time():
                last_dt = datetime.fromisoformat(report.get("timestamp", ""))
                if (datetime.now() - last_dt).total_seconds() / 3600 >= config['interval_hours']:
                    break


if __name__ == "__main__":
    _restore_prospector_pause()
    main()
