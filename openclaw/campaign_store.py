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


def _log_activity(kind: str, message: str):
    try:
        entry = {"ts": datetime.now().isoformat(), "kind": kind, "msg": message}
        with open(ACTIVITY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        if media.get("interchange"):
            item["media_interchange"] = [u for u in media["interchange"] if u]
        out.append(item)
    return sorted(out, key=lambda x: x["step"])


def _media_of(entry: dict) -> dict:
    for m in entry.get("messages", []):
        media = m.get("media")
        if media and media.get("url"):
            out = {"enabled": bool(media.get("enabled", True)), "type": media.get("type", "image"),
                   "url": media.get("url", ""), "caption": media.get("caption", "")}
            if media.get("interchange"):
                out["interchange"] = [u for u in media["interchange"] if u]
            return out
    return {}


def _state() -> dict:
    return _read_json(STATE_FILE, {})


def _entry_rubros(entry: dict) -> Optional[list]:
    rubros = entry.get("rubros")
    if isinstance(rubros, list) and rubros:
        return [str(r).strip() for r in rubros if str(r).strip()]
    rubro = entry.get("rubro")
    if rubro:
        return [str(rubro).strip()]
    return None


def _patch_entry(key: str, patch: dict):
    """Apply a patch to a campaign entry in plantillas.json (no-op if absent)."""
    plantillas = _read_json(PLANTILLAS_FILE, [])
    changed = False
    for e in _campaign_entries(plantillas):
        if e["campaign"] == key:
            e.update({k: v for k, v in patch.items() if v is not None})
            changed = True
            break
    if changed:
        _write_json(PLANTILLAS_FILE, plantillas)


def _effective_rubros(entry: dict) -> list:
    explicit = _entry_rubros(entry)
    if explicit:
        return explicit
    for cl in _read_json(CLIENTS_FILE, []):
        if cl.get("id") == entry.get("client_id"):
            rubros = cl.get("rubros")
            if isinstance(rubros, list) and rubros:
                return [str(r) for r in rubros if str(r)]
            break
    rubro = entry.get("rubro")
    return [rubro] if rubro else []


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
            "rubros": _effective_rubros(entry),
            "channel": "whatsapp",
            "active": bool(st.get("active", True)),
            "enviando": bool(st.get("enviando", st.get("active", True))),
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
    if "enviando" in data:
        st["enviando"] = bool(data["enviando"])
    if "paises_objetivo" in data and isinstance(data["paises_objetivo"], list):
        st["paises_objetivo"] = [str(p) for p in data["paises_objetivo"]]
    if "meta_diaria_por_pais" in data and isinstance(data["meta_diaria_por_pais"], dict):
        st["meta_diaria_por_pais"] = {str(k): int(v) for k, v in data["meta_diaria_por_pais"].items()}
    if "cities_per_country" in data:
        st["cities_per_country"] = max(1, int(data["cities_per_country"]))
    if "rubros" in data and isinstance(data["rubros"], list):
        rubros = [str(r).strip() for r in data["rubros"] if str(r).strip()]
        if rubros:
            _patch_entry(str(key), {"rubros": rubros})
    state[str(key)] = st
    _write_json(STATE_FILE, state)
    if "active" in data or "paises_objetivo" in data:
        _sync_prospector_targets()
    return st


def _sync_prospector_targets() -> None:
    """Recalcula el objetivo del prospector a partir de TODAS las campañas
    activas: paises_activos = unión de países, límites = unión de metas."""
    try:
        from prospector import save_config, load_config
        campaigns = [c for c in list_campaigns() if c.get("channel") == "whatsapp" and c.get("active", True)]
        cfg = load_config()
        paises: list = []
        limites: dict = {}
        for camp in campaigns:
            for p in (camp.get("paises_objetivo") or []):
                if p and p not in paises:
                    paises.append(p)
            for p, v in (camp.get("meta_diaria_por_pais") or {}).items():
                limites[str(p)] = max(int(limites.get(str(p), 0)), int(v))
        if paises:
            cfg["paises_activos"] = paises
        if limites:
            cfg["limites_por_pais"] = limites
            cfg["max_por_pais_diario"] = max(limites.values())
        save_config(cfg)
    except Exception as e:
        _log_activity("campaign_activate", f"no pude sincronizar prospector ({e})")


def activate_campaign(key: str) -> dict:
    """Activa la campaña SIN apagar el resto.

    No pausa/resume el prospector ni vacía la cola: solo marca esta campaña
    como activa + enviando, y sincroniza el objetivo del prospector con la
    UNIÓN de países/rubros/metas de todas las campañas activas para que el
    PRÓXIMO ciclo de prospección capture para todas a la vez.
    """
    key = str(key)
    camp = get_campaign(key)
    if not camp:
        return {"error": "campaign not found"}
    state = _state()
    # No apaga las demás: SOLO enciende esta.
    st = dict(state.get(key, {}))
    st["active"] = True
    st["enviando"] = True
    state[key] = st
    _write_json(STATE_FILE, state)

    _sync_prospector_targets()

    _log_activity("campaign_activate", f"Campaña «{key}» activada (no detiene las demás)")
    return {"status": "ok", "campaign": get_campaign(key)}


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
        interchange = media.get("interchange") or (prev or {}).get("media_interchange") or []
        if media_url:
            msg["media"] = {"enabled": media_enabled, "type": media_type or "image",
                            "url": media_url, "caption": caption}
            if interchange:
                msg["media"]["interchange"] = [u for u in interchange if u]
        elif prev and prev.get("media_url"):
            msg["media"] = {"enabled": media_enabled, "type": prev["media_type"] or "image",
                            "url": prev["media_url"], "caption": prev.get("caption", "")}
            if interchange:
                msg["media"]["interchange"] = [u for u in interchange if u]
        new_messages.append(msg)
    target["messages"] = sorted(new_messages, key=lambda m: m["step"])
    _write_json(PLANTILLAS_FILE, plantillas)
    return get_campaign(key)


def _existing_keys(plantillas: list = None) -> set:
    plantillas = plantillas if plantillas is not None else _read_json(PLANTILLAS_FILE, [])
    return {e.get("campaign") for e in _campaign_entries(plantillas)}


def _unique_key(rubro: str, plantillas: list = None) -> str:
    base = _slugify(rubro)
    keys = _existing_keys(plantillas)
    if base not in keys:
        return base
    n = 2
    while f"{base}_{n}" in keys:
        n += 1
    return f"{base}_{n}"


def create_campaign(client_id: str, rubro: str, paises_objetivo: list,
                    mensajes: list, meta_diaria_total: int = 25,
                    image_media: dict = None, rubros: list = None) -> dict:
    """Crea una campaña WhatsApp nueva en plantillas.json y la activa."""
    plantillas = _read_json(PLANTILLAS_FILE, [])
    key = _unique_key(rubro, plantillas)
    image_media = image_media or {}
    rubros = [str(r).strip() for r in (rubros or []) if str(r).strip()] or [str(rubro).strip()]

    steps = sorted([(int(m.get("step", 0)), str(m.get("text", ""))) for m in (mensajes or []) if m.get("text")])
    steps = steps[:3]
    messages = []
    for i, (step, text) in enumerate(steps, start=1):
        msg = {"step": i, "text": text, "enabled": True}
        if i == 3 and image_media.get("url"):
            msg["media"] = {
                "enabled": bool(image_media.get("enabled", True)),
                "type": image_media.get("type", "image"),
                "url": image_media.get("url"),
                "caption": image_media.get("caption", ""),
            }
        messages.append(msg)

    paises = [str(p).strip() for p in paises_objetivo if str(p).strip()]
    per = max(1, int(meta_diaria_total) // max(len(paises), 1)) if paises else int(meta_diaria_total)

    entry = {
        "client_id": client_id,
        "campaign": key,
        "paises_objetivo": paises,
        "meta_diaria_total": int(meta_diaria_total),
        "meta_diaria_por_pais": {p: per for p in paises},
        "rubro": str(rubro).strip(),
        "rubros": rubros,
        "channel": "whatsapp",
        "messages": messages,
    }
    plantillas.append(entry)
    _write_json(PLANTILLAS_FILE, plantillas)

    save_state(key, {"active": True, "cities_per_country": 5, "paises_objetivo": paises,
                     "meta_diaria_por_pais": {p: per for p in paises}})
    _log_activity("campaign_create", f"Campaña «{key}» creada (rubro: {rubros})")
    return get_campaign(key)


def reset_campaign(key: str) -> dict:
    """Reinicia una campaña: limpia su cola, pone a 0 los envíos de hoy y
    borra los filtros anti-duplicado vinculados a esa campaña."""
    key = str(key)
    from queue_manager import _load_country_counts, _save_country_counts

    # 1) Cleans leads de la campaña de la cola
    try:
        from queue_manager import _queue, save_queue
        kept = []
        removed = 0
        for e in _queue if isinstance(_queue, list) else []:
            if e.get("campaign_key") == key:
                removed += 1
                continue
            if not e.get("campaign_key"):
                active = [c for c in list_campaigns() if c.get("active", True)]
                if len(active) == 1 and active[0]["key"] == key:
                    removed += 1
                    continue
            kept.append(e)
        if removed:
            _queue[:] = kept
            save_queue(force=True)
    except Exception:
        removed = 0

    # 2) Pone a 0 los envíos de hoy de la campaña
    counts = _load_country_counts()
    rubro = ""
    c = get_campaign(key)
    if c:
        rubro = c.get("rubro", "")
    for k in list(counts.keys()):
        pais, _, r = k.partition("|")
        if c and (pais in (c.get("paises_objetivo") or [])) and (r == rubro):
            counts[k] = 0
    _save_country_counts(counts)

    return {"ok": True, "campaign": key, "queue_removed": removed}


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
    """Filter each client's ubicaciones to ALL active campaigns: union of the
    objetivo countries, top-N main cities per country and client rubros across
    every active campaign of the client. Falls back to the full list when none."""
    campaigns = list_campaigns()
    geo = client_country_cities()
    for client in clients:
        my = [c for c in campaigns if c.get("client_id") == client.id and c.get("channel") == "whatsapp"]
        active = [c for c in my if c.get("active", True)]
        if not active:
            continue

        # Unión de rubros del cliente para captación multi-campaña
        merged_rubros: list = []
        for campaign in active:
            for r in (campaign.get("rubros") or []):
                r = str(r).strip()
                if r and r not in merged_rubros:
                    merged_rubros.append(r)
        if merged_rubros:
            client.rubros = merged_rubros

        # Unión de países objetivo + top-N ciudades por país de cada campaña
        selected: list = []
        max_daily = client.whatsapp.max_daily
        for campaign in active:
            paises = campaign.get("paises_objetivo") or []
            n = max(1, int(campaign.get("cities_per_country", 5)))
            for pais in paises:
                cities = geo.get(pais)
                if cities is None and pais in client.ubicaciones:
                    cities = [client.ubicaciones[client.ubicaciones.index(pais)]]
                for ciudad in (cities or [])[:n]:
                    entry = f"{ciudad}, {pais}"
                    if entry in client.ubicaciones and entry not in selected:
                        selected.append(entry)
            n_msgs = max(1, sum(1 for m in (campaign.get("messages") or []) if m.get("enabled", True)))
            max_daily = max(max_daily, sum(campaign.get("meta_diaria_por_pais", {}).values()) * n_msgs)
        if not selected:
            # All-objective countries unknown in geography; keep original order
            all_paises = set()
            for campaign in active:
                all_paises.update(campaign.get("paises_objetivo") or [])
            with_country = []
            for ub in client.ubicaciones:
                u = ub.split(",")
                p = u[-1].strip() if len(u) > 1 else ub.strip()
                if p in all_paises:
                    with_country.append(ub)
            selected = with_country
        if selected:
            client.ubicaciones = selected
            client.whatsapp.max_daily = max_daily
    return clients


# ─── Queue / activity for the Campaign panel ───


def queue_by_country(key: str) -> dict:
    from queue_manager import get_queue_status, _queue
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
    queue_this = 0
    queue_unassigned = 0
    try:
        for e in _queue if isinstance(_queue, list) else []:
            ck = e.get("campaign_key", "")
            if ck == key:
                queue_this += 1
            elif not ck:
                queue_unassigned += 1
    except Exception:
        pass
    return {
        "campaign": key,
        "active": (campaign or {}).get("active", True),
        "total_pendiente": sum(r["pendiente"] for r in rows),
        "rows": rows,
        "queue_total": int(qs.get("pending", 0)),
        "queue_de_esta_campana": queue_this,
        "queue_sin_campana": queue_unassigned,
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


def collect_campaign(key: str, max_por_pais: int = 25) -> dict:
    """Recolección dedicada para UNA campaña sin afectar otras ni el envío.

    Busca los rubros de la campaña en sus países/ciudades objetivo, guarda en
    prospectos_locales y ENCOLA con campaign_key, para alimentar una cola lista
    que solo se enviará cuando la campaña esté con «enviando» activo.
    """
    from prospector import scrape_local, enqueue_to_openclaw, load_config
    from local_search import agregar_prospectos_locales
    camp = get_campaign(key)
    if not camp:
        return {"error": "campaign not found"}
    geo = client_country_cities()
    cfg = load_config()
    max_results = int(cfg.get("max_leads_per_search", 50))
    openclaw_url = cfg.get("openclaw_url", "http://openclaw:9000")
    client_id = camp.get("client_id", "")
    n_cities = max(1, int(camp.get("cities_per_country", 5)))
    rubros = camp.get("rubros") or [camp.get("rubro") or ""]
    paises = camp.get("paises_objetivo") or []

    total_found = 0
    total_enqueued = 0
    por_pais: dict = {}
    ciclos = []
    for pais in paises:
        cities = (geo.get(pais) or [])[:n_cities]
        if not cities:
            cities = [pais]
        for rubro in rubros:
            por_pais[pais] = por_pais.get(pais, 0)
            for ciudad in cities:
                ubicacion = f"{ciudad}, {pais}"
                try:
                    resultados = scrape_local(rubro, ubicacion, max_results=max_results)
                    if resultados:
                        agregar_prospectos_locales(resultados)
                    con_telefono = [r for r in resultados if r.get("telefono")][:max_por_pais]
                    total_found += len(con_telefono)
                    if con_telefono:
                        cues = enqueue_to_openclaw(
                            con_telefono, openclaw_url, client_id=client_id, campaign_key=key
                        )
                        total_enqueued += cues
                        por_pais[pais] += cues
                        ciclos.append({"rubro": rubro, "ubicacion": ubicacion,
                                       "con_telefono": len(con_telefono), "encolados": cues})
                    _log_activity("collect", f"Campaña {key}: {len(con_telefono)} {rubro} en {ubicacion}")
                except Exception:
                    continue

    _log_activity("collect", f"Campaña {key}: {total_enqueued} encolados de {total_found} con teléfono")
    return {
        "campaign": key,
        "found": total_found,
        "enqueued": total_enqueued,
        "por_pais": por_pais,
        "ciclos": ciclos,
    }