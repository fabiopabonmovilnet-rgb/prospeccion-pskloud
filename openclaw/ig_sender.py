"""
Instagram DM sender using Playwright + stealth.
Sends max 3 DMs/day total (global). Rotates one hashtag per day.
If lead shows interest, sends WhatsApp Business link.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("openclaw.ig")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = "/app/data"
COOKIES_DIR = os.path.join(DATA_DIR, "ig_cookies")
STATE_FILE = os.path.join(DATA_DIR, "ig_state.json")
DAILY_LIMIT = int(os.getenv("IG_DAILY_LIMIT", "6"))  # max DMs per day (global, not per country)
IG_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone14,3; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# State persistence (per-country daily counters)
# ---------------------------------------------------------------------------


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            if data.get("date") == date.today().isoformat():
                return data
        except Exception:
            pass
    return {"date": date.today().isoformat(), "sent_today": 0}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["date"] = date.today().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _can_send() -> bool:
    state = _load_state()
    return state["sent_today"] < DAILY_LIMIT


def _mark_sent():
    state = _load_state()
    state["sent_today"] += 1
    _save_state(state)


def remaining_today() -> int:
    state = _load_state()
    return max(0, DAILY_LIMIT - state["sent_today"])


# ---------------------------------------------------------------------------
# Browser management
# ---------------------------------------------------------------------------


async def _get_browser():
    """Get or create a persistent Playwright browser with stealth."""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    ua = random.choice(IG_USER_AGENTS)

    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--window-size={random.randint(360,420)},{random.randint(700,800)}",
        ],
    )

    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": random.randint(360, 420), "height": random.randint(700, 800)},
        device_scale_factor=random.choice([1.0, 2.0, 3.0]),
        locale="es-ES",
        timezone_id="America/Panama",
    )

    # Stealth: override navigator.webdriver
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en'] });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    """)

    return p, browser, context


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def _cookie_path(username: str) -> str:
    os.makedirs(COOKIES_DIR, exist_ok=True)
    return os.path.join(COOKIES_DIR, f"{username}.json")


async def _login(context, username: str, password: str) -> bool:
    """Login to Instagram. Returns True if successful (session cookie present)."""
    page = await context.new_page()

    # Try loading saved cookies first
    cookie_file = _cookie_path(username)
    has_session = False
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r") as f:
                cookies = json.load(f)
            if any(c.get("name") == "sessionid" for c in cookies):
                await context.add_cookies(cookies)
                has_session = True
                logger.info(f"Loaded saved session cookies for {username}")
            else:
                logger.info(f"Cookie file for {username} has no sessionid; will re-login")
        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")

    # If we have a valid session cookie, verify it works
    if has_session:
        await page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 4))
        body = await page.locator("body").inner_text(timeout=8000)
        if "entrar" not in body[:200].lower() and "log in" not in body[:200].lower():
            await page.close()
            return True
        logger.info(f"Saved session for {username} expired; re-logging in")
        has_session = False

    # Go directly to the login page and fill the form
    await page.goto("https://www.instagram.com/accounts/login/", timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(random.uniform(3, 5))

    # If a username field is visible, we need to log in
    login_needed = page.locator('input[name="username"]')
    if await login_needed.is_visible(timeout=4000):
        logger.info(f"Logging in as {username}...")

        # Accept cookies if present (multi-language)
        try:
            for txt in ("Allow all", "Aceptar todo", "Aceptar", "Permitir", "Allow"):
                accept = page.locator(f'button:has-text("{txt}"), div[role="button"]:has-text("{txt}")')
                if await accept.first.is_visible(timeout=1500):
                    await accept.first.click()
                    await asyncio.sleep(1)
                    break
        except Exception:
            pass

        # Fill username
        user_input = page.locator('input[name="username"]')
        await user_input.click()
        await _human_type(page, username)

        # Fill password
        pass_input = page.locator('input[name="password"]')
        await pass_input.click()
        await _human_type(page, password)

        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Click login (multi-language, button or div[role=button])
        clicked = False
        for txt in ("Log in", "Iniciar sesión", "Entrar", "Iniciar sesión con Facebook"):
            for sel in (f'button[type="submit"]:has-text("{txt}")',
                        f'div[role="button"]:has-text("{txt}")'):
                try:
                    el = page.locator(sel)
                    if await el.count() > 0 and await el.first.is_visible(timeout=1500):
                        await el.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if clicked:
                break
        if not clicked:
            try:
                submit = page.locator('button[type="submit"]')
                await submit.first.click()
            except Exception:
                await page.keyboard.press("Enter")

        # Wait for login to complete
        await asyncio.sleep(random.uniform(3, 6))

        # Save cookies only if a real session cookie exists
        cookies = await context.cookies()
        names = [c["name"] for c in cookies]
        if "sessionid" in names:
            with open(cookie_file, "w") as f:
                json.dump(cookies, f)
            logger.info(f"Logged in and saved cookies for {username} (sessionid present)")
        else:
            logger.warning(f"No sessionid after login attempt for {username}")

    # Final check: verify session cookie + not on login/challenge page
    cookies = await context.cookies()
    names = [c["name"] for c in cookies]
    current_url = page.url
    if "sessionid" not in names:
        logger.error(f"Login failed for {username}: no sessionid cookie (url={current_url})")
        await page.screenshot(path=os.path.join(DATA_DIR, f"ig_challenge_{username}.png"))
        await page.close()
        return False
    if "challenge" in current_url or "two_factor" in current_url:
        logger.error(f"Instagram challenge/2FA required for {username}")
        await page.screenshot(path=os.path.join(DATA_DIR, f"ig_challenge_{username}.png"))
        await page.close()
        return False

    await page.close()
    return True


async def _human_type(page, text: str):
    """Simulate human typing with random delays."""
    for char in text:
        await page.keyboard.type(char, delay=random.randint(60, 180))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.1, 0.3))


