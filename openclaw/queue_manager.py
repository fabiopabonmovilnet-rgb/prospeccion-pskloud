from __future__ import annotations

import asyncio
import httpx
import json
import logging
import os
import random
import re
import time
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

from config import settings
from models import Lead, Message, Conversation, Classification, Client, WhatsAppChannel
from evolution_client import evolution_from_channel
from gemini_brain import gemini
from handoff import send_handoff_alert
from email_sender import send_email
from ig_sender import InstagramSender, build_dm_text
from client_store import get_client, get_template, list_clients
from aprendizaje import registrar_caso
from store import (
    get_conversation,
    save_conversation,
    add_message,
    get_today_count,
    increment_today_count,
    reset_daily_if_needed,
    is_phone_excluded,
    list_excluded_phones,
    list_conversations,
    exclude_phone,
)

logger = logging.getLogger("openclaw.queue")

_queue: list[dict] = []
_running = False
_running_since = 0.0  # watchdog: when _running was last observed stuck
_queue_paused = False  # manual pause from UI (Play/Stop buttons)

# Debounce queue persistence: the autonomous prospector enqueues in bursts,
# and each save rewrites the whole JSON file. Throttle writes to avoid
# saturating disk I/O (which starves the send loop and the API).
_last_queue_save = 0.0
_QUEUE_SAVE_DEBOUNCE = 15.0  # seconds between disk writes at most

# ---------------------------------------------------------------------------
# Activity log for dashboard
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Per-client daily counters
# ---------------------------------------------------------------------------


def _load_channel_counts() -> dict:
    path = settings.country_counts_file.replace("envios_por_pais", "envios_por_cliente")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == date.today().isoformat():
                return data.get("channels", {})
        except Exception:
            pass
    return {}


def _save_channel_counts(counts: dict):
    path = settings.country_counts_file.replace("envios_por_pais", "envios_por_cliente")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": date.today().isoformat(), "channels": counts}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving channel counts: {e}")


def _prospector_paused() -> bool:
    """True when the autonomous prospector is paused (stops all queue sends too)."""
    try:
        import prospector
        return bool(getattr(prospector, "_prospector_paused", False))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Queue Play / Stop / Replay controls (UI buttons)
# ---------------------------------------------------------------------------

def pause_queue():
    """Stop all message sending immediately."""
    global _queue_paused
    _queue_paused = True
    _log_activity("pause", "Cola pausada por el usuario (Stop)")
    logger.warning("QUEUE PAUSED by user")


def resume_queue():
    """Resume message sending."""
    global _queue_paused
    _queue_paused = False
    _log_activity("resume", "Cola reanudada por el usuario (Play)")
    logger.warning("QUEUE RESUMED by user")


def replay_queue():
    """Reload the queue from disk and resume sending."""
    global _queue_paused, _queue
    _queue_paused = False
    load_queue(force_reload=True)
    _log_activity("resume", f"Cola reiniciada (Replay): {len(_queue)} leads recargados")
    logger.warning(f"QUEUE REPLAY by user: {len(_queue)} leads reloaded")
    return len(_queue)


def is_queue_paused() -> bool:
    return _queue_paused


def _can_send_channel(client_id: str, channel: str) -> bool:
    counts = _load_channel_counts()
    key = f"{client_id}|{channel}"
    sent = counts.get(key, 0)
    client = get_client(client_id)
    if not client:
        return False
    ch_cfg = _get_channel_config(client, channel)
    if not ch_cfg:
        return False
    return sent < ch_cfg.max_daily


def _mark_channel_sent(client_id: str, channel: str):
    counts = _load_channel_counts()
    key = f"{client_id}|{channel}"
    counts[key] = counts.get(key, 0) + 1
    _save_channel_counts(counts)


def _get_channel_config(client: Client, channel: str):
    return {
        "whatsapp": client.whatsapp,
        "email": client.email,
        "instagram": client.instagram,
    }.get(channel)


# ---------------------------------------------------------------------------
# Legacy country counters (backwards compat)
# ---------------------------------------------------------------------------

def _load_country_counts() -> dict:
    path = settings.country_counts_file
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            today = date.today().isoformat()
            if data.get("date") == today:
                return data.get("countries", {})
        except Exception:
            pass
    return {}


def _save_country_counts(counts: dict):
    path = settings.country_counts_file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": date.today().isoformat(), "countries": counts}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving country counts: {e}")


def _country_rubro_key(country: str, rubro: str = "") -> str:
    return f"{country or 'Desconocido'}|{rubro or ''}"


def _can_send_to_country(country: str, rubro: str = "") -> bool:
    counts = _load_country_counts()
    sent = counts.get(_country_rubro_key(country, rubro), 0)
    return sent < settings.max_per_country_daily


