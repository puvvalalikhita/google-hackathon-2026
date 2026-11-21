"""End-to-end async & WebSocket verification for DeliverEx Live v2 (Backend Workflows + Go-Live Readiness)."""
import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from fastapi.testclient import TestClient

from app.main import app


async def run_async_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", verify=False) as client:
        # 1. Reset DB cleanly
        r = await client.post("/api/reset")
        assert r.status_code == 200, r.text
        print("[OK] POST /api/reset")

        # 2. Root UI, Health & Go-Live Compatibility Check
        r = await client.get("/")
        assert r.status_code == 200 and "DeliverEx Live" in r.text
        health = (await client.get("/api/health")).json()
        assert health["status"] == "ok" and health["database_ok"] is True
        go_live = (await client.get("/api/go-live-check")).json()
        assert go_live["ready_for_working_model"] is True and len(go_live["checks"]) >= 5
        print(
            f"[OK] GET / & /api/health & /api/go-live-check -> "
            f"auth={health['auth_mode']}, score={go_live['score_pct']}%"
        )

        # 3. Hinglish Customer Lookup (Old Delhi)
        r = await client.post(
            "/api/demo/tool",
            json={"name": "lookup_customer_and_invoice", "args": {"customer_name": "Krishna Hardware"}},
        )
        assert r.status_code == 200 and r.json()["result"]["customer_id"] == "CUST-104"
        print("[OK] lookup_customer_and_invoice -> CUST-104 (Krishna Hardware)")

        # 4. Frontline Coach HUD update tool
        r = await client.post(
            "/api/demo/tool",
            json={
                "name": "update_frontline_guidance",
                "args": {
                    "intent": "DAMAGE_CLAIM",
                    "language": "Hinglish (HI+EN)",
                    "sentiment": "CONCERNED",
                    "coach_tip": "Capture camera proof of 2 torn bags for Priya Ma'am.",
                },
            },
        )
        assert r.status_code == 200 and r.json()["result"]["updated"] is True
        print("[OK] update_frontline_guidance -> Frontline Coach HUD")

        # 5. Grounded Company Policy lookup
        r = await client.post(
            "/api/demo/tool",
            json={"name": "check_company_policy", "args": {"topic": "discount damaged bags"}},
        )
        pol_ids = [p["id"] for p in r.json()["result"]["matched_policies"]]
        assert "SOP-4.2" in pol_ids and "SOP-5.1" in pol_ids
        print(f"[OK] check_company_policy -> {pol_ids}")

        # 6. Pre-delivery visual proof + ledger merge (must NOT double-count quarantine or create 2 cards!)
        r = await client.post(
            "/api/proof-photo",
            json={
                "data_url": "data:image/jpeg;base64,TESTPROOF_PRE",
                "caption": "2 Torn Bags",
                "customer_name": "Krishna Hardware",
                "damaged_bags": 2,
                "auto_create_approval": True,
            },
        )
        assert r.status_code == 200
        pre_apr_id = r.json()["proof"]["attached_to_approval"]
        assert pre_apr_id is not None

        r = await client.post(
            "/api/demo/tool",
            json={
                "name": "record_delivery_and_update_ledger",
                "args": {
                    "customer_name": "Krishna Hardware",
                    "delivered_bags": 18,
                    "damaged_bags": 2,
                    "cash_received": 15000,
                    "discount_requested": 500,
                    "driver_name": "Raju Kumar",
                },
            },
        )
        led = r.json()["result"]
        assert led["success"] is True and led["needs_manager_approval"] is True
        approval_id = led["approval"]["approval_id"]
        assert approval_id == pre_apr_id, "Expected visual proof approval to merge cleanly with delivery exception"
        cem_inv = [i for i in r.json()["state"]["inventory"] if i["sku_code"] == "SKU-CEM-50"][0]
        assert cem_inv["damaged_quarantine"] == 6, f"Expected 4+2=6 quarantine bags, got {cem_inv['damaged_quarantine']}"
        print(f"[OK] Visual proof + ledger merge -> {led['tally_entry_id']} + {approval_id} (no double quarantine)")

        # 7. Priya's 1-Tap Approval -> settles Tally/SAP + issues WhatsApp receipt + idempotency check
        r = await client.post(f"/api/approvals/{approval_id}/decide", json={"decision": "APPROVED"})
        apr_res = r.json()
        assert apr_res["decision"] == "APPROVED" and apr_res["receipt"]["balance_remaining"] == 0
        r_dup = await client.post(f"/api/approvals/{approval_id}/decide", json={"decision": "APPROVED"})
        assert r_dup.status_code == 400
        print(f"[OK] Priya 1-Tap APPROVED + Idempotency -> Receipt {apr_res['receipt']['receipt_id']} (Balance Rs 0)")

        # 8. Backend Guided Workflows (Steps 1, 2, 3, 4)
        await client.post("/api/reset")
        g1 = (await client.post("/api/agent/guided/1")).json()
        assert g1["customer_match"]["customer_id"] == "CUST-104"
        g2 = (await client.post("/api/agent/guided/2")).json()
        assert g2["is_barge_in"] is True and g2["result"]["needs_manager_approval"] is True
        g3 = (await client.post("/api/agent/guided/3")).json()
        assert g3["intent"] == "ESCALATE" and "handoff_id" in g3["result"]
        g4 = (await client.post("/api/agent/guided/4")).json()
        assert g4["result"]["needs_manager_approval"] is False and g4["result"]["customer_id"] == "CUST-115"
        print("[OK] Backend Guided Workflows 1-4 (Hinglish, Barge-In, Escalate, Tanglish)")

        # 9. Free-form Backend Agent Turn
        t_res = (
            await client.post(
                "/api/agent/turn",
                json={"text": "Bharat Traders ka kitna balance baki hai?", "active_store": "Bharat Traders"},
            )
        ).json()
        assert t_res["intent"] == "LOOKUP_CUSTOMER" and t_res["customer_match"]["customer_id"] == "CUST-112"
        print("[OK] POST /api/agent/turn -> Bharat Traders lookup")

        # 10. WhatsApp Voice Note & Webhook Verification + HMAC Signature Security
        r = await client.post(
            "/api/whatsapp/voice-note",
            data={"text": "Shri Ganesh Stores 30 bags delivered, 22000 cash received", "driver_name": "Raju Kumar"},
        )
        assert r.status_code == 200 and r.json()["erp_result"]["success"] is True
        print(f"[OK] POST /api/whatsapp/voice-note -> {r.json()['erp_result']['tally_entry_id']}")

        r = await client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "deliverex_hackathon_verify_2026",
                "hub.challenge": "CHALLENGE_OK_123",
            },
        )
        assert r.status_code == 200 and r.text == "CHALLENGE_OK_123"

        # Test HMAC verification when WHATSAPP_APP_SECRET is configured
        prev_secret = os.environ.get("WHATSAPP_APP_SECRET")
        os.environ["WHATSAPP_APP_SECRET"] = "test_app_secret_xyz"
        try:
            body_bytes = json.dumps({
                "entry": [{
                    "changes": [{
                        "value": {
                            "contacts": [{"profile": {"name": "Raju Kumar"}}],
                            "messages": [{"from": "919811000001", "type": "text", "text": {"body": "Krishna Hardware ka balance kitna hai?"}}],
                        }
                    }]
                }]
            }).encode("utf-8")
            bad = await client.post("/webhook/whatsapp", content=body_bytes)
            assert bad.status_code == 403
            sig = "sha256=" + hmac.new(b"test_app_secret_xyz", body_bytes, hashlib.sha256).hexdigest()
            good = await client.post("/webhook/whatsapp", content=body_bytes, headers={"X-Hub-Signature-256": sig})
            assert good.status_code == 200 and good.json()["processed_count"] == 1
        finally:
            if prev_secret is None:
                os.environ.pop("WHATSAPP_APP_SECRET", None)
            else:
                os.environ["WHATSAPP_APP_SECRET"] = prev_secret
        print("[OK] GET/POST /webhook/whatsapp verification + HMAC-SHA256 signature enforcement")

        # 11. Reset DB clean
        await client.post("/api/reset")


def run_websocket_check() -> None:
    prev_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = ""
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live-call") as ws:
                erp_msg = ws.receive_json()
                assert erp_msg["type"] == "erp_state"
                status_msg = ws.receive_json()
                assert status_msg["type"] == "status" and status_msg["workflow_ready"] is True

                ws.send_json({"type": "ping"})
                assert ws.receive_json()["type"] == "pong"

                ws.send_json({"type": "guided_step", "step": 2})
                seen_types = []
                for _ in range(15):
                    ev = ws.receive_json()
                    seen_types.append(ev["type"])
                    if ev["type"] == "turn_complete":
                        break
                assert "interrupted" in seen_types and "workflow_reply" in seen_types and "turn_complete" in seen_types
                print("[OK] WS /ws/live-call -> ping/pong + backend guided_step workflow + barge-in")
            client.post("/api/reset")
    finally:
        if prev_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = prev_key


if __name__ == "__main__":
    asyncio.run(run_async_checks())
    run_websocket_check()
    print("\nALL DELIVEREX LIVE BACKEND WORKFLOW & GO-LIVE CHECKS PASSED!")