# ---------------------------------------------------------------------------
# Search leads by hashtag
# ---------------------------------------------------------------------------


async def _search_hashtag(context, hashtag: str, max_results: int = 20) -> list[dict]:
    """Search Instagram accounts by keyword (topsearch). Returns matching users."""
    page = await context.new_page()
    leads = []

    try:
        # Build a searchable keyword query (strip #, split compound tag for better matches)
        tag = hashtag.replace("#", "").strip()
        # Convert a compound tag like "tiendadeportivapanama" into "tienda deportiva panama"
        word_map = [
            ("indumentaria", "indumentaria"),
            ("zapatilla", "zapatillas"),
            ("articulos", "articulos"),
            ("tiendadeportiva", "tienda deportiva"),
            ("tiendadeportes", "tienda deportes"),
            ("tienda", "tienda"),
            ("deportiv", "deportiva"),
            ("deporte", "deportes"),
            ("sport", "sport"),
            ("shop", "shop"),
            ("store", "store"),
            ("venta", "venta"),
            ("mexico", "mexico"),
            ("panama", "panama"),
            ("colombia", "colombia"),
            ("argentina", "argentina"),
            ("chile", "chile"),
            ("peru", "peru"),
            ("ecuador", "ecuador"),
            ("salvador", "salvador"),
            ("nicaragua", "nicaragua"),
            ("costa", "costa"),
            ("rica", "rica"),
            ("honduras", "honduras"),
        ]
        query_words = []
        rest = tag
        for frag, word in word_map:
            if frag in rest:
                query_words.append(word)
                rest = rest.replace(frag, " ", 1)
        if not query_words:
            query_words = [tag]
        query = " ".join(query_words).strip() or tag

        # Establish origin, then query topsearch with session cookies
        await page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1, 2))

        result = await page.evaluate(
            """
            async (q) => {
                try {
                    const r = await fetch('https://www.instagram.com/web/search/topsearch/?context=blended&query=' + encodeURIComponent(q), {credentials: 'include'});
                    return {status: r.status, body: await r.text()};
                } catch(e) { return {status: 0, body: String(e)}; }
            }
            """,
            query,
        )
        if result["status"] != 200:
            logger.error(f"topsearch HTTP {result['status']}: {result['body'][:200]}")
            return leads

        import json as _json
        data = _json.loads(result["body"])
        users = data.get("users", []) or data.get("user", [])
        for u in users:
            uu = u.get("user", {})
            username = uu.get("username", "")
            if not username:
                continue
            leads.append({
                "username": username,
                "full_name": uu.get("full_name", ""),
                "follower_count": uu.get("follower_count", 0),
                "source": query,
            })
            if len(leads) >= max_results:
                break
        logger.info(f"topsearch '{query}': {len(leads)} users")

    except Exception as e:
        logger.error(f"Error searching IG users for {hashtag}: {e}")
    finally:
        await page.close()

    return leads


# ---------------------------------------------------------------------------
# Follow user
# ---------------------------------------------------------------------------


async def _follow_user(context, username: str) -> bool:
    """Follow an Instagram user from their profile. Returns True if followed."""
    page = await context.new_page()

    try:
        await page.goto(f"https://www.instagram.com/{username}/", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 3))

        for txt in ("Follow", "Seguir", "Seguir de nuevo"):
            try:
                el = page.locator(f'button:has-text("{txt}")').first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(random.uniform(1, 2))
                    logger.info(f"Followed {username}")
                    return True
            except Exception:
                continue
        logger.info(f"Cannot follow {username}: no Follow button")
        return False

    except Exception as e:
        logger.error(f"Error following {username}: {e}")
        return False
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Send DM
# ---------------------------------------------------------------------------


