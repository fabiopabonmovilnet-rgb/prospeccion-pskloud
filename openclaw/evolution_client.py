from __future__ import annotations

import base64

import httpx
from config import settings
from models import WhatsAppChannel


class EvolutionClient:
    def __init__(self, base_url: str = "", api_key: str = "", instance: str = ""):
        self.base_url = (base_url or settings.evolution_api_url).rstrip("/")
        self.api_key = api_key or settings.evolution_api_key
        self.instance = instance or settings.evolution_instance
        self.headers = {
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=self.headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    def _clean(self, number: str) -> str:
        return number.replace("+", "").replace(" ", "").replace("-", "").replace(".", "").replace(",", "")

    async def send_text(self, number: str, text: str, delay_ms: int = 3000) -> dict:
        return await self._request(
            "POST",
            f"/message/sendText/{self.instance}",
            json={"number": self._clean(number), "text": text, "delay": delay_ms},
        )

    async def send_media(
        self,
        number: str,
        media_url: str,
        media_type: str = "image",
        caption: str = "",
        delay_ms: int = 3000,
    ) -> dict:
        media_type = media_type.lower().strip()
        if media_type not in ("image", "video", "document", "audio"):
            media_type = "image"
        mimetype_map = {
            "image": "image/png",
            "video": "video/mp4",
            "document": "application/pdf",
            "audio": "audio/mpeg",
        }
        # Evolution rejects media URLs whose hostname has no dot ("Owned media must be a url
        # or base64"), so always resolve the file and send it as base64.
        media_b64 = await self._media_to_base64(media_url)
        return await self._request(
            "POST",
            f"/message/sendMedia/{self.instance}",
            json={
                "number": self._clean(number),
                "mediatype": media_type,
                "mimetype": mimetype_map.get(media_type, "image/png"),
                "caption": caption,
                "media": media_b64,
                "fileName": media_url.split("/")[-1] if "/" in media_url else "media.png",
                "delay": delay_ms,
            },
        )

    async def _media_to_base64(self, media_url: str) -> str:
        if media_url.startswith("/"):
            media_url = settings.media_base_url.rstrip("/") + media_url
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(media_url)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode()

    async def send_typing(self, number: str) -> None:
        try:
            await self._request(
                "POST",
                f"/chat/sendPresence/{self.instance}",
                json={"number": self._clean(number), "presence": "composing", "delay": 1000},
            )
        except Exception:
            pass

    async def get_qr_code(self) -> dict | None:
        try:
            return await self._request("GET", f"/instance/connect/{self.instance}")
        except Exception:
            return None

    async def check_number(self, number: str) -> bool | None:
        try:
            clean = self._clean(number)
            resp = await self._request("GET", f"/chat/whatsappNumbers/{self.instance}?numbers={clean}")
            if isinstance(resp, list) and len(resp) > 0:
                return resp[0].get("exists", False)
            return None
        except Exception:
            return None

    async def contact_name(self, number: str) -> str | None:
        """Nombre de perfil del contacto, si está disponible (protección anti-contacto-equivocado)."""
        phone = self._clean(number)
        for endpoint in ("contacts", "chats/findContacts"):
            try:
                resp = await self._request("GET", f"/{endpoint}/{self.instance}?numbers={phone}")
            except Exception:
                continue
            items = resp.get("contacts") if isinstance(resp, dict) else resp
            if isinstance(items, list):
                for c in items:
                    cid = str(c.get("id", "")).split("@")[0]
                    cnum = str(c.get("number", "")).replace("+", "")
                    if cid == phone or cnum == phone:
                        name = str(c.get("name") or c.get("pushName") or "").strip()
                        if name:
                            return name
        return None

    async def connection_state(self) -> dict | None:
        try:
            return await self._request("GET", f"/instance/connectionState/{self.instance}")
        except Exception:
            return None


def evolution_from_channel(ch: WhatsAppChannel) -> EvolutionClient:
    return EvolutionClient(
        base_url=ch.evolution_api_url or settings.evolution_api_url,
        api_key=ch.evolution_api_key or settings.evolution_api_key,
        instance=ch.evolution_instance or settings.evolution_instance,
    )


def evolution_default() -> EvolutionClient:
    return EvolutionClient(
        base_url=settings.evolution_api_url,
        api_key=settings.evolution_api_key,
        instance=settings.evolution_instance,
    )
