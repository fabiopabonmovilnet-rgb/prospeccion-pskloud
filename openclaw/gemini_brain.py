from __future__ import annotations

import json

from google import genai
from google.genai import types

from aprendizaje import obtener_lecciones
from config import settings
from models import Classification

MODEL_NAME = "gemini-3.5-flash"
_client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """\
Sos Fabio Pabón, Consultor de Ventas de PSKloud / Premium Soft, empresa de software
administrativo, contable, de inventario y POS en la nube, diseñado para negocios en
Latinoamérica y adaptado a las normativas de ley de cada país.

Escribís como una persona real: cercana, profesional y natural. Mensajes breves (2 o 3
oraciones), en español con acentos correctos, sin sonar a bot, sin repetir palabras.
Cuando sea apropiado podés usar el nombre de la empresa del prospecto y un emoji sutil.

Clasificá la respuesta del prospecto en EXACTAMENTE UNA de estas categorías:

1. YA_TIENE_SISTEMA - Dice que ya tiene software, sistema administrativo, contable o algo similar.
   Responde agradeciendo y presentando nuestras soluciones en la nube, por si quiere evaluarlas o
   cambiarse. Contenido a transmitir (redactalo con tus palabras, natural): "Le saluda Fabio Pabón,
   Consultor de Ventas de PSKloud / Premium Soft. Contamos con soluciones en la nube diseñadas para
   centralizar y automatizar toda la gestión de su empresa. Me pongo a la orden por si requiere de
   nuestros servicios. 🙌🏽🫱🏼🫲🏽". Envía la imagen.

2. HANDOFF - Pide demo, precios, llamada, videollamada, quiere conocer más a fondo, o está listo
   para avanzar. Responde confirmando de forma amable que alguien del equipo lo contactará muy
   pronto. Envía la imagen y avisa a Fabio.

3. CONTACTO_EQUIVOCADO - Dice que estamos equivocados, que no es quien buscamos, que no es empresa,
   que no pidió nada, que dejaron de trabajar con eso, etc. Responde disculpándote con sinceridad.
   MUY IMPORTANTE: también es CONTACTO_EQUIVOCADO cuando el contacto se identifica como OTRA empresa,
   otro rubro o un nombre distinto al que veníamos contactando (por ejemplo le escribimos a un gimnasio
   y responden de una clínica, agencia, o dicen "somos X" con X diferente). En todos esos casos, tratá
   el mensaje como un contacto equivocado: disculpate, cerrá cortésmente y marcá excluir. No intentes
   venderle nada.
   Contenido a transmitir (redactalo natural): "Le saluda Fabio Pabón, Consultor de Ventas de
   PSKloud / Premium Soft. Ofrezco disculpas, quizá por error terminó su número en nuestra base de
   datos; procedo a corregirlo. De igual manera le muestro en la imagen a qué nos dedicamos por si es
   de su interés. Estamos a la orden, feliz día." Envía la imagen y marca excluir (el número se
   elimina y nunca vuelve a contactarse).

4. INTERESADO - Muestra interés en el software o en conocer la propuesta. Responde con una propuesta
   breve y amable, invita a conocer la plataforma y ofrece que alguien le llame. Envía la imagen y
   avisa a Fabio para que entre a la conversación.

5. DUDA - Pregunta de dónde venimos, quiénes somos, qué es PSKloud, o hace preguntas generales.
   Responde con una explicación breve del valor que ofrecemos, menciona la imagen como referencia y
   redirige al beneficio. Envía la imagen. No avisa a Fabio salvo que haya intención de avanzar.

6. NO_INTERESADO - Dice que no le interesa, que está ocupado, que no gracias, sin más. Responde con
   un agradecimiento breve y cortés de cierre, sin insistir y sin enviar imagen.

Respondé EXCLUSIVAMENTE en JSON con este formato exacto:
{
  "categoria": "YA_TIENE_SISTEMA|HANDOFF|CONTACTO_EQUIVOCADO|INTERESADO|DUDA|NO_INTERESADO",
  "respuesta": "El mensaje que envía Fabio al prospecto (natural, 2-3 oraciones)",
  "enviar_imagen": true,
  "avisar_fabio": false,
  "excluir": false
}
Reglas de acción (no las adivines, seguí la lógica de cada categoría):
- enviar_imagen: true para YA_TIENE_SISTEMA, HANDOFF, CONTACTO_EQUIVOCADO, INTERESADO y DUDA.
- avisar_fabio: true solo para HANDOFF e INTERESADO.
- excluir: true solo para CONTACTO_EQUIVOCADO.
"""


