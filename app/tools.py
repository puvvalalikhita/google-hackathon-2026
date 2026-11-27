import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.database import (
    add_whatsapp_message,
    db_attach_visual_proof,
    db_decide_approval,
    db_log_damaged_bags,
    db_queue_handoff,
    db_record_delivery,
    find_customer,
    get_full_state,
)
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
        attached_to = db_attach_visual_proof(
            cust=cust,
            data_url=data_url,
            damaged_bags=damaged_bags,
            auto_create_approval=auto_create_approval,
            driver_name=driver_name,
        )

    return {
        "stored": bool(data_url),
        "attached_to_approval": attached_to,
        "customer_id": cust["customer_id"] if cust else None,
        "customer_name": cust["name"] if cust else resolved_name,
        "invoice_id": cust["pending_invoice_id"] if cust else None,
        "caption": caption,
    }


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
                        "customer_name": {"type": "STRING", "description": "Customer/shop name, e.g. 'Krishna Hardware'"},
                        "delivered_bags": {"type": "INTEGER", "description": "Number of intact bags delivered to the customer"},
                        "damaged_bags": {"type": "INTEGER", "description": "Number of damaged/torn bags (0 if none)"},
                        "cash_received": {"type": "INTEGER", "description": "Cash collected in INR (e.g. 15000)"},
                        "discount_requested": {"type": "INTEGER", "description": "Extra discount requested in INR (0 if none)"},
                        "driver_name": {"type": "STRING", "description": "Field driver name, default 'Raju Kumar'"},
                        "notes": {"type": "STRING", "description": "Brief summary of delivery details or customer request"},
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
                        "customer_name": {"type": "STRING", "description": "Exact store/shop name where torn bags occurred"},
                        "damaged_bags": {"type": "INTEGER", "description": "Exact number of torn/damaged bags"},
                        "notes": {"type": "STRING", "description": "Details of the damage"},
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
                        "intent": {"type": "STRING", "description": "Detected intent"},
                        "language": {"type": "STRING", "description": "Detected language/code-switch"},
                        "sentiment": {"type": "STRING", "description": "One of: CALM, CONCERNED, FRUSTRATED, POSITIVE, RESOLVED"},
                        "coach_tip": {"type": "STRING", "description": "Concise actionable next step for the frontline driver"},
                        "suggested_phrase": {"type": "STRING", "description": "Recommended polite phrase for the driver"},
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
    Executes a backend business tool against Firestore/GCS or SQLite Tally/SAP ERP.
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
        approval_id = db_log_damaged_bags(
            cust=cust,
            damaged_bags=dmg,
            driver_name=driver,
            notes=notes,
            proof_data_url=LATEST_VISUAL_PROOF.get("data_url"),
        )
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

        result = db_record_delivery(
            cust=cust,
            delivered=delivered,
            damaged=damaged,
            cash=cash,
            discount=discount,
            driver_name=driver,
            notes=notes,
            channel=channel,
            proof_data_url=LATEST_VISUAL_PROOF.get("data_url"),
            idempotency_key=args.get("idempotency_key"),
        )
        receipt_payload = result.get("receipt")
        if receipt_payload and not result.get("idempotent_replay") and channel not in {"WHATSAPP_VOICE_NOTE", "WHATSAPP_CHAT"}:
            add_whatsapp_message(
                sender="bot",
                body=receipt_payload["message"],
                msg_type="receipt",
                driver_name="DeliverEx Ops",
                metadata={
                    "receipt_id": receipt_payload["receipt_id"],
                    "customer_name": cust["name"],
                    "tally_entry_id": result["tally_entry_id"],
                    "channel": channel,
                },
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        needs_approval = bool(result.get("needs_manager_approval"))
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
        approval_id = db_queue_handoff(
            customer_id=cust_id,
            customer_name=cust_name,
            driver_name=driver,
            reason=reason,
            proof_data_url=LATEST_VISUAL_PROOF.get("data_url"),
        )
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


def decide_approval(approval_id: str, decision: str, actor: str = "Priya Sharma (Area Manager)") -> Dict[str, Any]:
    """
    Processes Priya's 1-tap decision: APPROVED, REJECTED, or TAKE_OVER.
    Updates Firestore/SQLite ledger, customer balance, audit chain, and creates WhatsApp receipt.
    """
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED", "TAKE_OVER"}:
        raise ValueError("Decision must be APPROVED, REJECTED, or TAKE_OVER")

    apr, receipt_payload = db_decide_approval(approval_id, decision, actor=actor)

    if decision == "APPROVED" and receipt_payload:
        add_whatsapp_message(
            sender="bot",
            body=receipt_payload["message"],
            msg_type="receipt",
            driver_name=actor,
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
                f"✅ Manager {actor} APPROVED exception {approval_id} for {apr['customer_name']} "
                f"({apr['policy_ref']}). Tally/SAP & quarantine records updated!"
            ),
            msg_type="text",
            driver_name=actor,
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )
    elif decision == "REJECTED":
        add_whatsapp_message(
            sender="bot",
            body=(
                f"❌ Manager {actor} REJECTED extra discount (Rs {apr['discount_requested']}) for "
                f"{apr['customer_name']}. Remaining balance stays open on customer credit ledger."
            ),
            msg_type="text",
            driver_name=actor,
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )
    elif decision == "TAKE_OVER":
        add_whatsapp_message(
            sender="manager",
            body=(
                f"📞 {actor}: Raju, main abhi {apr['customer_name']} ke customer se "
                f"direct call/chat takeover kar rahi hoon ({approval_id})."
            ),
            msg_type="text",
            driver_name=actor,
            metadata={"approval_id": approval_id, "customer_name": apr["customer_name"], "decision": decision},
        )

    return {
        "approval_id": approval_id,
        "decision": decision,
        "approval": apr,
        "receipt": receipt_payload,
        "state": get_full_state(),
    }
