import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.database import get_full_state, init_db
from app.gemini_live import ACTIVE_SESSIONS, LiveBridgeSession
from app.policies import COMPANY_POLICIES
from app.tools import decide_approval, execute_tool, set_latest_visual_proof
from app.whatsapp import process_whatsapp_voice_note, send_meta_whatsapp_message

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(
    title="DeliverEx Live — Real-Time Gemini Voice & WhatsApp Field Ops",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db(force_reset=False)

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ApprovalDecisionBody(BaseModel):
    decision: str


class DemoToolBody(BaseModel):
    name: str
    args: Dict[str, Any] = {}
    channel: str = "GEMINI_LIVE_VOICE"


class ProofPhotoBody(BaseModel):
    data_url: str
    caption: str = "Field Camera Proof (Damaged Bags)"


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    return {
        "status": "ok",
        "gemini_configured": bool(api_key),
        "live_model": os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live"),
        "voice_note_model": os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash"),
        "whatsapp_configured": bool(wa_token and os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()),
    }


@app.get("/api/state")
async def api_state():
    return {"state": get_full_state(), "policies": COMPANY_POLICIES}


@app.post("/api/reset")
async def api_reset():
    set_latest_visual_proof(None, "")
    init_db(force_reset=True)
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return {"status": "reset", "state": get_full_state()}


@app.post("/api/proof-photo")
async def api_proof_photo(body: ProofPhotoBody):
    info = set_latest_visual_proof(body.data_url, body.caption)
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return {"proof": info, "state": get_full_state()}


@app.post("/api/demo/tool")
async def api_demo_tool(body: DemoToolBody):
    result, meta = execute_tool(body.name, body.args, channel=body.channel)
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return {"result": result, "meta": meta, "state": get_full_state()}


@app.post("/api/approvals/{approval_id}/decide")
async def api_decide_approval(approval_id: str, body: ApprovalDecisionBody):
    try:
        res = decide_approval(approval_id, body.decision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Optional real WhatsApp receipt push if Meta Cloud API credentials are present
    receipt = res.get("receipt")
    if receipt and os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip():
        manager_or_driver_phone = os.getenv("MANAGER_WHATSAPP_NUMBER", "").strip()
        if manager_or_driver_phone:
            await send_meta_whatsapp_message(manager_or_driver_phone, receipt["message"])

    # Push live approval into Raju's active Gemini Live voice call!
    await ACTIVE_SESSIONS.notify_manager_decision(res)
    return res


@app.post("/api/whatsapp/voice-note")
async def api_whatsapp_voice_note(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    driver_name: str = Form(default="Raju Kumar"),
):
    audio_bytes = await file.read() if file else None
    mime_type = (file.content_type or "audio/webm") if file else "audio/webm"
    result = await process_whatsapp_voice_note(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        fallback_text=text,
        driver_name=driver_name,
    )
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return result


# --- Real Meta WhatsApp Cloud API Webhook Endpoints ---
@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "deliverex_hackathon_verify_2026")
    if hub_mode == "subscribe" and hub_verify_token == expected and hub_challenge:
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    """
    Receives real Meta WhatsApp Cloud API webhooks (audio voice notes or text messages),
    downloads the OGG voice note from Meta Graph API if configured, runs Gemini Ops Agent,
    updates Tally/SAP ERP, and sends back the WhatsApp confirmation.
    """
    payload = await request.json()
    entries = payload.get("entry", [])
    processed = []

    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])
            driver_name = (
                contacts[0].get("profile", {}).get("name", "Raju Kumar")
                if contacts
                else "Raju Kumar"
            )

            for msg in messages:
                sender = msg.get("from", "")
                msg_type = msg.get("type")
                audio_bytes = None
                mime_type = "audio/ogg"
                fallback_text = None

                if msg_type == "audio":
                    media_id = msg.get("audio", {}).get("id")
                    mime_type = msg.get("audio", {}).get("mime_type", "audio/ogg")
                    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
                    if media_id and token:
                        async with httpx.AsyncClient(timeout=20.0) as client:
                            meta_res = await client.get(
                                f"https://graph.facebook.com/v21.0/{media_id}",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                            if meta_res.is_success:
                                media_url = meta_res.json().get("url")
                                if media_url:
                                    bin_res = await client.get(
                                        media_url,
                                        headers={"Authorization": f"Bearer {token}"},
                                    )
                                    if bin_res.is_success:
                                        audio_bytes = bin_res.content
                elif msg_type == "text":
                    fallback_text = msg.get("text", {}).get("body", "")

                if audio_bytes or fallback_text:
                    res = await process_whatsapp_voice_note(
                        audio_bytes=audio_bytes,
                        mime_type=mime_type,
                        fallback_text=fallback_text,
                        driver_name=driver_name,
                        sender_phone=sender,
                    )
                    await ACTIVE_SESSIONS.broadcast_erp_state()
                    processed.append(res["erp_result"])

    return {"status": "received", "processed_count": len(processed), "processed": processed}


@app.websocket("/ws/live-call")
async def ws_live_call(websocket: WebSocket):
    bridge = LiveBridgeSession(websocket)
    await bridge.run()