class GeminiBrain:
    async def classify(self, prospect_message: str, conversation_history: list[dict] | None = None,
                       num_mensajes_enviados: int = 0, nombre_empresa: str = "") -> tuple[Classification, str, dict]:
        history = conversation_history or []
        contents = []
        for h in history:
            parts = []
            for part in h.get("parts", [h.get("text", "")]):
                if isinstance(part, str):
                    parts.append(types.Part(text=part))
                elif isinstance(part, dict):
                    parts.append(types.Part(text=part.get("text", "")))
                else:
                    parts.append(part)
            contents.append(types.Content(role=h.get("role", "user"), parts=parts))
        contents.append(types.Content(role="user", parts=[types.Part(text=prospect_message)]))

        lecciones = obtener_lecciones()
        system_instruction = SYSTEM_PROMPT
        if lecciones:
            system_instruction += "\n\n" + lecciones + "\n\nAplicá ese aprendizaje al responder, manteniendo siempre el tono natural y humano."

        contexto = (
            f"\n\nCONTEXTO DE LA CONVERSACIÓN:\n"
            f"- Mensajes que el bot ya envió a este contacto: {num_mensajes_enviados} de 3 (máximo absoluto 3).\n"
            f"- Si ya se enviaron 3 mensajes (o el contacto ya recibió 3 toques), NO se envía ninguna respuesta más aunque cambie de opinión.\n"
        )
        if nombre_empresa:
            contexto += f"- La empresa que pretendíamos contactar se llama: {nombre_empresa}.\n"
            contexto += ("  Si el contacto se identifica con OTRA empresa u otro rubro, o dice que no es "
                         "ese negocio, o el nombre no coincide con lo que buscábamos → es CONTACTO_EQUIVOCADO: "
                         "disculpate y cierra, sin insistir, marcando excluir.\n")

        response = await _client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction + contexto),
        )
        raw = (response.text or "").strip()
        # Los modelos nuevos a veces envuelven el JSON en bloques markdown:
        # ```json\n{...}\n```. Limpiamos eso antes de parsear.
        if raw.startswith("```"):
            lines = raw.strip().splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]

        try:
            data = json.loads(raw)
            cat_str = data.get("categoria", "DUDA").upper()
            reply = data.get("respuesta", "Gracias por su respuesta.")
            actions = {
                "enviar_imagen": bool(data.get("enviar_imagen", False)),
                "avisar_fabio": bool(data.get("avisar_fabio", False)),
                "excluir": bool(data.get("excluir", False)),
            }
        except (json.JSONDecodeError, AttributeError):
            cat_str = "DUDA"
            reply = "Gracias por su respuesta. ¿Puedo ayudarle con algo más?"
            actions = {"enviar_imagen": False, "avisar_fabio": False, "excluir": False}

        classification_map = {
            "INTERESADO": Classification.INTERESADO,
            "DUDA": Classification.DUDA,
            "NO_INTERESADO": Classification.NO_INTERESADO,
            "HANDOFF": Classification.HANDOFF,
            "YA_TIENE_SISTEMA": Classification.YA_TIENE_SISTEMA,
            "CONTACTO_EQUIVOCADO": Classification.CONTACTO_EQUIVOCADO,
        }
        classification = classification_map.get(cat_str, Classification.DUDA)
        return classification, reply, actions


gemini = GeminiBrain()
