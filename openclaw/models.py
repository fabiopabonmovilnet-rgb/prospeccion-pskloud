from __future__ import annotations

import enum
from datetime import datetime, time
from pydantic import BaseModel, Field


class Lead(BaseModel):
    nombre: str = ""
    empresa: str = ""
    telefono: str = ""
    rubro: str = ""
    pais: str = ""
    ciudad: str = ""
    email: str = ""
    website: str = ""
    fuente: str = ""
    client_id: str = ""
    keywords: str = ""
    campaign_key: str = ""


class Classification(str, enum.Enum):
    INTERESADO = "interesado"
    DUDA = "duda"
    NO_INTERESADO = "no_interesado"
    HANDOFF = "handoff"
    YA_TIENE_SISTEMA = "ya_tiene_sistema"
    CONTACTO_EQUIVOCADO = "contacto_equivocado"


class Message(BaseModel):
    id: str = ""
    direction: str = ""
    text: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    classification: Classification | None = None


class Conversation(BaseModel):
    lead: Lead
    status: str = "pending"
    messages: list[Message] = []
    current_step: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    last_reply_at: datetime | None = None
    classification: Classification | None = None
    sent_today: bool = False


class EnqueueRequest(BaseModel):
    leads: list[Lead]
    campaign_name: str = "default"


class ChannelSettings(BaseModel):
    enabled: bool = True
    max_daily: int = 20
    min_delay_seconds: int = 60
    max_delay_seconds: int = 120
    typing_delay_min_ms: int = 3000
    typing_delay_max_ms: int = 5000
    hour_start: int = 9
    hour_end: int = 16
    work_days: list[int] = [0, 1, 2, 3, 4]


class WhatsAppChannel(ChannelSettings):
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""
    media_url: str = ""
    media_type: str = ""


class EmailChannel(ChannelSettings):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_name: str = ""
    from_email: str = ""
    max_daily: int = 50
    min_delay_seconds: int = 120
    max_delay_seconds: int = 300


class InstagramChannel(ChannelSettings):
    instagram_username: str = ""
    instagram_password: str = ""
    ig_proxy: str = ""
    ig_hashtags: list[str] = ["boutique", "moda", "shopping", "accesorios"]
    ig_wa_phone: str = ""  # WhatsApp Business number for the live demo link (wa.me)
    ig_imagen: str = ""  # path to the presentation image to attach with the DM
    max_daily: int = 3
    min_delay_seconds: int = 180
    max_delay_seconds: int = 300


class TemplateMessage(BaseModel):
    step: int
    text: str
    enabled: bool = True
    media_url: str = ""
    media_type: str = ""  # "image", "video", "document", "audio"


class MessageTemplateSet(BaseModel):
    client_id: str
    channel: str
    messages: list[TemplateMessage] = []

    def enabled_messages(self) -> list[TemplateMessage]:
        return sorted([m for m in self.messages if m.enabled], key=lambda m: m.step)


class Client(BaseModel):
    id: str = ""
    name: str = ""
    rubros: list[str] = ["restaurante"]
    ubicaciones: list[str] = ["Ciudad de Panamá, Panamá"]
    whatsapp: WhatsAppChannel = Field(default_factory=WhatsAppChannel)
    email: EmailChannel = Field(default_factory=EmailChannel)
    instagram: InstagramChannel = Field(default_factory=InstagramChannel)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def active_channels(self) -> list[str]:
        channels = []
        if self.whatsapp.enabled and self.whatsapp.evolution_api_url:
            channels.append("whatsapp")
        if self.email.enabled and self.email.smtp_host:
            channels.append("email")
        if self.instagram.enabled and self.instagram.instagram_username:
            channels.append("instagram")
        return channels
