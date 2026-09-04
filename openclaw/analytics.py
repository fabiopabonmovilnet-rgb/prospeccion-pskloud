from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

ACTIVITY_LOG = "/app/data/actividad_prospector.jsonl"
CONVERSACIONES_DB = "/app/data/conversaciones.db"
PROSPECTOS_LOCALES = "/app/data/prospectos_locales.json"
RESUMEN_DIARIO = "/app/data/resumen_diario.json"
SENT_MESSAGES = "/app/data/sent_messages.json"
DISTRIBUIDORES_DB = "/app/data/prospeccion.db"

_MEMO = {}


def _load(path, default):
    try:
        mtime = os.path.getmtime(path)
        if _MEMO.get(path, (None, None))[0] == mtime:
            return _MEMO[path][1]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _MEMO[path] = (mtime, data)
        return data
    except Exception:
        return default


def _load_lines(path):
    try:
        mtime = os.path.getmtime(path)
        if _MEMO.get(path, (None, None))[0] == mtime:
            return _MEMO[path][1]
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    lines.append(json.loads(line))
                except Exception:
                    pass
        _MEMO[path] = (mtime, lines)
        return lines
    except Exception:
        return []


def _date_only(ts: str):
    try:
        return ts[:10]
    except Exception:
        return ""


def _hour_of(ts: str):
    try:
        return int(ts[11:13])
    except Exception:
        return -1


def _db_conversations():
    out = {"rows": [], "por_status": defaultdict(int), "por_clasificacion": defaultdict(int)}
    try:
        con = sqlite3.connect(CONVERSACIONES_DB)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        out_msgs = defaultdict(int)
        try:
            for r in cur.execute("SELECT phone, COUNT(*) AS n FROM messages WHERE direction='out' GROUP BY phone"):
                out_msgs[r["phone"]] = r["n"]
        except Exception:
            pass
        rows = cur.execute(
            "SELECT phone, lead_json, status, current_step, classification, started_at, last_reply_at FROM conversations"
        ).fetchall()
        for r in rows:
            try:
                lead = json.loads(r["lead_json"] or "{}")
            except Exception:
                lead = {}
            row = {
                "phone": r["phone"],
                "nombre": lead.get("nombre") or "",
                "pais": lead.get("pais") or "",
                "rubro": lead.get("rubro") or "",
                "ciudad": lead.get("ciudad") or "",
                "status": r["status"],
                "step": r["current_step"],
                "clasificacion": r["classification"],
                "started_at": r["started_at"],
                "last_reply_at": r["last_reply_at"],
                "out": out_msgs.get(r["phone"], 0),
            }
            out["rows"].append(row)
            out["por_status"][r["status"] or "sin_estado"] += 1
            out["por_clasificacion"][r["classification"] or "sin_clasificar"] += 1
        con.close()
    except Exception:
        pass
    return out


def _db_distribuidores_envios():
    """Lee de distribuidores_actividad (EMAIL_ENVIADO) cruzando con distribuidores.
    Devuelve: {total, daily:{fecha:count}, by_country:{pais:count}, by_rubro:{rubro:count},
               pais_diario:{fecha:{pais:count}}, rubro_diario:{fecha:{rubro:count}}}"""
    total = 0
    daily = defaultdict(int)
    by_country = defaultdict(int)
    by_rubro = defaultdict(int)
    pais_diario = lambda: defaultdict(int)
    try:
        con = sqlite3.connect(DISTRIBUIDORES_DB)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        rows = cur.execute("""
            SELECT a.fecha, d.pais_target, d.rubro
            FROM distribuidores_actividad a
            JOIN distribuidores d ON d.id = a.distribuidor_id
            WHERE a.accion IN ('EMAIL_ENVIADO', 'EMAIL_SMTP')
        """).fetchall()
        con.close()
        for r in rows:
            f = r["fecha"] or ""
            if not f:
                continue
            daily[f] += 1
            total += 1
            p = (r["pais_target"] or "Sin país").replace("_", " ")
            rub = r["rubro"] or "Sin rubro"
            by_country[p] += 1
            by_rubro[rub] += 1
    except Exception:
        pass
    return {"total": total, "daily": daily, "by_country": by_country, "by_rubro": by_rubro}