def _load_blocked_countries() -> set[str]:
    path = os.path.join(settings.data_dir, "paises_bloqueados.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {str(c).strip() for c in data if str(c).strip()}
    except Exception as e:
        logger.error(f"Error reading paises_bloqueados.json: {e}")
    return set()


def _is_country_blocked(country: str) -> bool:
    c = (country or "").strip()
    if not c:
        return False
    return c in _load_blocked_countries()


def _mark_country_sent(country: str, rubro: str = ""):
    counts = _load_country_counts()
    key = _country_rubro_key(country, rubro)
    counts[key] = counts.get(key, 0) + 1
    _save_country_counts(counts)


# ---------------------------------------------------------------------------
# Queue persistence
# ---------------------------------------------------------------------------


def save_queue(force: bool = False):
    global _last_queue_save
    now = time.time()
    if not force and (now - _last_queue_save) < _QUEUE_SAVE_DEBOUNCE:
        return
    _last_queue_save = now
    try:
        with open(settings.queue_file, "w", encoding="utf-8") as f:
            json.dump(_queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving queue: {e}")


def clear_queue_with_backup() -> int:
    """Vacía la cola actual respaldándola antes a un archivo fechado (nuevo embudo)."""
    global _queue
    n = len(_queue)
    if n:
        try:
            import shutil
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = settings.queue_file.replace(".json", f"_backup_{ts}.json")
            shutil.copy2(settings.queue_file, backup)
        except Exception as e:
            logger.error(f"clear_queue_with_backup: no pude respaldar: {e}")
        _queue = []
        save_queue(force=True)
        _log_activity("queue_clear", f"Cola vaciada ({n} leads) — nuevo embudo")
    return n


def _norm_phone(phone: str) -> str:
    """Normalize phone for consistent dedup."""
    if not phone:
        return ""
    for ch in " .(),-\t":
        phone = phone.replace(ch, "")
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _get_contacted_phones() -> set[str]:
    """Load all already-contacted phones in a single query (fast dedup)."""
    for attempt in range(3):
        try:
            import sqlite3
            db_path = settings.conversations_db
            if not os.path.exists(db_path):
                return set()
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                rows = conn.execute("SELECT phone FROM conversations").fetchall()
            finally:
                conn.close()
            return {r[0] for r in rows}
        except Exception as e:
            if attempt == 2:
                logger.error(f"Dedup: error leyendo contactados: {e}")
            time.sleep(0.5)
    return set()


def _business_key(entry: dict) -> str:
    """Clave de negocio: nombre limpio normalizado + país (evita recontactar
    el mismo negocio aunque tenga otro teléfono scrapeado)."""
    name = _clean_business_name(entry.get("empresa") or entry.get("nombre") or "")
    if not name:
        return ""
    key = name.lower()
    key = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    pais = (entry.get("pais") or "").strip().lower()
    return f"{key}|{pais}"


def _get_contacted_business_keys() -> set[str]:
    """Carga las claves de negocio ya contactadas (nombre limpio + país)."""
    keys: set[str] = set()
    try:
        import sqlite3
        db_path = settings.conversations_db
        if not os.path.exists(db_path):
            return keys
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            rows = conn.execute("SELECT lead_json, started_at FROM conversations").fetchall()
        finally:
            conn.close()
        for lead_json, _ in rows:
            try:
                lead = json.loads(lead_json)
            except Exception:
                continue
            key = _business_key(lead)
            if key:
                keys.add(key)
    except Exception as e:
        logger.error(f"Dedup: error leyendo negocios contactados: {e}")
    return keys


_contacted_business_cache: set[str] = set()
_contacted_business_ts = 0.0


def _business_key_contacted(biz_key: str) -> bool:
    """Caché de 60s para el guard de negocio ya contactado en el send loop."""
    global _contacted_business_cache, _contacted_business_ts
    if time.time() - _contacted_business_ts > 60:
        _contacted_business_cache = _get_contacted_business_keys()
        _contacted_business_ts = time.time()
    return biz_key in _contacted_business_cache


def _get_historic_phones() -> set[str]:
    """Load phones from leads_historicos.json (imported/CRM leads already contacted)."""
    phones: set[str] = set()
    path = os.path.join(settings.data_dir, "leads_historicos.json")
    if not os.path.exists(path):
        return phones
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for lead in data.values():
            if not isinstance(lead, dict):
                continue
            tel = lead.get("teléfono") or lead.get("telefono") or ""
            for part in str(tel).split(";"):
                part = _norm_phone(part.strip())
                if len(part) >= 8:
                    phones.add(part)
    except Exception:
        pass
    return phones


def _deduplicate_queue(queue: list[dict]) -> list[dict]:
    """Remove duplicates by normalized phone, skip already-conversation leads."""
    seen: set[str] = set()
    seen_emails: set[str] = set()
    seen_business: set[str] = set()
    result = []
    dropped_dup = 0
    dropped_conv = 0
    dropped_nocontact = 0
    dropped_business = 0
    contacted = _get_contacted_phones()
    historic = _get_historic_phones()
    excluded = list_excluded_phones()
    contacted_business = _get_contacted_business_keys()
    for entry in queue:
        phone = _format_phone(entry.get("telefono", ""), entry.get("pais", ""))
        if phone and phone in seen:
            dropped_dup += 1
            continue
        if phone and (phone in contacted or phone in historic or phone in excluded):
            dropped_conv += 1
            continue
        biz_key = _business_key(entry)
        if biz_key and (biz_key in contacted_business or biz_key in seen_business):
            dropped_business += 1
            _log_activity("skip", f"Omitido (negocio ya contactado): {entry.get('nombre','')} ({entry.get('pais','?')})")
            continue
        if biz_key:
            seen_business.add(biz_key)
        if phone:
            seen.add(phone)
        # Normalize phone in the entry (country-code corrected)
        if phone:
            entry["telefono"] = phone
        email = (entry.get("email") or "").strip().lower()
        if not phone and not email and not (entry.get("instagram_username") or "").strip():
            dropped_nocontact += 1
            continue
        if email and email in seen_emails:
            dropped_dup += 1
            continue
        if email:
            seen_emails.add(email)
        result.append(entry)
    if dropped_dup or dropped_conv or dropped_nocontact or dropped_business:
        logger.info(f"Dedup: {dropped_dup} duplicates removed, {dropped_conv} already-conversation removed, {dropped_nocontact} no-contact-channel removed, {dropped_business} same-business removed")
        _log_activity("dedup", f"Dedup: {dropped_dup} duplicados, {dropped_conv} ya-contactados, {dropped_nocontact} sin canal, {dropped_business} negocio ya-contactado")
    return result


def load_queue(force_reload: bool = False):
    global _queue
    if not force_reload and _queue:
        save_queue(force=True)
    if os.path.exists(settings.queue_file):
        try:
            with open(settings.queue_file, "r", encoding="utf-8") as f:
                _queue = json.load(f)
        except Exception:
            _queue = []
    _queue = _deduplicate_queue(_queue)


def enqueue_leads(leads: list[Lead]) -> int:
    count = 0
    contacted = _get_contacted_phones()
    historic = _get_historic_phones()
    contacted_business = _get_contacted_business_keys()
    queued_phones = {_norm_phone(e.get("telefono", "")) for e in _queue if e.get("telefono")}
    queued_emails = {e.get("email", "") for e in _queue if e.get("email")}
    queued_business = {e.get("_biz_key", "") for e in _queue if e.get("_biz_key")}
    for lead in leads:
        is_ig = lead.fuente and lead.fuente.startswith("instagram")
        if not lead.telefono and not lead.email and not is_ig:
            continue
        channel = _pick_channel(lead)
        entry = {
            "nombre": _clean_business_name(lead.nombre),
            "empresa": _clean_business_name(lead.empresa),
            "telefono": _format_phone(lead.telefono, lead.pais),
            "email": lead.email,
            "rubro": lead.rubro,
            "pais": lead.pais,
            "ciudad": lead.ciudad,
            "fuente": lead.fuente,
            "client_id": lead.client_id or _default_client_id(),
            "channel": channel,
            "queued_at": datetime.now().isoformat(),
        }
        biz_key = _business_key(entry)
        if channel == "whatsapp" and biz_key and (biz_key in contacted_business or biz_key in queued_business):
            _log_activity("skip", f"Omitido (negocio ya contactado): {lead.nombre} ({lead.pais or '?'})")
            continue
        phone = entry.get("telefono", "")
        if phone:
            if phone in contacted or phone in historic:
                _log_activity("skip", f"Omitido (ya contactado): {lead.nombre} ({lead.pais or '?'}) - {phone}")
                continue
            if phone in queued_phones:
                _log_activity("skip", f"Omitido (duplicado en cola): {lead.nombre} ({lead.pais or '?'}) - {phone}")
                continue
            queued_phones.add(phone)
        elif entry.get("email") and entry["email"] in queued_emails:
            continue
        if biz_key:
            entry["_biz_key"] = biz_key
            queued_business.add(biz_key)
        _queue.append(entry)
        count += 1
    save_queue()  # debounced: prospector bursts don't rewrite the whole file each time
    logger.info(f"Enqueued {count} leads (total queue: {len(_queue)})")
    _log_activity("enqueue", f"{count} leads encolados (cola: {len(_queue)})")
    return count


def _default_client_id() -> str:
    clients = list_clients()
    return clients[0].id if clients else "default"


def _pick_channel(lead: Lead) -> str:
    """Pick best channel for a lead based on available data and client config."""
    # IG leads from prospector are tagged with IG source
    if lead.fuente and lead.fuente.startswith("instagram"):
        return "instagram"
    client = get_client(lead.client_id) if lead.client_id else None
    if not client:
        return "whatsapp" if lead.telefono else ("email" if lead.email else "whatsapp")
    channels = client.active_channels
    if "whatsapp" in channels and lead.telefono:
        return "whatsapp"
    if "email" in channels and lead.email:
        return "email"
    return channels[0] if channels else "whatsapp"


def get_queue_status() -> dict:
    pais_counts = defaultdict(int)
    channel_counts = defaultdict(int)
    for e in _queue:
        pais_counts[e.get("pais", "Desconocido")] += 1
        channel_counts[e.get("channel", "whatsapp")] += 1

    country_counts = _load_country_counts()
    today = date.today().isoformat()

    return {
        "pending": len(_queue),
        "pending_por_pais": dict(pais_counts),
        "pending_por_channel": dict(channel_counts),
        "sent_today": get_today_count(),
        "sent_por_pais": country_counts,
        "max_daily": settings.max_daily_outbound,
        "max_por_pais": settings.max_per_country_daily,
        "running": _running,
        "queue_paused": _queue_paused,
        "date": today,
    }


# Zona horaria por país: el horario de envío (9-16) se evalúa en hora LOCAL del lead.
_COUNTRY_TZ = {
    "Colombia": "America/Bogota",
    "Panamá": "America/Panama",
    "Panama": "America/Panama",
    "El Salvador": "America/El_Salvador",
    "Nicaragua": "America/Managua",
    "Costa Rica": "America/Costa_Rica",
    "Honduras": "America/Tegucigalpa",
    "Guatemala": "America/Guatemala",
    "México": "America/Mexico_City",
    "Mexico": "America/Mexico_City",
    "Venezuela": "America/Caracas",
    "Ecuador": "America/Guayaquil",
    "Perú": "America/Lima",
    "Peru": "America/Lima",
    "Bolivia": "America/La_Paz",
    "Brasil": "America/Sao_Paulo",
    "Paraguay": "America/Asuncion",
    "Uruguay": "America/Montevideo",
    "Argentina": "America/Argentina/Buenos_Aires",
    "Chile": "America/Santiago",
    "República Dominicana": "America/Santo_Domingo",
    "Republica Dominicana": "America/Santo_Domingo",
    "Cuba": "America/Havana",
    "Puerto Rico": "America/Puerto_Rico",
}


def _is_work_time(client_id: str = None, channel: str = "whatsapp", country: str = None) -> bool:
    now = datetime.now()
    tz_name = _COUNTRY_TZ.get((country or "").strip())
    if tz_name:
        try:
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    if client_id:
        client = get_client(client_id)
        if client:
            ch = _get_channel_config(client, channel)
            if ch:
                if now.weekday() not in ch.work_days:
                    return False
                return ch.hour_start <= now.hour < ch.hour_end
    # Fallback to global settings
    work_days = [int(d.strip()) for d in os.getenv("WORK_DAYS", "0,1,2,3,4,5,6").split(",")]
    hour_start = int(os.getenv("HOUR_START", "9"))
    hour_end = int(os.getenv("HOUR_END", "22"))
    if now.weekday() not in work_days:
        return False
    return hour_start <= now.hour < hour_end


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------

SUMMARY_FILE = "/app/data/resumen_diario.json"


def _save_daily_summary(sent_list: list[dict]):
    try:
        all_s = []
        if os.path.exists(SUMMARY_FILE):
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                all_s = json.load(f)
        today = date.today().isoformat()
        if all_s and all_s[-1].get("fecha") == today:
            summary = all_s[-1]
        else:
            summary = {"fecha": today, "detalle": [], "por_pais": {}, "por_rubro": {}}
            all_s.append(summary)
        for s in sent_list:
            summary["detalle"].append(s)
            pais = s.get("pais", "Desconocido")
            summary["por_pais"][pais] = summary["por_pais"].get(pais, 0) + 1
            rubro = s.get("rubro", "General")
            summary["por_rubro"][rubro] = summary["por_rubro"].get(rubro, 0) + 1
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(all_s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving daily summary: {e}")


# ---------------------------------------------------------------------------
# Message sending — multi-channel routing
# ---------------------------------------------------------------------------


def _format_phone(phone: str, country: str = "") -> str:
    if not phone:
        return ""
    for ch in " .(),-":
        phone = phone.replace(ch, "")
    digits = phone.lstrip("+")
    if not digits.isdigit():
        return ""
    # Scraped numbers are often local (no country code) or carry a wrong
    # prefix. Prepend the country dialing code unless it's already present.
    code = _country_code(country)
    if code and not digits.startswith(code):
        digits = code + digits.lstrip("0")
    phone = "+" + digits
    if len(digits) < 7:
        return ""
    return phone


def _country_code(country: str) -> str:
    """Resolve a country name to its international dialing code.
    Handles accents and mojibake variants (e.g. 'Panamá' vs 'Panamǭ')."""
    if not country:
        return ""
    c = country.lower()
    for key, code in _COUNTRY_CODES.items():
        if key in c:
            return code
    return ""


_COUNTRY_CODES = {
    "panam": "507",
    "costa rica": "506",
    "colombia": "57",
    "peru": "51",
    "chile": "56",
    "argentina": "54",
    "ecuador": "593",
    "mexico": "52",
    "españa": "34",
    "espa~a": "34",
    "espana": "34",
}


def _get_messages_for_lead(entry: dict) -> list[dict]:
    """Get the appropriate template messages for a lead."""
    client_id = entry.get("client_id", _default_client_id())
    channel = entry.get("channel", "whatsapp")
    template_set = get_template(client_id, channel)
    if template_set:
        msgs = template_set.enabled_messages()
    else:
        msgs = []
    if not msgs:
        if channel == "instagram":
            msgs = [{"step": 1, "text": "¡Hola {nombre_empresa}! Soy Fabio Pabón, consultor de ventas internacional de PSKloud (Premium-Soft). ¿Les interesaría conocer nuestro software administrativo y contable?"}]
        else:
            msgs = [{"step": 1, "text": "Buenos días, señores de {nombre_empresa}, un gusto saludarles."}]
    # Convert TemplateMessage objects to dicts with media info
    result = []
    for m in msgs:
        if isinstance(m, dict):
            result.append(m)
        else:
            result.append({
                "step": m.step,
                "text": m.text,
                "media_url": getattr(m, "media_url", "") or "",
                "media_type": getattr(m, "media_type", "") or "",
            })
    return result


_SPINTX_RE = re.compile(r"\{\{(.*?)\}\}")


def _spintax(text: str) -> str:
    """Resuelve variaciones {{opción A|opción B|opción C}} eligiendo una al azar.
    Mantiene intactos los placeholders de una llave {nombre_empresa}, {rubro}."""
    def _pick(m):
        return random.choice(m.group(1).split("|"))
    return _SPINTX_RE.sub(_pick, text)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_IN_NAME_RE = re.compile(r"\+?\d[\d\s.,\-()]{6,}")
_DIRECCION_KEYWORDS = re.compile(
    r"\b(?:telefonos?|tel[eé]fono|telf\.?\b|\btlf\b|servicio\s+al\s+cliente|avenida|av\.?\b|calle\b|"
    r"carretera|km\b|kilometro|kil[oó]metro|provincia\b|province\b|circunvalaci[oó]n|distrito\b|"
    r"horarios?|colonia\b|contiguo\b|pricesmart\b|masaya\b)\b",
    re.IGNORECASE,
)


def _clean_business_name(raw: str | None) -> str:
    """Extrae solo el nombre/razón social de un nombre crudo del scraper.

    Elimina direcciones, teléfonos, ciudades y ruido que a veces entran en el
    campo 'nombre' durante el scraping, dejando únicamente el nombre del negocio.
    El scraper suele poner el nombre de la empresa primero, antes de la dirección.
    """
    if not raw:
        return ""
    text = str(raw).strip()
    text = _EMAIL_RE.sub(" ", text)
    text = _PHONE_IN_NAME_RE.sub(" ", text)
    text = re.sub(r"[\[\](){}]", " ", text)

    if "—" in text:
        text = text.split("—")[-1].strip()
    name = text.split(",", 1)[0].strip()
    name = _DIRECCION_KEYWORDS.split(name, 1)[0].strip()
    name = re.sub(r"\s+", " ", name).strip(" .,-_")
    if len(name) < 2:
        return str(raw).strip()
    return name


def _render_template(text: str, entry: dict) -> str:
    text = _spintax(text)
    name = _clean_business_name(entry.get("empresa") or entry.get("nombre", ""))
    saludo = _saludo_por_hora(entry.get("pais", ""))
    bot_wa = _bot_wa_number(entry.get("client_id", ""))
    rendered = (text.replace("{saludo}", saludo)
                    .replace("{nombre_empresa}", name)
                    .replace("{rubro}", entry.get("rubro", ""))
                    .replace("{bot_wa}", bot_wa))
    # Red de seguridad: si una plantilla mal escrita dejó ANOTADO algún
    # placeholder sin sustituir (p.ej. {saludo} literal), no debe salir jamás
    # en un mensaje real. Se limpia cualquier llave simple residual.
    if "{" in rendered:
        rendered = rendered.replace("{saludo}", saludo) \
            .replace("{nombre_empresa}", name) \
            .replace("{rubro}", entry.get("rubro", "")) \
            .replace("{bot_wa}", bot_wa)
    if "{" in rendered:
        rendered = re.sub(r"\{[^{}]*\}", "", rendered).strip()
    return rendered


_bot_wa_cache: dict[str, str] = {}


def _bot_wa_number(client_id: str = "") -> str:
    """Número del bot (WhatsApp Business) para plantillas: {bot_wa} → wa.me link."""
    cid = client_id or _default_client_id()
    if cid in _bot_wa_cache:
        return _bot_wa_cache[cid]
    client = get_client(cid)
    wa = ""
    if client:
        wa = (getattr(client.instagram, "ig_wa_phone", "") or "").strip()
        if not wa:
            wa = (getattr(client.whatsapp, "ig_wa_phone", "") or "").strip()
    if not wa:
        wa = settings.handoff_phone or ""
    wa_link = wa.replace("+", "").replace(" ", "").replace("-", "").replace(".", "")
    result = f"https://wa.me/{wa_link}" if wa_link else ""
    _bot_wa_cache[cid] = result
    return result


def _saludo_por_hora(country: str = "") -> str:
    """Saludo adaptado a la hora LOCAL del lead (misma tz que la ventana de envío)."""
    tz_name = _COUNTRY_TZ.get((country or "").strip())
    now = datetime.now()
    if tz_name:
        try:
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    if now.hour < 12:
        return "Buenos días"
    if now.hour < 19:
        return "Buenas tardes"
    return "Buenas noches"


_number_check_cache: dict[str, tuple[bool | None, float]] = {}
_NUMBER_CHECK_TTL = 12 * 3600  # 12h


async def _check_number_exists(evo, phone: str) -> bool | None:
    """onWhatsApp: True si existe, False si no, None si no se pudo determinar."""
    cached = _number_check_cache.get(phone)
    if cached and (time.time() - cached[1]) < _NUMBER_CHECK_TTL:
        return cached[0]
    exists = await evo.check_number(phone)
    if exists is not None:
        _number_check_cache[phone] = (exists, time.time())
    return exists


_PHONE_BUSINESS_HINTS = [
    "gym", "fitness", "centro", "center", "studio", "medical", "medica",
    "clin", "clinic", "salon", "barber", "spa", "restaurant", "hotel",
    "school", "escuela", "auto", "taller", "agencia", "immobiliaria",
    "inmobiliaria", "contab", "legal", "abog", "dental", "optic",
    "farmac", "panader", "bakery", "crossfit", "entren",
]


def _profile_looks_like_different_business(profile: str, expected: str) -> bool:
    """True si el nombre del perfil de WhatsApp parece OTRO negocio distinto
    del que esperábamos (protección anti-contacto-equivocado).

    Heurística conservadora: solo salta cuando hay señal fuerte de que el
    perfil es un negocio cuyo nombre es claramente distinto y no encontramos
    el negocio esperado. Nombres personales o perfiles cortos NO se tocan."""
    if not profile or not expected:
        return False
    p = profile.lower()
    e = expected.lower()
    # Términos del negocio esperado presentes en el perfil -> OK
    for token in e.replace("/", " ").split():
        if len(token) >= 3 and token in p:
            return False
    # Sin señal de negocio en el perfil (parece nombre de persona) -> no tocar
    if not any(h in p for h in _PHONE_BUSINESS_HINTS):
        return False
    # Normalizar acentos para comparar palabras de forma robusta
    _accmap = str.maketrans("áàäâãéèëêíìïîóòöôõúùüûñ", "aaaaaaeeeeiiiiooooouuuun")
    p_words = set(re.findall(r"[a-z0-9]+", p.translate(_accmap)))
    e_words = set(re.findall(r"[a-z0-9]+", e.translate(_accmap))) - {"de", "del", "la", "el", "los", "las", "y", "e"}
    if e_words and not (p_words & e_words):
        return True
    return False


_profile_check_cache: dict[str, tuple[bool, float]] = {}
_PROFILE_CHECK_TTL = 24 * 3600  # 24h


async def _profile_mismatch(evo, phone: str, expected_name: str) -> bool:
    """Consulta el nombre del perfil WhatsApp del número y decide si parece ser
    OTRO negocio (contacto equivocado). Caché de 24h para no golpear la API."""
    cached = _profile_check_cache.get(phone)
    if cached and (time.time() - cached[1]) < _PROFILE_CHECK_TTL:
        return cached[0]
    try:
        profile = await evo.contact_name(phone)
        mismatch = _profile_looks_like_different_business(profile or "", expected_name)
        _profile_check_cache[phone] = (mismatch, time.time())
        if mismatch:
            logger.warning(f"PERFIL-DISTINTO: {phone} perfil='{profile}' vs esperado='{expected_name}'")
        return mismatch
    except Exception as e:
        logger.error(f"profile check error for {phone}: {e}")
        return False


# ---------------------------------------------------------------------------
# Salvavida anti-duplicado: registro de los textos enviados por número.
# Nunca se envía el MISMO texto dos veces al mismo número en 72h, aunque
# otro bug intente reenviarlo (contención ante cualquier fallo futuro).
# ---------------------------------------------------------------------------
SENT_LOG_FILE = os.path.join(settings.data_dir, "sent_messages.json")
_sent_log: list[dict] = []
_sent_log_loaded = False

# Regla dura de PROSPECCIÓN: máximo 3 mensajes salientes por teléfono.
# Es un valor inquebrantable: jamás se supera, sin importar respuestas del
# contacto (bots, dudas, reclamos). A los 3, silencio total con ese número.
MAX_OUTBOUND_PER_CONTACT = 3

# Reserva en memoria para hacer el tope duro incluso bajo envíos simultáneos
# (la secuencia y una respuesta pueden coincidir milisegundos en el event loop).
_outbound_reserved: dict[str, int] = {}


def _outbound_reserved_for_phone(phone: str) -> int:
    return _outbound_reserved.get(phone, 0)


def _outbound_count_real(phone: str, window_hours: int = 30 * 24) -> int:
    return _outbound_count_for_phone(phone, window_hours) + _outbound_reserved_for_phone(phone)


def _release_outbound_reservation(phone: str):
    cur = _outbound_reserved.get(phone, 0)
    if cur > 0:
        _outbound_reserved[phone] = cur - 1


def _outbound_count_for_phone(phone: str, window_hours: int = 30 * 24) -> int:
    """Cuenta cuántos mensajes salientes reales se han enviado a un número."""
    if not phone:
        return 0
    log = _load_sent_log()
    cutoff = time.time() - window_hours * 3600
    return sum(1 for e in log if e.get("phone") == phone and e.get("ts", 0) >= cutoff)


def _load_sent_log() -> list[dict]:
    global _sent_log, _sent_log_loaded
    if _sent_log_loaded:
        return _sent_log
    _sent_log_loaded = True
    try:
        if os.path.exists(SENT_LOG_FILE):
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                _sent_log = json.load(f)
    except Exception as e:
        logger.error(f"sent log load error: {e}")
        _sent_log = []
    return _sent_log


def _was_text_sent(phone: str, text: str, window_hours: int = 72) -> bool:
    if not phone or not text:
        return False
    log = _load_sent_log()
    text_n = " ".join(text.lower().split())
    cutoff = time.time() - window_hours * 3600
    for e in log:
        if e.get("phone") == phone and e.get("text_n") == text_n and e.get("ts", 0) >= cutoff:
            return True
    return False


def _mark_text_sent(phone: str, text: str):
    log = _load_sent_log()
    log.append({
        "phone": phone,
        "text": text,
        "text_n": " ".join(text.lower().split()),
        "ts": time.time(),
    })
    if len(log) > 5000:
        del log[: len(log) - 5000]
    try:
        with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"sent log save error: {e}")


async def _send_whatsapp(entry: dict, msg_text: str, client_id: str, media_url: str = "", media_type: str = "") -> bool:
    """Send a single WhatsApp message with optional media attachment."""
    msg_text = _spintax(msg_text)
    client = get_client(client_id)
    if not client or not client.whatsapp.enabled:
        return False
    evo = evolution_from_channel(client.whatsapp)
    phone = _format_phone(entry.get("telefono", ""), entry.get("pais", ""))
    if not phone:
        return False
    if _was_text_sent(phone, msg_text):
        logger.warning(f"SALVAVIDA: texto idéntico ya enviado a {phone} (72h) — omitido")
        return False
    if _outbound_count_real(phone) >= MAX_OUTBOUND_PER_CONTACT:
        logger.warning(f"TOPE-DURO: {phone} ya recibió {MAX_OUTBOUND_PER_CONTACT} mensajes — regla de 3, omitido")
        return False
    # Reserva el cupo ANTES de enviar: si otra corrutina intenta el 4º mientras
    # este mensaje está en vuelo, queda bloqueada igualmente.
    _outbound_reserved[phone] = _outbound_reserved.get(phone, 0) + 1
    try:
        exists = await _check_number_exists(evo, phone)
        if exists is False:
            _release_outbound_reservation(phone)
            logger.info(f"Invalid number (pre-check) for {entry.get('nombre','')} ({phone})")
            return None
        await evo.send_typing(phone)
        await asyncio.sleep(random.uniform(
            client.whatsapp.typing_delay_min_ms / 1000,
            client.whatsapp.typing_delay_max_ms / 1000,
        ))
        if media_url:
            # Resolve relative URLs against media_base_url
            if media_url.startswith("/"):
                media_url = settings.media_base_url.rstrip("/") + media_url
            await evo.send_media(phone, media_url, media_type, caption=msg_text, delay_ms=1000)
        else:
            await evo.send_text(phone, msg_text, delay_ms=1000)
        _mark_text_sent(phone, msg_text)
        _release_outbound_reservation(phone)
        return True
    except httpx.HTTPStatusError as e:
        _release_outbound_reservation(phone)
        if '"exists":false' in e.response.text:
            logger.info(f"Invalid number for {entry.get('nombre','')} ({phone})")
            return None
        logger.error(f"WA error for {phone}: {e.response.text[:200]}")
        return False
    except Exception as e:
        _release_outbound_reservation(phone)
        logger.error(f"WA error for {phone}: {e}")
        return False


async def _send_email_message(entry: dict, msg_text: str, client_id: str) -> bool:
    """Send a single email message."""
    client = get_client(client_id)
    if not client or not client.email.enabled:
        return False
    to_email = entry.get("email", "")
    to_name = entry.get("empresa") or entry.get("nombre", "")
    if not to_email:
        return False
    subject = f"Contacto - {to_name}"
    return send_email(client.email, to_email, to_name, subject, msg_text)


async def _send_instagram_message(entry: dict, msg_text: str, client_id: str) -> bool:
    """Send a single Instagram DM."""
    client = get_client(client_id)
    if not client or not client.instagram.enabled:
        return False

    ig_username = entry.get("nombre", "")
    if not ig_username:
        return False

    # Build DM with WA transfer link
    wa_phone = client.instagram.ig_wa_phone or client.whatsapp.evolution_api_url or ""
    dm_text = build_dm_text(
        lead_name=entry.get("nombre", ""),
        company=entry.get("empresa", ""),
        rubro=entry.get("rubro", ""),
        wa_phone=wa_phone,
    )

    # Use a per-client IG sender (cached)
    sender = _get_ig_sender(client)
    if not sender:
        return False

    success = await sender.send_dm(ig_username, dm_text, country=entry.get("pais", ""))
    if success:
        logger.info(f"IG DM sent to {ig_username}")
        _log_activity("sent_instagram", f"DM → {ig_username} ({entry.get('pais','?')})", {"username": ig_username, "pais": entry.get("pais","")})
    return success


# Global IG sender cache (per client)
_ig_senders: dict[str, InstagramSender] = {}


def _get_ig_sender(client) -> InstagramSender | None:
    if not client.instagram.enabled or not client.instagram.instagram_username:
        return None
    if client.id not in _ig_senders:
        _ig_senders[client.id] = InstagramSender(
            username=client.instagram.instagram_username,
            password=client.instagram.instagram_password,
        )
    return _ig_senders[client.id]


async def _ensure_ig_logins():
    """Ensure all IG senders are logged in."""
    clients = list_clients()
    for c in clients:
        sender = _get_ig_sender(c)
        if sender:
            await sender.ensure_login()


async def _send_messages(lead: Lead) -> bool | None:
    """Send the full message sequence for a lead's best channel."""
    entry = {
        "nombre": lead.nombre,
        "empresa": lead.empresa,
        "telefono": lead.telefono,
        "email": lead.email,
        "rubro": lead.rubro,
        "pais": lead.pais,
        "ciudad": lead.ciudad,
        "client_id": lead.client_id or _default_client_id(),
        "channel": _pick_channel(lead),
    }
    channel = entry["channel"]
    client_id = entry["client_id"]
    client = get_client(client_id)
    if not client:
        logger.warning(f"Client {client_id} not found, skipping")
        return False

    ch_cfg = _get_channel_config(client, channel)
    if not ch_cfg or not ch_cfg.enabled:
        logger.warning(f"Channel {channel} disabled for client {client_id}")
        return False

    # Protección anti-contacto-equivocado: antes del primer mensaje por
    # WhatsApp, consultamos el nombre del perfil del número. Si parece ser
    # OTRO negocio (perfil con señal comercial distinta al nombre esperado),
    # se excluye sin gastar ningún mensaje.
    if channel == "whatsapp":
        evo = evolution_from_channel(client.whatsapp)
        try:
            expected_name = _clean_business_name(entry.get("empresa") or entry.get("nombre", ""))
            if expected_name:
                phone_check = _format_phone(entry.get("telefono", ""), entry.get("pais", ""))
                if phone_check and await _profile_mismatch(evo, phone_check, expected_name):
                    excluded = exclude_phone(phone_check, "Perfil WhatsApp no coincide (auto)")
                    remove_from_queue(phone_check)
                    _log_activity("excluido_perfil", f"Perfil distinto → {entry.get('nombre','')} ({phone_check})")
                    logger.warning(f"Perfil no coincide: {entry.get('nombre','')} ({phone_check}) excluido sin enviar")
                    return False
        except Exception as e:
            logger.error(f"Perfil-check falló para {entry.get('nombre','')}: {e}")

    msgs = _get_messages_for_lead(entry)
    total = len(msgs)
    sent_any = False

    # La conversación se crea AHORA (no al final de la secuencia): si el
    # prospecto responde mientras dormimos el delay entre mensajes (45-90s),
    # handle_incoming debe poder encontrarla. Guardamos tras cada envío.
    conv = Conversation(
        lead=lead,
        status="active",
        current_step=0,
        started_at=datetime.now(),
    )

    for i, tmpl in enumerate(msgs):
        text = _render_template(tmpl["text"] if isinstance(tmpl, dict) else tmpl.text, entry)
        media_url = tmpl.get("media_url", "") if isinstance(tmpl, dict) else getattr(tmpl, "media_url", "")
        media_type = tmpl.get("media_type", "") if isinstance(tmpl, dict) else getattr(tmpl, "media_type", "")

        if channel == "whatsapp":
            result = await _send_whatsapp(entry, text, client_id, media_url=media_url, media_type=media_type)
        elif channel == "email":
            result = await _send_email_message(entry, text, client_id)
        elif channel == "instagram":
            result = await _send_instagram_message(entry, text, client_id)
        else:
            logger.warning(f"Unknown channel: {channel}")
            return False

        if result is None:
            return None  # Invalid number

        if result:
            sent_any = True
            conv.current_step = i + 1
            conv.messages.append(Message(
                direction="out", text=text, timestamp=datetime.now(),
            ))
            try:
                phone_for_log = _format_phone(entry.get("telefono", ""), entry.get("pais", ""))
                if phone_for_log:
                    add_message(phone_for_log, conv.messages[-1])
                save_conversation(conv)
            except Exception as e:
                logger.error(f"Error persistiendo conversación de {entry.get('nombre','')}: {e}")
            _log_activity(f"sent_{channel}", f"MSG{i+1}/{total} → {entry.get('nombre','')} ({channel})")
            logger.info(f"MSG{i+1}/{total} ({channel}) sent to {entry.get('nombre','')}")

        if i < total - 1:
            await asyncio.sleep(random.uniform(
                ch_cfg.min_delay_seconds,
                ch_cfg.max_delay_seconds,
            ))

    if sent_any:
        _log_activity("sent_complete", f"{total} MSG ({channel}) → {entry.get('nombre','')} ({entry.get('pais','')})")

    return sent_any


FOLLOWUP_AFTER_HOURS = 24  # mínimo 24h tras el primer contacto (anti-spam)

_FOLLOWUP_MSG = (
    "{{Le saluda Fabio Pabón, consultor de ventas de Premium Soft Internacional. Por acá le "
    "comparto una imagen con nuestros productos estandarizados, que cumplen con las normativas "
    "de ley local. Quedo a total disposición: si gusta, pautamos una demo en vivo sin ningún "
    "compromiso. 🙌🏽🫱🏼🫲🏽|"
    "Quedo nuevamente a su disposición: soy Fabio Pabón, de Premium Soft Internacional. Le "
    "comparto una imagen con nuestra línea de productos estandarizados, todos conforme a las "
    "normativas de ley de su país. Si gusta, agendamos una demo en vivo sin ningún compromiso. "
    "🙌🏽|"
    "Hola, por aquí de nuevo Fabio Pabón, de Premium Soft Internacional. Adjunto una imagen de "
    "nuestros productos estandarizados, que cumplen la normativa fiscal local. Quedo pendiente "
    "por si quieren agendar una demo en vivo, sin ningún compromiso. 🙌🏽🫱🏼🫲🏽}}"
)


_last_followup_ts = 0.0


async def _maybe_send_followup():
    """Send the presentation image+message to leads who never replied after N hours.

    Anti-spam: at most ONE follow-up per cycle, with a long random pause between
    each (45-90 min), and it respects the per-channel, per-country and daily caps.
    Sends ONLY ONCE per conversation (current_step 2 -> 3).
    """
    global _last_followup_ts
    if time.time() - _last_followup_ts < 2700:  # min 45 min entre follow-ups
        return
    for conv in list_conversations(status="active"):
        if conv.current_step < 2 or conv.current_step >= 3 or conv.last_reply_at is not None:
            continue
        if (datetime.now() - conv.started_at).total_seconds() < FOLLOWUP_AFTER_HOURS * 3600:
            continue
        client_id = conv.lead.client_id or _default_client_id()
        client = get_client(client_id)
        if not client or not client.whatsapp.enabled:
            continue
        if not _is_work_time(client_id, "whatsapp", conv.lead.pais):
            continue
        if not _can_send_channel(client_id, "whatsapp"):
            break
        if not _can_send_to_country(conv.lead.pais, conv.lead.rubro):
            continue
        if get_today_count() >= settings.max_daily_outbound:
            break
        phone = _format_phone(conv.lead.telefono, conv.lead.pais)
        if not phone:
            continue
        entry = {
            "nombre": conv.lead.nombre,
            "empresa": conv.lead.empresa,
            "telefono": conv.lead.telefono,
            "rubro": conv.lead.rubro,
            "pais": conv.lead.pais,
            "client_id": client_id,
        }
        media_url = getattr(client.whatsapp, "media_url", "") or ""
        media_type = getattr(client.whatsapp, "media_type", "") or ""
        _last_followup_ts = time.time()
        result = await _send_whatsapp(entry, _render_template(_FOLLOWUP_MSG, entry), client_id, media_url=media_url, media_type=media_type)
        if result is None:
            exclude_phone(phone, "Número inválido en seguimiento")
            conv.status = "excluido"
            logger.info(f"Follow-up invalid number, excluded {conv.lead.nombre} ({phone})")
        elif result:
            _mark_channel_sent(client_id, "whatsapp")
            _mark_country_sent(conv.lead.pais, conv.lead.rubro)
            increment_today_count()
            conv.current_step = 3
            _log_activity("followup", f"Imagen de presentación → {conv.lead.nombre} ({phone})")
            logger.info(f"Follow-up image sent to {conv.lead.nombre} ({phone})")
        save_conversation(conv)
        break  # una sola por ciclo


async def _evolution_connection_ok(client_id: str) -> bool:
    """Si la sesión WhatsApp se cae (logout/401/bloqueo), pausa la prospección."""
    try:
        client = get_client(client_id)
        if not client or not client.whatsapp.enabled:
            return True
        evo = evolution_from_channel(client.whatsapp)
        state = await evo.connection_state()
        if not state:
            return True  # no se pudo consultar: no asumir
        st = state.get("state") or (state.get("instance", {}) or {}).get("state") or ""
        reason = state.get("statusReason")
        if st in ("close", "logout", "dead", "disconnected") or reason in (401, "401"):
            logger.warning(f"EVOLUTION session no abierta (state={st}, reason={reason}) — PAUSANDO prospección")
            try:
                import prospector
                prospector._prospector_paused = True
            except Exception:
                pass
            return False
        return True
    except Exception as e:
        logger.warning(f"connection_state check failed: {e}")
        return True


# ---------------------------------------------------------------------------
# Queue processor — cycles by client+channel, respects per-channel limits
# ---------------------------------------------------------------------------


def _group_queue_by_client() -> dict:
    groups = defaultdict(list)
    for e in _queue:
        key = f"{e.get('client_id', _default_client_id())}|{e.get('channel', 'whatsapp')}"
        groups[key].append(e)
    return dict(groups)


_rubro_conversion_cache: dict[str, float] = {}
_rubro_conversion_ts = 0.0


def _rubro_conversion_score(rubro: str) -> float:
    """Conversión histórica de un rubro (handoff + interesado / total contactados).

    Funnel por rubro: prioriza los rubros que más señales de avance dan
    (demo/llamada/interés) frente a los que solo acumulan 'no responde'."""
    global _rubro_conversion_cache, _rubro_conversion_ts
    if time.time() - _rubro_conversion_ts < 30 * 60:  # re-mide cada 30 min
        return _rubro_conversion_cache.get(rubro or "", 0.0)
    try:
        conn = _ConversionsDB()
        rows = conn.execute("SELECT lead_json, status FROM conversations").fetchall()
        conn.close()
        by_rubro: dict[str, dict[str, int]] = {}
        for lead_json, status in rows:
            rubro = "General"
            try:
                lead = json.loads(lead_json)
                rubro = lead.get("rubro") or "General"
            except Exception:
                pass
            d = by_rubro.setdefault(rubro, {})
            d[status] = d.get(status, 0) + 1
        scoring: dict[str, float] = {}
        for rubro_key, counts in by_rubro.items():
            contactados = sum(counts.values())
            if contactados == 0:
                scoring[rubro_key] = 0.0
                continue
            avanzan = counts.get("handoff", 0) + counts.get("opciones", 0)
            categorias_interes = counts.get("ya_tiene_sistema", 0)
            scoring[rubro_key] = (avanzan * 2.0 + categorias_interes * 0.5) / contactados
        # rubros sin datos empiezan neutrales (0.25) para no dejarlos atrás por azar
        _rubro_conversion_cache = {k: scoring.get(k, 0.25) for k in set(_rubro_conversion_cache)}
        _rubro_conversion_ts = time.time()
        return _rubro_conversion_cache.get(rubro or "", scoring.get(rubro or "", 0.25))
    except Exception as e:
        logger.error(f"rubro conversion error: {e}")
        _rubro_conversion_ts = time.time()
        return _rubro_conversion_cache.get(rubro or "", 0.0)


def _ConversionsDB():
    import sqlite3
    return sqlite3.connect(settings.conversations_db, timeout=10)


def _reorder_queue_by_funnel():
    """Order the queue by funnel: rubros con mejor conversión primero, y dentro
    de cada rubro respeta el orden previo de países prioritarios."""
    try:
        rank = {c: i for i, c in enumerate([
            "Colombia", "Costa Rica", "Nicaragua", "El Salvador", "Honduras",
        ])}
        snapshot = list(_queue)
        idx = {id(e): i for i, e in enumerate(snapshot)}
        snapshot.sort(key=lambda e: (
            -_rubro_conversion_score(e.get("rubro", "")),
            rank.get(e.get("pais", ""), len(rank)),
            idx.get(id(e), 0),
        ))
        _queue[:] = snapshot
    except Exception as e:
        logger.error(f"funnel reorder error: {e}")


async def process_auto():
    """Auto-loop: sends up to 5 leads per cycle, respects per-channel limits."""
    global _queue, _running, _running_since
    logger.info("Auto-queue processor started")

    cycle = 0
    while True:
        cycle += 1
        try:
            await asyncio.sleep(30)

            if _queue_paused:
                if cycle % 10 == 1:
                    logger.info(f"Queue paused by user (Stop button, cycle {cycle})")
                continue

            if _running:
                if _running_since and time.monotonic() - _running_since > 900:
                    logger.warning("Queue watchdog: send loop stuck >15min, forcing _running reset")
                    _running = False
                    _running_since = 0.0
                elif not _running_since:
                    _running_since = time.monotonic()
                continue

            load_queue()
            _reorder_queue_by_funnel()
            if not await _evolution_connection_ok(_default_client_id()):
                if cycle % 10 == 1:
                    logger.info(f"Queue paused (WhatsApp session no conectada, cycle {cycle})")
                continue
            await _maybe_send_followup()
            if not _queue:
                if cycle % 10 == 1:
                    logger.info(f"Queue empty (cycle {cycle})")
                continue

            groups = _group_queue_by_client()
            available = [k for k in groups if _can_send_group(k)]
            if not available:
                continue

            # Respect per-client/per-channel work hours in each country's LOCAL time (9-16 lun-vie)
            work_time_groups = []
            for k in available:
                cid, ch = k.split("|", 1)
                if any(_is_work_time(cid, ch, e.get("pais")) for e in groups[k]):
                    work_time_groups.append(k)
            if not work_time_groups:
                if cycle % 10 == 1:
                    logger.info(f"Queue idle (outside client work hours, cycle {cycle})")
                continue
            available = work_time_groups

            _running = True
            _running_since = time.monotonic()
            sent_batch = []
            skip_keys = set()
            max_per_cycle = 5

            try:
                for group_key in available:
                    if len(sent_batch) >= max_per_cycle:
                        break
                    client_id, channel = group_key.split("|", 1)
                    for entry in list(groups[group_key]):
                        if len(sent_batch) >= max_per_cycle:
                            break
                        if not _can_send_channel(client_id, channel):
                            break
                        if not _is_work_time(client_id, channel, entry.get("pais")):
                            continue
                        if not _can_send_to_country(entry.get("pais", ""), entry.get("rubro", "")):
                            continue
                        if _is_country_blocked(entry.get("pais", "")):
                            _log_activity("skip", f"Omitido (país bloqueado): {entry.get('nombre','')} ({entry.get('pais','?')})")
                            continue
                        if get_today_count() >= settings.max_daily_outbound:
                            break

                        phone_raw = entry.get("telefono", "")
                        phone_clean = _format_phone(phone_raw, entry.get("pais", "")) if phone_raw else ""

                        if channel == "whatsapp" and phone_clean and get_conversation(phone_clean):
                            skip_keys.add(phone_clean)
                            _log_activity("skip", f"Omitido (ya contactado): {entry.get('nombre','')} ({entry.get('pais','?')})")
                            continue

                        biz_key = _business_key(entry)
                        if channel == "whatsapp" and biz_key and _business_key_contacted(biz_key):
                            skip_keys.add(phone_clean or entry.get("email", ""))
                            _log_activity("skip", f"Omitido (negocio ya contactado por otro número): {entry.get('nombre','')} ({entry.get('pais','?')})")
                            continue

                        if channel == "whatsapp" and phone_clean and is_phone_excluded(phone_clean):
                            skip_keys.add(phone_clean)
                            _log_activity("skip", f"Omitido (excluido): {entry.get('nombre','')} ({entry.get('pais','?')})")
                            continue

                        if not phone_clean and not entry.get("email", "") and not (entry.get("instagram_username") or "").strip():
                            skip_keys.add("")
                            _log_activity("skip", f"Omitido (sin canal de contacto): {entry.get('nombre','')} ({entry.get('pais','?')})")
                            continue

                        lead = Lead(**{k: v for k, v in entry.items() if k in Lead.model_fields})
                        try:
                            result = await asyncio.wait_for(_send_messages(lead), timeout=600)
                        except asyncio.TimeoutError:
                            logger.warning(f"Queue watchdog: send timeout for {entry.get('nombre','?')}, skipping")
                            result = False
                        if result is True:
                            skip_keys.add(phone_clean or entry.get("email", ""))
                            _mark_channel_sent(client_id, channel)
                            _mark_country_sent(entry.get("pais", ""), entry.get("rubro", ""))
                            increment_today_count()
                            sent_batch.append(entry)
                        if result is None:
                            skip_keys.add(phone_clean or entry.get("email", ""))

                        delay = random.uniform(5, 10) if result is None else random.uniform(
                            settings.min_delay_seconds, settings.max_delay_seconds
                        )
                        await asyncio.sleep(delay)

            finally:
                if skip_keys:
                    _queue = [e for e in _queue if _norm_phone(e.get("telefono", "") or e.get("email", "")) not in skip_keys]
                save_queue(force=True)
                if sent_batch:
                    _save_daily_summary(sent_batch)
                    _log_activity("batch", f"Auto-lote: {len(sent_batch)} enviados, {len(_queue)} restantes", {"sent": len(sent_batch), "queue": len(_queue)})
                    logger.info(f"Auto-batch: {len(sent_batch)} sent, {len(_queue)} remain")
                _running = False

        except Exception as e:
            logger.error(f"process_auto cycle error: {e}", exc_info=True)
            _running = False
        except BaseException as e:
            logger.critical(f"process_auto FATAL cycle error ({type(e).__name__}): {e}", exc_info=True)
            _running = False


def _can_send_group(group_key: str) -> bool:
    client_id, channel = group_key.split("|", 1)
    return _can_send_channel(client_id, channel)


async def process_next_batch(count: int = 5) -> dict:
    """Manual on-demand: send up to `count` leads from queue."""
    global _running, _queue
    if _running:
        return {"sent": 0, "error": "already_running"}

    load_queue(force_reload=True)
    if not _queue:
        return {"sent": 0, "error": "empty_queue"}

    if not await _evolution_connection_ok(_default_client_id()):
        return {"sent": 0, "queue_status": get_queue_status(), "error": "session_no_conectada"}

    _running = True
    _running_since = time.monotonic()
    sent_list = []

    try:
        logger.info(f"process_next_batch: starting scan of {len(_queue)} leads")
        while len(sent_list) < count:
            if get_today_count() >= settings.max_daily_outbound:
                break

            found = False
            scanned = 0
            for i, entry in enumerate(_queue):
                scanned += 1
                client_id = entry.get("client_id", _default_client_id())
                channel = entry.get("channel", "whatsapp")
                pais = entry.get("pais", "")

                if not _is_work_time(client_id, channel, pais):
                    if scanned <= 3:
                        logger.info(f"  SKIP work_time: {entry.get('nombre','')} ({pais})")
                    continue
                if not _can_send_channel(client_id, channel):
                    if scanned <= 3:
                        logger.info(f"  SKIP can_send_channel: {entry.get('nombre','')} ({pais})")
                    continue
                if not _can_send_to_country(pais, entry.get("rubro", "")):
                    if scanned <= 3:
                        logger.info(f"  SKIP can_send_to_country: {entry.get('nombre','')} ({pais})")
                    continue
                if _is_country_blocked(pais):
                    if scanned <= 3:
                        logger.info(f"  SKIP country_blocked: {entry.get('nombre','')} ({pais})")
                    continue

                phone_clean = _format_phone(entry.get("telefono", ""), pais)
                if channel == "whatsapp":
                    if not phone_clean or len(phone_clean.replace("+", "")) < 10:
                        if scanned <= 3:
                            logger.info(f"  SKIP phone_invalid: {entry.get('nombre','')} ({phone_clean})")
                        continue
                if channel == "whatsapp" and phone_clean and get_conversation(phone_clean):
                    if scanned <= 3:
                        logger.info(f"  SKIP has_conv: {entry.get('nombre','')}")
                    continue

                biz_key = _business_key(entry)
                if channel == "whatsapp" and biz_key and _business_key_contacted(biz_key):
                    if scanned <= 3:
                        logger.info(f"  SKIP biz_contacted: {entry.get('nombre','')} ({biz_key})")
                    continue

                if channel == "whatsapp" and phone_clean and is_phone_excluded(phone_clean):
                    if scanned <= 3:
                        logger.info(f"  SKIP excluded: {entry.get('nombre','')}")
                    continue

                if not phone_clean and not entry.get("email", "") and not (entry.get("instagram_username") or "").strip():
                    if scanned <= 3:
                        logger.info(f"  SKIP no_channel: {entry.get('nombre','')}")
                    continue

                _queue.pop(i)
                found = True

                lead = Lead(**{k: v for k, v in entry.items() if k in Lead.model_fields})
                try:
                    result = await asyncio.wait_for(_send_messages(lead), timeout=600)
                except asyncio.TimeoutError:
                    logger.warning(f"Queue watchdog: manual send timeout for {entry.get('nombre','?')}, skipping")
                    result = False
                if result is True:
                    _mark_channel_sent(client_id, channel)
                    _mark_country_sent(pais, entry.get("rubro", ""))
                    increment_today_count()
                    sent_list.append(entry)
                elif result is None:
                    _queue = [e for e in _queue if _norm_phone(e.get("telefono", "") or e.get("email", "")) != _norm_phone(entry.get("telefono", "") or entry.get("email", ""))]

                delay = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
                await asyncio.sleep(delay)
                break

            if not found:
                logger.info(f"process_next_batch: no sendable lead found after scanning {scanned} leads")
                break

    finally:
        save_queue(force=True)
        if sent_list:
            _save_daily_summary(sent_list)
        _running = False

    return {"sent": len(sent_list), "queue_status": get_queue_status()}


def get_daily_summary() -> list:
    try:
        if os.path.exists(SUMMARY_FILE):
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


_queue_task = None


def remove_from_queue(phone: str) -> int:
    """Remove all pending queue entries matching a phone (used when excluding a contact)."""
    global _queue
    target = _norm_phone(phone or "")
    before = len(_queue)
    if target:
        _queue = [e for e in _queue if _norm_phone(e.get("telefono", "") or e.get("email", "")) != target]
        save_queue(force=True)
    return before - len(_queue)


def rename_in_queue(phone: str, nombre: str = "", empresa: str = "") -> int:
    """Update name/company on any pending queue entries matching a phone."""
    global _queue
    target = _norm_phone(phone or "")
    n = 0
    if target:
        for e in _queue:
            if _norm_phone(e.get("telefono", "") or e.get("email", "")) == target:
                if nombre:
                    e["nombre"] = nombre
                if empresa:
                    e["empresa"] = empresa
                n += 1
        if n:
            save_queue(force=True)
    return n


def start_queue_task():
    global _queue_task
    if _queue_task is None:
        loop = asyncio.new_event_loop()

        async def _run():
            await process_auto()

        def _start():
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_run())
            except Exception as e:
                logger.error(f"Queue thread crashed (Exception): {e}", exc_info=True)
            except BaseException as e:
                logger.critical(f"Queue thread crashed FATAL: {e}", exc_info=True)

        import threading
        t = threading.Thread(target=_start, daemon=True)
        t.start()
        _queue_task = t
        logger.info("Auto-queue background task started")


_incoming_dedup: set[str] = set()

_AUTO_REPLY_PATTERNS = [
    "gracias por su mensaje",
    "gracias por contactarnos",
    "gracias por escribirnos",
    "gracias por comunicarte",
    "gracias por ponerte en contacto",
    "gracias por comunicarte con nosotros",
    "thank you for your message",
    "we'll get back to you",
    "bienvenidos a",
    "bienvenido a",
    "pronto nos comunicaremos",
    "le responderemos a la brevedad",
    "te responderemos a la brevedad",
    "recibimos tu mensaje",
    "hemos recibido su mensaje",
    "te contactaremos pronto",
    "lo contactaremos pronto",
    "un asesor le atenderá",
    "un asesor te atenderá",
    "nuestro asesor te contactará",
    "nuestro asesor le contactará",
    "nuestro equipo te contactará",
    "nuestro equipo le contactará",
    "en breve te contactaremos",
    "en breve le contactaremos",
    "un miembro de nuestro equipo",
    "atendemos tu solicitud",
    "estás hablando a",
    "estas hablando a",
    "en qué puedo ayudarte",
    "en que puedo ayudarte",
    "puedo ayudarte con",
    "puedo ayudarle con",
    "solo puedo ayudarte",
    "solo puedo ayudarle",
    "solo gestionamos",
    "solo me dedico a",
    "solo puedo asistirte",
    "no recibimos propuestas",
    "no recibimos propuesta",
    "no aceptamos propuestas",
    "no contamos con",
    "no atendemos propuestas",
    "asistente de",
    "asistentes de",
    "este número pertenece",
    "este número está asociado",
    "no es la empresa",
    "no somos la empresa",
    "nos especializamos únicamente",
    "nos dedicamos únicamente",
    # --- Patrones de bots centroamericanos / WhatsApp Business auto-replies ---
    "puedes compartirnos",
    "compartirnos un nombre",
    "nombre y apellido",
    "horario de atención",
    "horario de atencion",
    "horario de delivery",
    "será un gusto atenderte",
    "sera un gusto atenderte",
    "lunes cerrado",
    "martes a domingo",
    "nosotros te atendemos",
    "te atenderemos pronto",
    "en horario de",
    "nuestro horario",
    "whatsapp business",
    "este chat es automatico",
    "este chat es automático",
    "respuesta automatica",
    "respuesta automática",
    "no podemos responder",
    "no cuentan con personal",
    "fuera de horario",
    "horario no laboral",
    "agentes disponibles",
    "un agente le atenderá",
    "un agente te atenderá",
    "pronto un agente",
    "dónde nos contactas",
    "donde nos contactas",
    "de dónde nos contactas",
    "de donde nos contactas",
]

_auto_reply_seen: dict[str, tuple[int, float]] = {}  # texto normalizado -> (veces, última_ts)


def _note_reply_template(text: str):
    """Cuenta plantillas compartidas: si el MISMO texto llega desde >=3 negocios
    distintos, es un bot de respuesta automática, no una interacción real."""
    lower = " ".join((text or "").lower().split())
    if len(lower) < 40:
        return
    count, _ = _auto_reply_seen.get(lower, (0, 0.0))
    _auto_reply_seen[lower] = (count + 1, time.time())
    if len(_auto_reply_seen) > 1000:
        for k in list(_auto_reply_seen):
            if time.time() - _auto_reply_seen[k][1] > 7 * 86400:
                del _auto_reply_seen[k]
    if count + 1 >= 3:
        logger.info(f"Plantilla de bot detectada (vista en {count+1} negocios): {lower[:70]}")


def _is_active_prospect(phone: str, conv: Conversation) -> bool:
    """¿El número es un prospecto ACTIVO de la campaña actual?

    El bot atiende SIEMPRE (cualquier hora, día o fin de semana) a contactos de
    la campaña de hoy: en la cola actual o con conversación iniciada en las
    últimas PROSPECT_ACTIVE_HOURS. Campañas anteriores: silencio total.
    """
    phone_norm = _norm_phone(phone)
    for e in _queue:
        if _norm_phone(e.get("telefono", "")) == phone_norm:
            return True
    if conv.started_at and (datetime.now() - conv.started_at).total_seconds() <= settings.prospect_active_hours * 3600:
        return True
    return False


def _is_auto_reply(text: str, gap_secs: float | None = None) -> bool:
    lower = " ".join((text or "").lower().split())
    for pattern in _AUTO_REPLY_PATTERNS:
        if pattern in lower:
            return True
    # Plantilla compartida: mismo texto visto desde >=3 negocios = bot
    if len(lower) >= 40 and _auto_reply_seen.get(lower, (0, 0))[0] >= 3:
        return True
    # Respuesta demasiado rápida (bot responde al instante) y genérica/corta
    if gap_secs is not None and gap_secs < 8 and len(lower) <= 120:
        return True
    return False


def _fallback_classify(message_text: str) -> tuple[Classification, str, dict]:
    """Fallback local humanizado cuando Gemini no está disponible (cuota gratuita o red)."""
    low = (message_text or "").lower()

    if any(w in low for w in ("equivoca", "no soy", "no es ", "no trabajo", "me equivo", "no pid", "es un error", "no exist", "dejé de trabajar")):
        return (
            Classification.CONTACTO_EQUIVOCADO,
            "Le saluda Fabio Pabón, Consultor de Ventas de PSKloud / Premium Soft. Ofrezco disculpas, quizá por error terminó su número en nuestra base de datos; procedo a corregirlo. De igual manera le muestro en la imagen a qué nos dedicamos por si es de su interés. Estamos a la orden, feliz día.",
            {"enviar_imagen": True, "avisar_fabio": False, "excluir": True},
        )

    if any(w in low for w in ("ya tengo", "tengo sistema", "tengo software", "ya uso", "ya contamos", "tenemos sistema", "ya tenemos", "tengo un sistema")):
        return (
            Classification.YA_TIENE_SISTEMA,
            "Le saluda Fabio Pabón, Consultor de Ventas de PSKloud / Premium Soft. Contamos con soluciones en la nube diseñadas para centralizar y automatizar toda la gestión de su empresa. Me pongo a la orden por si requiere de nuestros servicios. 🙌🏽🫱🏼🫲🏽",
            {"enviar_imagen": True, "avisar_fabio": False, "excluir": False},
        )

    if any(w in low for w in ("demo", "precio", "cuánto", "llamar", "llamada", "videollamada", "interes", "me interesa", "quiero saber", "muestren", "conocer más", "más información", "me gustaría")):
        return (
            Classification.HANDOFF,
            "¡Claro que sí! Me encantaría mostrarle la plataforma. Con gusto le agendo una breve demostración en vivo, sin ningún compromiso. 🙌🏽",
            {"enviar_imagen": True, "avisar_fabio": True, "excluir": False},
        )

    if any(w in low for w in ("no gracias", "no me interesa", "no interesa", "estoy bien", "ocupado", "no estoy interesado")):
        return (
            Classification.NO_INTERESADO,
            "Entendido, no se preocupe. Agradezco su tiempo y quedo atento por si más adelante necesita nuestros servicios. ¡Feliz día!",
            {"enviar_imagen": False, "avisar_fabio": False, "excluir": False},
        )

    return (
        Classification.DUDA,
        "Gracias por su mensaje. Somos PSKloud / Premium Soft y ofrecemos software administrativo, contable y POS en la nube. Le comparto la imagen para que conozca nuestras soluciones; quedo a la orden. 🙌🏽",
        {"enviar_imagen": True, "avisar_fabio": False, "excluir": False},
    )


async def handle_incoming(phone: str, sender_name: str, message_text: str):
    # Dedup: skip if same phone+text already processed in last 60s
    dedup_key = f"{phone}:{message_text[:50]}"
    if dedup_key in _incoming_dedup:
        logger.info(f"Ignoring duplicate incoming from {phone}")
        return
    _incoming_dedup.add(dedup_key)
    if len(_incoming_dedup) > 100:
        _incoming_dedup.clear()

    conv = get_conversation(phone)
    if not conv:
        # Maybe it arrived while the sequence sleeps between MSG1 and MSG2 —
        # but the conversation should exist by now. If a lead was interrupted
        # (crash mid-sequence) fall back to creating it from the queue entry.
        entry = next((e for e in _queue if _norm_phone(e.get("telefono", "")) == _norm_phone(phone)), None)
        if entry:
            lead = Lead(**{k: v for k, v in entry.items() if k in Lead.model_fields})
            conv = Conversation(lead=lead, status="active", current_step=1, started_at=datetime.now())
            save_conversation(conv)
            logger.info(f"Creada conversación recuperada para {lead.nombre} ({phone}) en handle_incoming")
        else:
            logger.info(f"Message from unknown number {phone}, ignoring")
            return

    # SOLO respondemos a prospectos ACTIVOS de la campaña actual. Un contacto
    # de una prospección anterior, o un contacto manual del usuario, NUNCA debe
    # recibir respuestas automáticas (aunque tenga conversación guardada en DB).
    if conv.status in ("handoff", "closed", "excluido", "opciones"):
        logger.info(f"Conversación {conv.status} de {sender_name} ({phone}) — sin respuesta automática")
        return
    if not _is_active_prospect(phone, conv):
        logger.info(f"Contacto fuera de prospección activa: {sender_name} ({phone}) — sin respuesta automática")
        return

    # Gap desde nuestro último mensaje saliente (los bots responden al instante)
    gap_secs = None
    for m in reversed(conv.messages):
        if m.direction == "out":
            gap_secs = (datetime.now() - m.timestamp).total_seconds()
            break
    conv.messages.append(Message(direction="in", text=message_text))
    _note_reply_template(message_text)
    try:
        add_message(_norm_phone(phone), conv.messages[-1])
    except Exception as e:
        logger.error(f"Error persistiendo mensaje entrante de {phone}: {e}")

    # Detect auto-replies (bot de otro negocio): se guardan como contexto PERO
    # no cuentan como interacción real (no last_reply_at, no handoff, no reply).
    if _is_auto_reply(message_text, gap_secs):
        logger.info(f"Auto-reply/bot de {sender_name} ({phone}) ignorado — no cuenta como respuesta")
        save_conversation(conv)
        return

    conv.last_reply_at = datetime.now()

    # Tope duro también en el CONTADOR de la conversación: si este contacto ya
    # recibió sus 3 mensajes, NO se responde nada, ni siquiera se llama a Gemini.
    cphone = _format_phone(conv.lead.telefono, conv.lead.pais or "")
    num_enviados = _outbound_count_real(cphone)
    if num_enviados >= MAX_OUTBOUND_PER_CONTACT:
        logger.info(f"TOPE-DURO en conversación: {phone} ya recibió {num_enviados} mensajes — respuesta omitida")
        save_conversation(conv)
        return

    try:
        history = []
        for m in conv.messages[-6:]:
            role = "user" if m.direction == "in" else "model"
            history.append({"role": role, "parts": [m.text]})

        empresa_nombre = _clean_business_name(conv.lead.empresa or conv.lead.nombre)
        classification, reply, actions = await gemini.classify(
            message_text, history,
            num_mensajes_enviados=num_enviados,
            nombre_empresa=empresa_nombre,
        )
    except Exception as e:
        logger.error(f"Gemini error (using fallback): {e}")
        classification, reply, actions = _fallback_classify(message_text)

    conv.classification = classification
    conv.messages.append(Message(direction="out", text=reply, classification=classification))
    try:
        add_message(_norm_phone(phone), conv.messages[-1])
    except Exception as e:
        logger.error(f"Error persistiendo respuesta a {phone}: {e}")

    try:
        client_id = conv.lead.client_id
        client = get_client(client_id) if client_id else None
        if client and client.whatsapp.enabled:
            send_image = bool(actions.get("enviar_imagen"))
            media_url = getattr(client.whatsapp, "media_url", "") or ""
            media_type = getattr(client.whatsapp, "media_type", "") or ""
            entry = {
                "nombre": conv.lead.nombre,
                "empresa": conv.lead.empresa,
                "telefono": conv.lead.telefono,
                "pais": conv.lead.pais,
                "rubro": conv.lead.rubro,
                "client_id": client_id,
            }
            # Pasa por el MISMO salvavidas que la secuencia: anti-duplicado +
            # tope duro de 3 mensajes. Un bot de otro negocio jamás provoca una
            # 4ª respuesta: a los 3 mensajes, silencio total con ese número.
            await _send_whatsapp(
                entry, reply, client_id,
                media_url=media_url if send_image else "",
                media_type=media_type if send_image else "",
            )
    except Exception as e:
        logger.error(f"Error sending reply: {e}")

    if actions.get("excluir"):
        exclude_phone(cphone, "Contacto equivocado (automático)")
        remove_from_queue(cphone)
        conv.status = "excluido"
        logger.info(f"Contacto equivocado, excluido {conv.lead.nombre} ({cphone})")
    elif actions.get("avisar_fabio") or classification in (Classification.INTERESADO, Classification.HANDOFF):
        summary = "\n".join([f"{'Yo' if m.direction == 'out' else 'Lead'}: {m.text[:100]}" for m in conv.messages[-6:]])
        await send_handoff_alert(conv.lead, message_text, summary)
        conv.status = "handoff"
    elif classification == Classification.YA_TIENE_SISTEMA:
        conv.status = "opciones"
    elif classification == Classification.NO_INTERESADO:
        conv.status = "closed"
    else:
        conv.status = "duda"

    save_conversation(conv)
    registrar_caso(phone, message_text, reply, classification)
    logger.info(f"Incoming from {sender_name}: classified as {classification.value}")
