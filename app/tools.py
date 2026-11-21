import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.database import _now_iso, add_whatsapp_message, find_customer, get_conn, get_full_state
from app.policies import lookup_policies

# Holds the latest multimodal camera/photo proof & active store context
LATEST_VISUAL_PROOF: Dict[str, Any] = {
    "data_url": None,
    "caption": None,
    "customer_name": "Krishna Hardware",
}


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


def set_latest_visual_proof(
    data_url: Optional[str],
    caption: str = "Field Camera Proof",
    customer_name: Optional[str] = None,
    damaged_bags: int = 2,
    auto_create_approval: bool = False,
    driver_name: str = "Raju Kumar",
) -> Dict[str, Any]:
    LATEST_VISUAL_PROOF["data_url"] = data_url
    LATEST_VISUAL_PROOF["caption"] = caption
    if customer_name:
        LATEST_VISUAL_PROOF["customer_name"] = customer_name

    resolved_name = customer_name or LATEST_VISUAL_PROOF.get("customer_name") or "Krishna Hardware"
    cust = find_customer(resolved_name) or find_customer("Krishna Hardware")
    attached_to = None

    if data_url and cust:
        conn = get_conn()
        cur = conn.cursor()
        # 1. Prefer an existing PENDING approval for THIS exact store
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
                (data_url, new_dmg, attached_to),
            )
            if dmg_delta > 0:
                cur.execute(
                    "UPDATE inventory SET warehouse_stock = MAX(0, warehouse_stock - ?), damaged_quarantine = damaged_quarantine + ?, updated_at = ? WHERE sku_code = ?",
                    (dmg_delta, dmg_delta, _now_iso(), cust["sku_code"]),
                )
            conn.commit()
        elif auto_create_approval:
            # 2. If user clicked Show Torn Bags BEFORE logging delivery, create an explicit store-tagged SOP-5.1 approval card!
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
                (attached_to, now, driver_name or "Raju Kumar", cust["customer_id"], cust["name"], summary, dmg, data_url),
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
            conn.commit()
        conn.close()

    return {
        "stored": bool(data_url),
        "attached_to_approval": attached_to,
        "customer_id": cust["customer_id"] if cust else None,
        "customer_name": cust["name"] if cust else resolved_name,
        "invoice_id": cust["pending_invoice_id"] if cust else None,
        "caption": caption,
    }