def _parse_country_from_msg(msg: str):
    try:
        if "(" in msg and ")" in msg:
            inside = msg.split("(", 1)[1].split(")", 1)[0]
            return inside.strip()
    except Exception:
        pass
    return None


def build_analytics():
    events = _load_lines(ACTIVITY_LOG)
    daily = defaultdict(lambda: defaultdict(int))
    hourly = defaultdict(int)
    first_ts = None
    last_ts = None

    for e in events:
        ts = e.get("ts") or ""
        kind = e.get("kind") or ""
        d = _date_only(ts)
        if not d:
            continue
        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts

        h = _hour_of(ts)
        if kind in ("sent_whatsapp", "followup", "sent_email", "sent_instagram"):
            if h >= 0:
                hourly[h] += 1

        key = "other"
        if kind == "search":
            key = "searches"
        elif kind == "found":
            key = "found"
        elif kind in ("enqueue",):
            key = "enqueued"
        elif kind in ("sent_whatsapp", "sent_complete", "sent_email", "sent_instagram"):
            key = "sent"
        elif kind == "followup":
            key = "followups"
        elif kind == "skip":
            key = "skips"
        elif kind == "dedup":
            key = "dedups"
        elif kind in ("pause", "resume"):
            key = "pauses"
        elif kind in ("set_rubro", "embudo", "queue_clear"):
            key = "correcciones"
        elif kind == "excluido_perfil":
            key = "excluidos"
        daily[d][key] += 1

    # Series continua desde la primera fecha hasta hoy
    today = datetime.now().date().isoformat()
    daily_series = []
    if first_ts:
        start = datetime.strptime(first_ts[:10], "%Y-%m-%d").date()
        cur = start
        while cur.isoformat() <= today:
            k = cur.isoformat()
            row = dict(daily.get(k, {}))
            row["date"] = k
            row["found"] = row.get("found", 0)
            row["enqueued"] = row.get("enqueued", 0)
            row["sent"] = row.get("sent", 0)
            row["followups"] = row.get("followups", 0)
            row["skips"] = row.get("skips", 0)
            row["dedups"] = row.get("dedups", 0)
            row["searches"] = row.get("searches", 0)
            row["correcciones"] = row.get("correcciones", 0)
            row["excluidos"] = row.get("excluidos", 0)
            daily_series.append(row)
            cur += timedelta(days=1)

    hourly_series = [{"hour": h, "count": hourly.get(h, 0)} for h in range(24)]

    # Totales
    totals = {
        "encontrados": sum(d.get("found", 0) for d in daily_series),
        "encolados": sum(d.get("enqueued", 0) for d in daily_series),
        "enviados": sum(d.get("sent", 0) for d in daily_series),
        "followups": sum(d.get("followups", 0) for d in daily_series),
        "skips": sum(d.get("skips", 0) for d in daily_series),
        "excluidos": sum(d.get("excluidos", 0) for d in daily_series),
        "correcciones": sum(d.get("correcciones", 0) for d in daily_series),
        "dias_activos": len([d for d in daily_series if d.get("sent") or d.get("found")]),
        "primera_actividad": first_ts,
        "ultima_actividad": last_ts,
    }

    # Conversaciones
    convs = _db_conversations()
    total_conv = len(convs["rows"])
    responded = [r for r in convs["rows"] if r["last_reply_at"]]
    totals["conversaciones"] = total_conv
    totals["respondieron"] = len(responded)
    totals["tasa_respuesta"] = round(len(responded) * 100.0 / total_conv, 1) if total_conv else 0

    # KPIs de distribuidores
    dist_data = _db_distribuidores_envios()
    totals["dist_emails_enviados"] = dist_data["total"]

    # ─── Canales separados ───
    # WhatsApp: conversations reales (conversaciones.db)
    totals["wsp_enviados"] = sum(r["out"] for r in convs["rows"])
    totals["wsp_conversaciones"] = total_conv
    totals["wsp_respondieron"] = len(responded)
    totals["wsp_tasa_respuesta"] = round(len(responded) * 100.0 / total_conv, 1) if total_conv else 0
    # Email (distribuidores)
    totals["email_enviados"] = dist_data["total"]
    totals["email_tasa_respuesta"] = 0  # no hay tracking de respuesta de email aún
    # Instagram (eventos sent_instagram)
    ig_events = [e for e in events if (e.get("kind") or "") == "sent_instagram"]
    totals["ig_enviados"] = len(ig_events)

    # Por país (conversaciones reales)
    by_country_conv = defaultdict(lambda: {"conversaciones": 0, "respondieron": 0})
    for r in convs["rows"]:
        c = r["pais"] or "Sin país"
        by_country_conv[c]["conversaciones"] += 1
        if r["last_reply_at"]:
            by_country_conv[c]["respondieron"] += 1

    # Pool de prospectos scrapeados
    pool = _load(PROSPECTOS_LOCALES, [])
    if isinstance(pool, dict):
        pool = pool.get("leads", [])
    pool_by_country = defaultdict(int)
    pool_by_rubro = defaultdict(int)
    pool_by_city = defaultdict(int)
    for lead in pool:
        p = lead.get("pais") or "Sin país"
        r = lead.get("rubro") or "Sin rubro"
        ci = lead.get("ciudad") or lead.get("ubicacion_busqueda") or "Sin ciudad"
        pool_by_country[p] += 1
        pool_by_rubro[r] += 1
        pool_by_city[(ci, p)] += 1
    totals["pool_prospectos"] = len(pool)

    # Envíos por país/rubro: mensajes outbound reales desde las conversaciones.
    # (resumen_diario.json no es fiable: se crea por lote y puede no existir).
    sent_by_country = defaultdict(int)
    sent_by_rubro = defaultdict(int)
    for r in convs["rows"]:
        sent_by_country[r["pais"] or "Sin país"] += r["out"]
        sent_by_rubro[r["rubro"] or "Sin rubro"] += r["out"]

    # ─── Distribuidores: envíos SMTP por país/rubro/día ───
    dist_data = _db_distribuidores_envios()
    for p, n in dist_data["by_country"].items():
        sent_by_country[p] += n
    for r, n in dist_data["by_rubro"].items():
        sent_by_rubro[r] += n
    # Inyectar envíos de distribuidores en daily_series
    for d in daily_series:
        d["sent_dist"] = dist_data["daily"].get(d["date"], 0)
        d["sent"] = d.get("sent", 0) + d["sent_dist"]

    # Correcciones detalladas (últimas 50)
    correcciones = []
    for e in events:
        if e.get("kind") in ("set_rubro", "embudo", "queue_clear", "excluido_perfil", "renombrar"):
            correcciones.append({"ts": e.get("ts"), "kind": e.get("kind"), "msg": e.get("msg"), "data": e.get("data")})
    correcciones = correcciones[-50:]

    by_country = []
    all_countries = set(sent_by_country) | set(by_country_conv) | set(pool_by_country)
    for c in sorted(all_countries):
        by_country.append({
            "pais": c,
            "enviados": sent_by_country.get(c, 0),
            "conversaciones": by_country_conv[c]["conversaciones"],
            "respondieron": by_country_conv[c]["respondieron"],
            "pool": pool_by_country.get(c, 0),
        })

    by_rubro = []
    all_rubros = set(sent_by_rubro) | set(pool_by_rubro)
    for r in sorted(all_rubros):
        by_rubro.append({
            "rubro": r,
            "enviados": sent_by_rubro.get(r, 0),
            "pool": pool_by_rubro.get(r, 0),
        })

    by_city = []
    for (ci, p), n in sorted(pool_by_city.items(), key=lambda x: -x[1])[:60]:
        by_city.append({"ciudad": ci, "pais": p, "pool": n})

    return {
        "totals": totals,
        "daily": daily_series,
        "hourly": hourly_series,
        "by_country": by_country,
        "by_rubro": by_rubro,
        "by_city": by_city,
        "conversaciones": convs,
        "correcciones": correcciones,
    }
