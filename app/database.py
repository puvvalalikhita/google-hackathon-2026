import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent


def get_db_path() -> Path:
    custom = os.getenv("DELIVEREX_DB_PATH", "").strip()
    if custom:
        p = Path(custom)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return BASE_DIR / "deliverex.db"


DB_PATH = get_db_path()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


def check_db_health() -> Dict[str, Any]:
    try:
        db_path = get_db_path()
        conn = get_conn()
        cust_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        conn.close()
        return {
            "ok": True,
            "path": str(db_path),
            "persistent_path_configured": bool(os.getenv("DELIVEREX_DB_PATH", "").strip()),
            "customers_seeded": cust_count,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def init_db(force_reset: bool = False) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            aliases TEXT NOT NULL,
            location TEXT NOT NULL,
            route TEXT NOT NULL,
            phone TEXT NOT NULL,
            pending_invoice_id TEXT NOT NULL,
            invoice_amount INTEGER NOT NULL,
            expected_bags INTEGER NOT NULL,
            sku_code TEXT NOT NULL,
            balance_due INTEGER NOT NULL,
            credit_limit INTEGER NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory (
            sku_code TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            warehouse_stock INTEGER NOT NULL,
            damaged_quarantine INTEGER NOT NULL DEFAULT 0,
            unit_price INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ledger_entries (
            entry_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            sku_code TEXT NOT NULL,
            delivered_qty INTEGER NOT NULL,
            damaged_qty INTEGER NOT NULL DEFAULT 0,
            cash_received INTEGER NOT NULL,
            discount_amount INTEGER NOT NULL DEFAULT 0,
            channel TEXT NOT NULL,
            tally_status TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            driver_name TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            entry_id TEXT,
            exception_type TEXT NOT NULL,
            policy_ref TEXT NOT NULL,
            summary TEXT NOT NULL,
            discount_requested INTEGER NOT NULL DEFAULT 0,
            damaged_qty INTEGER NOT NULL DEFAULT 0,
            proof_image TEXT,
            manager_name TEXT NOT NULL DEFAULT 'Priya Sharma (Area Manager)',
            status TEXT NOT NULL DEFAULT 'PENDING'
        );

        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            delivered_qty INTEGER NOT NULL,
            damaged_qty INTEGER NOT NULL,
            cash_received INTEGER NOT NULL,
            discount_approved INTEGER NOT NULL,
            balance_remaining INTEGER NOT NULL,
            channel TEXT NOT NULL,
            message_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS insights (
            insight_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            route TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            msg_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            sender TEXT NOT NULL,
            driver_name TEXT NOT NULL DEFAULT 'Raju Kumar',
            msg_type TEXT NOT NULL DEFAULT 'text',
            body TEXT NOT NULL,
            media_data_url TEXT,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS whatsapp_sessions (
            session_id TEXT PRIMARY KEY,
            driver_name TEXT NOT NULL DEFAULT 'Raju Kumar',
            active_customer_id TEXT,
            active_customer_name TEXT,
            workflow_stage TEXT NOT NULL DEFAULT 'IDLE',
            pending_draft_json TEXT,
            last_msg_hash TEXT,
            last_msg_ts REAL NOT NULL DEFAULT 0,
            turn_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )

    if force_reset:
        cur.executescript(
            """
            DELETE FROM whatsapp_messages;
            DELETE FROM insights;
            DELETE FROM receipts;
            DELETE FROM approvals;
            DELETE FROM ledger_entries;
            DELETE FROM inventory;
            DELETE FROM customers;
            """
        )

    # Seed only if empty
    count = cur.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if count == 0:
        now = _now_iso()
        cur.executemany(
            """
            INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "CUST-104",
                    "Krishna Hardware",
                    "krishna hardware,krishna store,krishna,old delhi hardware",
                    "Old Delhi Wholesale Market",
                    "Route-4 (Old Delhi)",
                    "+91-98110-10401",
                    "INV-8841",
                    15500,
                    20,
                    "SKU-CEM-50",
                    15500,
                    50000,
                    "OUT_FOR_DELIVERY",
                ),
                (
                    "CUST-108",
                    "Shri Ganesh Stores",
                    "shri ganesh,ganesh stores,ganesh hardware,chandni chowk",
                    "Chandni Chowk Bazaar",
                    "Route-4 (Old Delhi)",
                    "+91-98110-10802",
                    "INV-8845",
                    22000,
                    30,
                    "SKU-ACC-50",
                    22000,
                    75000,
                    "OUT_FOR_DELIVERY",
                ),
                (
                    "CUST-112",
                    "Bharat Traders",
                    "bharat traders,bharat,sadar bazar",
                    "Sadar Bazar Mandi",
                    "Route-2 (Central)",
                    "+91-98110-11203",
                    "INV-8850",
                    14500,
                    10,
                    "SKU-TMT-12",
                    14500,
                    40000,
                    "PENDING_DISPATCH",
                ),
                (
                    "CUST-115",
                    "Murugan Builders",
                    "murugan builders,murugan hardware,murugan,t nagar,chennai",
                    "T. Nagar Market, Chennai",
                    "Route-7 (Chennai South)",
                    "+91-98400-11509",
                    "INV-8862",
                    18400,
                    25,
                    "SKU-CEM-50",
                    18400,
                    60000,
                    "OUT_FOR_DELIVERY",
                ),
            ],
        )

        cur.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("SKU-CEM-50", "UltraTech Cement (50kg Bag)", 450, 4, 775, now),
                ("SKU-ACC-50", "ACC Gold Cement (50kg Bag)", 320, 1, 760, now),
                ("SKU-TMT-12", "Tata Tiscon TMT 12mm Bundle", 180, 0, 1450, now),
            ],
        )

        cur.executemany(
            """
            INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "TALLY-9001",
                    now,
                    "Vikram Singh",
                    "CUST-112",
                    "Bharat Traders",
                    "INV-8832",
                    "SKU-TMT-12",
                    12,
                    0,
                    17400,
                    0,
                    "GEMINI_LIVE_VOICE",
                    "SYNCED_TALLY",
                    "Full cash settlement on delivery",
                ),
            ],
        )

        cur.executemany(
            """
            INSERT INTO insights (created_at, route, category, severity, title, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    now,
                    "Route-4 (Old Delhi)",
                    "DAMAGED_GOODS",
                    "MEDIUM",
                    "Prior Torn Cement Bags on Route-4",
                    "2 bags reported torn during unloading on Truck MH-03-AB-1254 (Shift B) earlier this week.",
                ),
                (
                    now,
                    "Route-4 (Old Delhi)",
                    "PAYMENT_FRICTION",
                    "LOW",
                    "Wholesale Discount Requests Trending Up",
                    "3 Tier-2 dealers requested Rs 300-500 spot discounts during morning peak hours.",
                ),
            ],
        )

    wa_count = cur.execute("SELECT COUNT(*) FROM whatsapp_messages").fetchone()[0]
    if wa_count == 0:
        cur.execute(
            """
            INSERT INTO whatsapp_messages (
                msg_id, created_at, sender, driver_name, msg_type, body, media_data_url, metadata_json
            ) VALUES (?, ?, 'bot', 'DeliverEx Ops', 'text', ?, NULL, ?)
            """,
            (
                "WA-WELCOME-01",
                _now_iso(),
                (
                    "Namaste Raju! Delivery complete hone par text message, photo proof, ya 10-second voice note "
                    "yahan bhej do — Tally/SAP & Priya Ma'am ko auto-update ho jayega.\n\n"
                    "Try: \"Krishna Hardware pe 20 bags deliver, 15000 cash, 500 discount\" ya \"Krishna Hardware ka balance kitna hai?\""
                ),
                json.dumps({"sender_label": "DeliverEx Official Ops (+91-80-DELIVEREX)", "verified": True}),
            ),
        )

    conn.commit()
    conn.close()


def add_whatsapp_message(
    sender: str,
    body: str,
    msg_type: str = "text",
    driver_name: str = "Raju Kumar",
    media_data_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    msg_id = f"WA-{uuid.uuid4().hex[:8].upper()}"
    now = _now_iso()
    meta_json = json.dumps(metadata) if metadata else None
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO whatsapp_messages (
            msg_id, created_at, sender, driver_name, msg_type, body, media_data_url, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (msg_id, now, sender, driver_name, msg_type, body, media_data_url, meta_json),
    )
    conn.commit()
    conn.close()
    return {
        "msg_id": msg_id,
        "created_at": now,
        "sender": sender,
        "driver_name": driver_name,
        "msg_type": msg_type,
        "body": body,
        "media_data_url": media_data_url,
        "metadata": metadata or {},
    }


def get_whatsapp_session(session_id: str = "default") -> Dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM whatsapp_sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return {
            "session_id": session_id,
            "driver_name": "Raju Kumar",
            "active_customer_id": None,
            "active_customer_name": None,
            "workflow_stage": "IDLE",
            "pending_draft": {},
            "last_msg_hash": None,
            "last_msg_ts": 0.0,
            "turn_count": 0,
            "updated_at": _now_iso(),
        }
    item = dict(row)
    raw_draft = item.pop("pending_draft_json", None)
    try:
        item["pending_draft"] = json.loads(raw_draft) if raw_draft else {}
    except Exception:
        item["pending_draft"] = {}
    return item


def save_whatsapp_session(
    session_id: str,
    *,
    driver_name: str = "Raju Kumar",
    active_customer_id: Optional[str] = None,
    active_customer_name: Optional[str] = None,
    workflow_stage: str = "IDLE",
    pending_draft: Optional[Dict[str, Any]] = None,
    last_msg_hash: Optional[str] = None,
    last_msg_ts: float = 0.0,
    turn_count: int = 0,
) -> Dict[str, Any]:
    now = _now_iso()
    draft_json = json.dumps(pending_draft or {})
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO whatsapp_sessions (
            session_id, driver_name, active_customer_id, active_customer_name,
            workflow_stage, pending_draft_json, last_msg_hash, last_msg_ts, turn_count, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            driver_name = excluded.driver_name,
            active_customer_id = excluded.active_customer_id,
            active_customer_name = excluded.active_customer_name,
            workflow_stage = excluded.workflow_stage,
            pending_draft_json = excluded.pending_draft_json,
            last_msg_hash = excluded.last_msg_hash,
            last_msg_ts = excluded.last_msg_ts,
            turn_count = excluded.turn_count,
            updated_at = excluded.updated_at
        """,
        (
            session_id,
            driver_name,
            active_customer_id,
            active_customer_name,
            workflow_stage,
            draft_json,
            last_msg_hash,
            float(last_msg_ts or 0.0),
            int(turn_count or 0),
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_whatsapp_session(session_id)


def clear_whatsapp_session(session_id: str = "default") -> Dict[str, Any]:
    return save_whatsapp_session(
        session_id,
        driver_name="Raju Kumar",
        active_customer_id=None,
        active_customer_name=None,
        workflow_stage="IDLE",
        pending_draft={},
        last_msg_hash=None,
        last_msg_ts=0.0,
        turn_count=0,
    )


def get_full_state() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    wa_rows = cur.execute(
        "SELECT * FROM (SELECT rowid AS seq, * FROM whatsapp_messages ORDER BY rowid DESC LIMIT 60) ORDER BY seq ASC"
    ).fetchall()
    whatsapp_messages = []
    for r in wa_rows:
        item = dict(r)
        raw_meta = item.pop("metadata_json", None)
        item.pop("seq", None)
        try:
            item["metadata"] = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            item["metadata"] = {}
        whatsapp_messages.append(item)

    state = {
        "customers": [dict(r) for r in cur.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()],
        "inventory": [dict(r) for r in cur.execute("SELECT * FROM inventory ORDER BY sku_code").fetchall()],
        "ledger": [
            dict(r)
            for r in cur.execute("SELECT * FROM ledger_entries ORDER BY timestamp DESC, entry_id DESC LIMIT 20").fetchall()
        ],
        "approvals": [
            dict(r)
            for r in cur.execute("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 20").fetchall()
        ],
        "receipts": [
            dict(r)
            for r in cur.execute("SELECT * FROM receipts ORDER BY created_at DESC LIMIT 10").fetchall()
        ],
        "insights": [
            dict(r)
            for r in cur.execute("SELECT * FROM insights ORDER BY insight_id DESC LIMIT 15").fetchall()
        ],
        "whatsapp_messages": whatsapp_messages,
    }
    conn.close()
    state["whatsapp_session"] = get_whatsapp_session("default")
    return state


def find_customer(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip().lower()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM customers").fetchall()
    conn.close()
    for row in rows:
        r = dict(row)
        haystack = f"{r['customer_id']} {r['name']} {r['aliases']} {r['location']}".lower()
        if q in haystack or any(tok in haystack for tok in q.split() if len(tok) >= 4):
            return r
    return None
