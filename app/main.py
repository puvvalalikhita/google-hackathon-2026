import hashlib
import hmac
import json
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.database import (
    append_audit_log,
    check_db_health,
    get_all_ledger_entries,
    get_audit_logs,
    get_full_state,
    get_storage_mode,
    init_db,
)
from app.gemini_live import ACTIVE_SESSIONS, LiveBridgeSession
from app.policies import COMPANY_POLICIES
from app.security import (
    extract_bearer,
    get_owner_pin,
    is_manager_auth_enforced,
    issue_token,
    require_owner_session,
    verify_token,
)
from app.ntfy_bridge import get_ntfy_config, publish_ntfy_message
from app.storage_gcp import get_gcs_bucket_name, read_proof_from_gcs
from app.tally_export import build_ledger_csv, build_tally_prime_xml
from app.tools import decide_approval, execute_tool, set_latest_visual_proof
from app.tts import GREETING_TEXT, prewarm_common_tts, synthesize_speech_b64
from app.whatsapp import process_whatsapp_voice_note, send_meta_whatsapp_message
from app.workflows import (
    evaluate_go_live_readiness,
    is_vertex_configured,
    reset_conversation_memory,
    run_guided_workflow_step,
    run_voice_agent_workflow,
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(force_reset=False)
    asyncio.create_task(prewarm_common_tts())
    yield


app = FastAPI(
    title="Raju Bhai — Real-Time Gemini Voice & WhatsApp Field Ops",
    version="2.0.0",
    lifespan=lifespan,
)

raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
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


class AgentTurnBody(BaseModel):
    text: str
    driver_name: str = "Raju Kumar"
    active_store: Optional[str] = None
    channel: str = "GEMINI_LIVE_VOICE"
    lookup_only: bool = False
    preferred_language: Optional[str] = None


class ProofPhotoBody(BaseModel):
    data_url: str
    caption: str = "Field Camera Proof (Damaged Bags)"
    customer_name: Optional[str] = None
    damaged_bags: int = 2
    auto_create_approval: bool = True
    driver_name: str = "Raju Kumar"


class WhatsAppChatBody(BaseModel):
    text: Optional[str] = None
    driver_name: str = "Raju Kumar"
    image_data_url: Optional[str] = None
    active_store: Optional[str] = None


class OwnerLoginBody(BaseModel):
    pin: str
    actor: str = "Priya Sharma (Area Manager)"


@app.get("/")
async def root():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/api/health")
async def health():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    use_vertex = is_vertex_configured(api_key)
    db_health = check_db_health()
    audit_info = get_audit_logs(limit=1)
    return {
        "status": "ok" if db_health.get("ok") else "degraded",
        "gemini_configured": bool(api_key),
        "auth_mode": "vertex_ai" if use_vertex else ("ai_studio" if api_key else "workflow_offline"),
        "live_model": os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live"),
        "voice_note_model": os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash"),
        "whatsapp_configured": bool(wa_token and os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()),
        "environment": os.getenv("ENVIRONMENT", "development").strip().lower(),
        "database_ok": db_health.get("ok", False),
        "storage_mode": get_storage_mode(),
        "gcs_bucket": get_gcs_bucket_name() or None,
        "manager_auth_enforced": is_manager_auth_enforced(),
        "audit_chain_verified": audit_info.get("chain_verified", True),
    }


@app.get("/api/app/version")
async def api_app_version():
    """Returns the latest Android APK metadata + open-source ntfy channel so Raju Bhai apps notify & self-update."""
    ntfy = get_ntfy_config()
    return {
        "app_name": "Raju Bhai",
        "latest_version_code": int(os.getenv("ANDROID_LATEST_VERSION_CODE", "6")),
        "latest_version_name": os.getenv("ANDROID_LATEST_VERSION_NAME", "1.5.0").strip(),
        "apk_url": os.getenv(
            "ANDROID_APK_URL",
            "https://storage.googleapis.com/deliverex-downloads-353183969363/Raju-Bhai-v1.5.0.apk",
        ).strip(),
        "release_notes": os.getenv(
            "ANDROID_RELEASE_NOTES",
            "Replaced WhatsApp with open-source ntfy Ops Chat (github.com/binwiederhier/ntfy), 1-tap Ledger & Receipt push dispatch, and real-time push update notifications.",
        ).strip(),
        "force_update": os.getenv("ANDROID_FORCE_UPDATE", "false").strip().lower() in {"true", "1", "yes"},
        "ntfy_topic": ntfy["topic"],
        "ntfy_topic_url": ntfy["topic_url"],
    }


@app.post("/api/auth/login")
async def api_auth_login(body: OwnerLoginBody):
    if body.pin.strip() != get_owner_pin():
        raise HTTPException(status_code=401, detail="Invalid Owner/Manager PIN")
    token = issue_token(actor=body.actor, role="OWNER")
    append_audit_log(
        actor=body.actor,
        role="OWNER",
        action="OWNER_LOGIN",
        target_id="auth-session",
        summary=f"{body.actor} authenticated Manager/Owner session",
    )
    return {
        "token": token,
        "role": "OWNER",
        "actor": body.actor,
        "expires_in": 86400,
    }


@app.get("/api/auth/session")
async def api_auth_session(
    authorization: Optional[str] = Header(default=None),
    x_owner_token: Optional[str] = Header(default=None),
):
    claims = verify_token(extract_bearer(authorization, x_owner_token))
    enforced = is_manager_auth_enforced()
    return {
        "authenticated": bool(claims) or (not enforced),
        "token_valid": bool(claims),
        "auth_enforced": enforced,
        "role": claims.get("role") if claims else ("OWNER" if not enforced else "GUEST"),
        "actor": claims.get("sub") if claims else ("Local Dev" if not enforced else "Guest"),
    }


@app.get("/api/proofs/{proof_name}")
async def api_get_proof(proof_name: str):
    found = read_proof_from_gcs(proof_name)
    if not found:
        raise HTTPException(status_code=404, detail="Proof photo not found")
    content, mime = found
    return Response(
        content=content,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/audit-logs")
async def api_audit_logs(
    limit: int = Query(default=40, ge=1, le=200),
    _owner: Dict[str, Any] = Depends(require_owner_session),
):
    return get_audit_logs(limit=limit)


@app.get("/api/ledger/export/tally.xml")
async def api_export_tally_xml(owner: Dict[str, Any] = Depends(require_owner_session)):
    entries = get_all_ledger_entries()
    xml_data = build_tally_prime_xml(entries)
    append_audit_log(
        actor=owner.get("sub", "Priya Sharma"),
        role="OWNER",
        action="LEDGER_EXPORTED",
        target_id="tally-xml",
        summary=f"Exported {len(entries)} vouchers as TallyPrime XML",
    )
    return Response(
        content=xml_data,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=deliverex_tally_vouchers.xml"},
    )


@app.get("/api/ledger/export/ledger.csv")
async def api_export_ledger_csv(owner: Dict[str, Any] = Depends(require_owner_session)):
    entries = get_all_ledger_entries()
    csv_data = build_ledger_csv(entries)
    append_audit_log(
        actor=owner.get("sub", "Priya Sharma"),
        role="OWNER",
        action="LEDGER_EXPORTED",
        target_id="ledger-csv",
        summary=f"Exported {len(entries)} ledger rows as CSV",
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deliverex_ledger.csv"},
    )


@app.get("/api/go-live-check")
async def api_go_live_check():
    return evaluate_go_live_readiness()


@app.get("/api/state")
async def api_state():
    return {"state": get_full_state(), "policies": COMPANY_POLICIES}


class TtsBody(BaseModel):
    text: str = GREETING_TEXT
    language: Optional[str] = "Hinglish (HI+EN)"


@app.post("/api/tts")
async def api_tts(body: TtsBody):
    audio_b64 = await synthesize_speech_b64(body.text, body.language)
    return {
        "audio_b64": audio_b64,
        "audio_mime": "audio/mpeg" if audio_b64 else None,
    }


@app.post("/api/reset")
async def api_reset(
    x_admin_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    x_owner_token: Optional[str] = Header(default=None),
):
    env_mode = os.getenv("ENVIRONMENT", "development").strip().lower()
    allow_demo_reset = os.getenv("ALLOW_DEMO_RESET", "true").strip().lower() == "true"
    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    owner_claims = verify_token(extract_bearer(authorization, x_owner_token))

    if env_mode == "production" and not allow_demo_reset:
        if not admin_key or x_admin_key != admin_key:
            raise HTTPException(status_code=403, detail="Reset disabled in production without valid X-Admin-Key")
    elif is_manager_auth_enforced():
        valid_admin = bool(admin_key and x_admin_key == admin_key)
        valid_owner = bool(owner_claims and owner_claims.get("role") in {"OWNER", "MANAGER"})
        if not (valid_admin or valid_owner):
            raise HTTPException(status_code=401, detail="Owner sign-in or valid X-Admin-Key required to reset")

    set_latest_visual_proof(None, "")
    reset_conversation_memory()
    init_db(force_reset=True)
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return {"status": "reset", "state": get_full_state()}


@app.post("/api/agent/turn")
async def api_agent_turn(body: AgentTurnBody):
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="Agent turn text is required")
    res = await run_voice_agent_workflow(
        body.text,
        driver_name=body.driver_name,
        active_store=body.active_store,
        channel=body.channel,
        lookup_only=body.lookup_only,
        preferred_language=body.preferred_language,
    )
    res["audio_b64"] = await synthesize_speech_b64(res.get("reply_text") or "", res.get("detected_language"))
    res["audio_mime"] = "audio/mpeg" if res["audio_b64"] else None
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return res


@app.post("/api/agent/guided/{step}")
async def api_agent_guided(step: int, preferred_language: Optional[str] = Query(default=None)):
    try:
        res = await run_guided_workflow_step(step, preferred_language=preferred_language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    res["audio_b64"] = await synthesize_speech_b64(res.get("reply_text") or "", res.get("detected_language"))
    res["audio_mime"] = "audio/mpeg" if res["audio_b64"] else None
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return res


@app.post("/api/proof-photo")
async def api_proof_photo(body: ProofPhotoBody):
    if not body.data_url or not body.data_url.strip():
        raise HTTPException(status_code=400, detail="data_url is required")
    info = set_latest_visual_proof(
        body.data_url,
        body.caption,
        customer_name=body.customer_name,
        damaged_bags=body.damaged_bags,
        auto_create_approval=body.auto_create_approval,
        driver_name=body.driver_name,
    )
    await ACTIVE_SESSIONS.broadcast_erp_state()
    asyncio.create_task(
        publish_ntfy_message(
            title=f"📷 Torn Bags Photo — {info.get('customer_name') or body.customer_name or 'Shop'}",
            message=f"{body.driver_name} uploaded photo proof ({body.damaged_bags} damaged bags). Open Raju Bhai Manager Portal to approve.",
            tags=["camera", "raju-ops"],
            priority="high",
        )
    )
    return {"proof": info, "state": get_full_state()}


@app.post("/api/demo/tool")
async def api_demo_tool(body: DemoToolBody):
    result, meta = execute_tool(body.name, body.args, channel=body.channel)
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return {"result": result, "meta": meta, "state": get_full_state()}


@app.post("/api/approvals/{approval_id}/decide")
async def api_decide_approval(
    approval_id: str,
    body: ApprovalDecisionBody,
    owner: Dict[str, Any] = Depends(require_owner_session),
):
    try:
        res = decide_approval(approval_id, body.decision, actor=owner.get("sub", "Priya Sharma (Area Manager)"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Dispatch official receipt & decision via open-source ntfy (WhatsApp alternative)
    receipt = res.get("receipt")
    apr = res.get("approval") or {}
    asyncio.create_task(
        publish_ntfy_message(
            title=f"✅ Approval {body.decision} — {apr.get('customer_name', 'Shop')}",
            message=receipt["message"] if receipt else f"Priya {body.decision} request {approval_id} for {apr.get('customer_name', 'Shop')}.",
            tags=["white_check_mark", "raju-receipt"],
            priority="high",
        )
    )

    # Optional real WhatsApp receipt push if Meta Cloud API credentials are present
    if receipt and os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip():
        manager_or_driver_phone = os.getenv("MANAGER_WHATSAPP_NUMBER", "").strip()
        if manager_or_driver_phone:
            await send_meta_whatsapp_message(manager_or_driver_phone, receipt["message"])

    # Push live approval into Raju's active Gemini Live voice call!
    await ACTIVE_SESSIONS.notify_manager_decision(res)
    return res


class OpsPushBody(BaseModel):
    title: str = "Raju Bhai Ops Update"
    message: str = ""
    tags: Optional[List[str]] = None


@app.post("/api/ops/push-ledger")
async def api_ops_push_ledger():
    """Dispatches the current Account Book / Tally Ledger summary via open-source ntfy."""
    state = get_full_state()
    entries = state.get("ledger", [])
    total_cash = sum(int(e.get("cash_received") or 0) for e in entries)
    total_ok = sum(int(e.get("delivered_qty") or 0) for e in entries)
    total_dmg = sum(int(e.get("damaged_qty") or 0) for e in entries)
    lines = [
        f"📒 Raju Bhai Live Ledger Summary ({len(entries)} entries)",
        f"Cash Collected: Rs {total_cash:,} | Delivered: {total_ok} ok, {total_dmg} dmg",
        "--- Recent Entries ---",
    ]
    for e in entries[:8]:
        lines.append(
            f"• {e.get('customer_name')} ({e.get('invoice_id')}): {e.get('delivered_qty')} bags, Rs {int(e.get('cash_received') or 0):,} [{e.get('tally_status')}]"
        )
    summary_text = "\n".join(lines)
    ntfy_res = await publish_ntfy_message(
        title=f"📒 Raju Bhai Ledger ({len(entries)} entries • Rs {total_cash:,})",
        message=summary_text,
        tags=["ledger", "raju-ledger"],
        priority="high",
    )
    return {"ok": ntfy_res.get("ok", False), "ntfy": ntfy_res, "summary": summary_text}


@app.post("/api/ops/push-receipt")
async def api_ops_push_receipt(body: OpsPushBody):
    """Dispatches a receipt or custom ops message via open-source ntfy."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    ntfy_res = await publish_ntfy_message(
        title=body.title or "🧾 Raju Bhai Official Receipt",
        message=body.message.strip(),
        tags=body.tags or ["receipt", "raju-receipt"],
        priority="high",
    )
    return {"ok": ntfy_res.get("ok", False), "ntfy": ntfy_res}


@app.post("/api/ops/push-update")
async def api_ops_push_update():
    """Broadcasts a direct app update push notification to all Raju Bhai phones via ntfy."""
    ver = await api_app_version()
    ntfy_res = await publish_ntfy_message(
        title=f"🚀 Raju Bhai v{ver['latest_version_name']} Update Ready",
        message=f"{ver['release_notes']}\nTap to download & install directly.",
        tags=["rocket", "raju-update"],
        priority="urgent",
        click_url=ver["apk_url"],
    )
    return {"ok": ntfy_res.get("ok", False), "version": ver, "ntfy": ntfy_res}


@app.get("/api/whatsapp/messages")
async def api_whatsapp_messages():
    return {"messages": get_full_state().get("whatsapp_messages", [])}


@app.post("/api/whatsapp/message")
async def api_whatsapp_message(body: WhatsAppChatBody):
    if not (body.text and body.text.strip()) and not body.image_data_url:
        raise HTTPException(status_code=400, detail="Message text or image_data_url is required")
    result = await process_whatsapp_voice_note(
        fallback_text=body.text,
        driver_name=body.driver_name,
        image_data_url=body.image_data_url,
        active_store=body.active_store,
    )
    await ACTIVE_SESSIONS.broadcast_erp_state()
    return result


@app.post("/api/whatsapp/voice-note")
async def api_whatsapp_voice_note(
    file: Optional[UploadFile] = File(default=None),
    image: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    image_data_url: Optional[str] = Form(default=None),
    active_store: Optional[str] = Form(default=None),
    driver_name: str = Form(default="Raju Kumar"),
):
    audio_bytes = await file.read() if file else None
    mime_type = (file.content_type or "audio/webm") if file else "audio/webm"
    image_bytes = await image.read() if image else None
    image_mime_type = (image.content_type or "image/jpeg") if image else "image/jpeg"
    result = await process_whatsapp_voice_note(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        fallback_text=text,
        driver_name=driver_name,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        image_data_url=image_data_url,
        active_store=active_store,
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
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
):
    """
    Receives real Meta WhatsApp Cloud API webhooks (audio voice notes, images, or text messages),
    verifies X-Hub-Signature-256 when WHATSAPP_APP_SECRET is configured, downloads media from
    Meta Graph API, runs DeliverEx Ops Agent workflow, updates Tally/SAP ERP, and replies.
    """
    raw_body = await request.body()
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if app_secret:
        if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
            raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")
        expected_sig = "sha256=" + hmac.new(
            app_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid X-Hub-Signature-256")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload")

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
                image_bytes = None
                image_mime_type = "image/jpeg"
                fallback_text = None
                token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()

                if msg_type == "audio":
                    media_id = msg.get("audio", {}).get("id")
                    mime_type = msg.get("audio", {}).get("mime_type", "audio/ogg")
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
                elif msg_type == "image":
                    media_id = msg.get("image", {}).get("id")
                    image_mime_type = msg.get("image", {}).get("mime_type", "image/jpeg")
                    fallback_text = msg.get("image", {}).get("caption", "") or "Damaged bags photo proof"
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
                                        image_bytes = bin_res.content
                elif msg_type == "text":
                    fallback_text = msg.get("text", {}).get("body", "")

                if audio_bytes or image_bytes or fallback_text:
                    res = await process_whatsapp_voice_note(
                        audio_bytes=audio_bytes,
                        mime_type=mime_type,
                        fallback_text=fallback_text,
                        driver_name=driver_name,
                        sender_phone=sender,
                        image_bytes=image_bytes,
                        image_mime_type=image_mime_type,
                    )
                    await ACTIVE_SESSIONS.broadcast_erp_state()
                    processed.append(res["erp_result"])

    return {"status": "received", "processed_count": len(processed), "processed": processed}


@app.websocket("/ws/live-call")
async def ws_live_call(
    websocket: WebSocket,
    driver_name: str = Query(default="Raju Kumar"),
    lang: str = Query(default="Hinglish"),
):
    bridge = LiveBridgeSession(websocket, driver_name=driver_name, preferred_language=lang)
    await bridge.run()
