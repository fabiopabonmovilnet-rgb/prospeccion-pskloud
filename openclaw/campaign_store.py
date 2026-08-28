from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional

DATA_DIR = "/app/data"
CLIENTS_FILE = os.path.join(DATA_DIR, "clientes.json")
PLANTILLAS_FILE = os.path.join(DATA_DIR, "plantillas.json")
STATE_FILE = os.path.join(DATA_DIR, "campaign_state.json")
REPORT_FILE = os.path.join(DATA_DIR, "reporte_prospector.json")
ACTIVITY_FILE = os.path.join(DATA_DIR, "actividad_prospector.jsonl")
QUEUE_FILE = os.path.join(DATA_DIR, "leads_para_enviar.json")
COUNTRY_COUNTS_FILE = os.path.join(DATA_DIR, "envios_por_pais.json")
MEDIA_DIR = os.path.join(DATA_DIR, "media")


def _read_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "campana"


# ─── Geography: countries and cities from Client config ───


def client_country_cities() -> dict:
    """Country -> list of cities in the order they appear in clientes.json."""
    out: dict = {}
    clients = _read_json(CLIENTS_FILE, [])
    for c in clients:
        for ubicacion in c.get("ubicaciones", []):
            parts = [p.strip() for p in ubicacion.split(",")]
            if len(parts) >= 2:
                pais = parts[-1]
                ciudad = parts[0]
            else:
                pais = parts[0]
                ciudad = parts[0]
            out.setdefault(pais, [])
            if ciudad not in out[pais]:
                out[pais].append(ciudad)
    return out


def client_countries() -> list:
    return list(client_country_cities().keys())


# ─── Plantilla campaign entries ───


def _campaign_entries(plantillas: list = None):
    plantillas = plantillas if plantillas is not None else _read_json(PLANTILLAS_FILE, [])
    for e in plantillas:
        if isinstance(e, dict) and e.get("channel") == "whatsapp" and e.get("campaign"):
            yield e


def _normalize_messages(entry: dict) -> list:
    """Convert plantilla messages into step dicts with media normalized."""
    out = []
    for m in entry.get("messages", []):
        step = int(m.get("step", 0))
        text = m.get("text", "")
        enabled = bool(m.get("enabled", True))
        media = m.get("media") or {}
        item = {
            "step": step,
            "text": text,
            "enabled": enabled,
            "media_url": media.get("url", ""),
            "media_type": media.get("type", ""),
            "media_enabled": bool(media.get("enabled", True)),
            "caption": media.get("caption", ""),
        }
        out.append(item)
    return sorted(out, key=lambda x: x["step"])


def _media_of(entry: dict) -> dict:
    for m in entry.get("messages", []):
        media = m.get("media")
        if media and media.get("url"):
            return {"enabled": bool(media.get("enabled", True)), "type": media.get("type", "image"),
                    "url": media.get("url", ""), "caption": media.get("caption", "")}
    return {}


def _state() -> dict:
    return _read_json(STATE_FILE, {})


