import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.security import compute_audit_hash, verify_audit_chain
from app.storage_gcp import FirestoreStore, get_gcs_bucket_name, is_firestore_enabled, upload_proof_to_gcs

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


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:5].upper()}"


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return int(val)
    cleaned = str(val).replace(",", "").strip()
    if not cleaned:
        return default
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return default


_firestore_store: Optional[FirestoreStore] = None


def _get_firestore_store() -> Optional[FirestoreStore]:
    global _firestore_store
    if not is_firestore_enabled():
        return None
    if _firestore_store is None:
        _firestore_store = FirestoreStore()
    return _firestore_store


def _build_seed_payload(now: str) -> Dict[str, Any]:
    return {
        "customers": [
            {
                "customer_id": "CUST-104",
                "name": "Krishna Hardware",
                "aliases": "krishna hardware,krishna store,krishna,old delhi hardware",
                "location": "Old Delhi Wholesale Market",
                "route": "Route-4 (Old Delhi)",
                "phone": "+91-98110-10401",
                "pending_invoice_id": "INV-8841",
                "invoice_amount": 15500,
                "expected_bags": 20,
                "sku_code": "SKU-CEM-50",
                "balance_due": 15500,
                "credit_limit": 50000,
                "status": "OUT_FOR_DELIVERY",
            },
            {
                "customer_id": "CUST-108",
                "name": "Shri Ganesh Stores",
                "aliases": "shri ganesh,ganesh stores,ganesh hardware,chandni chowk",
                "location": "Chandni Chowk Bazaar",
                "route": "Route-4 (Old Delhi)",
                "phone": "+91-98110-10802",
                "pending_invoice_id": "INV-8845",
                "invoice_amount": 22000,
                "expected_bags": 30,
                "sku_code": "SKU-ACC-50",
                "balance_due": 22000,
                "credit_limit": 75000,
                "status": "OUT_FOR_DELIVERY",
            },
            {
                "customer_id": "CUST-112",
                "name": "Bharat Traders",
                "aliases": "bharat traders,bharat,sadar bazar",
                "location": "Sadar Bazar Mandi",
                "route": "Route-2 (Central)",
                "phone": "+91-98110-11203",
                "pending_invoice_id": "INV-8850",
                "invoice_amount": 14500,
                "expected_bags": 10,
                "sku_code": "SKU-TMT-12",
                "balance_due": 14500,
                "credit_limit": 40000,
                "status": "PENDING_DISPATCH",
            },
            {
                "customer_id": "CUST-115",
                "name": "Murugan Builders",
                "aliases": "murugan builders,murugan hardware,murugan,t nagar,chennai",
                "location": "T. Nagar Market, Chennai",
                "route": "Route-7 (Chennai South)",
                "phone": "+91-98400-11509",
                "pending_invoice_id": "INV-8862",
                "invoice_amount": 18400,
                "expected_bags": 25,
                "sku_code": "SKU-CEM-50",
                "balance_due": 18400,
                "credit_limit": 60000,
                "status": "OUT_FOR_DELIVERY",
            },
        ],
        "inventory": [
            {
                "sku_code": "SKU-CEM-50",
                "item_name": "UltraTech Cement (50kg Bag)",
                "warehouse_stock": 450,
                "damaged_quarantine": 4,
                "unit_price": 775,
                "updated_at": now,
            },
            {
                "sku_code": "SKU-ACC-50",
                "item_name": "ACC Gold Cement (50kg Bag)",
                "warehouse_stock": 320,
                "damaged_quarantine": 1,
                "unit_price": 760,
                "updated_at": now,
            },
            {
                "sku_code": "SKU-TMT-12",
                "item_name": "Tata Tiscon TMT 12mm Bundle",
                "warehouse_stock": 180,
                "damaged_quarantine": 0,
                "unit_price": 1450,
                "updated_at": now,
            },
        ],
        "ledger": [
            {
                "entry_id": "TALLY-9001",
                "timestamp": now,
                "driver_name": "Vikram Singh",
                "customer_id": "CUST-112",
                "customer_name": "Bharat Traders",
                "invoice_id": "INV-8832",
                "sku_code": "SKU-TMT-12",
                "delivered_qty": 12,
                "damaged_qty": 0,
                "cash_received": 17400,
                "discount_amount": 0,
                "channel": "GEMINI_LIVE_VOICE",
                "tally_status": "SYNCED_TALLY",
                "notes": "Full cash settlement on delivery",
            }
        ],
        "insights": [
            {
                "insight_id": 1,
                "created_at": now,
                "route": "Route-4 (Old Delhi)",
                "category": "DAMAGED_GOODS",
                "severity": "MEDIUM",
                "title": "Prior Torn Cement Bags on Route-4",
                "detail": "2 bags reported torn during unloading on Truck MH-03-AB-1254 (Shift B) earlier this week.",
            },
            {
                "insight_id": 2,
                "created_at": now,
                "route": "Route-4 (Old Delhi)",
                "category": "PAYMENT_FRICTION",
                "severity": "LOW",
                "title": "Wholesale Discount Requests Trending Up",
                "detail": "3 Tier-2 dealers requested Rs 300-500 spot discounts during morning peak hours.",
            },
        ],
        "whatsapp_messages": [
            {
                "msg_id": "WA-WELCOME-01",
                "created_at": now,
                "seq_ts": 0.0,
                "sender": "bot",
                "driver_name": "DeliverEx Ops",
                "msg_type": "text",
                "body": (
                    "Namaste Raju! Delivery complete hone par text message, photo proof, ya 10-second voice note "
                    "yahan bhej do — Tally/SAP & Priya Ma'am ko auto-update ho jayega.\n\n"
                    "Try: \"Krishna Hardware pe 20 bags deliver, 15000 cash, 500 discount\" ya \"Krishna Hardware ka balance kitna hai?\""
                ),
                "media_data_url": None,
                "metadata": {"sender_label": "DeliverEx Official Ops (+91-80-DELIVEREX)", "verified": True},
            }
        ],
    }


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


