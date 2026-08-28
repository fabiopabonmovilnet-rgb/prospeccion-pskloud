"""
Distribuidores Auto-Prospecting Engine v2.
Multi-source: APIs (Hunter/Lusha/RocketReach) + Scraping (OSM + DuckDuckGo).
Scraping = 50%+ of pipeline. APIs supplement when credits available.
Runs continuously until weekly reunion target is met.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, date
from typing import Optional

import distribuidores_store as store
import api_search
import email_campaign

logger = logging.getLogger("distribuidores.engine")

ENGINE_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "engine_state.json")
# Also try /app/data (inside container)
if os.path.isdir("/app/data"):
    ENGINE_STATE_FILE = "/app/data/engine_state.json"

# ─── Engine state (in-memory singleton) ───

class EngineState:
    def __init__(self):
        self.running = False
        self.pais_target: str = ""
        self.rubros: list[str] = []
        self.ciudades: list[str] = []
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.status_text: str = "Idle"
        self.ciclos_completados: int = 0
        self.total_encontrados: int = 0
        self.total_ingestados: int = 0
        self.total_descartados: int = 0
        self.errores: list[str] = []
        self.log: list[dict] = []
        self.started_at: Optional[str] = None
        self.last_cycle_at: Optional[str] = None
        self.api_keys_used: list[str] = []
        self.fuentes_activas: list[str] = []

    def to_dict(self) -> dict:
        saved = self.load_state()
        return {
            "running": self.running,
            "pais_target": self.pais_target,
            "rubros": self.rubros,
            "ciudades": self.ciudades,
            "status_text": self.status_text,
            "ciclos_completados": self.ciclos_completados,
            "total_encontrados": self.total_encontrados,
            "total_ingestados": self.total_ingestados,
            "total_descartados": self.total_descartados,
            "errores": self.errores[-10:],
            "log": self.log[-30:],
            "started_at": self.started_at,
            "last_cycle_at": self.last_cycle_at,
            "api_keys_used": self.api_keys_used,
            "fuentes_activas": self.fuentes_activas,
            "has_saved_state": bool(saved),
            "saved_at": saved.get("saved_at") if saved else None,
        }

    def add_log(self, msg: str, level: str = "info"):
        entry = {"ts": datetime.now().isoformat(), "msg": msg, "level": level}
        self.log.append(entry)
        if len(self.log) > 100:
            self.log = self.log[-100:]
        getattr(logger, level, logger.info)(f"[ENGINE] {msg}")

    def save_state(self):
        """Persist engine state to disk so it survives restarts."""
        data = {
            "pais_target": self.pais_target,
            "rubros": self.rubros,
            "ciudades": self.ciudades,
            "ciclos_completados": self.ciclos_completados,
            "total_encontrados": self.total_encontrados,
            "total_ingestados": self.total_ingestados,
            "total_descartados": self.total_descartados,
            "started_at": self.started_at,
            "last_cycle_at": self.last_cycle_at,
            "fuentes_activas": self.fuentes_activas,
            "saved_at": datetime.now().isoformat(),
        }
        try:
            os.makedirs(os.path.dirname(ENGINE_STATE_FILE), exist_ok=True)
            with open(ENGINE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save engine state: {e}")

    def load_state(self) -> dict:
        """Load persisted engine state from disk."""
        if not os.path.exists(ENGINE_STATE_FILE):
            return {}
        try:
            with open(ENGINE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def clear_state(self):
        """Remove persisted engine state."""
        try:
            if os.path.exists(ENGINE_STATE_FILE):
                os.remove(ENGINE_STATE_FILE)
        except Exception:
            pass


_engine = EngineState()


def get_engine_state() -> dict:
    return _engine.to_dict()


# ─── Semaphore classifier ───

# Keyword matching config-driven (RUBROS_CONFIG en distribuidores_store)
_RUBRO_KEYWORDS = []
for _cfg in store.RUBROS_CONFIG.values():
    _RUBRO_KEYWORDS.append(_cfg.get("cargo", "").lower())
    _RUBRO_KEYWORDS.extend([k.lower() for k in _cfg.get("keywords", [])])
_RUBRO_KEYWORDS = [k for k in _RUBRO_KEYWORDS if k]


def _rubro_coincide(rubro_lower: str) -> bool:
    for k in _RUBRO_KEYWORDS:
        if len(k) <= 3:
            if re.search(r'\b' + re.escape(k) + r'\b', rubro_lower):
                return True
        elif k in rubro_lower:
            return True
    return False


def classify_semaphore(lead: dict) -> str:
    """
    Auto-classify based on data quality:
    - VERDE: email valid + domain active + rubro match + contact name
    - AMARILLO: email exists but unverified, or missing phone
    - ROJO: no valid email, domain dead, or no contact at all
    """
    email = (lead.get("Correo") or lead.get("contacto_email") or "").strip()
    dominio = (lead.get("dominio") or lead.get("website") or "").strip()
    nombre = (lead.get("Contacto Clabe") or lead.get("contacto_nombre") or
              lead.get("nombre") or lead.get("nombre_negocio") or "").strip()
    rubro = (lead.get("Rubro") or lead.get("rubro") or "").strip()
    telefono = (lead.get("Telefono") or lead.get("Teléfono") or
                lead.get("contacto_telefono") or lead.get("telefono") or "").strip()

    score = 0

    # Email checks
    if email and re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        score += 2
    elif email:
        score -= 1

    # Domain check
    if dominio and "." in dominio and len(dominio) > 4:
        score += 1

    # Contact name
    if nombre and len(nombre) > 2:
        score += 1

    # Rubro match (config-driven)
    if rubro and _rubro_coincide(rubro.lower()):
        score += 2

    # Phone
    if telefono and len(telefono) >= 8:
        score += 1

    if score >= 5:
        return "VERDE"
    elif score >= 2:
        return "AMARILLO"
    else:
        return "ROJO"


# ─── Envío real de correos a distribuidores ───

def enviar_correos_distribuidores(ids: list, plantilla_key: str = "") -> dict:
    """Envía correos SMTP a los distribuidores seleccionados usando su plantilla por rubro.
    Marca CONTACTADO + canal EMAIL_SMTP solo si el envío fue exitoso."""
    cfg = email_campaign.get_config()
    if not (cfg.get("host") and (cfg.get("user") or cfg.get("smtp_email")) and cfg.get("password")):
        return {"status": "smtp_incompleto",
                "mensaje": "Configura primero el correo SMTP en la pestaña Correo (campaign).",
                "enviados": 0, "fallidos": 0, "sin_email": [], "resultados": []}

    plantillas_por_rubro = {}
    for key, tpl in store.PLANTILLAS_DISTRIBUIDOR.items():
        plantillas_por_rubro[tpl["rubro"]] = (key, tpl)
    plantilla_def = store.PLANTILLAS_DISTRIBUIDOR.get(plantilla_key)

    enviados = 0
    fallidos = 0
    sin_email = []
    resultados = []
    errores = []

    with store._get_conn() as conn:
        for dist_id in ids:
            row = conn.execute(
                "SELECT * FROM distribuidores WHERE id = ?", (dist_id,)
            ).fetchone()
            if not row:
                errores.append(f"id {dist_id} no existe")
                continue

            email = (row["contacto_email"] or "").strip()
            if not email:
                sin_email.append({"id": dist_id, "empresa": row["empresa"]})
                resultados.append({"id": dist_id, "empresa": row["empresa"] if row["empresa"] else None,
                                   "ok": False, "mensaje": "Sin dirección de correo"})
                continue

            nombre = (row["contacto_nombre"] or row["empresa"] or "").strip()
            empresa = (row["empresa"] or "").strip()
            pais = (row["pais_target"] or "").replace("_", " ")
            rubro = (row["rubro"] or "").strip()

            key_plant, tpl = plantillas_por_rubro.get(rubro, (plantilla_key, plantilla_def))
            if not tpl:
                tpl = email_campaign.DEFAULT_PLANTILLA
            asunto = email_campaign.renderizar_plantilla(tpl["asunto"], nombre, empresa, pais, "", email)
            cuerpo = email_campaign.renderizar_plantilla(tpl["cuerpo"], nombre, empresa, pais, "", email)

            exito, msg = email_campaign.enviar_correo_real(cfg, email, asunto, cuerpo)
            email_campaign.registrar_envio(email, nombre, empresa, asunto, "ok" if exito else "error", msg)

            if exito:
                enviados += 1
                conn.execute("""
                    UPDATE distribuidores SET estado_conversion = 'CONTACTADO',
                        canal_contacto = 'EMAIL_SMTP', updated_at = ? WHERE id = ?
                """, (datetime.now().isoformat(), dist_id))
                store._registrar_actividad(conn, dist_id, "EMAIL_ENVIADO", "Correo enviado OK",
                                           "EMAIL_SMTP", key_plant)
            else:
                fallidos += 1
                _engine.add_log(f"[MAIL] {empresa}: {msg}", "error")
                store._registrar_actividad(conn, dist_id, "EMAIL_FALLIDO", f"Error: {msg}",
                                           "EMAIL_SMTP", key_plant)

            resultados.append({"id": dist_id, "empresa": empresa, "ok": exito, "mensaje": msg})
            time.sleep(email_campaign.DELAY_BETWEEN)

    return {
        "status": "ok",
        "enviados": enviados,
        "fallidos": fallidos,
        "sin_email": sin_email,
        "resultados": resultados,
        "errores": errores[:10],
    }


# ─── Dedup check ───

def _is_duplicate(conn, empresa: str, pais: str) -> bool:
    row = conn.execute(
        "SELECT id FROM distribuidores WHERE empresa = ? AND pais_target = ?",
        (empresa.strip(), pais.upper())
    ).fetchone()
    return row is not None


# ─── Source 1: Local scraping (DDG + OSM) — backbone ───

def _scrape_local(pais: str, rubros: list[str], ciudades: list[str], max_leads: int = None) -> dict:
    """Use local_search (DDG batch + OSM) as the primary scraping source.
    OSM may fail from Docker (403), so DDG is the reliable backbone.
    max_leads caps how many leads are ingested in a single country pass (modo Todos)."""
    import local_search
    found = 0
    ingested = 0
    discarded = 0
    errors = []

    for rubro in rubros:
        if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
            break

        config = store.RUBROS_CONFIG.get(rubro, {})
        queries = config.get("queries") or [rubro.lower()]

        for query in queries[:2]:
            if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                break

            for ciudad in ciudades[:3]:
                if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                    break

                ubicacion = f"{ciudad}, {pais.replace('_', ' ')}"
                _engine.status_text = f"Scraping: {query} en {ciudad}"

                try:
                    # Use only DDG batch (reliable from Docker), skip OSM
                    leads = local_search._buscar_ddg_batch(query, ubicacion, max_results=20)
                    found += len(leads)
                    _engine.add_log(f"[DDG] {ciudad}/{rubro}: {len(leads)} encontrados")

                    for lead in leads:
                        if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                            break

                        nombre = lead.get("nombre", "").strip()
                        if not nombre or len(nombre) < 3:
                            discarded += 1
                            continue

                        telefono = lead.get("telefono", "").strip()
                        website = lead.get("website", "").strip()
                        if not telefono and not website:
                            discarded += 1
                            continue

                        semaforo = classify_semaphore(lead)

                        dist_data = {
                            "empresa": nombre,
                            "contacto_nombre": nombre,
                            "contacto_email": "",
                            "contacto_telefono": telefono,
                            "pais_target": pais,
                            "ciudad": ciudad,
                            "rubro": rubro,
                            "clasificacion_semaforo": semaforo,
                            "canal_contacto": "WHATSAPP_DIRECTO" if telefono else "",
                            "website": website,
                            "maps_url": lead.get("maps_url", ""),
                            "fuente": "scraping_ddg",
                            "notas": f"Auto-prospeccion scraping ciclo {_engine.ciclos_completados + 1}",
                        }

                        with store._get_conn() as conn:
                            if _is_duplicate(conn, nombre, pais):
                                discarded += 1
                                continue

                        result = store.crear_distribuidor(dist_data)
                        if result.get("status") == "created":
                            ingested += 1
                        else:
                            discarded += 1

                except Exception as e:
                    errors.append(f"[DDG] {ciudad}/{rubro}: {str(e)}")
                    _engine.add_log(f"Error scraping {ciudad}/{rubro}: {e}", "error")

                time.sleep(1)

    return {"found": found, "ingested": ingested, "discarded": discarded, "errors": errors}


# ─── Source 2: API search (Hunter/Lusha/RocketReach) — supplement ───

def _search_apis(pais: str, rubros: list[str], ciudades: list[str], max_leads: int = None) -> dict:
    """Use APIs when keys are available. Supplements scraping."""
    keys = api_search.get_keys()
    _engine.api_keys_used = [k for k, v in keys.items() if v]

    if not _engine.api_keys_used:
        _engine.add_log("APIs no disponibles (sin keys). Solo scraping activo.", "warning")
        return {"found": 0, "ingested": 0, "discarded": 0, "errors": []}

    found = 0
    ingested = 0
    discarded = 0
    errors = []

    for rubro in rubros:
        config = store.RUBROS_CONFIG.get(rubro, {})
        cargo = config.get("cargo", rubro)
        queries = config.get("queries") or [rubro.lower()]

        for ciudad in ciudades[:2]:
            if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                break

            # Usa los términos de nicho estructurados (RUBROS_CONFIG) para extraer más leads
            for query in queries[:2]:
                if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                    break

                _engine.status_text = f"APIs: {query} en {ciudad}"

                try:
                    result = api_search.buscar_por_empresa(
                        empresa=query,
                        pais=pais.replace("_", " "),
                        cargo=cargo,
                        limite=25,
                    )
                    leads = result.get("leads", [])
                    errs = result.get("errores", [])
                    if errs:
                        errors.extend(errs)

                    found += len(leads)
                    _engine.add_log(f"[API] {ciudad}/{rubro}: {len(leads)} contactos")

                    for lead in leads:
                        if _engine.stop_event.is_set() or (max_leads and ingested >= max_leads):
                            break

                        empresa_name = lead.get("Empresa") or lead.get("empresa") or ""
                        if not empresa_name or len(empresa_name) < 3:
                            discarded += 1
                            continue

                        semaforo = classify_semaphore(lead)

                        dist_data = {
                            "empresa": empresa_name.strip(),
                            "contacto_nombre": (lead.get("Contacto Clabe") or "").strip(),
                            "contacto_email": (lead.get("Correo") or "").strip(),
                            "contacto_telefono": (lead.get("Telefono") or lead.get("Teléfono") or "").strip(),
                            "pais_target": pais,
                            "ciudad": ciudad,
                            "rubro": rubro,
                            "clasificacion_semaforo": semaforo,
                            "canal_contacto": "EMAIL_SMTP" if lead.get("Correo") else "",
                            "website": (lead.get("dominio") or "").strip(),
                            "fuente": lead.get("Fuente", "API"),
                            "notas": f"Auto-prospeccion API ciclo {_engine.ciclos_completados + 1}",
                        }

                        with store._get_conn() as conn:
                            if _is_duplicate(conn, empresa_name, pais):
                                discarded += 1
                                continue

                        result_ins = store.crear_distribuidor(dist_data)
                        if result_ins.get("status") == "created":
                            ingested += 1
                        else:
                            discarded += 1

                except Exception as e:
                    errors.append(f"[API] {ciudad}/{rubro}: {str(e)}")

                time.sleep(2)

    return {"found": found, "ingested": ingested, "discarded": discarded, "errors": errors}


# ─── Single search cycle (multi-source) ───

def _run_search_cycle(pais: str, rubros: list[str], ciudades: list[str], max_leads: int = None) -> dict:
    """Execute one cycle: scraping (always) + APIs (if available)."""
    total_found = 0
    total_ingested = 0
    total_discarded = 0
    total_errors = []

    # PHASE 1: Scraping (OSM + DDG) — always runs, ~50-70% of leads
    _engine.add_log("=== FASE 1: Scraping (OSM + DuckDuckGo) ===")
    scrape = _scrape_local(pais, rubros, ciudades, max_leads)
    total_found += scrape["found"]
    total_ingested += scrape["ingested"]
    total_discarded += scrape["discarded"]
    total_errors.extend(scrape["errors"])

    # PHASE 2: APIs (if keys available) — llenan lo que falte hasta la meta
    restante = (max_leads - scrape["ingested"]) if max_leads else None
    keys = api_search.get_keys()
    has_keys = any(v for v in keys.values() if v)
    if has_keys and restante is not None and restante <= 0:
        has_keys = False
    if has_keys:
        _engine.add_log("=== FASE 2: APIs (Hunter/Lusha/RocketReach/Apollo) ===")
        api_res = _search_apis(pais, rubros, ciudades, restante)
        total_found += api_res["found"]
        total_ingested += api_res["ingested"]
        total_discarded += api_res["discarded"]
        total_errors.extend(api_res["errors"])
    else:
        _engine.add_log("APIs sin credits — solo scraping activo")

    _engine.fuentes_activas = ["scraping_osm_ddg"] + (["api_hunter_lusha"] if has_keys else [])

    return {
        "found": total_found,
        "ingested": total_ingested,
        "discarded": total_discarded,
        "errors": total_errors,
    }


# ─── Continuous engine loop ───

# Presupuesto por país del día en modo "TODOS" (reparto justo del tope global)
def _share_por_pais(paises: list[str]) -> int:
    return max(4, store.META_TOTAL_SEMANAL // max(1, len(paises)))


def _engine_loop(paises: list[str], rubros: list[str], ciudades_global: list[str]):
    """Main engine loop. Runs cycles until stop or (global) targets met.
    - Un país: se detiene al cumplir la meta de reuniones (comportamiento original).
    - Varios países (modo TODOS): round-robin justo con tope global META_TOTAL_SEMANAL.
    """
    _engine.running = True
    if len(paises) == 1:
        _engine.pais_target = paises[0]
    else:
        _engine.pais_target = "TODOS"
    _engine.rubros = rubros
    _engine.started_at = datetime.now().isoformat()
    _engine.status_text = "Iniciando motor..."

    _engine.add_log(f"Motor iniciado: {', '.join(paises)} / {len(rubros)} rubros")
    _engine.save_state()

    idx = 0
    share = _share_por_pais(paises) if len(paises) > 1 else store.META_TOTAL_SEMANAL

    while not _engine.stop_event.is_set():
        pais = paises[idx % len(paises)]
        idx += 1

        # 1. Reunión meta por país (un único país: comportamiento original)
        cuotas = store.obtener_cuota_con_progreso(pais)
        if pais in cuotas:
            reuniones = cuotas[pais].get("reuniones", {}).get("actual", 0)
            meta_reuniones = cuotas[pais].get("reuniones", {}).get("meta", 5)
            if reuniones >= meta_reuniones:
                if len(paises) == 1:
                    _engine.status_text = f"Meta alcanzada ({reuniones}/{meta_reuniones} reuniones)"
                    _engine.add_log(f"Meta de reuniones cumplida: {reuniones}/{meta_reuniones}. Motor detenido.")
                    break
                else:
                    _engine.add_log(f"[{pais}] alcanzó su meta de reuniones ({reuniones}/{meta_reuniones}). Paso al siguiente país.")

        # 2. Modo TODOS: tope global semanal
        if len(paises) > 1:
            if _engine.total_ingestados >= store.META_TOTAL_SEMANAL:
                _engine.status_text = f"Meta alcanzada ({_engine.total_ingestados}/{store.META_TOTAL_SEMANAL} prospectos)"
                _engine.add_log(f"Meta semanal cumplida: {_engine.total_ingestados}/{store.META_TOTAL_SEMANAL}. Motor detenido.")
                break
            cupo = store.puede_encolar(pais, "investigados")
            if not cupo["puede"]:
                _engine.add_log(f"[{pais}] sin cupos ({cupo.get('actual', 0)}/{cupo.get('meta', 40)}). Paso al siguiente país.")
                continue

        # 3. Run a search cycle for this country (scraping + optional APIs)
        ciudades = ciudades_global or store.PAISES.get(pais, {}).get("ciudades", [])
        _engine.status_text = f"Ciclo {_engine.ciclos_completados + 1}: {pais} — Buscando prospectos..."
        result = _run_search_cycle(pais, rubros, ciudades, max_leads=share)
        _engine.total_encontrados += result["found"]
        _engine.total_ingestados += result["ingested"]
        _engine.total_descartados += result["discarded"]
        _engine.errores.extend(result["errors"])
        _engine.ciclos_completados += 1
        _engine.last_cycle_at = datetime.now().isoformat()

        _engine.add_log(
            f"Ciclo {_engine.ciclos_completados} ({pais}) completo: "
            f"{result['ingested']} ingeridos, {result['discarded']} descartados"
        )

        # 4. Save state after every cycle
        _engine.save_state()

        # 5. Brief pause between cycles (20s, interruptible)
        _engine.status_text = f"Ciclo {_engine.ciclos_completados} OK. Pausa 20s..."
        _engine.stop_event.wait(20)

    # Graceful shutdown: save final state
    _engine.running = False
    _engine.status_text = "Detenido"
    _engine.save_state()
    _engine.add_log("Motor detenido. Estado guardado.")


# ─── Public API ───

def start_engine(pais: str = "", rubros: list[str] = None, ciudades: list[str] = None) -> dict:
    """pais="" → modo TODOS: reparte META_TOTAL_SEMANAL entre los países activos."""
    if pais and not store.is_pais_activo(pais):
        return {"status": "pais_inactivo", "pais": pais,
                "mensaje": f"El país {pais} está desactivado. Actívalo en la pestaña Distribuidores del panel antes de iniciar el motor."}

    paises = [pais] if pais else [p for p in store.get_paises_activos() if store.is_pais_activo(p)]
    if not paises:
        return {"status": "sin_paises", "mensaje": "No hay países activos para prospectar."}

    if _engine.running:
        return {"status": "already_running", "pais": _engine.pais_target}

    _engine.stop_event.clear()
    _engine.__init__()

    saved = _engine.load_state()
    if saved and len(paises) == 1 and saved.get("pais_target") == pais:
        actual_count = len(store.listar_distribuidores(pais=pais))
        saved_ingested = saved.get("total_ingestados", 0)
        if actual_count == 0 and saved_ingested > 0:
            _engine.add_log(f"⚠️ Estado guardado inválido (DB vacía pero saved={saved_ingested}). Reiniciando contadores.")
            _engine.clear_state()
        else:
            _engine.ciclos_completados = saved.get("ciclos_completados", 0)
            _engine.total_encontrados = saved.get("total_encontrados", 0)
            _engine.total_ingestados = actual_count
            _engine.total_descartados = saved.get("total_descartados", 0)
            _engine.started_at = saved.get("started_at")
            _engine.fuentes_activas = saved.get("fuentes_activas", [])
            _engine.add_log(f"Resumiendo desde estado guardado: {_engine.ciclos_completados} ciclos previos, {actual_count} leads en BD")

    _rubros = rubros or store.RUBROS_DISTRIBUIDORES
    _ciudades = ciudades or (store.PAISES.get(pais, {}).get("ciudades", []) if pais else [])

    t = threading.Thread(target=_engine_loop, args=(paises, _rubros, _ciudades), daemon=True)
    _engine.thread = t
    t.start()
    return {"status": "started", "paises": paises, "pais": _engine.pais_target,
            "rubros": _rubros, "ciudades": _ciudades, "resumed": bool(saved)}


def stop_engine() -> dict:
    if not _engine.running:
        return {"status": "not_running"}
    _engine.stop_event.set()
    _engine.status_text = "Deteniendo (guardando estado)..."
    # State will be saved by the engine thread when it exits
    # Don't block the API response
    return {"status": "stopping", "ciclos": _engine.ciclos_completados, "ingestados": _engine.total_ingestados}


def engine_status() -> dict:
    return _engine.to_dict()


def engine_log(limit: int = 50) -> list:
    return _engine.log[-limit:]
