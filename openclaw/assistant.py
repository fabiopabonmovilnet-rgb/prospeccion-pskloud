from __future__ import annotations

import json
import logging
from datetime import datetime

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger("openclaw.assistant")

MODEL_NAME = "gemini-3.5-flash"
_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_PROMPT = """\
Sos el asistente operativo de la plataforma de prospección PSKloud / Premium Soft (OpenClaw).

Tu trabajo es ayudar al operador (Fabio) a gestionar el prospector usando HERRAMIENTAS.
Cuando Fabio te pida algo, elegí la herramienta adecuada, ejecutala, y respondé con un
resumen claro y breve en español (acentos correctos).

Reglas:
- Si te pide resumen/estado (dónde se prospecta, cuántos en cola, qué rubro, mensajes
  enviados, campaña actual): llamá a la herramienta de estado correspondiente.
- Si te pide DETENER/PAUSAR la prospección: llamá a pausar.
- Si te pide REANUDAR: llamá a reanudar.
- Si te pide CAMBIAR DE RUBRO o armar un NUEVO EMBUDO: usá cambiar_rubro con la lista de
  rubros que indique (ej. ["distribuidores"]). Esto vacía la cola anterior automáticamente.
- Si te pide ELIMINAR/LIMPIAR la cola: usá limpiar_cola.
- Si te pide mejores rubros/opciones para cierre de ventas: usá mejores_rubros.
- Si te pide reordenar el embudo por conversión: usá reordenar_embudo.
- NO inventes datos: lo que no conozcas de las herramientas, decilo honestamente.
- Ante pedidos de riesgo (vaciar cola, cambiar rubro) que no estén claros, pedí confirmación
  antes de ejecutar.
"""

_TOOL_DEFS = [
    {
        "name": "obtener_estado",
        "description": "Resumen general: dónde está prospectando el bot, rubro actual, cola pendiente por país y por canal, mensajes enviados hoy, límites diarios y si está corriendo.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "pausar_prospeccion",
        "description": "Pausa/detiene la prospección en curso (web scraping y envíos).",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "reanudar_prospeccion",
        "description": "Reanuda la prospección después de una pausa.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "cambiar_rubro",
        "description": "Cambia el rubro/embudo de búsqueda. Ejecuta un nuevo embudo: vacía y respalda la cola actual. Ej. rubros=['distribuidores'] para prospección de distribuidores.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "rubros": {"type": "array", "items": {"type": "string"}, "description": "Lista de rubros a prospectar, ej. ['salon de belleza', 'barberia']"}
            },
            "required": ["rubros"],
        },
    },
    {
        "name": "limpiar_cola",
        "description": "Elimina (con respaldo) la cola de prospectos pendientes actual.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "reordenar_embudo",
        "description": "Reordena la cola actual por embudo: rubros con mejor conversión histórica primero, y países prioritarios dentro de cada rubro.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "mejores_rubros",
        "description": "Analiza conversaciones históricas y devuelve los rubros con mejor señal de cierre (handoff/interés/ya_tiene_sistema vs contactados).",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "resumen_diario",
        "description": "Resumen del día: cuántos mensajes se enviaron hoy, por país, y si se alcanzaron límites.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
]


class _ToolRunner:
    """Ejecuta las herramientas sobre el prospector. Todas las llamadas a
    prospector/queue_manager se hacen con import diferido para no acoplarse."""

    async def run(self, name: str, args: dict) -> dict:
        import queue_manager as qm
        import prospector

        if name == "obtener_estado":
            return self._estado(qm, prospector)
        if name == "pausar_prospeccion":
            prospector.pause()
            return {"status": "pausada", "mensaje": "Prospección pausada"}
        if name == "reanudar_prospeccion":
            prospector.resume()
            return {"status": "reanudada", "mensaje": "Prospección reanudada"}
        if name == "cambiar_rubro":
            rubros = args.get("rubros") or []
            prospector.set_rubro(rubros)
            qs = qm.get_queue_status()
            return {"status": "ok", "rubros": rubros, "cola_pendiente_tras_cambio": qs["pending"]}
        if name == "limpiar_cola":
            n = qm.clear_queue_with_backup()
            return {"status": "ok", "eliminados": n, "cola_pendiente": 0}
        if name == "reordenar_embudo":
            qm.load_queue()
            qm._reorder_queue_by_funnel()
            qm.save_queue(force=True)
            return {"status": "ok", "cola_pendiente": len(qm._queue)}
        if name == "mejores_rubros":
            return self._mejores_rubros()
        if name == "resumen_diario":
            qs = qm.get_queue_status()
            return {
                "enviados_hoy": qs["sent_today"],
                "max_diario": qs["max_daily"],
                "max_por_pais": qs["max_por_pais"],
                "enviados_por_pais": qs["sent_por_pais"],
                "pendientes": qs["pending"],
                "pendientes_por_pais": qs["pending_por_pais"],
            }
        return {"error": f"herramienta desconocida: {name}"}

    def _estado(self, qm, prospector) -> dict:
        qs = qm.get_queue_status()
        st = prospector.get_status()
        return {
            "pausado": st["paused"],
            "corriendo": st["running"],
            "rubro_override": st["rubro_override"],
            "rubro_cliente": st["current_rubro"],
            "ultimo_ciclo": st["last_cycle"],
            "cola_pendiente": qs["pending"],
            "pendientes_por_pais": qs["pending_por_pais"],
            "pendientes_por_canal": qs["pending_por_channel"],
            "enviados_hoy": qs["sent_today"],
            "enviados_por_pais": qs["sent_por_pais"],
            "max_diario": qs["max_daily"],
            "max_por_pais": qs["max_por_pais"],
            "fecha": qs["date"],
        }

    def _mejores_rubros(self) -> dict:
        import queue_manager as qm
        import sqlite3
        try:
            conn = sqlite3.connect(settings.conversations_db, timeout=10)
            rows = conn.execute("SELECT lead_json, status FROM conversations").fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"mejores_rubros: {e}")
            return {"error": str(e)}
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
        ranking = []
        for rubro, counts in by_rubro.items():
            contactados = sum(counts.values())
            avanzan = counts.get("handoff", 0) + counts.get("opciones", 0) + counts.get("ya_tiene_sistema", 0)
            no_interes = counts.get("no_interesado", 0) + counts.get("closed", 0)
            score = round((avanzan * 2.0 - no_interes * 0.5) / contactados, 3) if contactados else 0.0
            ranking.append({
                "rubro": rubro,
                "contactados": contactados,
                "avanzan": avanzan,
                "no_interes": no_interes,
                "score": score,
            })
        ranking.sort(key=lambda r: (-r["score"], -r["contactados"]))
        return {"ranking": ranking[:10], "total_rubros": len(by_rubro)}


