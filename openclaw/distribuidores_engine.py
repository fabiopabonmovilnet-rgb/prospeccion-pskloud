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

    # Rubro match
    target_rubros = ["contable", "fiscal", "ti", "soporte", "pos", "erp", "integrador",
                     "informat", "tecnolog", "software", "consultor"]
    if rubro:
        rubro_lower = rubro.lower()
        if any(t in rubro_lower for t in target_rubros):
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


# ─── Dedup check ───

def _is_duplicate(conn, empresa: str, pais: str) -> bool:
    row = conn.execute(
        "SELECT id FROM distribuidores WHERE empresa = ? AND pais_target = ?",
        (empresa.strip(), pais.upper())
    ).fetchone()
    return row is not None


# ─── Source 1: Local scraping (DDG + OSM) — backbone ───

def _scrape_local(pais: str, rubros: list[str], ciudades: list[str]) -> dict:
    """Use local_search (DDG batch + OSM) as the primary scraping source.
    OSM may fail from Docker (403), so DDG is the reliable backbone."""
    import local_search
    found = 0
    ingested = 0
    discarded = 0
    errors = []

    rubro_queries = {
        "Firmas Contables": "contadores publicos",
        "Soporte TI": "soporte tecnico informatica",
        "Integradores POS": "sistemas punto de venta",
        "Consultores Fiscales": "consultoria fiscal tributaria",
        "Revendedores ERP": "software erp empresarial",
    }

    for rubro in rubros:
        for ciudad in ciudades[:3]:
            if _engine.stop_event.is_set():
                break

            query = rubro_queries.get(rubro, rubro.lower())
            ubicacion = f"{ciudad}, {pais.replace('_', ' ')}"
            _engine.status_text = f"Scraping: {query} en {ciudad}"

            try:
                # Use only DDG batch (reliable from Docker), skip OSM
                leads = local_search._buscar_ddg_batch(query, ubicacion, max_results=20)
                found += len(leads)
                _engine.add_log(f"[DDG] {ciudad}/{rubro}: {len(leads)} encontrados")

                for lead in leads:
                    if _engine.stop_event.is_set():
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

def _search_apis(pais: str, rubros: list[str], ciudades: list[str]) -> dict:
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
        for ciudad in ciudades[:2]:
            query = f"{rubro} {ciudad}"
            _engine.status_text = f"APIs: {query}"

            try:
                result = api_search.buscar_por_empresa(
                    empresa=query,
                    pais=pais.replace("_", " "),
                    cargo=rubro,
                    limite=5,
                )
                leads = result.get("leads", [])
                errs = result.get("errores", [])
                if errs:
                    errors.extend(errs)

                found += len(leads)
                _engine.add_log(f"[API] {ciudad}/{rubro}: {len(leads)} contactos")

                for lead in leads:
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

def _run_search_cycle(pais: str, rubros: list[str], ciudades: list[str]) -> dict:
    """Execute one cycle: scraping (always) + APIs (if available)."""
    total_found = 0
    total_ingested = 0
    total_discarded = 0
    total_errors = []

    # PHASE 1: Scraping (OSM + DDG) — always runs, ~50-70% of leads
    _engine.add_log("=== FASE 1: Scraping (OSM + DuckDuckGo) ===")
    scrape = _scrape_local(pais, rubros, ciudades)
    total_found += scrape["found"]
    total_ingested += scrape["ingested"]
    total_discarded += scrape["discarded"]
    total_errors.extend(scrape["errors"])

    # PHASE 2: APIs (if keys available) — supplements with ~30-50%
    keys = api_search.get_keys()
    has_keys = any(v for v in keys.values() if v)
    if has_keys:
        _engine.add_log("=== FASE 2: APIs (Hunter/Lusha/RocketReach) ===")
        api_res = _search_apis(pais, rubros, ciudades)
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

def _engine_loop(pais: str, rubros: list[str], ciudades: list[str]):
    """Main engine loop. Runs cycles until stop or reunion target met."""
    _engine.running = True
    _engine.pais_target = pais
    _engine.rubros = rubros
    _engine.ciudades = ciudades
    _engine.started_at = datetime.now().isoformat()
    _engine.status_text = "Iniciando motor..."

    _engine.add_log(f"Motor iniciado: {pais} / {len(rubros)} rubros / {len(ciudades)} ciudades")
    _engine.save_state()

    while not _engine.stop_event.is_set():
        # 1. Check reunion target
        cuotas = store.obtener_cuota_con_progreso(pais)
        if pais in cuotas:
            reuniones = cuotas[pais].get("reuniones", {}).get("actual", 0)
            meta_reuniones = cuotas[pais].get("reuniones", {}).get("meta", 5)
            if reuniones >= meta_reuniones:
                _engine.status_text = f"Meta alcanzada ({reuniones}/{meta_reuniones} reuniones)"
                _engine.add_log(f"Meta de reuniones cumplida: {reuniones}/{meta_reuniones}. Motor detenido.")
                break

        # 2. Always run a search cycle (scraping + optional APIs)
        _engine.status_text = f"Ciclo {_engine.ciclos_completados + 1}: Buscando prospectos..."
        result = _run_search_cycle(pais, rubros, ciudades)
        _engine.total_encontrados += result["found"]
        _engine.total_ingestados += result["ingested"]
        _engine.total_descartados += result["discarded"]
        _engine.errores.extend(result["errors"])
        _engine.ciclos_completados += 1
        _engine.last_cycle_at = datetime.now().isoformat()

        _engine.add_log(
            f"Ciclo {_engine.ciclos_completados} completo: "
            f"{result['ingested']} ingeridos, {result['discarded']} descartados"
        )

        # 3. Save state after every cycle
        _engine.save_state()

        # 4. Brief pause between cycles (20s, interruptible)
        _engine.status_text = f"Ciclo {_engine.ciclos_completados} OK. Pausa 20s..."
        _engine.stop_event.wait(20)

    # Graceful shutdown: save final state
    _engine.running = False
    _engine.status_text = "Detenido"
    _engine.save_state()
    _engine.add_log("Motor detenido. Estado guardado.")


# ─── Public API ───

def start_engine(pais: str, rubros: list[str] = None, ciudades: list[str] = None) -> dict:
    if _engine.running:
        return {"status": "already_running", "pais": _engine.pais_target}

    _engine.stop_event.clear()
    _engine.__init__()

    # Try to resume from persisted state
    saved = _engine.load_state()
    if saved and saved.get("pais_target") == pais:
        # Validate saved counts against actual DB
        actual_count = store.contar_por_pais(pais) if hasattr(store, 'contar_por_pais') else len(store.listar_distribuidores(pais=pais))
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
    _ciudades = ciudades or store.PAISES.get(pais, {}).get("ciudades", [])

    t = threading.Thread(target=_engine_loop, args=(pais, _rubros, _ciudades), daemon=True)
    _engine.thread = t
    t.start()
    return {"status": "started", "pais": pais, "rubros": _rubros, "ciudades": _ciudades, "resumed": bool(saved)}


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
