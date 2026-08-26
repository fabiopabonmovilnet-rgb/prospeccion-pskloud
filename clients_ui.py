"""Dashboard UI for multi-client management."""
from __future__ import annotations

import json, os, uuid
from datetime import datetime
from typing import Optional

import streamlit as st

# Data directory: use Docker mount if available, else local
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data") if os.path.isdir(os.path.join(BASE_DIR, "data")) else BASE_DIR
CLIENTS_FILE = os.path.join(DATA_DIR, "clientes.json")
TEMPLATES_FILE = os.path.join(DATA_DIR, "plantillas.json")

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _load(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def get_clients() -> list[dict]:
    return _load(CLIENTS_FILE)


def save_client(data: dict) -> str:
    clients = get_clients()
    cid = data.get("id", "")
    if not cid:
        cid = uuid.uuid4().hex[:8]
        data["id"] = cid
        data["created_at"] = datetime.now().isoformat()
        clients.append(data)
    else:
        for i, c in enumerate(clients):
            if c.get("id") == cid:
                clients[i] = data
                break
    _save(CLIENTS_FILE, clients)
    return cid


def delete_client(cid: str):
    clients = get_clients()
    clients = [c for c in clients if c.get("id") != cid]
    _save(CLIENTS_FILE, clients)
    templates = get_templates(for_client=cid)
    remaining = [t for t in _load(TEMPLATES_FILE) if t.get("client_id") != cid]
    _save(TEMPLATES_FILE, remaining)


def get_templates(for_client: str = "", for_channel: str = "") -> list[dict]:
    all_t = _load(TEMPLATES_FILE)
    if for_client:
        all_t = [t for t in all_t if t.get("client_id") == for_client]
    if for_channel:
        all_t = [t for t in all_t if t.get("channel") == for_channel]
    return all_t


def save_template(data: dict):
    templates = _load(TEMPLATES_FILE)
    cid = data.get("client_id", "")
    ch = data.get("channel", "")
    idx = next((i for i, t in enumerate(templates) if t.get("client_id") == cid and t.get("channel") == ch), None)
    if idx is not None:
        templates[idx] = data
    else:
        templates.append(data)
    _save(TEMPLATES_FILE, templates)


def default_templates(cid: str) -> dict:
    return {
        "whatsapp": {
            "client_id": cid,
            "channel": "whatsapp",
            "messages": [
                {"step": 1, "text": "Buenos dias, senores de {nombre_empresa}, un gusto saludarles.", "enabled": True},
                {"step": 2, "text": "Queria consultarles brevemente: actualmente disponen de un software administrativo, contable y de control de inventario/POS que cumpla con las exigencias de ley?", "enabled": True},
                {"step": 3, "text": "Pertenezco a la casa Premium-Soft creadora del software administrativo y contable disenado para adaptarse a todas las normativas de ley y facturacion electronica. Si tienes un espacio de tiempo esta semana, podemos agendar una llamada o videollamada para una demostracion en vivo.", "enabled": True},
            ],
        },
        "email": {
            "client_id": cid,
            "channel": "email",
            "messages": [
                {"step": 1, "text": "Hola {nombre_empresa},\n\nSomos Premium-Soft, especialistas en software administrativo y contable. Nos gustaria saber si estan interesados en conocer nuestras soluciones.", "enabled": True},
                {"step": 2, "text": "Hola {nombre_empresa},\n\nDamos seguimiento a nuestro anterior mensaje. Tenemos planes flexibles que podrian interesarles.", "enabled": True},
                {"step": 3, "text": "Hola {nombre_empresa},\n\nComo ultimo contacto, les ofrecemos una demo gratuita de nuestra suite. Sin compromiso.", "enabled": True},
            ],
        },
        "instagram": {
            "client_id": cid,
            "channel": "instagram",
            "messages": [
                {"step": 1, "text": "Hola {nombre_empresa}! Soy Fabio Pabon, consultor de ventas internacional de PSKloud (Premium-Soft). Somos creadores del software administrativo, contable y de inventario/POS lider en Latinoamerica. Les interesaría conocer como podemos ayudarles a optimizar su gestion?", "enabled": True},
                {"step": 2, "text": "Contamos con planes flexibles y una demostracion en vivo sin compromiso. Les parece si agendamos una breve llamada?", "enabled": True},
            ],
        },
    }


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------


def render_client_form(client: Optional[dict] = None) -> Optional[str]:
    """Render the client creation/editing form. Returns client_id if saved."""
    is_edit = client is not None
    title = "Editar Cliente" if is_edit else "Nuevo Cliente"

    with st.form(key=f"client_form_{client.get('id', 'new') if client else 'new'}"):
        st.subheader(title)

        name = st.text_input("Nombre del Cliente / Negocio", value=client.get("name", "") if client else "",
                             placeholder="Ej: Premium-Soft Panama")
        rubros_str = st.text_input("Rubros a prospectar (separados por coma)",
                                   value=", ".join(client.get("rubros", [])) if client else "restaurante, farmacia, hotel",
                                   placeholder="restaurante, farmacia, hotel")
        ubicaciones_str = st.text_area("Ubicaciones (una por linea)",
                                       value="\n".join(client.get("ubicaciones", [])) if client else "Ciudad de Panama, Panama",
                                       placeholder="Ciudad de Panama, Panama\nSan Jose, Costa Rica")

        st.divider()
        st.caption("WhatsApp")
        col_w1, col_w2 = st.columns(2)
        with col_w1:
            wa_enabled = st.checkbox("Activar WhatsApp", value=client.get("whatsapp_enabled", True) if client else True)
        with col_w2:
            wa_max = st.number_input("Max/dia", min_value=1, max_value=100,
                                     value=client.get("whatsapp_max_daily", 20) if client else 20)
        wa_api = st.text_input("Evolution API URL", value=client.get("whatsapp_api_url", "") if client else "",
                               placeholder="http://evolution-api:8080")
        wa_key = st.text_input("API Key", value=client.get("whatsapp_api_key", "") if client else "",
                               type="password" if not is_edit else "default")
        wa_inst = st.text_input("Instance Name", value=client.get("whatsapp_instance", "pskloud-prospector") if client else "pskloud-prospector")
        col_wh1, col_wh2 = st.columns(2)
        with col_wh1:
            wa_hs = st.number_input("Hora inicio", 0, 23, value=client.get("whatsapp_hour_start", 9) if client else 9)
        with col_wh2:
            wa_he = st.number_input("Hora fin", 0, 23, value=client.get("whatsapp_hour_end", 16) if client else 16)

        st.divider()
        st.caption("Email (SMTP)")
        col_e1, col_e2 = st.columns([1, 3])
        with col_e1:
            email_enabled = st.checkbox("Activar Email", value=client.get("email_enabled", False) if client else False)
        with col_e2:
            em_max = st.number_input("Max/dia email", min_value=1, max_value=500,
                                     value=client.get("email_max_daily", 50) if client else 50)
        em_host = st.text_input("SMTP Host", value=client.get("email_smtp_host", "") if client else "")
        col_ep1, col_ep2 = st.columns(2)
        with col_ep1:
            em_port = st.number_input("SMTP Port", 1, 65535, value=client.get("email_smtp_port", 587) if client else 587)
        with col_ep2:
            em_user = st.text_input("SMTP User", value=client.get("email_smtp_user", "") if client else "")
        em_pass = st.text_input("SMTP Password", value="", type="password",
                                help="Dejar vacio para mantener el valor actual" if is_edit else "")
        em_from_name = st.text_input("From Name", value=client.get("email_from_name", "") if client else "")
        em_from_email = st.text_input("From Email", value=client.get("email_from_email", "") if client else "")

        st.divider()
        st.caption("Instagram (Browser Automation)")
        col_i1, col_i2 = st.columns([1, 3])
        with col_i1:
            ig_enabled = st.checkbox("Activar Instagram", value=client.get("instagram_enabled", False) if client else False)
        with col_i2:
            ig_max = st.number_input("Max/dia IG", min_value=1, max_value=30,
                                     value=client.get("instagram_max_daily", 3) if client else 3,
                                     help="Maximo 3/dia/pais para evitar bloqueos")
        ig_user = st.text_input("Instagram Username", value=client.get("instagram_username", "") if client else "",
                                placeholder="usuario_ig")
        ig_pass = st.text_input("Instagram Password", value="", type="password",
                                help="Dejar vacio para mantener el valor actual" if is_edit else "")
        ig_proxy = st.text_input("Proxy (opcional)", value=client.get("ig_proxy", "") if client else "",
                                 placeholder="http://user:pass@host:port")
        ig_hashtags_str = st.text_input("Hashtags IG (separados por coma)",
                                        value=", ".join(client.get("instagram", {}).get("ig_hashtags", client.get("ig_hashtags", ["boutique", "moda", "shopping", "accesorios"]))) if client else "boutique, moda, shopping, accesorios",
                                        placeholder="boutique, moda, shopping, accesorios, tienda",
                                        help="Se combinaran con cada pais para buscar en IG ej: #boutiquepanama")

        submitted = st.form_submit_button("Guardar Cliente", type="primary", use_container_width=True)

    if submitted and name.strip():
        rubros_list = [r.strip() for r in rubros_str.split(",") if r.strip()]
        ubicaciones_list = [u.strip() for u in ubicaciones_str.split("\n") if u.strip()]

        data = {
            "id": client.get("id", "") if client else "",
            "name": name.strip(),
            "rubros": rubros_list,
            "ubicaciones": ubicaciones_list,
            "whatsapp_enabled": wa_enabled,
            "whatsapp_max_daily": wa_max,
            "whatsapp_api_url": wa_api,
            "whatsapp_api_key": wa_key if wa_key else (client.get("whatsapp_api_key", "") if client else ""),
            "whatsapp_instance": wa_inst,
            "whatsapp_hour_start": wa_hs,
            "whatsapp_hour_end": wa_he,
            "email_enabled": email_enabled,
            "email_max_daily": em_max,
            "email_smtp_host": em_host,
            "email_smtp_port": em_port,
            "email_smtp_user": em_user,
            "email_smtp_password": em_pass if em_pass else (client.get("email_smtp_password", "") if client else ""),
            "email_from_name": em_from_name,
            "email_from_email": em_from_email,
            "instagram_enabled": ig_enabled,
            "instagram_max_daily": ig_max,
            "instagram_username": ig_user,
            "instagram_password": ig_pass if ig_pass else (client.get("instagram_password", "") if client else ""),
            "ig_proxy": ig_proxy,
            "ig_hashtags": [h.strip() for h in ig_hashtags_str.split(",") if h.strip()],
        }
        if is_edit:
            data["created_at"] = client.get("created_at", datetime.now().isoformat())

        cid = save_client(data)

        # Create default templates on first save
        if not is_edit:
            defaults = default_templates(cid)
            for ch, tmpl in defaults.items():
                save_template(tmpl)

        st.success(f"Cliente '{name.strip()}' guardado (ID: {cid})")
        st.rerun()
        return cid

    if submitted and not name.strip():
        st.error("El nombre del cliente es obligatorio")

    return None


def render_client_card(client: dict):
    """Display a client summary card with edit/delete actions."""
    cid = client.get("id", "")
    name = client.get("name", "Sin nombre")

    with st.container(border=True):
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(f"**{name}**")
            rubros = client.get("rubros", [])
            ubicaciones = client.get("ubicaciones", [])
            st.caption(f"Rubros: {len(rubros)} | Ubicaciones: {len(ubicaciones)}")
            channels = []
            if client.get("whatsapp_enabled"):
                channels.append("WA")
            if client.get("email_enabled"):
                channels.append("Email")
            if client.get("instagram_enabled"):
                ig_tags = client.get("instagram", {}).get("ig_hashtags", client.get("ig_hashtags", []))
                tags_str = f" ({len(ig_tags)} hashtags)" if ig_tags else ""
                channels.append(f"IG{tags_str}")
            st.caption(f"Canales: {', '.join(channels) if channels else 'Ninguno'}")
        with cols[1]:
            if st.button("Editar", key=f"edit_{cid}", use_container_width=True):
                st.session_state["editing_client"] = cid
                st.rerun()
        with cols[2]:
            if st.button("Eliminar", key=f"del_{cid}", use_container_width=True, type="secondary"):
                delete_client(cid)
                st.rerun()


def render_templates_editor(client_id: str):
    """Render the template editor for all channels."""
    if not client_id:
        st.info("Selecciona un cliente para editar sus plantillas")
        return

    templates = get_templates(for_client=client_id)
    templates_by_channel = {t["channel"]: t for t in templates}

    st.subheader("Plantillas de Mensajes")

    for channel_name, channel_label in [("whatsapp", "WhatsApp"), ("email", "Email"), ("instagram", "Instagram")]:
        with st.expander(f"{channel_label}", expanded=(channel_name == "whatsapp")):
            tmpl = templates_by_channel.get(channel_name, default_templates(client_id).get(channel_name, {"client_id": client_id, "channel": channel_name, "messages": []}))

            msgs = tmpl.get("messages", [])
            updated_msgs = []

            col_add, _ = st.columns([1, 3])
            with col_add:
                if st.button(f"+ Agregar mensaje", key=f"add_msg_{client_id}_{channel_name}"):
                    msgs.append({"step": len(msgs) + 1, "text": "", "enabled": True})
                    tmpl["messages"] = msgs
                    save_template(tmpl)
                    st.rerun()

            for i, msg in enumerate(msgs):
                with st.container(border=True):
                    cols = st.columns([1, 10, 1])
                    with cols[0]:
                        enabled = st.checkbox("", value=msg.get("enabled", True),
                                              key=f"en_{client_id}_{channel_name}_{i}")
                    with cols[1]:
                        new_text = st.text_area(
                            f"Mensaje {msg.get('step', i+1)}",
                            value=msg.get("text", ""),
                            key=f"txt_{client_id}_{channel_name}_{i}",
                            height=80,
                            placeholder="Usa {nombre_empresa} y {rubro} como placeholders",
                        )
                    with cols[2]:
                        if st.button("🗑️", key=f"del_msg_{client_id}_{channel_name}_{i}"):
                            continue  # handled below via state
                    updated_msgs.append({
                        "step": msg.get("step", i + 1),
                        "text": new_text,
                        "enabled": enabled,
                    })

            if st.button(f"Guardar plantillas {channel_label}", key=f"save_tmpl_{client_id}_{channel_name}", type="primary"):
                # Filter out deleted (empty text and disabled)
                active = [m for m in updated_msgs if m["enabled"] or m["text"].strip()]
                # Re-number steps
                for j, m in enumerate(active):
                    m["step"] = j + 1
                tmpl["messages"] = active
                save_template(tmpl)
                st.success(f"Plantillas de {channel_label} guardadas")
                st.rerun()


def render_page():
    st.header("Clientes")
    st.caption("Gestiona tus clientes, canales de comunicacion y plantillas de mensajes")

    # State
    if "editing_client" not in st.session_state:
        st.session_state["editing_client"] = ""
    if "viewing_templates" not in st.session_state:
        st.session_state["viewing_templates"] = ""

    clients = get_clients()

    # Action buttons
    col_new, col_tmpl = st.columns([1, 3])
    with col_new:
        if st.button("+ Nuevo Cliente", type="primary", use_container_width=True):
            st.session_state["editing_client"] = "__new__"
            st.rerun()

    # Edit/Create form
    editing = st.session_state.get("editing_client", "")
    if editing:
        if editing == "__new__":
            render_client_form(client=None)
        else:
            client = next((c for c in clients if c.get("id") == editing), None)
            if client:
                render_client_form(client=client)
        if st.button("← Volver a lista"):
            st.session_state["editing_client"] = ""
            st.rerun()
        st.divider()
        return

    # Client list
    if not clients:
        st.info("No hay clientes configurados. Crea tu primer cliente para comenzar la prospeccion.")
        return

    for client in clients:
        render_client_card(client)

    # Templates section
    st.divider()
    st.subheader("Plantillas por Cliente")
    selected = st.selectbox(
        "Selecciona un cliente para editar plantillas",
        options=[c.get("id", "") for c in clients],
        format_func=lambda cid: next((c.get("name", cid) for c in clients if c.get("id") == cid), cid),
        key="template_selector",
    )
    if selected:
        render_templates_editor(selected)