# Gemini Live API Function Declarations (JSON Schema format compatible with google-genai)
GEMINI_TOOL_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "function_declarations": [
            {
                "name": "lookup_customer_and_invoice",
                "description": (
                    "Look up a customer/shop by spoken name or ID (e.g., 'Krishna Hardware', 'Shri Ganesh Stores') "
                    "to retrieve their official customer_id, pending invoice, expected bags, SKU, and balance due."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Spoken shop or customer name, e.g. 'Krishna Hardware'",
                        }
                    },
                    "required": ["customer_name"],
                },
            },
            {
                "name": "check_company_policy",
                "description": (
                    "Retrieve official DeliverEx company SOP rules for spot discounts, damaged goods, "
                    "cash settlement, or human handoff before making a promise to the driver or customer."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "topic": {
                            "type": "STRING",
                            "description": "Topic keywords such as 'discount', 'damaged bags', 'cash', or 'handoff'",
                        }
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "record_delivery_and_update_ledger",
                "description": (
                    "Record a delivery in Tally/SAP Ledger and update Warehouse Inventory. "
                    "Automatically enforces SOP-4.2 (discounts > Rs 200 need Manager Priya approval) and "
                    "SOP-5.1 (damaged bags go to quarantine + Manager approval). "
                    "Call this once the driver states delivered bags, cash received, and any damage or discount."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Customer/shop name, e.g. 'Krishna Hardware'",
                        },
                        "delivered_bags": {
                            "type": "INTEGER",
                            "description": "Number of intact bags delivered to the customer",
                        },
                        "damaged_bags": {
                            "type": "INTEGER",
                            "description": "Number of damaged/torn bags (0 if none)",
                        },
                        "cash_received": {
                            "type": "INTEGER",
                            "description": "Cash collected in INR (e.g. 15000)",
                        },
                        "discount_requested": {
                            "type": "INTEGER",
                            "description": "Extra discount requested in INR (0 if none)",
                        },
                        "driver_name": {
                            "type": "STRING",
                            "description": "Field driver name, default 'Raju Kumar'",
                        },
                        "notes": {
                            "type": "STRING",
                            "description": "Brief summary of delivery details or customer request",
                        },
                    },
                    "required": ["customer_name", "delivered_bags", "cash_received"],
                },
            },
            {
                "name": "log_damaged_bags_report",
                "description": (
                    "Log torn/damaged bags for a SPECIFIC store immediately (even before cash settlement is finalized). "
                    "Moves damaged bags to quarantine, attaches any camera proof, and notifies Area Manager Priya under SOP-5.1. "
                    "ALWAYS specify the exact store/customer_name."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Exact store/shop name where torn bags occurred, e.g. 'Krishna Hardware', 'Shri Ganesh Stores', or 'Murugan Builders'",
                        },
                        "damaged_bags": {
                            "type": "INTEGER",
                            "description": "Exact number of torn/damaged bags",
                        },
                        "notes": {
                            "type": "STRING",
                            "description": "Details of the damage",
                        },
                    },
                    "required": ["customer_name", "damaged_bags"],
                },
            },
            {
                "name": "request_human_handoff",
                "description": (
                    "Escalate the live interaction to Area Manager Priya Sharma when there is a customer "
                    "dispute, refusal to pay, or request to speak to a human manager."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {"type": "STRING", "description": "Customer/shop name"},
                        "reason": {"type": "STRING", "description": "Why human manager judgment is needed"},
                    },
                    "required": ["customer_name", "reason"],
                },
            },
            {
                "name": "update_frontline_guidance",
                "description": (
                    "Update the live Frontline Ops HUD with detected intent, code-switched language, "
                    "customer sentiment, and actionable next-step coaching for the field driver."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "intent": {"type": "STRING", "description": "Detected intent, e.g. DAMAGE_AND_DISCOUNT_NEGOTIATION"},
                        "language": {"type": "STRING", "description": "Detected language/code-switch, e.g. Hinglish (HI+EN) or Tanglish (TA+EN)"},
                        "sentiment": {"type": "STRING", "description": "One of: CALM, CONCERNED, FRUSTRATED, POSITIVE, RESOLVED"},
                        "coach_tip": {"type": "STRING", "description": "Concise actionable next step for the frontline driver"},
                        "suggested_phrase": {"type": "STRING", "description": "Recommended polite phrase for the driver to tell the shop owner"},
                    },
                    "required": ["intent", "language", "sentiment", "coach_tip"],
                },
            },
        ]
    }
]


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:5].upper()}"