def get_storage_mode() -> str:
    if is_firestore_enabled():
        return "firestore+gcs" if get_gcs_bucket_name() else "firestore"
    return "sqlite"


def check_db_health() -> Dict[str, Any]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.check_health()

    try:
        db_path = get_db_path()
        conn = get_conn()
        cust_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        conn.close()
        return {
            "ok": True,
            "backend": "sqlite",
            "path": str(db_path),
            "persistent_path_configured": bool(os.getenv("DELIVEREX_DB_PATH", "").strip()),
            "customers_seeded": cust_count,
        }
    except Exception as exc:
        return {"ok": False, "backend": "sqlite", "error": str(exc)}


def _append_sqlite_audit(
    cur: sqlite3.Cursor,
    *,
    actor: str,
    role: str,
    action: str,
    target_id: str,
    summary: str,
    before_obj: Any = None,
    after_obj: Any = None,
) -> Dict[str, Any]:
    last = cur.execute("SELECT seq, integrity_hash FROM audit_logs ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = last["integrity_hash"] if last else "GENESIS"
    seq = (int(last["seq"]) + 1) if last else 1
    now = _now_iso()
    audit_id = f"AUD-{seq:05d}"
    before_json = json.dumps(before_obj, sort_keys=True) if before_obj is not None else ""
    after_json = json.dumps(after_obj, sort_keys=True) if after_obj is not None else ""
    rec = {
        "audit_id": audit_id,
        "seq": seq,
        "timestamp": now,
        "actor": actor,
        "role": role,
        "action": action,
        "target_id": target_id,
        "summary": summary,
        "before_json": before_json,
        "after_json": after_json,
        "prev_hash": prev_hash,
    }
    rec["integrity_hash"] = compute_audit_hash(prev_hash, rec)
    cur.execute(
        """
        INSERT INTO audit_logs (
            audit_id, seq, timestamp, actor, role, action, target_id, summary,
            before_json, after_json, prev_hash, integrity_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec["audit_id"],
            rec["seq"],
            rec["timestamp"],
            rec["actor"],
            rec["role"],
            rec["action"],
            rec["target_id"],
            rec["summary"],
            rec["before_json"],
            rec["after_json"],
            rec["prev_hash"],
            rec["integrity_hash"],
        ),
    )
    return rec


def append_audit_log(
    *,
    actor: str,
    role: str,
    action: str,
    target_id: str,
    summary: str,
    before_obj: Any = None,
    after_obj: Any = None,
) -> Dict[str, Any]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.append_audit_log(
            actor=actor,
            role=role,
            action=action,
            target_id=target_id,
            summary=summary,
            before_obj=before_obj,
            after_obj=after_obj,
        )
    conn = get_conn()
    cur = conn.cursor()
    rec = _append_sqlite_audit(
        cur,
        actor=actor,
        role=role,
        action=action,
        target_id=target_id,
        summary=summary,
        before_obj=before_obj,
        after_obj=after_obj,
    )
    conn.commit()
    conn.close()
    return rec


def get_audit_logs(limit: int = 30) -> Dict[str, Any]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.get_audit_logs(limit=limit)

    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM audit_logs ORDER BY seq ASC").fetchall()]
    conn.close()
    chain_ok = verify_audit_chain(rows)
    recent = list(reversed(rows[-limit:]))
    return {
        "entries": recent,
        "total_count": len(rows),
        "chain_verified": chain_ok,
        "storage_backend": "sqlite",
    }


def init_db(force_reset: bool = False) -> None:
    seed = _build_seed_payload(_now_iso())
    fs = _get_firestore_store()
    if fs is not None:
        fs.init_seed(seed, force_reset=force_reset)
        return

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

        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            prev_hash TEXT NOT NULL,
            integrity_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idem_key TEXT PRIMARY KEY,
            created_ts REAL NOT NULL,
            result_json TEXT NOT NULL
        );
        """
    )

    if force_reset:
        cur.executescript(
            """
            DELETE FROM idempotency_keys;
            DELETE FROM audit_logs;
            DELETE FROM whatsapp_messages;
            DELETE FROM insights;
            DELETE FROM receipts;
            DELETE FROM approvals;
            DELETE FROM ledger_entries;
            DELETE FROM inventory;
            DELETE FROM customers;
            """
        )

    count = cur.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c["customer_id"],
                    c["name"],
                    c["aliases"],
                    c["location"],
                    c["route"],
                    c["phone"],
                    c["pending_invoice_id"],
                    c["invoice_amount"],
                    c["expected_bags"],
                    c["sku_code"],
                    c["balance_due"],
                    c["credit_limit"],
                    c["status"],
                )
                for c in seed["customers"]
            ],
        )
        cur.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    i["sku_code"],
                    i["item_name"],
                    i["warehouse_stock"],
                    i["damaged_quarantine"],
                    i["unit_price"],
                    i["updated_at"],
                )
                for i in seed["inventory"]
            ],
        )
        cur.executemany(
            "INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    l["entry_id"],
                    l["timestamp"],
                    l["driver_name"],
                    l["customer_id"],
                    l["customer_name"],
                    l["invoice_id"],
                    l["sku_code"],
                    l["delivered_qty"],
                    l["damaged_qty"],
                    l["cash_received"],
                    l["discount_amount"],
                    l["channel"],
                    l["tally_status"],
                    l["notes"],
                )
                for l in seed["ledger"]
            ],
        )
        cur.executemany(
            "INSERT INTO insights (created_at, route, category, severity, title, detail) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (ins["created_at"], ins["route"], ins["category"], ins["severity"], ins["title"], ins["detail"])
                for ins in seed["insights"]
            ],
        )

    wa_count = cur.execute("SELECT COUNT(*) FROM whatsapp_messages").fetchone()[0]
    if wa_count == 0:
        for wm in seed["whatsapp_messages"]:
            cur.execute(
                """
                INSERT INTO whatsapp_messages (
                    msg_id, created_at, sender, driver_name, msg_type, body, media_data_url, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wm["msg_id"],
                    wm["created_at"],
                    wm["sender"],
                    wm["driver_name"],
                    wm["msg_type"],
                    wm["body"],
                    wm["media_data_url"],
                    json.dumps(wm["metadata"]),
                ),
            )

    audit_count = cur.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    if audit_count == 0:
        _append_sqlite_audit(
            cur,
            actor="System",
            role="SYSTEM",
            action="SYSTEM_RESET" if force_reset else "SYSTEM_INIT",
            target_id="deliverex-erp",
            summary="Initialized SQLite WAL ledger, warehouse inventory & SOP guardrails",
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
    fs = _get_firestore_store()
    if fs is not None:
        return fs.add_whatsapp_message(
            sender=sender,
            body=body,
            msg_type=msg_type,
            driver_name=driver_name,
            media_data_url=media_data_url,
            metadata=metadata,
        )

    msg_id = f"WA-{uuid.uuid4().hex[:8].upper()}"
    now = _now_iso()
    stored_media = media_data_url
    meta = dict(metadata or {})
    if media_data_url and media_data_url.startswith("data:image/"):
        stored_media, gcs_uri = upload_proof_to_gcs(media_data_url, "WA_MEDIA")
        if gcs_uri:
            meta["gcs_uri"] = gcs_uri
    meta_json = json.dumps(meta) if meta else None
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO whatsapp_messages (
            msg_id, created_at, sender, driver_name, msg_type, body, media_data_url, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (msg_id, now, sender, driver_name, msg_type, body, stored_media, meta_json),
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
        "media_data_url": stored_media,
        "metadata": meta,
    }


def get_whatsapp_session(session_id: str = "default") -> Dict[str, Any]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.get_whatsapp_session(session_id)

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
    fs = _get_firestore_store()
    if fs is not None:
        return fs.save_whatsapp_session(
            session_id,
            driver_name=driver_name,
            active_customer_id=active_customer_id,
            active_customer_name=active_customer_name,
            workflow_stage=workflow_stage,
            pending_draft=pending_draft,
            last_msg_hash=last_msg_hash,
            last_msg_ts=last_msg_ts,
            turn_count=turn_count,
        )

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
    fs = _get_firestore_store()
    if fs is not None:
        return fs.get_full_state()

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

    audit_rows = [dict(r) for r in cur.execute("SELECT * FROM audit_logs ORDER BY seq ASC").fetchall()]
    chain_ok = verify_audit_chain(audit_rows)

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
        "audit_summary": {
            "total_count": len(audit_rows),
            "chain_verified": chain_ok,
            "storage_backend": "sqlite",
            "latest": list(reversed(audit_rows[-5:])),
        },
    }
    conn.close()
    state["whatsapp_session"] = get_whatsapp_session("default")
    return state


def get_all_ledger_entries() -> List[Dict[str, Any]]:
    fs = _get_firestore_store()
    if fs is not None:
        rows = [d.to_dict() for d in fs.db.collection("ledger_entries").stream()]
        rows.sort(key=lambda x: (x.get("timestamp", ""), x.get("entry_id", "")), reverse=True)
        return rows

    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM ledger_entries ORDER BY timestamp DESC, entry_id DESC").fetchall()]
    conn.close()
    return rows


def find_customer(query: str) -> Optional[Dict[str, Any]]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.find_customer(query)

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


def db_attach_visual_proof(
    *,
    cust: Dict[str, Any],
    data_url: str,
    damaged_bags: int,
    auto_create_approval: bool,
    driver_name: str,
) -> Optional[str]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.tx_attach_visual_proof(
            customer_id=cust["customer_id"],
            data_url=data_url,
            damaged_bags=damaged_bags,
            auto_create_approval=auto_create_approval,
            driver_name=driver_name,
        )

    stored_img, _ = upload_proof_to_gcs(data_url, cust["customer_id"])
    attached_to = None
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT approval_id, damaged_qty FROM approvals WHERE status = 'PENDING' AND customer_id = ? ORDER BY created_at DESC LIMIT 1",
        (cust["customer_id"],),
    ).fetchone()
    if row:
        attached_to = row["approval_id"]
        prev_dmg = _safe_int(row["damaged_qty"], 0)
        new_dmg = max(prev_dmg, _safe_int(damaged_bags, 0))
        dmg_delta = max(0, new_dmg - prev_dmg)
        cur.execute(
            "UPDATE approvals SET proof_image = ?, damaged_qty = ? WHERE approval_id = ?",
            (stored_img, new_dmg, attached_to),
        )
        if dmg_delta > 0:
            cur.execute(
                "UPDATE inventory SET warehouse_stock = MAX(0, warehouse_stock - ?), damaged_quarantine = damaged_quarantine + ?, updated_at = ? WHERE sku_code = ?",
                (dmg_delta, dmg_delta, _now_iso(), cust["sku_code"]),
            )
        _append_sqlite_audit(
            cur,
            actor=driver_name,
            role="DRIVER",
            action="PROOF_ATTACHED",
            target_id=attached_to,
            summary=f"Attached visual damage proof to {attached_to} ({cust['name']})",
            after_obj={"damaged_qty": new_dmg},
        )
        conn.commit()
    elif auto_create_approval:
        now = _now_iso()
        attached_to = _short_id("APR")
        dmg = max(1, _safe_int(damaged_bags, 2))
        summary = f"{cust['name']} ({cust['pending_invoice_id']}): {dmg} torn/damaged bags visually verified via field camera — moved to quarantine"
        cur.execute(
            """
            INSERT INTO approvals (
                approval_id, created_at, driver_name, customer_id, customer_name,
                entry_id, exception_type, policy_ref, summary, discount_requested,
                damaged_qty, proof_image, status
            ) VALUES (?, ?, ?, ?, ?, NULL, 'DAMAGED_GOODS', 'SOP-5.1', ?, 0, ?, ?, 'PENDING')
            """,
            (attached_to, now, driver_name or "Raju Kumar", cust["customer_id"], cust["name"], summary, dmg, stored_img),
        )
        cur.execute(
            """
            UPDATE inventory
            SET warehouse_stock = MAX(0, warehouse_stock - ?),
                damaged_quarantine = damaged_quarantine + ?,
                updated_at = ?
            WHERE sku_code = ?
            """,
            (dmg, dmg, now, cust["sku_code"]),
        )
        cur.execute(
            """
            INSERT INTO insights (created_at, route, category, severity, title, detail)
            VALUES (?, ?, 'DAMAGED_GOODS', 'HIGH', ?, ?)
            """,
            (
                now,
                cust["route"],
                f"Visual Damage Verified at {cust['name']} ({dmg} bags torn)",
                f"Field camera captured {dmg} torn {cust['sku_code']} bags at {cust['name']} ({cust['location']}). Routed to Priya Sharma under SOP-5.1.",
            ),
        )
        _append_sqlite_audit(
            cur,
            actor=driver_name,
            role="DRIVER",
            action="PROOF_ATTACHED",
            target_id=attached_to,
            summary=f"Created SOP-5.1 approval {attached_to} with visual proof for {cust['name']}",
            after_obj={"damaged_qty": dmg},
        )
        conn.commit()
    conn.close()
    return attached_to


def db_log_damaged_bags(
    *,
    cust: Dict[str, Any],
    damaged_bags: int,
    driver_name: str,
    notes: str,
    proof_data_url: Optional[str],
) -> str:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.tx_log_damaged_bags(
            customer_id=cust["customer_id"],
            damaged_bags=damaged_bags,
            driver_name=driver_name,
            notes=notes,
            proof_data_url=proof_data_url,
        )

    stored_img = proof_data_url
    if proof_data_url and proof_data_url.startswith("data:image/"):
        stored_img, _ = upload_proof_to_gcs(proof_data_url, cust["customer_id"])

    dmg = max(1, _safe_int(damaged_bags, 1))
    now = _now_iso()
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT approval_id, damaged_qty FROM approvals WHERE status = 'PENDING' AND customer_id = ? ORDER BY created_at DESC LIMIT 1",
        (cust["customer_id"],),
    ).fetchone()
    if existing:
        approval_id = existing["approval_id"]
        prev_dmg = _safe_int(existing["damaged_qty"], 0)
        new_dmg = max(prev_dmg, dmg)
        dmg_delta = max(0, new_dmg - prev_dmg)
        cur.execute(
            "UPDATE approvals SET damaged_qty = ?, summary = ?, proof_image = COALESCE(proof_image, ?) WHERE approval_id = ?",
            (new_dmg, f"{cust['name']} ({cust['pending_invoice_id']}): {notes}", stored_img, approval_id),
        )
        if dmg_delta > 0:
            cur.execute(
                "UPDATE inventory SET warehouse_stock = MAX(0, warehouse_stock - ?), damaged_quarantine = damaged_quarantine + ?, updated_at = ? WHERE sku_code = ?",
                (dmg_delta, dmg_delta, now, cust["sku_code"]),
            )
    else:
        approval_id = _short_id("APR")
        cur.execute(
            """
            INSERT INTO approvals (
                approval_id, created_at, driver_name, customer_id, customer_name,
                entry_id, exception_type, policy_ref, summary, discount_requested,
                damaged_qty, proof_image, status
            ) VALUES (?, ?, ?, ?, ?, NULL, 'DAMAGED_GOODS', 'SOP-5.1', ?, 0, ?, ?, 'PENDING')
            """,
            (approval_id, now, driver_name, cust["customer_id"], cust["name"], f"{cust['name']} ({cust['pending_invoice_id']}): {notes}", dmg, stored_img),
        )
        cur.execute(
            "UPDATE inventory SET warehouse_stock = MAX(0, warehouse_stock - ?), damaged_quarantine = damaged_quarantine + ?, updated_at = ? WHERE sku_code = ?",
            (dmg, dmg, now, cust["sku_code"]),
        )
        cur.execute(
            "INSERT INTO insights (created_at, route, category, severity, title, detail) VALUES (?, ?, 'DAMAGED_GOODS', 'HIGH', ?, ?)",
            (
                now,
                cust["route"],
                f"Damaged Bags Logged at {cust['name']} ({dmg} bags torn)",
                f"{dmg} torn {cust['sku_code']} bags logged at {cust['name']} ({cust['location']}). Escalated under SOP-5.1.",
            ),
        )

    _append_sqlite_audit(
        cur,
        actor=driver_name,
        role="DRIVER",
        action="DAMAGE_LOGGED",
        target_id=approval_id,
        summary=f"Logged {dmg} damaged bags at {cust['name']} (SOP-5.1)",
        after_obj={"damaged_bags": dmg, "approval_id": approval_id},
    )
    conn.commit()
    conn.close()
    return approval_id


def db_record_delivery(
    *,
    cust: Dict[str, Any],
    delivered: int,
    damaged: int,
    cash: int,
    discount: int,
    driver_name: str,
    notes: str,
    channel: str,
    proof_data_url: Optional[str],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.tx_record_delivery(
            customer_id=cust["customer_id"],
            delivered=delivered,
            damaged=damaged,
            cash=cash,
            discount=discount,
            driver_name=driver_name,
            notes=notes,
            channel=channel,
            proof_data_url=proof_data_url,
            idempotency_key=idempotency_key,
        )

    idem_key = idempotency_key or hashlib.sha256(
        f"{cust['customer_id']}|{delivered}|{damaged}|{cash}|{discount}|{channel}".encode("utf-8")
    ).hexdigest()[:24]

    stored_img = proof_data_url
    if proof_data_url and proof_data_url.startswith("data:image/"):
        stored_img, _ = upload_proof_to_gcs(proof_data_url, cust["customer_id"])

    conn = get_conn()
    cur = conn.cursor()
    idem_row = cur.execute("SELECT created_ts, result_json FROM idempotency_keys WHERE idem_key = ?", (idem_key,)).fetchone()
    if idem_row:
        age_sec = datetime.now(timezone.utc).timestamp() - float(idem_row["created_ts"] or 0)
        if age_sec < 12.0:
            cached = json.loads(idem_row["result_json"])
            cached["idempotent_replay"] = True
            conn.close()
            return cached

    needs_approval = discount > 200 or damaged > 0
    now = _now_iso()
    entry_id = _short_id("TALLY")
    tally_status = "PARTIAL_PENDING_APPROVAL" if needs_approval else "SYNCED_TALLY"

    unlinked_apr = cur.execute(
        """
        SELECT approval_id, damaged_qty, proof_image
        FROM approvals
        WHERE status = 'PENDING' AND customer_id = ? AND entry_id IS NULL AND exception_type = 'DAMAGED_GOODS'
        ORDER BY created_at DESC LIMIT 1
        """,
        (cust["customer_id"],),
    ).fetchone()
    already_quarantined = _safe_int(unlinked_apr["damaged_qty"], 0) if unlinked_apr else 0
    net_new_damaged = max(0, damaged - already_quarantined)

    inv_row = cur.execute("SELECT warehouse_stock FROM inventory WHERE sku_code = ?", (cust["sku_code"],)).fetchone()
    prev_stock = int(inv_row["warehouse_stock"]) if inv_row else 0

    cur.execute(
        """
        INSERT INTO ledger_entries (
            entry_id, timestamp, driver_name, customer_id, customer_name, invoice_id,
            sku_code, delivered_qty, damaged_qty, cash_received, discount_amount,
            channel, tally_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            now,
            driver_name,
            cust["customer_id"],
            cust["name"],
            cust["pending_invoice_id"],
            cust["sku_code"],
            delivered,
            damaged,
            cash,
            0 if needs_approval else discount,
            channel,
            tally_status,
            notes,
        ),
    )

    cur.execute(
        """
        UPDATE inventory
        SET warehouse_stock = MAX(0, warehouse_stock - ?),
            damaged_quarantine = damaged_quarantine + ?,
            updated_at = ?
        WHERE sku_code = ?
        """,
        (delivered + net_new_damaged, net_new_damaged, now, cust["sku_code"]),
    )

    applied_discount = 0 if needs_approval else discount
    prev_balance = int(cust["balance_due"])
    new_balance = max(0, prev_balance - cash - applied_discount)
    new_status = "PENDING_MANAGER_APPROVAL" if needs_approval else ("SETTLED" if new_balance == 0 else "PARTIAL_PAID")
    cur.execute(
        "UPDATE customers SET balance_due = ?, status = ? WHERE customer_id = ?",
        (new_balance, new_status, cust["customer_id"]),
    )

    approval_payload = None
    receipt_payload = None

    if needs_approval:
        reasons = []
        policy_refs = []
        if discount > 200:
            reasons.append(f"Special discount of Rs {discount} exceeds driver auto-limit of Rs 200")
            policy_refs.append("SOP-4.2")
        effective_damaged = max(damaged, already_quarantined)
        if effective_damaged > 0:
            reasons.append(f"{effective_damaged} damaged/torn bags moved to quarantine")
            policy_refs.append("SOP-5.1")

        policy_ref = " & ".join(policy_refs)
        summary = f"{cust['name']} ({cust['pending_invoice_id']}): " + "; ".join(reasons)
        exc_type = (
            "DISCOUNT_AND_DAMAGE"
            if (discount > 200 and effective_damaged > 0)
            else ("SPECIAL_DISCOUNT" if discount > 200 else "DAMAGED_GOODS")
        )

        if unlinked_apr:
            approval_id = unlinked_apr["approval_id"]
            cur.execute(
                """
                UPDATE approvals
                SET driver_name = ?, entry_id = ?, exception_type = ?, policy_ref = ?,
                    summary = ?, discount_requested = ?, damaged_qty = ?,
                    proof_image = COALESCE(proof_image, ?)
                WHERE approval_id = ?
                """,
                (
                    driver_name,
                    entry_id,
                    exc_type,
                    policy_ref,
                    summary,
                    discount,
                    effective_damaged,
                    stored_img,
                    approval_id,
                ),
            )
        else:
            approval_id = _short_id("APR")
            cur.execute(
                """
                INSERT INTO approvals (
                    approval_id, created_at, driver_name, customer_id, customer_name,
                    entry_id, exception_type, policy_ref, summary, discount_requested,
                    damaged_qty, proof_image, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    approval_id,
                    now,
                    driver_name,
                    cust["customer_id"],
                    cust["name"],
                    entry_id,
                    exc_type,
                    policy_ref,
                    summary,
                    discount,
                    effective_damaged,
                    stored_img,
                ),
            )
        approval_payload = {
            "approval_id": approval_id,
            "policy_ref": policy_ref,
            "summary": summary,
            "manager": "Priya Sharma (Area Manager)",
            "status": "PENDING",
        }
        if net_new_damaged > 0:
            cur.execute(
                "INSERT INTO insights (created_at, route, category, severity, title, detail) VALUES (?, ?, 'DAMAGED_GOODS', 'HIGH', ?, ?)",
                (
                    now,
                    cust["route"],
                    f"Recurring Damage Alert on {cust['route']} ({damaged} more bags torn)",
                    f"Driver {driver_name} reported {damaged} damaged {cust['sku_code']} bags at {cust['name']}. Pattern detected — recommend auditing Warehouse Loader Shift B.",
                ),
            )
    else:
        receipt_id = _short_id("RCPT")
        msg = (
            f"DeliverEx Official Receipt ({receipt_id})\n"
            f"Shop: {cust['name']} ({cust['pending_invoice_id']})\n"
            f"Delivered: {delivered} bags | Cash: Rs {cash:,} | Discount: Rs {discount:,}\n"
            f"Balance Due: Rs {new_balance:,} | Tally Ref: {entry_id}"
        )
        cur.execute(
            "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt_id,
                now,
                driver_name,
                cust["name"],
                cust["pending_invoice_id"],
                delivered,
                damaged,
                cash,
                discount,
                new_balance,
                channel,
                msg,
            ),
        )
        receipt_payload = {"receipt_id": receipt_id, "message": msg}

    result = {
        "success": True,
        "tally_entry_id": entry_id,
        "customer_id": cust["customer_id"],
        "customer_name": cust["name"],
        "invoice_id": cust["pending_invoice_id"],
        "delivered_bags": delivered,
        "damaged_bags": damaged,
        "cash_posted_inr": cash,
        "tally_status": tally_status,
        "remaining_balance_inr": new_balance,
        "needs_manager_approval": needs_approval,
        "approval": approval_payload,
        "receipt": receipt_payload,
    }

    _append_sqlite_audit(
        cur,
        actor=driver_name,
        role="DRIVER",
        action="DELIVERY_RECORDED",
        target_id=entry_id,
        summary=f"{cust['name']}: {delivered} ok, {damaged} dmg, Rs {cash} cash ({tally_status})",
        before_obj={"balance_due": prev_balance, "warehouse_stock": prev_stock},
        after_obj={"balance_due": new_balance, "tally_entry_id": entry_id, "status": tally_status},
    )
    cur.execute(
        """
        INSERT INTO idempotency_keys (idem_key, created_ts, result_json)
        VALUES (?, ?, ?)
        ON CONFLICT(idem_key) DO UPDATE SET created_ts = excluded.created_ts, result_json = excluded.result_json
        """,
        (idem_key, datetime.now(timezone.utc).timestamp(), json.dumps(result)),
    )
    conn.commit()
    conn.close()
    return result


def db_queue_handoff(
    *,
    customer_id: str,
    customer_name: str,
    driver_name: str,
    reason: str,
    proof_data_url: Optional[str],
) -> str:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.tx_queue_handoff(
            customer_id=customer_id,
            customer_name=customer_name,
            driver_name=driver_name,
            reason=reason,
            proof_data_url=proof_data_url,
        )

    stored_img = proof_data_url
    if proof_data_url and proof_data_url.startswith("data:image/"):
        stored_img, _ = upload_proof_to_gcs(proof_data_url, customer_id)

    now = _now_iso()
    approval_id = _short_id("HANDOFF")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO approvals (
            approval_id, created_at, driver_name, customer_id, customer_name,
            entry_id, exception_type, policy_ref, summary, discount_requested,
            damaged_qty, proof_image, status
        ) VALUES (?, ?, ?, ?, ?, NULL, 'LIVE_HANDOFF', 'SOP-6.0', ?, 0, 0, ?, 'PENDING')
        """,
        (approval_id, now, driver_name, customer_id, customer_name, reason, stored_img),
    )
    _append_sqlite_audit(
        cur,
        actor=driver_name,
        role="DRIVER",
        action="HANDOFF_REQUESTED",
        target_id=approval_id,
        summary=f"SOP-6.0 live handoff queued for {customer_name}: {reason}",
    )
    conn.commit()
    conn.close()
    return approval_id