def list_campaigns() -> list:
    state = _state()
    geo = client_country_cities()
    all_countries = list(geo.keys())
    result = []
    for entry in _campaign_entries():
        key = entry["campaign"]
        st = state.get(key, {})
        paises = st.get("paises_objetivo") or entry.get("paises_objetivo") or list(all_countries)
        # Keep only countries that exist in the geography, else pass through
        metas = {**entry.get("meta_diaria_por_pais", {}), **st.get("meta_diaria_por_pais", {})}
        if not metas:
            total = int(entry.get("meta_diaria_total", 40))
            per = max(1, total // max(len(paises), 1)) if paises else 40
            metas = {p: per for p in paises}
        result.append({
            "key": key,
            "client_id": entry.get("client_id", ""),
            "rubro": entry.get("rubro", "") or "",
            "channel": "whatsapp",
            "active": bool(st.get("active", True)),
            "paises_objetivo": paises,
            "meta_diaria_por_pais": metas,
            "cities_per_country": int(st.get("cities_per_country", 5)),
            "paises_disponibles": all_countries,
            "ciudades_por_pais": geo,
            "messages": _normalize_messages(entry),
            "media": _media_of(entry),
        })
    return result


def get_campaign(key: str) -> Optional[dict]:
    key = str(key)
    for c in list_campaigns():
        if c["key"] == key:
            return c
    return None


def save_state(key: str, data: dict) -> dict:
    state = _state()
    st = state.get(str(key), {})
    if "active" in data:
        st["active"] = bool(data["active"])
    if "paises_objetivo" in data and isinstance(data["paises_objetivo"], list):
        st["paises_objetivo"] = [str(p) for p in data["paises_objetivo"]]
    if "meta_diaria_por_pais" in data and isinstance(data["meta_diaria_por_pais"], dict):
        st["meta_diaria_por_pais"] = {str(k): int(v) for k, v in data["meta_diaria_por_pais"].items()}
    if "cities_per_country" in data:
        st["cities_per_country"] = max(1, int(data["cities_per_country"]))
    state[str(key)] = st
    _write_json(STATE_FILE, state)
    return st


def save_messages(key: str, messages: list) -> dict:
    """Persist normalized steps (with optional nested media) into plantillas.json."""
    key = str(key)
    plantillas = _read_json(PLANTILLAS_FILE, [])
    target = next((e for e in _campaign_entries(plantillas) if e["campaign"] == key), None)
    if target is None:
        return {"error": "campaign not found"}
    current = _normalize_messages(target)
    new_messages = []
    for s in messages:
        step = int(s.get("step", 0))
        text = str(s.get("text", ""))
        enabled = bool(s.get("enabled", True))
        prev = next((c for c in current if c["step"] == step), None)
        media = s.get("media") or {}
        media_url = media.get("url") or (prev or {}).get("media_url") or ""
        media_type = media.get("type") or (prev or {}).get("media_type") or ""
        media_enabled = media.get("enabled", True) if "url" in media or (prev or {}).get("media_url") else True
        caption = media.get("caption") or (prev or {}).get("caption") or ""
        msg = {"step": step, "text": text, "enabled": enabled}
        if media_url:
            msg["media"] = {"enabled": media_enabled, "type": media_type or "image",
                            "url": media_url, "caption": caption}
        elif prev and prev.get("media_url"):
            msg["media"] = {"enabled": media_enabled, "type": prev["media_type"] or "image",
                            "url": prev["media_url"], "caption": prev.get("caption", "")}
        new_messages.append(msg)
    target["messages"] = sorted(new_messages, key=lambda m: m["step"])
    _write_json(PLANTILLAS_FILE, plantillas)
    return get_campaign(key)


def _current_media_filename(key: str) -> Optional[str]:
    c = get_campaign(key)
    if c and c.get("media", {}).get("url", "").startswith("/media/"):
        return os.path.basename(c["media"]["url"])
    return None


def upload_media(key: str, raw: bytes, ext: str) -> dict:
    """Replace the campaign image. Keeps the existing filename if present so URLs stay stable."""
    key = str(key)
    ext = (ext or "jpg").lower().lstrip(".").replace("jpeg", "jpg")
    os.makedirs(MEDIA_DIR, exist_ok=True)
    existing = _current_media_filename(key)
    filename = existing or f"Campana_{_slugify(key)}.{ext}"
    if existing and not existing.lower().endswith(f".{ext}"):
        # keep the same stem but honor the new extension for future references
        stem = os.path.splitext(existing)[0]
        filename = f"{stem}.{ext}"
    path = os.path.join(MEDIA_DIR, filename)
    with open(path, "wb") as f:
        f.write(raw)
    media_type = "image" if ext in ("jpg", "jpeg", "png", "webp", "gif") else "document"
    url = f"/media/{filename}"

    # 1) Update plantillas step media references
    plantillas = _read_json(PLANTILLAS_FILE, [])
    for e in _campaign_entries(plantillas):
        if e["campaign"] == key:
            changed = False
            for m in e.get("messages", []):
                media = m.get("media")
                if media and media.get("url"):
                    media["url"] = url
                    media["type"] = media_type
                    changed = True
            if changed:
                _write_json(PLANTILLAS_FILE, plantillas)

    # 2) Update client whatsapp media reference
    clients = _read_json(CLIENTS_FILE, [])
    c = get_campaign(key)
    client_id = c.get("client_id", "") if c else ""
    for cl in clients:
        if cl.get("id") == client_id:
            wa = cl.setdefault("whatsapp", {})
            wa["media_url"] = url
            wa["media_type"] = media_type
            _write_json(CLIENTS_FILE, clients)
            break
    return {"url": url, "filename": filename, "bytes": len(raw)}


def remove_media(key: str) -> dict:
    """Quita la imagen de la campaña (paso 3 pasa a texto puro) y del cliente."""
    key = str(key)
    url_anterior = ""
    # 1) plantillas: dejar el media del paso con imagen sin url / deshabilitado
    plantillas = _read_json(PLANTILLAS_FILE, [])
    changed = False
    for e in _campaign_entries(plantillas):
        if e["campaign"] == key:
            for m in e.get("messages", []):
                media = m.get("media")
                if media and media.get("url"):
                    url_anterior = media.get("url", "")
                    media["url"] = ""
                    media["enabled"] = False
                    changed = True
            break
    if changed:
        _write_json(PLANTILLAS_FILE, plantillas)
    # 2) cliente whatsapp media reference
    ist = _read_json(CLIENTS_FILE, [])
    c = get_campaign(key)
    client_id = c.get("client_id", "") if c else ""
    for cl in ist:
        if cl.get("id") == client_id:
            wa = cl.setdefault("whatsapp", {})
            if wa.get("media_url"):
                url_anterior = wa.get("media_url", url_anterior)
                wa["media_url"] = ""
                wa["media_type"] = ""
            _write_json(CLIENTS_FILE, ist)
            break
    return {"status": "ok", "media_removed": url_anterior or True}


# ─── Prospector integration: active targets ───


def apply_campaign_targets(clients: list) -> list:
    """Filter each client's ubicaciones to active campaigns: only objetivo countries
    and the top-N main cities per country. Falls back to the full list when no campaign."""
    campaigns = list_campaigns()
    geo = client_country_cities()
    for client in clients:
        my = [c for c in campaigns if c.get("client_id") == client.id and c.get("channel") == "whatsapp"]
        active = [c for c in my if c.get("active", True)]
        if not active:
            continue
        campaign = active[0]
        paises = campaign.get("paises_objetivo") or []
        n = max(1, int(campaign.get("cities_per_country", 5)))
        selected: list = []
        for pais in paises:
            cities = geo.get(pais)
            if cities is None and pais in client.ubicaciones:
                cities = [client.ubicaciones[client.ubicaciones.index(pais)]]
            for ciudad in (cities or [])[:n]:
                entry = f"{ciudad}, {pais}"
                if entry in client.ubicaciones and entry not in selected:
                    selected.append(entry)
        if not selected:
            # All-objective countries unknown in geography; keep original order
            with_country = []
            for ub in client.ubicaciones:
                u = ub.split(",")
                p = u[-1].strip() if len(u) > 1 else ub.strip()
                if p in paises:
                    with_country.append(ub)
            selected = with_country
        if selected:
            client.ubicaciones = selected
            n_msgs = max(1, sum(1 for m in (campaign.get("messages") or []) if m.get("enabled", True)))
            client.whatsapp.max_daily = sum(campaign.get("meta_diaria_por_pais", {}).values()) * n_msgs or client.whatsapp.max_daily
    return clients


# ─── Queue / activity for the Campaign panel ───


def queue_by_country(key: str) -> dict:
    from queue_manager import get_queue_status
    qs = get_queue_status()
    campaign = get_campaign(key)
    pending = qs.get("pending_por_pais", {})
    sent = _read_json(COUNTRY_COUNTS_FILE, {})
    metas = (campaign or {}).get("meta_diaria_por_pais", {}) or {}
    geo = client_country_cities()
    rows = []
    countries = (campaign or {}).get("paises_objetivo") or []
    for pais in countries:
        rows.append({
            "pais": pais,
            "ciudades": (geo.get(pais) or [])[: (campaign or {}).get("cities_per_country", 5)],
            "pendiente": int(pending.get(pais, 0)),
            "enviados_hoy": int(sent.get(pais, {}).get("today", 0)) if isinstance(sent.get(pais), dict) else int(sent.get(pais, 0)),
            "meta": int(metas.get(pais, 0)),
        })
    return {
        "campaign": key,
        "active": (campaign or {}).get("active", True),
        "total_pendiente": sum(r["pendiente"] for r in rows),
        "rows": rows,
        "queue_total": int(qs.get("pending", 0)),
        "running": bool(qs.get("running", False)),
        "queue_paused": bool(qs.get("queue_paused", False)),
        "last_cycle": _last_cycle_ts(),
    }


def _last_cycle_ts() -> str:
    rpt = _read_json(REPORT_FILE, {})
    return rpt.get("timestamp", "") if isinstance(rpt, dict) else ""


def recent_activity(limit: int = 40) -> list:
    entries = []
    if os.path.exists(ACTIVITY_FILE):
        try:
            with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
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