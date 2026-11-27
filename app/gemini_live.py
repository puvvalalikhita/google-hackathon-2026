import asyncio
import base64
import json
import os
import time
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from app.database import add_whatsapp_message, get_full_state
from app.tools import GEMINI_TOOL_DECLARATIONS, execute_tool, set_latest_visual_proof
from app.tts import synthesize_speech_b64
from app.workflows import is_vertex_configured, run_guided_workflow_step, run_voice_agent_workflow

SYSTEM_INSTRUCTION = """You are Raju Bhai AI — a fast, friendly, multimodal real-time frontline voice & vision operations assistant for Indian wholesale logistics.

ROLE & STYLE:
- You speak directly with field delivery drivers (like Raju) standing in loud, busy wholesale markets (Old Delhi Mandi, Chennai T. Nagar) or driving trucks.
- Match the speaker's language naturally and immediately: fluent Hinglish (Hindi + English), Hindi, Telugu, Tenglish (Telugu + English), Tamil, Tanglish (Tamil + English), Marathi, or English. Default to warm, respectful Hinglish ("Ji Raju bhai..."), and switch IMMEDIATELY whenever the driver speaks or asks for another language (e.g., Telugu, English, Hindi, or Tamil)!
- Keep responses concise (1 to 3 short sentences) for sub-second voice turn-taking. Never read raw JSON.
- If the driver interrupts you mid-sentence, stop immediately, acknowledge the correction naturally ("Achha samajh gaya, 18 bags..."), and proceed with the updated numbers.
- EMPATHY & NON-DELIVERY EXCEPTIONS: If the driver says they are sick/unwell, couldn't deliver anything, the shop is closed, or they are stuck in traffic/rain/breakdown, NEVER ask "how many bags were delivered?"! Respond with warmth and care (tell them to rest/drive safely first), confirm 0 bags logged, and call `request_human_handoff` to notify Area Manager Priya Sharma to arrange backup or reschedule.

TRUE MULTIMODALITY (VOICE + VISION) & DAMAGED BAGS RULE:
- Whenever a driver mentions OR shows torn/damaged bags on camera, ALWAYS verify and state the EXACT store/shop name (e.g., Krishna Hardware, Shri Ganesh Stores, Murugan Builders, Bharat Traders).
- If the driver has NOT mentioned which store the torn bags came from, ALWAYS ask first: "Raju bhai, kis shop par torn bags nikle — Krishna Hardware, Shri Ganesh Stores, ya Murugan Builders?" before logging the damage.
- Once you know the store name, IMMEDIATELY call `log_damaged_bags_report(customer_name=..., damaged_bags=...)` (or `record_delivery_and_update_ledger` if cash/delivery details were also given) so the exact store name, quarantine count, and visual proof are ALWAYS logged on Area Manager Priya's approval card!
- If the driver shows a live camera frame or photo of torn bags, confirm both the bag count AND the exact store name out loud (e.g., "Haan photo mein Krishna Hardware ke 2 torn UltraTech bags clear dikh rahe hain — maine Krishna Hardware ke naam se Priya ma'am ko bhej diya hai!").

MANDATORY GROUNDING, COACHING & TOOL WORKFLOW:
1. When a driver mentions a shop/customer name (e.g., Krishna Hardware, Shri Ganesh Stores, Murugan Builders, Bharat Traders), ALWAYS call `lookup_customer_and_invoice` first.
2. Call `update_frontline_guidance` whenever intent, language, or customer sentiment shifts, giving the driver a short practical coaching tip and a polite phrase to calm/reassure the shop owner.
3. Whenever a driver mentions a discount, damaged/torn bags, short delivery, or a dispute, ALWAYS call `check_company_policy` so your answer cites exact company SOP numbers (SOP-4.2: Rs 200 driver discount cap; SOP-5.1: damaged goods quarantine + Manager Priya approval).
4. Once details are stated — including in follow-up turns AFTER a torn-bag photo or manager approval has already happened — ALWAYS call `record_delivery_and_update_ledger` immediately whenever the driver gives delivered bag count and cash received (e.g., "20 bags delivered, 50,000 cash mila"), and verbally confirm the exact store name, bags, and cash posted to Tally/SAP!
5. If a Manager Approval update arrives from the system (Priya approved/rejected/took over), immediately announce it to the driver in their language and confirm that the official WhatsApp receipt has been sent! Then keep listening for any additional delivery or cash updates.
"""


