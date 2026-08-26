from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

from config import settings
from models import Conversation, Message, Classification

_DB_PATH = os.path.join(settings.data_dir, "conversaciones.db")
_SCHEMA_INITIALIZED = False


def _ensure_db() -> sqlite3.Connection:
    global _SCHEMA_INITIALIZED
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    # WAL + busy_timeout: the queue loop, webhook and prospector write/read
    # concurrently; without these, reads fail with "database is locked" and
    # dedup silently breaks (re-sending already-contacted leads).
    conn = sqlite3.connect(_DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    if not _SCHEMA_INITIALIZED:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                phone TEXT PRIMARY KEY,
                lead_json TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                current_step INTEGER DEFAULT 0,
                classification TEXT,
                started_at TEXT,
                last_reply_at TEXT,
                sent_today INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                direction TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                classification TEXT,
                FOREIGN KEY (phone) REFERENCES conversations(phone)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_counter (
                date TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        _SCHEMA_INITIALIZED = True
    return conn


def get_conversation(phone: str) -> Conversation | None:
    conn = _ensure_db()
    phone = _normalize_phone(phone)
    row = conn.execute("SELECT * FROM conversations WHERE phone = ?", (phone,)).fetchone()
    if not row:
        conn.close()
        return None
    lead_data = json.loads(row["lead_json"])
    msgs = conn.execute(
        "SELECT * FROM messages WHERE phone = ? ORDER BY timestamp", (phone,)
    ).fetchall()
    conn.close()
    return Conversation(
        lead=lead_data,
        status=row["status"],
        current_step=row["current_step"],
        classification=Classification(row["classification"]) if row["classification"] else None,
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else datetime.now(),
        last_reply_at=datetime.fromisoformat(row["last_reply_at"]) if row["last_reply_at"] else None,
        sent_today=bool(row["sent_today"]),
        messages=[
            Message(
                id=str(m["id"]),
                direction=m["direction"],
                text=m["text"],
                timestamp=datetime.fromisoformat(m["timestamp"]),
                classification=Classification(m["classification"]) if m["classification"] else None,
            )
            for m in msgs
        ],
    )


def list_conversations(status: str | None = None) -> list[Conversation]:
    conn = _ensure_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE status = ? ORDER BY started_at", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM conversations ORDER BY started_at").fetchall()
    conn.close()
    conversations = []
    for row in rows:
        try:
            lead_data = json.loads(row["lead_json"])
        except Exception:
            lead_data = {}
        conversations.append(
            Conversation(
                lead=lead_data,
                status=row["status"],
                current_step=row["current_step"],
                classification=Classification(row["classification"]) if row["classification"] else None,
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else datetime.now(),
                last_reply_at=datetime.fromisoformat(row["last_reply_at"]) if row["last_reply_at"] else None,
                sent_today=bool(row["sent_today"]),
            )
        )
    return conversations


def _normalize_phone(phone: str) -> str:
    """Strip formatting, ensure + prefix."""
    if not phone:
        return ""
    for ch in " .(),-\t":
        phone = phone.replace(ch, "")
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def save_conversation(conv: Conversation):
    conn = _ensure_db()
    phone = _normalize_phone(conv.lead.telefono)
    conn.execute(
        """INSERT OR REPLACE INTO conversations
           (phone, lead_json, status, current_step, classification, started_at, last_reply_at, sent_today)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            phone,
            json.dumps(conv.lead.model_dump(), ensure_ascii=False),
            conv.status,
            conv.current_step,
            conv.classification.value if conv.classification else None,
            conv.started_at.isoformat(),
            conv.last_reply_at.isoformat() if conv.last_reply_at else None,
            int(conv.sent_today),
        ),
    )
    conn.commit()
    conn.close()


def add_message(phone: str, msg: Message):
    conn = _ensure_db()
    conn.execute(
        "INSERT INTO messages (phone, direction, text, timestamp, classification) VALUES (?, ?, ?, ?, ?)",
        (
            phone,
            msg.direction,
            msg.text,
            msg.timestamp.isoformat(),
            msg.classification.value if msg.classification else None,
        ),
    )
    conn.commit()
    conn.close()


def get_today_count() -> int:
    conn = _ensure_db()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute("SELECT count FROM daily_counter WHERE date = ?", (today,)).fetchone()
    conn.close()
    return row["count"] if row else 0


def increment_today_count() -> int:
    conn = _ensure_db()
    today = datetime.now().strftime("%Y-%m-%d")
    current = get_today_count()
    conn.execute(
        "INSERT OR REPLACE INTO daily_counter (date, count) VALUES (?, ?)",
        (today, current + 1),
    )
    conn.commit()
    conn.close()
    return current + 1


def reset_daily_if_needed():
    conn = _ensure_db()
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute("UPDATE conversations SET sent_today = 0 WHERE sent_today = 1")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Excluded contacts (wrong numbers, no re-contact)
# ---------------------------------------------------------------------------

EXCLUDED_FILE = os.path.join(settings.data_dir, "contactos_excluidos.json")


def _load_excluded() -> dict:
    if os.path.exists(EXCLUDED_FILE):
        try:
            with open(EXCLUDED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_excluded(data: dict):
    try:
        with open(EXCLUDED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def list_excluded_phones() -> set:
    return set(_load_excluded().keys())


def is_phone_excluded(phone: str) -> bool:
    p = _normalize_phone(phone or "")
    return bool(p) and p in _load_excluded()


def exclude_phone(phone: str, motivo: str = "Contacto equivocado") -> str:
    p = _normalize_phone(phone or "")
    data = _load_excluded()
    data[p] = {"motivo": motivo, "fecha": datetime.now().isoformat()}
    _save_excluded(data)
    try:
        conn = _ensure_db()
        conn.execute(
            "UPDATE conversations SET status = 'excluido', classification = 'excluido' WHERE phone = ?",
            (p,),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return p


def rename_contact(phone: str, nombre: str = "", empresa: str = "") -> dict:
    p = _normalize_phone(phone or "")
    lead = {}
    try:
        conn = _ensure_db()
        row = conn.execute("SELECT lead_json FROM conversations WHERE phone = ?", (p,)).fetchone()
        if row:
            try:
                lead = json.loads(row["lead_json"])
            except Exception:
                lead = {}
            if nombre:
                lead["nombre"] = nombre
            if empresa:
                lead["empresa"] = empresa
            conn.execute(
                "UPDATE conversations SET lead_json = ? WHERE phone = ?",
                (json.dumps(lead, ensure_ascii=False), p),
            )
            conn.commit()
        conn.close()
    except Exception:
        pass
    return lead