def execute_tool(
    name: str, args: Dict[str, Any], channel: str = "GEMINI_LIVE_VOICE"
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Executes a backend business tool against SQLite Tally/SAP ERP.
    Returns (tool_result_for_gemini, ui_event_metadata).
    """
    t0 = time.perf_counter()
    args = args or {}

    if name == "lookup_customer_and_invoice":
        cust = find_customer(args.get("customer_name", ""))
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if not cust:
            return (
                {"found": False, "message": f"No customer matched '{args.get('customer_name')}'."},
                {"tool": name, "elapsed_ms": elapsed_ms, "status": "NOT_FOUND"},
            )
        LATEST_VISUAL_PROOF["customer_name"] = cust["name"]
        return (
            {
                "found": True,
                "customer_id": cust["customer_id"],
                "name": cust["name"],
                "location": cust["location"],
                "route": cust["route"],
                "pending_invoice_id": cust["pending_invoice_id"],
                "invoice_amount_inr": cust["invoice_amount"],
                "expected_bags": cust["expected_bags"],
                "sku_code": cust["sku_code"],
                "balance_due_inr": cust["balance_due"],
            },
            {"tool": name, "elapsed_ms": elapsed_ms, "status": "OK", "customer": cust},
        )

    if name == "check_company_policy":
        topic = args.get("topic", "discount")
        policies = lookup_policies(topic)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return (
            {"matched_policies": policies},
            {"tool": name, "elapsed_ms": elapsed_ms, "status": "OK", "policies": policies},
        )

    if name == "log_damaged_bags_report":
        cust = find_customer(args.get("customer_name") or LATEST_VISUAL_PROOF.get("customer_name") or "")
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if not cust:
            return (
                {"success": False, "error": "Store name missing or not found. Ask the driver which shop had the torn bags."},
                {"tool": name, "elapsed_ms": elapsed_ms, "status": "NEED_STORE_NAME"},
            )
        LATEST_VISUAL_PROOF["customer_name"] = cust["name"]
        dmg = max(1, _safe_int(args.get("damaged_bags", 1), 1))
        driver = args.get("driver_name") or "Raju Kumar"
        notes = args.get("notes") or f"{dmg} torn/damaged bags reported at {cust['name']}"
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
                (new_dmg, f"{cust['name']} ({cust['pending_invoice_id']}): {notes}", LATEST_VISUAL_PROOF.get("data_url"), approval_id),
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
                (
                    approval_id,
                    now,
                    driver,
                    cust["customer_id"],
                    cust["name"],
                    f"{cust['name']} ({cust['pending_invoice_id']}): {notes}",
                    dmg,
                    LATEST_VISUAL_PROOF.get("data_url"),
                ),
            )
            cur.execute(
                "UPDATE inventory SET warehouse_stock = MAX(0, warehouse_stock - ?), damaged_quarantine = damaged_quarantine + ?, updated_at = ? WHERE sku_code = ?",
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
                    f"Damaged Bags Logged at {cust['name']} ({dmg} bags torn)",
                    f"{dmg} torn {cust['sku_code']} bags logged at {cust['name']} ({cust['location']}). Escalated under SOP-5.1.",
                ),
            )
        conn.commit()
        conn.close()
        result = {
            "success": True,
            "approval_id": approval_id,
            "customer_id": cust["customer_id"],
            "customer_name": cust["name"],
            "invoice_id": cust["pending_invoice_id"],
            "damaged_bags": dmg,
            "policy_ref": "SOP-5.1",
            "status": "LOGGED_AND_SENT_TO_PRIYA",
        }
        return result, {"tool": name, "elapsed_ms": elapsed_ms, "status": "ESCALATED", "result": result}

    if name == "record_delivery_and_update_ledger":
        cust = find_customer(args.get("customer_name") or LATEST_VISUAL_PROOF.get("customer_name") or "Krishna Hardware")
        if not cust:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            return (
                {"success": False, "error": "Customer not found in ERP. Please confirm shop name."},
                {"tool": name, "elapsed_ms": elapsed_ms, "status": "ERROR"},
            )
        LATEST_VISUAL_PROOF["customer_name"] = cust["name"]

        delivered = max(0, _safe_int(args.get("delivered_bags"), cust["expected_bags"]))
        damaged = max(0, _safe_int(args.get("damaged_bags"), 0))
        cash = max(0, _safe_int(args.get("cash_received"), 0))
        discount = max(0, _safe_int(args.get("discount_requested"), 0))
        driver = args.get("driver_name") or "Raju Kumar"
        notes = args.get("notes") or f"{delivered} bags delivered, Rs {cash} cash received"

        needs_approval = discount > 200 or damaged > 0
        now = _now_iso()
        entry_id = _short_id("TALLY")
        tally_status = "PARTIAL_PENDING_APPROVAL" if needs_approval else "SYNCED_TALLY"

        conn = get_conn()
        cur = conn.cursor()

        # Check if an unlinked visual-damage PENDING approval already exists for this customer (avoid double-counting quarantine)
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

        # 1. Insert Ledger entry
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
                driver,
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

        # 2. Update Warehouse Inventory (without double-subtracting pre-quarantined damaged bags)
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

        # 3. Update Customer Balance
        applied_discount = 0 if needs_approval else discount
        new_balance = max(0, cust["balance_due"] - cash - applied_discount)
        new_status = "PENDING_MANAGER_APPROVAL" if needs_approval else ("SETTLED" if new_balance == 0 else "PARTIAL_PAID")
        cur.execute(
            "UPDATE customers SET balance_due = ?, status = ? WHERE customer_id = ?",
            (new_balance, new_status, cust["customer_id"]),
        )

        approval_payload = None
        receipt_payload = None

        # 4. Route exception to Priya OR issue immediate receipt
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
                        driver,
                        entry_id,
                        exc_type,
                        policy_ref,
                        summary,
                        discount,
                        effective_damaged,
                        LATEST_VISUAL_PROOF.get("data_url"),
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
                        driver,
                        cust["customer_id"],
                        cust["name"],
                        entry_id,
                        exc_type,
                        policy_ref,
                        summary,
                        discount,
                        effective_damaged,
                        LATEST_VISUAL_PROOF.get("data_url"),
                    ),
                )
            approval_payload = {
                "approval_id": approval_id,
                "policy_ref": policy_ref,
                "summary": summary,
                "manager": "Priya Sharma (Area Manager)",
                "status": "PENDING",
            }

            # Add Field Intelligence insight only if net new damaged bags occurred
            if net_new_damaged > 0:
                cur.execute(
                    """
                    INSERT INTO insights (created_at, route, category, severity, title, detail)
                    VALUES (?, ?, 'DAMAGED_GOODS', 'HIGH', ?, ?)
                    """,
                    (
                        now,
                        cust["route"],
                        f"Recurring Damage Alert on {cust['route']} ({damaged} more bags torn)",
                        f"Driver {driver} reported {damaged} damaged {cust['sku_code']} bags at {cust['name']}. "
                        f"Pattern detected (3rd incident this week) — recommend auditing Warehouse Loader Shift B.",
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
                """
                INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    now,
                    driver,
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

        conn.commit()
        conn.close()

        if receipt_payload and channel not in {"WHATSAPP_VOICE_NOTE", "WHATSAPP_CHAT"}:
            add_whatsapp_message(
                sender="bot",
                body=receipt_payload["message"],
                msg_type="receipt",
                driver_name="DeliverEx Ops",
                metadata={
                    "receipt_id": receipt_payload["receipt_id"],
                    "customer_name": cust["name"],
                    "tally_entry_id": entry_id,
                    "channel": channel,
                },
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

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
        return (
            result,
            {
                "tool": name,
                "elapsed_ms": elapsed_ms,
                "status": "ESCALATED" if needs_approval else "SYNCED",
                "result": result,
            },
        )

    if name == "request_human_handoff":
        cust = find_customer(args.get("customer_name", "Krishna Hardware"))
        cust_id = cust["customer_id"] if cust else "CUST-UNKNOWN"
        cust_name = cust["name"] if cust else args.get("customer_name", "Unknown Shop")
        reason = args.get("reason", "Driver requested live manager support")
        driver = args.get("driver_name") or "Raju Kumar"
        now = _now_iso()
        approval_id = _short_id("HANDOFF")

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO approvals (
                approval_id, created_at, driver_name, customer_id, customer_name,
                entry_id, exception_type, policy_ref, summary, discount_requested,
                damaged_qty, proof_image, status
            ) VALUES (?, ?, ?, ?, ?, NULL, 'LIVE_HANDOFF', 'SOP-6.0', ?, 0, 0, ?, 'PENDING')
            """,
            (approval_id, now, driver, cust_id, cust_name, reason, LATEST_VISUAL_PROOF.get("data_url")),
        )
        conn.commit()
        conn.close()

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        result = {
            "handoff_id": approval_id,
            "assigned_to": "Priya Sharma (Area Manager)",
            "status": "QUEUED_FOR_LIVE_TAKEOVER",
            "message": "Manager Priya has been notified with full transcript and context.",
        }
        return result, {"tool": name, "elapsed_ms": elapsed_ms, "status": "HANDOFF", "result": result}

    if name == "update_frontline_guidance":
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        guidance = {
            "intent": args.get("intent", "DELIVERY_UPDATE"),
            "language": args.get("language", "Hinglish (HI+EN)"),
            "sentiment": args.get("sentiment", "CALM"),
            "coach_tip": args.get("coach_tip", "Confirm intact bags and cash amount clearly."),
            "suggested_phrase": args.get("suggested_phrase", ""),
        }
        return {"updated": True, "guidance": guidance}, {
            "tool": name,
            "elapsed_ms": elapsed_ms,
            "status": "COACHED",
            "guidance": guidance,
        }

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {"error": f"Unknown tool {name}"}, {"tool": name, "elapsed_ms": elapsed_ms, "status": "ERROR"}


def decide_approval(approval_id: str, decision: str) -> Dict[str, Any]:
    """
    Processes Priya's 1-tap decision: APPROVED, REJECTED, or TAKE_OVER.
    Updates Tally/SAP ledger, customer balance, and creates closed-loop WhatsApp receipt.
    """
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED", "TAKE_OVER"}:
        raise ValueError("Decision must be APPROVED, REJECTED, or TAKE_OVER")

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
            f"DeliverEx Official Receipt ({receipt_id}) ✅\n"
            f"Shop: {cust['name']} | Invoice: {cust['pending_invoice_id']}\n"
            f"Delivered: {ledger['delivered_qty']} intact bags (Quarantined: {ledger['damaged_qty']})\n"
            f"Cash Received: Rs {ledger['cash_received']:,} | Approved Discount: Rs {discount:,}\n"
            f"Approved By: Priya Sharma (Area Manager)\n"
            f"Balance Remaining: Rs {new_balance:,} | Tally Ref: {apr['entry_id']}"
        )
        cur.execute(
            """
            INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
                "WHATSAPP_RECEIPT",
                msg,
            ),
        )
        receipt_payload = {"receipt_id": receipt_id, "message": msg, "balance_remaining": new_balance}
    elif decision == "REJECTED" and cust and ledger:
        cur.execute(
            "UPDATE ledger_entries SET tally_status = 'DISCOUNT_REJECTED_BALANCE_OPEN' WHERE entry_id = ?",
            (apr["entry_id"],),
        )
        cur.execute(
            "UPDATE customers SET status = 'PARTIAL_BALANCE_OPEN' WHERE customer_id = ?",
            (cust["customer_id"],),
        )

    conn.commit()
    conn.close()

    if decision == "APPROVED" and receipt_payload:
        add_whatsapp_message(
            sender="bot",
            body=receipt_payload["message"],
            msg_type="receipt",
            driver_name="Priya Sharma (Manager)",
            metadata={
                "receipt_id": receipt_payload["receipt_id"],
                "approval_id": approval_id,
                "customer_name": apr["customer_name"],
                "decision": decision,
            },
        )
    elif decision == "APPROVED":
        add_whatsapp_message(
            sender="bot",
            body=(
                f"✅ Manager Priya Sharma APPROVED exception {approval_id} for {apr['customer_name']} "
                f"({apr['policy_ref']}). Tally/SAP & quarantine records updated!"
            ),
            msg_type="text",
            driver_name="Priya Sharma (Manager)",
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )
    elif decision == "REJECTED":
        add_whatsapp_message(
            sender="bot",
            body=(
                f"❌ Manager Priya Sharma REJECTED extra discount (Rs {apr['discount_requested']}) for "
                f"{apr['customer_name']}. Remaining balance stays open on customer credit ledger."
            ),
            msg_type="text",
            driver_name="Priya Sharma (Manager)",
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )
    elif decision == "TAKE_OVER":
        add_whatsapp_message(
            sender="manager",
            body=(
                f"📞 Priya Sharma (Area Manager): Raju, main abhi {apr['customer_name']} ke customer se "
                f"direct call/chat takeover kar rahi hoon ({approval_id})."
            ),
            msg_type="text",
            driver_name="Priya Sharma (Manager)",
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )

    return {
        "approval_id": approval_id,
        "decision": decision,
        "approval": apr,
        "receipt": receipt_payload,
        "state": get_full_state(),
    }
