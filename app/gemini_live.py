import asyncio
import base64
import json
import os
import time
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from app.database import get_full_state
from app.tools import GEMINI_TOOL_DECLARATIONS, execute_tool, set_latest_visual_proof

SYSTEM_INSTRUCTION = """You are DeliverEx Live AI — a fast, friendly, multimodal real-time frontline voice & vision operations agent for Indian MSME wholesale logistics (DeliverEx Logistics).

ROLE & STYLE:
- You speak directly with field delivery drivers (like Raju) standing in loud, busy wholesale markets (Old Delhi Mandi, Chennai T. Nagar) or driving trucks.
- Match the speaker's language naturally: fluent Hinglish (Hindi + English), Tanglish (Tamil + English), Hindi, Tamil, Marathi, or English. Default to warm, respectful Hinglish ("Ji Raju bhai..."), or switch instantaneously to Tanglish ("Seri anna...") if the driver speaks Tamil/Tanglish!
- Keep responses concise (1 to 3 short sentences) for sub-second voice turn-taking. Never read raw JSON.
- If the driver interrupts you mid-sentence, stop immediately, acknowledge the correction naturally ("Achha samajh gaya, 18 bags..."), and proceed with the updated numbers.

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
    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
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
                    f"Tally/SAP invoice is now SETTLED and official WhatsApp Receipt {receipt['receipt_id'] if receipt else ''} "
                    f"has been sent. Immediately inform Raju in upbeat, natural Hinglish!"
                )
            elif decision == "REJECTED":
                prompt = (
                    f"[SYSTEM UPDATE FROM AREA MANAGER PRIYA SHARMA]: Priya has REJECTED the Rs {apr['discount_requested']} "
                    f"extra discount for {apr['customer_name']}. Inform Raju politely in Hinglish that the extra discount "
                    f"was not approved and the remaining balance stays open on the customer's credit ledger."
                )
            else:
                prompt = (
                    f"[SYSTEM UPDATE]: Area Manager Priya Sharma is joining/taking over the call for {apr['customer_name']}. "
                    f"Inform Raju in Hinglish that you are connecting him directly to Priya ma'am now."
                )

            try:
                self.last_user_audio_ts = time.perf_counter()
                self.awaiting_first_audio = True
                await self.gemini_session.send_realtime_input(text=prompt)
            except Exception as exc:
                await self.send_ui({"type": "error", "message": f"Approval injection error: {exc}"})

    async def run(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model_name = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
        voice_name = os.getenv("GEMINI_VOICE_NAME", "Kore").strip()
        use_vertex = os.getenv("USE_VERTEX_AI", "false").strip().lower() == "true"

        await self.ws.accept()
        ACTIVE_SESSIONS.register(self)
        await self.send_ui({"type": "erp_state", "state": get_full_state()})

        if not api_key:
            await self.send_ui(
                {
                    "type": "status",
                    "mode": "DEMO_ONLY",
                    "connected": False,
                    "message": "GEMINI_API_KEY is not set in .env — use Interactive Demo Mode or add your key to enable Live Gemini Voice.",
                }
            )
            try:
                while True:
                    raw = await self.ws.receive_text()
                    data = json.loads(raw)
                    if data.get("type") == "ping":
                        await self.send_ui({"type": "pong"})
            except WebSocketDisconnect:
                pass
            finally:
                self.closed = True
                ACTIVE_SESSIONS.unregister(self)
            return

        if use_vertex:
            client = genai.Client(vertexai=True, api_key=api_key)
            candidate_models = [
                model_name,
                "gemini-live-2.5-flash-native-audio",
                "gemini-3.8-live",
            ]
        else:
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
            candidate_models = [
                model_name,
                "gemini-3.8-live",
                "gemini-3.1-flash-live-preview",
                "gemini-2.5-flash-native-audio-latest",
                "gemini-2.5-flash-native-audio-preview-12-2025",
            ]
        # Preserve order & remove duplicates
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m]))

        config: Dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "system_instruction": SYSTEM_INSTRUCTION,
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

                    async with client.aio.live.connect(model=active_model, config=config) as session:
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

                        # Proactively greet Raju in Hinglish as soon as the live call connects
                        self.last_user_audio_ts = time.perf_counter()
                        self.awaiting_first_audio = True
                        await session.send_realtime_input(
                            text="[CALL CONNECTED]: Driver Raju just started the call. Greet him in 1 short friendly Hinglish sentence: 'Namaste Raju bhai, DeliverEx Live bol raha hoon — bataiye kis shop pe delivery hui?'"
                        )

                        done, pending = await asyncio.wait(
                            [recv_task, send_task], return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                        for task in done:
                            if not task.cancelled() and task.exception():
                                raise task.exception()
                    break
                except WebSocketDisconnect:
                    raise
                except Exception as exc:
                    last_err = exc
                    if connected_once:
                        raise
                    # Try next candidate model if initial handshake failed
                    continue

            if not connected_once and last_err is not None:
                raise last_err

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            await self.send_ui(
                {
                    "type": "error",
                    "message": f"Gemini Live connection failed: {exc}. If using Vertex AI Express, verify Live API access or use a Google AI Studio key (AIza...) in .env.",
                }
            )
        finally:
            self.closed = True
            self.gemini_session = None
            ACTIVE_SESSIONS.unregister(self)

    async def _receive_from_browser(self) -> None:
        while not self.closed:
            raw = await self.ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "audio_chunk" and self.gemini_session is not None:
                pcm_bytes = base64.b64decode(msg["data"])
                # Track end-of-speech timestamp for latency measurement when voice activity is detected
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

            elif msg_type == "text_turn" and self.gemini_session is not None:
                text = (msg.get("text") or "").strip()
                if text:
                    self.last_user_audio_ts = time.perf_counter()
                    self.awaiting_first_audio = True
                    await self.send_ui({"type": "transcript", "role": "user", "text": text, "final": True})
                    await self.gemini_session.send_realtime_input(text=text)

            elif msg_type == "force_end_turn" and self.gemini_session is not None:
                self.last_user_audio_ts = time.perf_counter()
                self.awaiting_first_audio = True
                await self.gemini_session.send_realtime_input(audio_stream_end=True)

            elif msg_type == "ping":
                await self.send_ui({"type": "pong"})

    async def _receive_from_gemini(self) -> None:
        while not self.closed and self.gemini_session is not None:
            async for chunk in self.gemini_session.receive():
                server_content = getattr(chunk, "server_content", None)

                if server_content:
                    # 1. Mid-sentence barge-in / interruption detected by Gemini Live API!
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

                    # 2. Input audio transcription (Raju's spoken Hinglish/regional speech)
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

                    # 3. Output audio transcription (AI's spoken response)
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

                    # 4. Native 24kHz PCM audio chunks
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

                # 5. Live Function / Tool Calling during voice conversation
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

                        result_data, meta = execute_tool(fn_name, fn_args, channel="GEMINI_LIVE_VOICE")

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