_tool_runner = _ToolRunner()
_CHAT_HISTORY_FILE = "/app/data/assistant_chat.json"


def _load_history() -> list[dict]:
    try:
        with open(_CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(history: list[dict]):
    try:
        with open(_CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-40:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"assistant history save: {e}")


async def chat(message: str, session_id: str = "default") -> dict:
    """Procesa un mensaje del operador: Gemini decide herramientas, las ejecuta
    y devuelve la respuesta final con el historial actualizado."""
    history = _load_history()
    messages = [m for m in history if m.get("session", "default") == session_id]

    tool_decls = [types.FunctionDeclaration(**d) for d in _TOOL_DEFS]
    tool = types.Tool(function_declarations=tool_decls)

    contents = []
    for m in messages[-20:]:
        contents.append(types.Content(role=m["role"], parts=[types.Part(text=m["text"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    tools_result = None
    for _round in range(4):  # máximo 4 rondas de herramientas
        try:
            response = await _client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    tools=[tool],
                ),
            )
        except Exception as e:
            logger.error(f"assistant gemini error: {e}")
            return {"reply": f"Error consultando Gemini: {e}", "actions": [], "history": []}

        # Iteramos los parts crudos de la respuesta: conservan thought_signature
        # (obligatorio en gemini 3.5-flash al reenviar el function_call).
        raw_parts = []
        if response.candidates and getattr(response.candidates[0].content, "parts", None):
            raw_parts = response.candidates[0].content.parts
        elif getattr(response, "function_calls", None):
            raw_parts = response.function_calls
        fcalls = []
        echo_parts = []
        if raw_parts:
            for p in raw_parts:
                fc = getattr(p, "function_call", None)
                if fc is not None:
                    fcalls.append(fc)
                    ts = getattr(p, "thought_signature", None)
                    echo_parts.append(types.Part(function_call=fc, thought_signature=ts) if ts else types.Part(function_call=fc))
                elif getattr(p, "name", None):
                    fcalls.append(p)
                    echo_parts.append(p)
        if not fcalls:
            text = (response.text or "").strip()
            if not text:
                # Sin texto ni tool calls: algo raro en la respuesta, reportar.
                text = "No pude interpretar la solicitud. Intentá reformularla."
            history.append({"session": session_id, "role": "user", "text": message, "ts": datetime.now().isoformat()})
            history.append({"session": session_id, "role": "assistant", "text": text, "ts": datetime.now().isoformat()})
            _save_history(history)
            return {"reply": text, "actions": tools_result or [], "history": history[-30:]}

        tool_responses = []
        for fc in fcalls:
            name = fc.name
            args = {k: (v if not isinstance(v, str) else v) for k, v in (fc.args or {}).items()}
            if args is None:
                args = {}
            try:
                result = await _tool_runner.run(name, args)
            except Exception as e:
                result = {"error": str(e)}
            logger.info(f"assistant tool: {name} -> {json.dumps(result, ensure_ascii=False)[:200]}")
            tool_responses.append(types.Part(function_response=types.FunctionResponse(name=name, response=result)))
            tools_result = (tools_result or []) + [{"name": name, "result": result}]
        contents.append(types.Content(role="model", parts=echo_parts))
        contents.append(types.Content(role="user", parts=tool_responses))

    text = (response.text or "").strip() if response else ""
    history.append({"session": session_id, "role": "user", "text": message, "ts": datetime.now().isoformat()})
    history.append({"session": session_id, "role": "assistant", "text": text or "Listo, acción ejecutada.", "ts": datetime.now().isoformat()})
    _save_history(history)
    return {"reply": text or "Listo, acción ejecutada.", "actions": tools_result or [], "history": history[-30:]}