async def text_area_enable(page):
    """Ensure the DM compose text area is opened (waits for it to be actionable)."""
    for _ in range(5):
        try:
            text_area = page.locator('div[role="textbox"]')
            cnt = text_area.count()
            if cnt > 0:
                try:
                    await text_area.first.click(timeout=2000)
                except Exception:
                    pass
                return True
        except Exception:
            pass
        await asyncio.sleep(random.uniform(1, 2))
    return False


async def _dismiss_popups(page):
    """Try to dismiss common Instagram popups that block interaction."""
    dismiss_texts = [
        "Ahora no", "Not Now", "No, gracias", "Cancel", "Cancelar",
        "Close", "Cerrar", "OK", "Entendido", "Got it",
    ]
    for txt in dismiss_texts:
        try:
            btn = page.locator(f'div[role="button"]:text-is("{txt}")').first
            if await btn.is_visible(timeout=800):
                await btn.click()
                await asyncio.sleep(random.uniform(0.5, 1))
        except Exception:
            continue


async def _send_dm(context, username: str, message_text: str, image_path: str = "") -> bool:
    """Send a DM to an Instagram user, optionally attaching an image. Returns True if sent."""
    page = await context.new_page()

    try:
        await page.goto(f"https://www.instagram.com/{username}/", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 3))

        # Dismiss any pre-existing popups
        await _dismiss_popups(page)
        await asyncio.sleep(random.uniform(0.5, 1))

        # Click "Message" button (multi-language)
        msg_clicked = False
        for txt in ("Enviar mensaje", "Message", "Mensaje"):
            try:
                el = page.locator(f'div[role="button"]:text-is("{txt}")').first
                if await el.is_visible(timeout=2500):
                    await el.click()
                    msg_clicked = True
                    break
            except Exception:
                continue
        if not msg_clicked:
            logger.info(f"Cannot message {username}: no Message button (private or restricted)")
            return False

        # Wait for chat to load, dismiss any popups that appear
        await asyncio.sleep(random.uniform(2, 3.5))
        await _dismiss_popups(page)
        await asyncio.sleep(random.uniform(1, 1.5))

        # Attach image if provided (photos/videos gallery icon -> file input).
        # Después de confirmar la imagen, seguimos para también escribir el mensaje.
        if image_path and os.path.exists(image_path):
            attached = False
            try:
                # Instagram uses a file input hidden behind the gallery button
                file_input = page.locator('input[type="file"]')
                # Ensure the compose input is visible / gallery available
                await text_area_enable(page)
                file_input_set = False
                for attempt in range(3):
                    count = await file_input.count()
                    if count > 0:
                        await file_input.first.set_input_files(image_path)
                        file_input_set = True
                        break
                    await asyncio.sleep(random.uniform(1, 2))
                if not file_input_set:
                    logger.warning(f"No file input found to attach image for {username}")
                await asyncio.sleep(random.uniform(2, 4))
                # Confirm the media send (small circle checkbox bottom-right)
                try:
                    confirm = page.locator('div[role="button"]:has-text("Enviar"), div[role="button"]:has-text("Send")').first
                    if await confirm.is_visible(timeout=2000):
                        await confirm.click()
                        attached = True
                        await asyncio.sleep(random.uniform(2, 3))
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Could not attach image for {username}: {e}")
            if attached:
                logger.info(f"Image attached to {username}, sending text too")
                await asyncio.sleep(random.uniform(2, 3))
                await _dismiss_popups(page)
        elif image_path:
            logger.warning(f"Image path does not exist: {image_path}")

        # Type message
        text_area = page.locator('div[role="textbox"]')
        await text_area.click()

        # Type character by character
        for char in message_text:
            await page.keyboard.type(char, delay=random.randint(40, 120))
            if random.random() < 0.03:
                await asyncio.sleep(random.uniform(0.2, 0.5))

        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Send (multi-language)
        send_clicked = False
        for txt in ("Enviar", "Send"):
            try:
                el = page.locator(f'div[role="button"]:text-is("{txt}")').first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    send_clicked = True
                    break
            except Exception:
                continue
        if not send_clicked:
            await page.keyboard.press("Enter")

        await asyncio.sleep(random.uniform(1, 2))
        logger.info(f"DM sent to {username}")
        return True

    except Exception as e:
        logger.error(f"Error sending DM to {username}: {e}")
        return False
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class InstagramSender:
    """High-level Instagram DM sender with rate limiting."""

    def __init__(self, username: str = None, password: str = None):
        self.username = username
        self.password = password
        self._playwright = None
        self._browser = None
        self._context = None
        self._logged_in = False

    async def ensure_login(self) -> bool:
        """Ensure we're logged into Instagram."""
        if self._logged_in and self._context:
            return True

        try:
            self._playwright, self._browser, self._context = await _get_browser()
            self._logged_in = await _login(self._context, self.username, self.password)
            return self._logged_in
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def search_leads(self, hashtags: list[str], max_per_tag: int = 10) -> list[dict]:
        """Search Instagram for leads by hashtag."""
        if not self._logged_in:
            if not await self.ensure_login():
                return []

        all_leads = []
        seen = set()
        for tag in hashtags:
            leads = await _search_hashtag(self._context, tag, max_results=max_per_tag)
            for l in leads:
                if l["username"] not in seen:
                    seen.add(l["username"])
                    all_leads.append(l)
            await asyncio.sleep(random.uniform(3, 6))
        return all_leads

    async def profile_country(self, username: str) -> str:
        """Visita el perfil y devuelve el país inferido desde la bio/ubicación ('', 'Colombia', ...)."""
        try:
            page = await self._context.new_page()
            await page.goto(f"https://www.instagram.com/{username}/", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 3))
            bio = ""
            try:
                bio = await page.locator("header section span, div._aa_c").first.inner_text(timeout=5000)
            except Exception:
                pass
            if not bio:
                try:
                    body = await page.locator("body").inner_text(timeout=5000)
                    bio = body[:800]
                except Exception:
                    pass
            await page.close()

            # Mapa de países <- subcadenas típicas en bios de clínicas
            mapas = {
                "Colombia": ["colombia", "bogotá", "medellín", "cali", "barranquilla", "cartagena", "cúcuta", "pereira", "manizales", "bucaramanga", "col. ", "colombiano"],
                "Panamá": ["panamá", "panama", "panam"],
                "Costa Rica": ["costa rica", "san josé", "san jose", "heredia", "alajuela", "cartago", "cr. "],
                "Nicaragua": ["nicaragua", "managua", "león", "granada", "masaya"],
                "Honduras": ["honduras", "tegucigalpa", "san pedro sula", "la ceiba"],
                "El Salvador": ["el salvador", "san salvador", "santa ana", "soyapango"],
                "Venezuela": ["venezuela", "caracas", "maracaibo"],
                "Ecuador": ["ecuador", "quito", "guayaquil"],
                "Perú": ["perú", "peru", "lima", "arequipa"],
                "México": ["méxico", "mexico", "cdmx", "guadalajara", "monterrey"],
                "Guatemala": ["guatemala", "guatemala city"],
            }
            tb = bio.lower()
            for pais, claves in mapas.items():
                for k in claves:
                    if k in tb:
                        return pais
            return ""
        except Exception as e:
            logger.error(f"profile_country error for {username}: {e}")
            return ""

    async def send_dm(self, username: str, message_text: str, country: str = "", follow: bool = True, image_path: str = "") -> bool:
        """Send a DM respecting daily limits (5/day global). Optionally attaches image and follows first."""
        if not self._logged_in:
            if not await self.ensure_login():
                return False

        if not _can_send():
            logger.info(f"Daily limit ({DAILY_LIMIT}) reached")
            return False

        success = await _send_dm(self._context, username, message_text, image_path)
        if success:
            _mark_sent()
            logger.info(f"DM sent to {username} (remaining: {remaining_today()})")
            if follow:
                try:
                    await _follow_user(self._context, username)
                except Exception as e:
                    logger.error(f"Follow failed for {username}: {e}")
        return success

    async def close(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._logged_in = False


def build_dm_text(lead_name: str, company: str = "", rubro: str = "", wa_phone: str = "") -> str:
    """Build the DM text with a live-demo WhatsApp Business link."""
    greeting = f"¡Hola {lead_name}!" if lead_name else "¡Hola!"
    msg = f"{greeting}\n\n"
    msg += "Somos Premium-Soft, casa de software especializada en soluciones administrativas, "
    msg += "contables y de control de inventario, diseñadas para adaptarse a las leyes y "
    msg += "normativas de Latinoamérica.\n\n"
    if rubro:
        msg += f"Vemos que tienes un negocio de {rubro}; justo para ese tipo de operación, "
        msg += "nuestro software te ayuda a controlar inventario, facturación y contabilidad "
        msg += "en un solo lugar, cumpliendo con las exigencias de ley.\n\n"
    msg += "Si gustas, podemos mostrarte una demo del comportamiento del software adaptado "
    msg += "a tu negocio.\n\n"
    if wa_phone:
        wa_link = wa_phone.replace("+", "").replace(" ", "").replace("-", "")
        msg += "Haz clic aquí para ver la demo:\n"
        msg += f"https://wa.me/{wa_link}\n\n"
    msg += "¡Quedamos atentos!"
    return msg