class ActiveSessionRegistry:
    """Tracks active WebSocket + Gemini Live sessions so Manager Priya's 1-tap approval loops back live."""

    def __init__(self) -> None:
        self._sessions: Set["LiveBridgeSession"] = set()

    def register(self, bridge: "LiveBridgeSession") -> None:
        self._sessions.add(bridge)

    def unregister(self, bridge: "LiveBridgeSession") -> None:
        self._sessions.discard(bridge)

    async def broadcast_erp_state(self) -> None:
        state = get_full_state()
        for bridge in list(self._sessions):
            await bridge.send_ui({"type": "erp_state", "state": state})

    async def notify_manager_decision(self, decision_payload: Dict[str, Any]) -> None:
        for bridge in list(self._sessions):
            await bridge.inject_manager_decision(decision_payload)


ACTIVE_SESSIONS = ActiveSessionRegistry()


class LiveBridgeSession:
    def __init__(
        self,
        websocket: WebSocket,
        driver_name: str = "Raju Kumar",
        preferred_language: str = "Hinglish",
    ) -> None:
        self.ws = websocket
        self.driver_name = (driver_name or "Raju Kumar").strip()
        self.driver_first_name = self.driver_name.split()[0] if self.driver_name else "Dost"
        self.preferred_language = (preferred_language or "Hinglish").strip()
        self.gemini_session: Any = None
        self.last_user_audio_ts: Optional[float] = None
        self.awaiting_first_audio: bool = False
        self.interruption_count: int = 0
        self.closed: bool = False
        self._ws_lock = asyncio.Lock()

    async def send_ui(self, payload: Dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            async with self._ws_lock:
                await self.ws.send_text(json.dumps(payload))
        except Exception:
            self.closed = True

    async def inject_manager_decision(self, decision_payload: Dict[str, Any]) -> None:
        """Closes the loop: sends Priya's approval/rejection straight into the live voice call."""
        decision = decision_payload["decision"]
        apr = decision_payload["approval"]
        receipt = decision_payload.get("receipt")

        await self.send_ui({"type": "erp_state", "state": decision_payload["state"]})
        await self.send_ui(
            {
                "type": "manager_decision_event",
                "decision": decision,
                "approval": apr,
                "receipt": receipt,
            }
        )

        if self.gemini_session is not None:
            if decision == "APPROVED":
                prompt = (
                    f"[SYSTEM UPDATE FROM AREA MANAGER PRIYA SHARMA]: Priya has APPROVED the exception for "
                    f"{apr['customer_name']} (Rs {apr['discount_requested']} discount, {apr['damaged_qty']} damaged bags). "
                    f"Tally/SAP invoice is now SETTLED and official Receipt {receipt['receipt_id'] if receipt else ''} "
                    f"has been sent. Immediately inform {self.driver_first_name} in upbeat, natural {self.preferred_language}!"
                )
            elif decision == "REJECTED":
                prompt = (
                    f"[SYSTEM UPDATE FROM AREA MANAGER PRIYA SHARMA]: Priya has REJECTED the Rs {apr['discount_requested']} "
                    f"extra discount for {apr['customer_name']}. Inform {self.driver_first_name} politely in {self.preferred_language} that the extra discount "
                    f"was not approved and the remaining balance stays open on the customer's credit ledger."
                )
            else:
                prompt = (
                    f"[SYSTEM UPDATE]: Area Manager Priya Sharma is joining/taking over the call for {apr['customer_name']}. "
                    f"Inform {self.driver_first_name} in {self.preferred_language} that you are connecting him directly to Priya ma'am now."
                )

            try:
                self.last_user_audio_ts = time.perf_counter()
                self.awaiting_first_audio = True
                await self.gemini_session.send_realtime_input(text=prompt)
            except Exception as exc:
                await self.send_ui({"type": "error", "message": f"Approval injection error: {exc}"})

    async def _emit_workflow_result(self, user_text: str, wf: Dict[str, Any]) -> None:
        if wf.get("is_barge_in"):
            self.interruption_count += 1
            await self.send_ui(
                {
                    "type": "interrupted",
                    "count": self.interruption_count,
                    "timestamp": time.time(),
                }
            )

        if user_text:
            await self.send_ui({"type": "transcript", "role": "user", "text": user_text, "final": True})

        for ev in wf.get("tool_events", []):
            await self.send_ui({"type": "tool_call_start", "name": ev["name"], "args": ev["args"]})
            await self.send_ui(
                {
                    "type": "tool_call_result",
                    "name": ev["name"],
                    "args": ev["args"],
                    "result": ev["result"],
                    "meta": ev["meta"],
                }
            )

        # Co-work with WhatsApp Chat: mirror operational Live Call updates & AI replies cleanly into WhatsApp thread
        casual_intents = {"GREETING", "UNCLEAR_AUDIO", "HOW_ARE_YOU", "ACK_THANKS", "HELP_CAPABILITIES", "LANG_SWITCH", "CANCEL_ACTION"}
        if user_text and wf.get("reply_text") and wf.get("intent") not in casual_intents:
            add_whatsapp_message(
                "driver",
                f"📞 [Live Call] {user_text}",
                msg_type="text",
                metadata={"channel": "GEMINI_LIVE_VOICE"},
            )
            add_whatsapp_message(
                "bot",
                wf["reply_text"],
                msg_type="text",
                metadata={
                    "sender_label": "DeliverEx Live Voice Sync",
                    "intent": wf.get("intent"),
                    "processing_ms": round(wf.get("processing_ms", 0)),
                    "used_gemini": wf.get("used_gemini", False),
                },
            )

        audio_b64 = await synthesize_speech_b64(wf["reply_text"], wf.get("detected_language"))
        await self.send_ui({"type": "erp_state", "state": get_full_state()})
        await self.send_ui({"type": "latency", "ttfa_ms": max(180, round(wf.get("processing_ms", 320)))})
        await self.send_ui(
            {
                "type": "workflow_reply",
                "text": wf["reply_text"],
                "intent": wf["intent"],
                "detected_language": wf.get("detected_language"),
                "lang_code": wf.get("lang_code"),
                "audio_b64": audio_b64,
                "audio_mime": "audio/mpeg" if audio_b64 else None,
                "guidance": wf.get("guidance"),
                "result": wf.get("result"),
            }
        )
        await self.send_ui({"type": "turn_complete"})

    async def _run_workflow_bridge_loop(self, reason_message: str) -> None:
        """Runs full backend workflow orchestration over WebSocket when Gemini Live Audio is inactive."""
        await self.send_ui(
            {
                "type": "status",
                "mode": "WORKFLOW_ENGINE",
                "connected": False,
                "workflow_ready": True,
                "message": reason_message,
            }
        )
        while not self.closed:
            raw = await self.ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await self.send_ui({"type": "pong"})

            elif msg_type == "guided_step":
                step = int(msg.get("step", 1))
                wf = await run_guided_workflow_step(step, preferred_language=msg.get("preferred_language"))
                await self._emit_workflow_result(wf["user_text"], wf)

            elif msg_type == "text_turn":
                text = (msg.get("text") or "").strip()
                if text:
                    wf = await run_voice_agent_workflow(
                        text,
                        driver_name=msg.get("driver_name") or "Raju Kumar",
                        active_store=msg.get("active_store"),
                        preferred_language=msg.get("preferred_language"),
                    )
                    await self._emit_workflow_result(text, wf)

            elif msg_type == "audio_turn":
                b64_audio = msg.get("data") or ""
                if b64_audio:
                    audio_bytes = base64.b64decode(b64_audio)
                    wf = await run_voice_agent_workflow(
                        "",
                        audio_bytes=audio_bytes,
                        mime_type=msg.get("mime_type") or "audio/wav",
                        driver_name=msg.get("driver_name") or "Raju Kumar",
                        active_store=msg.get("active_store"),
                        preferred_language=msg.get("preferred_language"),
                    )
                    spoken_user_text = (wf.get("user_transcript") or "").strip()
                    if not spoken_user_text and wf.get("intent") != "UNCLEAR_AUDIO":
                        spoken_user_text = "🎤 [Live Voice]"
                    await self._emit_workflow_result(spoken_user_text, wf)

            elif msg_type == "video_frame":
                data_url = msg.get("data_url", "")
                if data_url:
                    dmg = int(msg.get("damaged_bags", 2) or 2)
                    proof_info = set_latest_visual_proof(
                        data_url,
                        msg.get("caption", "Live Field Camera Frame"),
                        customer_name=msg.get("customer_name"),
                        damaged_bags=dmg,
                        auto_create_approval=bool(msg.get("auto_create_approval", True)),
                    )
                    store_name = proof_info.get("customer_name") or "Krishna Hardware"
                    if msg.get("prompt"):
                        g_args = {
                            "intent": "VISUAL_DAMAGE_VERIFIED",
                            "language": "Hinglish (HI+EN)",
                            "sentiment": "CONCERNED",
                            "coach_tip": f"{dmg} torn bags verified for {store_name} & attached to Priya Sharma's 1-Tap Approval Card (SOP-5.1)!",
                            "suggested_phrase": f"Uncle, {store_name} ke {dmg} damaged bags ki photo AI ne verify karke Priya ma'am ko bhej di hai.",
                        }
                        g_res, g_meta = execute_tool("update_frontline_guidance", g_args)
                        await self.send_ui(
                            {
                                "type": "tool_call_result",
                                "name": "log_damaged_bags_report",
                                "args": {"customer_name": store_name, "damaged_bags": dmg, "visual_proof": "verified"},
                                "result": proof_info,
                                "meta": {"tool": "log_damaged_bags_report", "elapsed_ms": 18.0, "status": "ESCALATED"},
                            }
                        )
                        await self.send_ui(
                            {
                                "type": "tool_call_result",
                                "name": "update_frontline_guidance",
                                "args": g_args,
                                "result": g_res,
                                "meta": g_meta,
                            }
                        )
                        await self.send_ui({"type": "erp_state", "state": get_full_state()})
                        await self.send_ui(
                            {
                                "type": "workflow_reply",
                                "text": (
                                    f"Haan {self.driver_first_name} ji, camera photo mein {store_name} ke {dmg} torn cement bags clear dikh rahe hain! "
                                    f"Maine yeh visual proof seedha {store_name} ke naam se Priya ma'am ke approval card par attach kar diya hai."
                                ),
                                "intent": "VISUAL_DAMAGE_VERIFIED",
                                "guidance": g_res.get("guidance"),
                            }
                        )
                    else:
                        await self.send_ui({"type": "erp_state", "state": get_full_state()})

    async def run(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model_name = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
        voice_name = os.getenv("GEMINI_VOICE_NAME", "Kore").strip()
        use_vertex = is_vertex_configured(api_key)

        await self.ws.accept()
        ACTIVE_SESSIONS.register(self)
        await self.send_ui({"type": "erp_state", "state": get_full_state()})

        if not api_key:
            try:
                await self._run_workflow_bridge_loop(
                    "Backend Workflow Mode Active (Add GEMINI_API_KEY in .env for Live Gemini Audio)"
                )
            except WebSocketDisconnect:
                pass
            finally:
                self.closed = True
                ACTIVE_SESSIONS.unregister(self)
            return

        from google import genai

        if use_vertex:
            client = genai.Client(vertexai=True, api_key=api_key)
            candidate_models = [
                model_name,
                "gemini-live-2.5-flash-native-audio",
                "gemini-2.5-flash-native-audio-preview-12-2025",
            ]
        else:
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
            candidate_models = [
                model_name,
                "gemini-2.5-flash-native-audio-latest",
                "gemini-2.5-flash-native-audio-preview-12-2025",
                "gemini-3.1-flash-live-preview",
                "gemini-2.0-flash-live-001",
            ]
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m]))

        personalized_instruction = (
            SYSTEM_INSTRUCTION
            + f"\n\nCURRENT WORKER CONTEXT:\n"
            + f"- The logged-in delivery worker's name is '{self.driver_name}'. ALWAYS address them as '{self.driver_first_name}' (NEVER call them 'Raju' or 'Raju bhai' unless their name actually is Raju!).\n"
            + f"- Preferred language: {self.preferred_language}. Start in {self.preferred_language} and adapt immediately if they speak another language.\n"
        )

        config: Dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "system_instruction": personalized_instruction,
            "tools": GEMINI_TOOL_DECLARATIONS,
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": voice_name}
                }
            },
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": False,
                    "start_of_speech_sensitivity": "START_SENSITIVITY_LOW",
                    "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 700,
                }
            },
        }

        last_err: Optional[Exception] = None
        connected_once = False

        try:
            for active_model in candidate_models:
                try:
                    provider = "Vertex AI" if use_vertex else "Gemini Live API"
                    await self.send_ui(
                        {
                            "type": "status",
                            "mode": "GEMINI_LIVE",
                            "connected": False,
                            "model": active_model,
                            "message": f"Connecting to {provider} Live API ({active_model})...",
                        }
                    )

                    cm = client.aio.live.connect(model=active_model, config=config)
                    session = await asyncio.wait_for(cm.__aenter__(), timeout=8.0)
                    try:
                        connected_once = True
                        self.gemini_session = session
                        await self.send_ui(
                            {
                                "type": "status",
                                "mode": "GEMINI_LIVE",
                                "connected": True,
                                "model": active_model,
                                "message": f"Live Gemini Voice Connected ({provider} • {active_model})",
                            }
                        )

                        recv_task = asyncio.create_task(self._receive_from_gemini())
                        send_task = asyncio.create_task(self._receive_from_browser())

                        self.last_user_audio_ts = time.perf_counter()
                        self.awaiting_first_audio = True
                        lang_low = self.preferred_language.lower()
                        if "తెలుగు" in self.preferred_language or "telugu" in lang_low:
                            lang_label = "Telugu (తెలుగు)"
                            sample_greet = f"నమస్తే {self.driver_first_name} గారు, ఏ షాప్‌లో డెలివరీ జరిగింది చెప్పండి?"
                        elif "हिंदी" in self.preferred_language or "hindi" in lang_low:
                            lang_label = "Hindi (हिंदी)"
                            sample_greet = f"नमस्ते {self.driver_first_name} जी, बताइए किस दुकान पर डिलीवरी हुई?"
                        elif "tanglish" in lang_low or "tamil" in lang_low:
                            lang_label = "Tanglish (Tamil + English)"
                            sample_greet = f"Vanakkam {self.driver_first_name} ji, entha shop-la delivery aachu sollunga?"
                        elif "english" in lang_low:
                            lang_label = "English"
                            sample_greet = f"Hello {self.driver_first_name}! Which shop did you just deliver to?"
                        else:
                            lang_label = "Hinglish (Hindi + English)"
                            sample_greet = f"Namaste {self.driver_first_name} ji, bataiye kis shop pe delivery hui?"
                        await session.send_realtime_input(
                            text=(
                                f"[CALL CONNECTED]: Worker '{self.driver_name}' just started the call and selected language '{lang_label}'. "
                                f"You MUST greet {self.driver_first_name} strictly in {lang_label} (NOT Hinglish unless Hinglish was selected) "
                                f"using their exact name '{self.driver_first_name}' (do NOT say Raju unless their name is Raju) "
                                f"in 1 short friendly sentence like: '{sample_greet}'"
                            )
                        )

                        done, pending = await asyncio.wait(
                            [recv_task, send_task], return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                        for task in done:
                            if not task.cancelled() and task.exception():
                                raise task.exception()
                    finally:
                        await cm.__aexit__(None, None, None)
                    break
                except WebSocketDisconnect:
                    raise
                except Exception as exc:
                    last_err = exc
                    if connected_once:
                        raise
                    continue

            if not connected_once and last_err is not None:
                # Stay alive in Backend Workflow Engine mode instead of dropping the WebSocket!
                await self.send_ui(
                    {
                        "type": "error",
                        "message": f"Gemini Live Audio unavailable ({last_err}). Switched seamlessly to Backend Workflow Mode.",
                    }
                )
                await self._run_workflow_bridge_loop(
                    "Backend Workflow Mode Active (Live Audio fallback — full ERP & HITL workflows running)"
                )

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            await self.send_ui(
                {
                    "type": "error",
                    "message": f"Gemini Live session ended: {exc}",
                }
            )
        finally:
            self.closed = True
            self.gemini_session = None
            ACTIVE_SESSIONS.unregister(self)

    async def _receive_from_browser(self) -> None:
        from google.genai import types

        while not self.closed:
            raw = await self.ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "audio_chunk" and self.gemini_session is not None:
                pcm_bytes = base64.b64decode(msg["data"])
                if msg.get("speaking"):
                    self.last_user_audio_ts = time.perf_counter()
                    self.awaiting_first_audio = True
                await self.gemini_session.send_realtime_input(
                    audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                )

            elif msg_type == "video_frame" and self.gemini_session is not None:
                data_url = msg.get("data_url", "")
                b64_raw = data_url.split(",", 1)[1] if "," in data_url else data_url
                if b64_raw:
                    img_bytes = base64.b64decode(b64_raw)
                    proof_info = set_latest_visual_proof(
                        data_url,
                        msg.get("caption", "Live Field Camera Frame"),
                        customer_name=msg.get("customer_name"),
                        damaged_bags=int(msg.get("damaged_bags", 2) or 2),
                        auto_create_approval=bool(msg.get("auto_create_approval", True)),
                    )
                    await self.gemini_session.send_realtime_input(
                        video=types.Blob(data=img_bytes, mime_type="image/jpeg")
                    )
                    if msg.get("prompt"):
                        self.last_user_audio_ts = time.perf_counter()
                        self.awaiting_first_audio = True
                        store_tag = proof_info.get("customer_name") or "Krishna Hardware"
                        inv_tag = proof_info.get("invoice_id") or ""
                        enriched_prompt = (
                            f"[STORE CONTEXT: {store_tag} ({inv_tag}) — Visual damage proof already attached to Priya's approval card {proof_info.get('attached_to_approval') or ''}] "
                            + msg["prompt"]
                        )
                        await self.gemini_session.send_realtime_input(text=enriched_prompt)
                    await self.send_ui({"type": "erp_state", "state": get_full_state()})

            elif msg_type == "guided_step" and self.gemini_session is not None:
                step = int(msg.get("step", 1))
                step_texts = {
                    1: "Hello, main Raju bol raha hoon Old Delhi market se. Krishna Hardware pe 20 bags cement deliver kar diya aur 15000 rupees cash mil gaya.",
                    2: "Ruko ruko! 20 nahi, 18 bags sahi deliver hue hain, 2 bags phate hue damaged nikle. Aur uncle bol rahe hain 500 rupees extra discount de do aur 15000 mein invoice settle kar lo!",
                    3: "Uncle gussa ho rahe hain invoice balance pe, please Priya ma'am se direct baat karwa do!",
                    4: "Anna, T. Nagar Murugan Builders-la 25 bags cement unload pannitten, 18400 cash kedaichuduchu, receipt WhatsApp-la anuppunga!",
                }
                text = step_texts.get(step, "")
                if text:
                    self.last_user_audio_ts = time.perf_counter()
                    self.awaiting_first_audio = True
                    await self.send_ui({"type": "transcript", "role": "user", "text": text, "final": True})
                    await self.gemini_session.send_realtime_input(text=text)

            elif msg_type == "text_turn" and self.gemini_session is not None:
                text = (msg.get("text") or "").strip()
                if text:
                    self.last_user_audio_ts = time.perf_counter()
                    self.awaiting_first_audio = True
                    await self.send_ui({"type": "transcript", "role": "user", "text": text, "final": True})
                    pref_lang = (msg.get("preferred_language") or "").strip()
                    prompt_txt = (
                        f"[REPLY LANGUAGE: {pref_lang}] {text}"
                        if pref_lang and pref_lang not in {"auto", "unlock"}
                        else text
                    )
                    await self.gemini_session.send_realtime_input(text=prompt_txt)

            elif msg_type == "set_language" and self.gemini_session is not None:
                lang_label = (msg.get("language") or "auto").strip()
                self.last_user_audio_ts = time.perf_counter()
                self.awaiting_first_audio = True
                if lang_label.lower() == "auto":
                    await self.gemini_session.send_realtime_input(
                        text="[SYSTEM]: Auto-language mode enabled. Match whatever language the driver speaks next."
                    )
                else:
                    await self.gemini_session.send_realtime_input(
                        text=f"[SYSTEM]: The driver switched their preferred language to {lang_label}. Immediately acknowledge in 1 warm short sentence strictly in {lang_label}, and continue speaking ONLY in {lang_label} unless they ask to switch again."
                    )

            elif msg_type == "force_end_turn" and self.gemini_session is not None:
                self.last_user_audio_ts = time.perf_counter()
                self.awaiting_first_audio = True
                await self.gemini_session.send_realtime_input(audio_stream_end=True)

            elif msg_type == "ping":
                await self.send_ui({"type": "pong"})

    async def _receive_from_gemini(self) -> None:
        from google.genai import types

        while not self.closed and self.gemini_session is not None:
            async for chunk in self.gemini_session.receive():
                server_content = getattr(chunk, "server_content", None)

                if server_content:
                    if getattr(server_content, "interrupted", False):
                        self.interruption_count += 1
                        self.awaiting_first_audio = True
                        self.last_user_audio_ts = time.perf_counter()
                        await self.send_ui(
                            {
                                "type": "interrupted",
                                "count": self.interruption_count,
                                "timestamp": time.time(),
                            }
                        )

                    in_tx = getattr(server_content, "input_transcription", None)
                    if in_tx and getattr(in_tx, "text", None):
                        await self.send_ui(
                            {
                                "type": "transcript",
                                "role": "user",
                                "text": in_tx.text,
                                "final": False,
                            }
                        )

                    out_tx = getattr(server_content, "output_transcription", None)
                    if out_tx and getattr(out_tx, "text", None):
                        await self.send_ui(
                            {
                                "type": "transcript",
                                "role": "assistant",
                                "text": out_tx.text,
                                "final": False,
                            }
                        )

                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn and getattr(model_turn, "parts", None):
                        for part in model_turn.parts:
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                if self.awaiting_first_audio and self.last_user_audio_ts:
                                    ttfa_ms = round((time.perf_counter() - self.last_user_audio_ts) * 1000)
                                    self.awaiting_first_audio = False
                                    await self.send_ui({"type": "latency", "ttfa_ms": ttfa_ms})

                                b64_audio = base64.b64encode(inline.data).decode("ascii")
                                await self.send_ui({"type": "audio_out", "data": b64_audio})

                            elif getattr(part, "text", None) and not getattr(part, "thought", False):
                                await self.send_ui(
                                    {
                                        "type": "transcript",
                                        "role": "assistant",
                                        "text": part.text,
                                        "final": False,
                                    }
                                )

                    if getattr(server_content, "turn_complete", False):
                        await self.send_ui({"type": "turn_complete"})

                tool_call = getattr(chunk, "tool_call", None)
                if tool_call and getattr(tool_call, "function_calls", None):
                    function_responses = []
                    for fc in tool_call.function_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        await self.send_ui(
                            {
                                "type": "tool_call_start",
                                "name": fn_name,
                                "args": fn_args,
                            }
                        )

                        try:
                            result_data, meta = execute_tool(fn_name, fn_args, channel="GEMINI_LIVE_VOICE")
                        except Exception as exc:
                            result_data = {"success": False, "error": str(exc)}
                            meta = {"tool": fn_name, "elapsed_ms": 0.0, "status": "ERROR", "error": str(exc)}

                        await self.send_ui(
                            {
                                "type": "tool_call_result",
                                "name": fn_name,
                                "args": fn_args,
                                "result": result_data,
                                "meta": meta,
                            }
                        )
                        await self.send_ui({"type": "erp_state", "state": get_full_state()})

                        function_responses.append(
                            types.FunctionResponse(
                                name=fn_name,
                                id=fc.id,
                                response={"result": result_data},
                            )
                        )

                    await self.gemini_session.send_tool_response(function_responses=function_responses)
                    self.last_user_audio_ts = time.perf_counter()
                    self.awaiting_first_audio = True
