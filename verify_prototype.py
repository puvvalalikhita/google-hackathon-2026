"""End-to-end async verification for DeliverEx Live v2 (Multimodal Vision + Frontline Coach + Hinglish/Tanglish + ERP + WhatsApp)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from app.main import app


async def run_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", verify=False) as client:
        # 1. Reset DB cleanly
        r = await client.post("/api/reset")
        assert r.status_code == 200, r.text
        print("[OK] POST /api/reset")

        # 2. Root UI & Health
        r = await client.get("/")
        assert r.status_code == 200 and "DeliverEx Live" in r.text
        health = (await client.get("/api/health")).json()
        assert health["status"] == "ok"
        print(f"[OK] GET / & /api/health -> gemini_configured={health['gemini_configured']}")

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

        # 6. Record delivery with exception (18 intact, 2 damaged, Rs 15,000 cash, Rs 500 discount)
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
        print(f"[OK] record_delivery_and_update_ledger -> {led['tally_entry_id']} + Approval {approval_id}")

        # 7. Attach Multimodal Vision Proof Photo -> auto-attaches to Priya's pending approval card!
        r = await client.post(
            "/api/proof-photo",
            json={"data_url": "data:image/jpeg;base64,TESTPROOF", "caption": "2 Torn Bags"},
        )
        assert r.status_code == 200 and r.json()["proof"]["attached_to_approval"] == approval_id
        print(f"[OK] POST /api/proof-photo -> attached visual proof to {approval_id}")

        # 8. Priya's 1-Tap Approval -> settles Tally/SAP + issues WhatsApp receipt
        r = await client.post(f"/api/approvals/{approval_id}/decide", json={"decision": "APPROVED"})
        apr_res = r.json()
        assert apr_res["decision"] == "APPROVED" and apr_res["receipt"]["balance_remaining"] == 0
        print(f"[OK] Priya 1-Tap APPROVED -> Receipt {apr_res['receipt']['receipt_id']} (Balance Rs 0)")

        # 9. Pan-India Tanglish (Chennai) settlement via Murugan Builders
        r = await client.post(
            "/api/demo/tool",
            json={
                "name": "record_delivery_and_update_ledger",
                "args": {
                    "customer_name": "Murugan Builders",
                    "delivered_bags": 25,
                    "damaged_bags": 0,
                    "cash_received": 18400,
                    "discount_requested": 0,
                    "driver_name": "Karthik",
                },
            },
        )
        m_res = r.json()["result"]
        assert m_res["success"] is True and m_res["needs_manager_approval"] is False
        print(f"[OK] Tanglish Chennai settlement -> {m_res['tally_entry_id']} (Auto-Settled)")

        # 10. WhatsApp Voice Note endpoint & Meta Webhook Verification
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
        print("[OK] GET /webhook/whatsapp verification challenge")

        # 11. Reset DB clean for demo
        await client.post("/api/reset")
        print("\nALL 11 DELIVEREX LIVE V2 CHECKS PASSED!")


if __name__ == "__main__":
    asyncio.run(run_checks())
