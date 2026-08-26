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


def enqueue_to_openclaw(leads: List[Dict], url: str, client_id: str = "") -> int:
    if not leads:
        return 0
    try:
        from queue_manager import enqueue_leads as local_enqueue
        from models import Lead
        lead_objs = []
        for l in leads:
            l["fuente"] = l.get("fuente_telefono", l.get("fuente", ""))
            l["client_id"] = client_id
            lead_objs.append(Lead(**{k: v for k, v in l.items() if k in Lead.model_fields}))
        count = local_enqueue(lead_objs)
        logger.info(f"Direct-enqueued {count} leads to OpenClaw queue")
        return count
    except ImportError:
        pass
    # Fallback: HTTP POST
    payload = {"leads": leads}
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


def run_prospecting_cycle(config: dict, report: dict):
    max_results = config.get("max_leads_per_search", 50)
    openclaw_url = config.get("openclaw_url", "http://openclaw:9000")
    limites_por_pais = config.get("limites_por_pais", {})
    clients = list_clients()

    if not clients:
        logger.warning("No clients configured. Create a client in the dashboard first.")
        return {"timestamp": datetime.now().isoformat(), "total_enqueued": 0, "total_found": 0, "ciclo": [], "completados": []}

    # Apply rubro override if set
    if _prospector_rubro_override is not None:
        for c in clients:
            c.rubros = _prospector_rubro_override
        logger.info(f"Rubro override active: {_prospector_rubro_override}")

    total_rubros = sum(len(c.rubros) for c in clients)
    total_ubicaciones = sum(len(c.ubicaciones) for c in clients)
    logger.info(f"=== Prospecting cycle: {len(clients)} clientes, {total_rubros} rubros x {total_ubicaciones} ubicaciones ===")
    total_enqueued = 0
    total_found = 0
    ciclo = []
    completados_ok = []

    for client in clients:
        for rubro in client.rubros:
            for ubicacion in client.ubicaciones:
                key = f"{client.id}|{rubro}|{ubicacion}"
                if cycle_was_done(report, key):
                    continue
                pais = _pais_de_ubicacion(ubicacion)
                limite_pais = limites_por_pais.get(pais)
                try:
                    logger.info(f"Buscando {rubro} en {ubicacion}")
                    _log_activity("search", f"Buscando {rubro} en {ubicacion} (cliente: {client.name})")
                    resultados = scrape_local(rubro, ubicacion, max_results=max_results)
                    con_telefono = [r for r in resultados if r.get("telefono")]
                    if limite_pais:
                        con_telefono = con_telefono[:limite_pais]
                        logger.info(f"  Límite país {pais}: {limite_pais}/rubro -> {len(con_telefono)} leads")
                    total_found += len(con_telefono)
                    _log_activity("found", f"{len(con_telefono)} teléfonos en {len(resultados)} {rubro} de {ubicacion}")

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
                        cues = enqueue_to_openclaw(tanda, openclaw_url, client_id=client.id)
                        total_enqueued += cues
                        logger.info(f"  -> Enqueued batch {cues}")

                    ciclo.append({
                        "cliente": client.name,
                        "rubro": rubro,
                        "ubicacion": ubicacion,
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
    """Search Instagram for ONE hashtag per day (rotates). Enqueue up to 3 leads total."""
    import asyncio
    from queue_manager import enqueue_leads
    from ig_sender import InstagramSender
    from models import Lead

    hashtags = client.instagram.ig_hashtags
    if not hashtags:
        return 0

    # Rotate hashtag: track index in report
    ig_idx = report.get("ig_hashtag_index", {}).get(client.id, 0)
    hashtag = hashtags[ig_idx % len(hashtags)]
    report.setdefault("ig_hashtag_index", {})[client.id] = (ig_idx + 1) % len(hashtags)

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

        logger.info(f"IG prospecting: #{hashtag} (dia {ig_idx % len(hashtags) + 1}/{len(hashtags)})")
        _log_activity("ig_day", f"IG hashtag del dia: #{hashtag}")

        for ubicacion in client.ubicaciones:
            if total >= 3:
                break
            city_country = ubicacion.strip()
            country = city_country.split(",")[-1].strip() if "," in city_country else city_country
            ig_query = _normalize_hashtag(f"{hashtag}{country}")
            logger.info(f"IG search: #{ig_query} ({city_country})")
            _log_activity("ig_search", f"Buscando #{ig_query}")

            try:
                leads = loop.run_until_complete(
                    sender.search_leads([ig_query], max_per_tag=3)
                )
            except Exception as e:
                logger.error(f"IG search error for #{ig_query}: {e}")
                continue

            if leads:
                lead_objs = []
                for l in leads:
                    if total >= 3:
                        break
                    lead_objs.append(Lead(
                        nombre=l["username"],
                        empresa="",
                        rubro=hashtag,
                        pais=country,
                        ciudad=city_country.split(",")[0].strip(),
                        fuente=f"instagram_{ig_query}",
                        client_id=client.id,
                    ))
                    total += 1
                if lead_objs:
                    enc = enqueue_leads(lead_objs)
                    logger.info(f"  IG #{ig_query}: {enc} leads enqueued (total: {total}/3)")
                    _log_activity("ig_found", f"{enc} leads de #{ig_query}")

        loop.run_until_complete(sender.close())
        logger.info(f"IG prospecting done: {total} leads enqueued for #{hashtag}")
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

def pause():
    global _prospector_paused
    _prospector_paused = True
    _log_activity("pause", "Prospector paused by user")
    logger.warning("PROSPECTOR PAUSED")

def resume():
    global _prospector_paused
    _prospector_paused = False
    _log_activity("resume", "Prospector resumed by user")
    logger.warning("PROSPECTOR RESUMED")

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
    return {
        "paused": _prospector_paused,
        "running": _prospector_running,
        "rubro_override": _prospector_rubro_override,
        "current_rubro": current_rubro,
        "last_cycle": last_cycle,
        "ig_paused": False,
        "email_paused": False,
        "local_paused": _prospector_paused,
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
    main()
