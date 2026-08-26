"""Dashboard UI for prospecting history (searches, sends, IG DMs)."""
from __future__ import annotations

import json, os
from datetime import datetime, date

import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data") if os.path.isdir(os.path.join(BASE_DIR, "data")) else BASE_DIR

ACTIVITY_LOG = os.path.join(DATA_DIR, "actividad_prospector.jsonl")
SUMMARY_FILE = os.path.join(DATA_DIR, "resumen_diario.json")
CLIENTS_FILE = os.path.join(DATA_DIR, "clientes.json")
IG_STATE_FILE = os.path.join(DATA_DIR, "ig_state.json")


def _read_activity(limit: int = 200) -> list[dict]:
    entries = []
    if os.path.exists(ACTIVITY_LOG):
        try:
            with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    return entries[-limit:]


def _read_summary() -> list[dict]:
    if os.path.exists(SUMMARY_FILE):
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _read_ig_state() -> dict:
    if os.path.exists(IG_STATE_FILE):
        try:
            with open(IG_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"date": "", "sent_today": 0, "sent_by_country": {}}


def _read_today_counts() -> dict:
    """Read daily counters from the channel counts file."""
    path = os.path.join(DATA_DIR, "envios_por_cliente.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def render_page():
    st.header("Historial de Actividad")
    st.caption("Registro completo de prospeccion, envios e interacciones")

    tab_cronologia, tab_resumen, tab_ig = st.tabs(["Cronologia", "Resumen Diario", "Instagram"])

    # --- Tab: Cronologia ---
    with tab_cronologia:
        activities = _read_activity(300)
        if not activities:
            st.info("Aun no hay actividad registrada. El prospector comenzara a buscar leads.")
        else:
            kind_filter = st.selectbox(
                "Filtrar por tipo",
                ["Todos", "search", "found", "enqueue", "sent_whatsapp", "sent_instagram", "sent_email", "sent_complete", "ig_search", "ig_found", "ig_day", "batch"],
                key="hist_kind",
            )
            filtered = activities if kind_filter == "Todos" else [a for a in activities if a.get("kind") == kind_filter]

            for entry in reversed(filtered):
                ts = entry.get("ts", "")[:19]
                kind = entry.get("kind", "")
                msg = entry.get("msg", "")
                emoji = {
                    "search": "🔍", "found": "📋", "enqueue": "📥",
                    "sent_whatsapp": "📤", "sent_instagram": "📸", "sent_email": "📧",
                    "sent_complete": "✅", "batch": "📊",
                    "ig_search": "🔎", "ig_found": "📸", "ig_day": "📅",
                }.get(kind, "•")
                st.caption(f"{emoji} `{ts}` **{kind}** — {msg}")

    # --- Tab: Resumen Diario ---
    with tab_resumen:
        summary = _read_summary()
        if not summary:
            st.info("No hay resumen diario disponible aun.")
        else:
            for day in reversed(summary[-10:]):
                fecha = day.get("fecha", "?")
                por_pais = day.get("por_pais", {})
                por_rubro = day.get("por_rubro", {})
                total = day.get("detalle", [])
                with st.expander(f"📆 {fecha} — {len(total)} envios", expanded=(fecha == date.today().isoformat())):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption("Por pais")
                        for p, c in sorted(por_pais.items(), key=lambda x: -x[1]):
                            st.write(f"{p}: {c}")
                    with col2:
                        st.caption("Por rubro")
                        for r, c in sorted(por_rubro.items(), key=lambda x: -x[1]):
                            st.write(f"{r}: {c}")

    # --- Tab: Instagram ---
    with tab_ig:
        ig_state = _read_ig_state()
        ig_date = ig_state.get("date", "")
        ig_sent = ig_state.get("sent_today", 0)
        remaining = max(0, 3 - ig_sent)

        st.metric("DMs enviados hoy", ig_sent, delta=remaining, delta_color="inverse",
                  help=f"Limite: 3/dia | Quedan: {remaining}")

        # Show IG-specific activity
        ig_activities = [a for a in _read_activity(500) if a.get("kind", "").startswith("ig_") or a.get("kind") == "sent_instagram"]
        if ig_activities:
            st.subheader("Actividad IG reciente")
            for entry in reversed(ig_activities[-20:]):
                ts = entry.get("ts", "")[:19]
                kind = entry.get("kind", "")
                msg = entry.get("msg", "")
                emoji = {"ig_search": "🔎", "ig_found": "📸", "ig_day": "📅", "sent_instagram": "📤"}.get(kind, "•")
                st.caption(f"{emoji} `{ts}` {msg}")
        else:
            st.info("No hay actividad de Instagram aun. El prospector ejecutara la fase IG cuando termine la fase web.")
