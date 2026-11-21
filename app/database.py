import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "deliverex.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force_reset: bool = False) -> None:
    if force_reset and DB_PATH.exists():
        DB_PATH.unlink()

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

    conn.commit()
    conn.close()


def get_full_state() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
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
    }
    conn.close()
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