def db_decide_approval(
    approval_id: str,
    decision: str,
    actor: str = "Priya Sharma (Area Manager)",
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    fs = _get_firestore_store()
    if fs is not None:
        return fs.tx_decide_approval(approval_id, decision, actor)

    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Approval {approval_id} not found")

    apr = dict(row)
    if apr["status"] != "PENDING":
        conn.close()
        raise ValueError(f"Approval {approval_id} is already {apr['status']}")

    now = _now_iso()
    cur.execute(
        "UPDATE approvals SET status = ?, decided_at = ? WHERE approval_id = ?",
        (decision, now, approval_id),
    )
    apr["status"] = decision
    apr["decided_at"] = now

    receipt_payload = None
    cust = cur.execute("SELECT * FROM customers WHERE customer_id = ?", (apr["customer_id"],)).fetchone()
    ledger = (
        cur.execute("SELECT * FROM ledger_entries WHERE entry_id = ?", (apr["entry_id"],)).fetchone()
        if apr["entry_id"]
        else None
    )

    if decision == "APPROVED" and cust and ledger:
        discount = int(apr["discount_requested"] or 0)
        new_balance = max(0, int(cust["balance_due"]) - discount)
        cur.execute(
            "UPDATE ledger_entries SET discount_amount = ?, tally_status = 'SYNCED_TALLY_APPROVED' WHERE entry_id = ?",
            (discount, apr["entry_id"]),
        )
        cur.execute(
            "UPDATE customers SET balance_due = ?, status = ? WHERE customer_id = ?",
            (new_balance, "SETTLED" if new_balance == 0 else "PARTIAL_PAID", cust["customer_id"]),
        )

        receipt_id = _short_id("RCPT")
        msg = (
            f"Raju Bhai Official Receipt ({receipt_id}) ✅\n"
            f"Shop: {cust['name']} | Invoice: {cust['pending_invoice_id']}\n"
            f"Delivered: {ledger['delivered_qty']} intact bags (Quarantined: {ledger['damaged_qty']})\n"
            f"Cash Received: Rs {ledger['cash_received']:,} | Approved Discount: Rs {discount:,}\n"
            f"Approved By: {actor}\n"
            f"Balance Remaining: Rs {new_balance:,} | Tally Ref: {apr['entry_id']}"
        )
        cur.execute(
            "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt_id,
                now,
                apr["driver_name"],
                cust["name"],
                cust["pending_invoice_id"],
                ledger["delivered_qty"],
                ledger["damaged_qty"],
                ledger["cash_received"],
                discount,
                new_balance,
                "OPS_RECEIPT",
                msg,
            ),
        )
        receipt_payload = {
            "receipt_id": receipt_id,
            "created_at": now,
            "driver_name": apr["driver_name"],
            "customer_name": cust["name"],
            "invoice_id": cust["pending_invoice_id"],
            "delivered_qty": int(ledger["delivered_qty"]),
            "damaged_qty": int(ledger["damaged_qty"]),
            "cash_received": int(ledger["cash_received"]),
            "discount_approved": int(discount),
            "balance_remaining": int(new_balance),
            "channel": "OPS_RECEIPT",
            "message_text": msg,
            "message": msg,
        }
    elif decision == "REJECTED" and cust and ledger:
        cur.execute(
            "UPDATE ledger_entries SET tally_status = 'DISCOUNT_REJECTED_BALANCE_OPEN' WHERE entry_id = ?",
            (apr["entry_id"],),
        )
        cur.execute(
            "UPDATE customers SET status = 'PARTIAL_BALANCE_OPEN' WHERE customer_id = ?",
            (cust["customer_id"],),
        )

    _append_sqlite_audit(
        cur,
        actor=actor,
        role="OWNER",
        action="APPROVAL_DECIDED",
        target_id=approval_id,
        summary=f"{actor} {decision} {approval_id} for {apr['customer_name']}",
        before_obj={"status": "PENDING"},
        after_obj={"status": decision, "receipt_id": receipt_payload["receipt_id"] if receipt_payload else None},
    )
    conn.commit()
    conn.close()
    return apr, receipt_payload
