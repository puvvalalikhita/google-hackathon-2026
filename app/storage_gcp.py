import base64
import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.security import compute_audit_hash, verify_audit_chain

try:
    from google.cloud import firestore, storage
except Exception:  # pragma: no cover - optional in bare local envs
    firestore = None
    storage = None


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


def is_firestore_enabled() -> bool:
    flag = os.getenv("USE_FIRESTORE", "").strip().lower()
    if flag in {"true", "1", "yes"}:
        return firestore is not None
    if flag in {"false", "0", "no"}:
        return False
    return False


def get_gcs_bucket_name() -> str:
    return os.getenv("GCS_PROOF_BUCKET", "").strip()


_gcs_client: Any = None
_fs_client: Any = None


def _get_gcs_client() -> Any:
    global _gcs_client
    if _gcs_client is None and storage is not None:
        proj = os.getenv("FIRESTORE_PROJECT", "").strip() or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip() or None
        _gcs_client = storage.Client(project=proj)
    return _gcs_client


def _get_fs_client() -> Any:
    global _fs_client
    if _fs_client is None and firestore is not None:
        proj = os.getenv("FIRESTORE_PROJECT", "").strip() or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip() or None
        db_name = os.getenv("FIRESTORE_DATABASE", "(default)").strip() or "(default)"
        _fs_client = firestore.Client(project=proj, database=db_name)
    return _fs_client


def upload_proof_to_gcs(data_url: str, customer_id: str) -> Tuple[str, Optional[str]]:
    """
    Uploads a data:image/...;base64,... proof image to the private GCS bucket when configured.
    Returns (display_url_or_data_url, gcs_uri_or_None).
    """
    bucket_name = get_gcs_bucket_name()
    if not bucket_name or storage is None or not data_url.startswith("data:image/"):
        return data_url, None

    try:
        header, b64_part = data_url.split(",", 1)
        mime_match = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64", header)
        mime = mime_match.group(1) if mime_match else "image/jpeg"
        ext = "png" if "png" in mime else ("webp" if "webp" in mime else "jpg")
        img_bytes = base64.b64decode(b64_part)

        safe_cust = re.sub(r"[^A-Za-z0-9_-]", "", customer_id or "CUST")
        proof_name = f"{safe_cust}_{uuid.uuid4().hex[:10]}.{ext}"
        blob_path = f"proofs/{proof_name}"

        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(img_bytes, content_type=mime)

        return f"/api/proofs/{proof_name}", f"gs://{bucket_name}/{blob_path}"
    except Exception:
        return data_url, None


def read_proof_from_gcs(proof_name: str) -> Optional[Tuple[bytes, str]]:
    bucket_name = get_gcs_bucket_name()
    if not bucket_name or storage is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", proof_name):
        return None
    try:
        client = _get_gcs_client()
        blob = client.bucket(bucket_name).blob(f"proofs/{proof_name}")
        if not blob.exists():
            return None
        content = blob.download_as_bytes()
        mime = blob.content_type or ("image/png" if proof_name.endswith(".png") else "image/jpeg")
        return content, mime
    except Exception:
        return None


class FirestoreStore:
    """
    ACID transactional Firestore + GCS storage layer for DeliverEx Live.
    Uses single-field queries and in-memory sorting for bounded operational sets
    so zero composite indexes are required.
    """

    def __init__(self) -> None:
        self.db = _get_fs_client()

    def check_health(self) -> Dict[str, Any]:
        try:
            docs = list(self.db.collection("customers").limit(10).stream())
            bucket_name = get_gcs_bucket_name()
            return {
                "ok": True,
                "backend": "firestore",
                "database": os.getenv("FIRESTORE_DATABASE", "(default)"),
                "gcs_bucket": bucket_name or None,
                "persistent_path_configured": True,
                "customers_seeded": len(docs),
            }
        except Exception as exc:
            return {"ok": False, "backend": "firestore", "error": str(exc)}

    def _delete_collection(self, name: str) -> None:
        batch = self.db.batch()
        count = 0
        for doc in self.db.collection(name).stream():
            batch.delete(doc.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
        if count > 0:
            batch.commit()

    def _append_audit_in_tx(
        self,
        tx: Any,
        *,
        actor: str,
        role: str,
        action: str,
        target_id: str,
        summary: str,
        before_obj: Any = None,
        after_obj: Any = None,
    ) -> Dict[str, Any]:
        meta_ref = self.db.collection("system_meta").document("audit_head")
        meta_snap = meta_ref.get(transaction=tx)
        meta_data = meta_snap.to_dict() if meta_snap.exists else {}
        prev_hash = meta_data.get("last_hash") or "GENESIS"
        seq = int(meta_data.get("seq") or 0) + 1
        now = _now_iso()
        audit_id = f"AUD-{seq:05d}"

        import json

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
        tx.set(self.db.collection("audit_logs").document(audit_id), rec)
        tx.set(meta_ref, {"last_hash": rec["integrity_hash"], "seq": seq, "updated_at": now})
        return rec

    def append_audit_log(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        target_id: str,
        summary: str,
        before_obj: Any = None,
        after_obj: Any = None,
    ) -> Dict[str, Any]:
        @firestore.transactional
        def _run(tx: Any) -> Dict[str, Any]:
            return self._append_audit_in_tx(
                tx,
                actor=actor,
                role=role,
                action=action,
                target_id=target_id,
                summary=summary,
                before_obj=before_obj,
                after_obj=after_obj,
            )

        return _run(self.db.transaction())

    def get_audit_logs(self, limit: int = 30) -> Dict[str, Any]:
        all_docs = [d.to_dict() for d in self.db.collection("audit_logs").stream()]
        all_docs.sort(key=lambda x: int(x.get("seq") or 0))
        chain_ok = verify_audit_chain(all_docs)
        recent = list(reversed(all_docs[-limit:]))
        return {
            "entries": recent,
            "total_count": len(all_docs),
            "chain_verified": chain_ok,
            "storage_backend": "firestore",
        }

    def init_seed(self, seed_payload: Dict[str, Any], force_reset: bool = False) -> None:
        if force_reset:
            for col in (
                "customers",
                "inventory",
                "ledger_entries",
                "approvals",
                "receipts",
                "insights",
                "whatsapp_messages",
                "whatsapp_sessions",
                "idempotency_keys",
                "audit_logs",
                "system_meta",
            ):
                self._delete_collection(col)

        existing = list(self.db.collection("customers").limit(1).stream())
        if not existing:
            batch = self.db.batch()
            for c in seed_payload["customers"]:
                batch.set(self.db.collection("customers").document(c["customer_id"]), c)
            for inv in seed_payload["inventory"]:
                batch.set(self.db.collection("inventory").document(inv["sku_code"]), inv)
            for led in seed_payload["ledger"]:
                batch.set(self.db.collection("ledger_entries").document(led["entry_id"]), led)
            for ins in seed_payload["insights"]:
                batch.set(self.db.collection("insights").document(f"INS-{ins['insight_id']:04d}"), ins)
            batch.commit()

        wa_existing = list(self.db.collection("whatsapp_messages").limit(1).stream())
        if not wa_existing:
            for wm in seed_payload["whatsapp_messages"]:
                self.db.collection("whatsapp_messages").document(wm["msg_id"]).set(wm)

        audit_existing = list(self.db.collection("audit_logs").limit(1).stream())
        if not audit_existing:
            self.append_audit_log(
                actor="System",
                role="SYSTEM",
                action="SYSTEM_RESET" if force_reset else "SYSTEM_INIT",
                target_id="deliverex-erp",
                summary="Initialized Firestore ledger, warehouse inventory & SOP guardrails",
            )

    def get_full_state(self) -> Dict[str, Any]:
        customers = [d.to_dict() for d in self.db.collection("customers").stream()]
        customers.sort(key=lambda x: x.get("customer_id", ""))

        inventory = [d.to_dict() for d in self.db.collection("inventory").stream()]
        inventory.sort(key=lambda x: x.get("sku_code", ""))

        ledger = [d.to_dict() for d in self.db.collection("ledger_entries").stream()]
        ledger.sort(key=lambda x: (x.get("timestamp", ""), x.get("entry_id", "")), reverse=True)

        approvals = [d.to_dict() for d in self.db.collection("approvals").stream()]
        approvals.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        receipts = [d.to_dict() for d in self.db.collection("receipts").stream()]
        receipts.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        insights = [d.to_dict() for d in self.db.collection("insights").stream()]
        insights.sort(key=lambda x: int(x.get("insight_id") or 0), reverse=True)

        wa_msgs = [d.to_dict() for d in self.db.collection("whatsapp_messages").stream()]
        wa_msgs.sort(key=lambda x: (x.get("seq_ts", 0), x.get("created_at", ""), x.get("msg_id", "")))

        audit_info = self.get_audit_logs(limit=15)

        return {
            "customers": customers,
            "inventory": inventory,
            "ledger": ledger[:20],
            "approvals": approvals[:20],
            "receipts": receipts[:10],
            "insights": insights[:15],
            "whatsapp_messages": wa_msgs[-60:],
            "whatsapp_session": self.get_whatsapp_session("default"),
            "audit_summary": {
                "total_count": audit_info["total_count"],
                "chain_verified": audit_info["chain_verified"],
                "storage_backend": "firestore",
                "latest": audit_info["entries"][:5],
            },
        }

    def find_customer(self, query: str) -> Optional[Dict[str, Any]]:
        q = (query or "").strip().lower()
        for doc in self.db.collection("customers").stream():
            r = doc.to_dict()
            haystack = f"{r['customer_id']} {r['name']} {r['aliases']} {r['location']}".lower()
            if q in haystack or any(tok in haystack for tok in q.split() if len(tok) >= 4):
                return r
        return None

    def add_whatsapp_message(
        self,
        sender: str,
        body: str,
        msg_type: str = "text",
        driver_name: str = "Raju Kumar",
        media_data_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        msg_id = f"WA-{uuid.uuid4().hex[:8].upper()}"
        now = _now_iso()
        stored_media = media_data_url
        gcs_uri = None
        if media_data_url and media_data_url.startswith("data:image/"):
            stored_media, gcs_uri = upload_proof_to_gcs(media_data_url, "WA_MEDIA")
        meta = dict(metadata or {})
        if gcs_uri:
            meta["gcs_uri"] = gcs_uri
        item = {
            "msg_id": msg_id,
            "created_at": now,
            "seq_ts": datetime.now(timezone.utc).timestamp(),
            "sender": sender,
            "driver_name": driver_name,
            "msg_type": msg_type,
            "body": body,
            "media_data_url": stored_media,
            "metadata": meta,
        }
        self.db.collection("whatsapp_messages").document(msg_id).set(item)
        return item

    def get_whatsapp_session(self, session_id: str = "default") -> Dict[str, Any]:
        snap = self.db.collection("whatsapp_sessions").document(session_id).get()
        if not snap.exists:
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
        return snap.to_dict()

    def save_whatsapp_session(
        self,
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
        item = {
            "session_id": session_id,
            "driver_name": driver_name,
            "active_customer_id": active_customer_id,
            "active_customer_name": active_customer_name,
            "workflow_stage": workflow_stage,
            "pending_draft": pending_draft or {},
            "last_msg_hash": last_msg_hash,
            "last_msg_ts": float(last_msg_ts or 0.0),
            "turn_count": int(turn_count or 0),
            "updated_at": _now_iso(),
        }
        self.db.collection("whatsapp_sessions").document(session_id).set(item)
        return item

    def tx_attach_visual_proof(
        self,
        *,
        customer_id: str,
        data_url: str,
        damaged_bags: int,
        auto_create_approval: bool,
        driver_name: str,
    ) -> Optional[str]:
        stored_img, gcs_uri = upload_proof_to_gcs(data_url, customer_id)
        pending_docs = [
            d.to_dict()
            for d in self.db.collection("approvals").where("customer_id", "==", customer_id).stream()
            if d.to_dict().get("status") == "PENDING"
        ]
        pending_docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        existing_id = pending_docs[0]["approval_id"] if pending_docs else None

        @firestore.transactional
        def _run(tx: Any) -> Optional[str]:
            cust_ref = self.db.collection("customers").document(customer_id)
            cust = cust_ref.get(transaction=tx).to_dict()
            inv_ref = self.db.collection("inventory").document(cust["sku_code"])
            inv = inv_ref.get(transaction=tx).to_dict()
            now = _now_iso()

            if existing_id:
                apr_ref = self.db.collection("approvals").document(existing_id)
                apr = apr_ref.get(transaction=tx).to_dict()
                prev_dmg = _safe_int(apr.get("damaged_qty"), 0)
                new_dmg = max(prev_dmg, _safe_int(damaged_bags, 0))
                dmg_delta = max(0, new_dmg - prev_dmg)
                tx.update(apr_ref, {"proof_image": stored_img, "proof_gcs_uri": gcs_uri, "damaged_qty": new_dmg})
                if dmg_delta > 0:
                    tx.update(
                        inv_ref,
                        {
                            "warehouse_stock": max(0, int(inv["warehouse_stock"]) - dmg_delta),
                            "damaged_quarantine": int(inv["damaged_quarantine"]) + dmg_delta,
                            "updated_at": now,
                        },
                    )
                self._append_audit_in_tx(
                    tx,
                    actor=driver_name,
                    role="DRIVER",
                    action="PROOF_ATTACHED",
                    target_id=existing_id,
                    summary=f"Attached visual damage proof to {existing_id} ({cust['name']})",
                    after_obj={"damaged_qty": new_dmg, "gcs_uri": gcs_uri},
                )
                return existing_id

            if not auto_create_approval:
                return None

            attached_to = _short_id("APR")
            dmg = max(1, _safe_int(damaged_bags, 2))
            summary = f"{cust['name']} ({cust['pending_invoice_id']}): {dmg} torn/damaged bags visually verified via field camera — moved to quarantine"
            tx.set(
                self.db.collection("approvals").document(attached_to),
                {
                    "approval_id": attached_to,
                    "created_at": now,
                    "decided_at": None,
                    "driver_name": driver_name or "Raju Kumar",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "entry_id": None,
                    "exception_type": "DAMAGED_GOODS",
                    "policy_ref": "SOP-5.1",
                    "summary": summary,
                    "discount_requested": 0,
                    "damaged_qty": dmg,
                    "proof_image": stored_img,
                    "proof_gcs_uri": gcs_uri,
                    "manager_name": "Priya Sharma (Area Manager)",
                    "status": "PENDING",
                },
            )
            tx.update(
                inv_ref,
                {
                    "warehouse_stock": max(0, int(inv["warehouse_stock"]) - dmg),
                    "damaged_quarantine": int(inv["damaged_quarantine"]) + dmg,
                    "updated_at": now,
                },
            )
            ins_id = int(datetime.now(timezone.utc).timestamp() * 1000) % 100000000
            tx.set(
                self.db.collection("insights").document(f"INS-{ins_id}"),
                {
                    "insight_id": ins_id,
                    "created_at": now,
                    "route": cust["route"],
                    "category": "DAMAGED_GOODS",
                    "severity": "HIGH",
                    "title": f"Visual Damage Verified at {cust['name']} ({dmg} bags torn)",
                    "detail": f"Field camera captured {dmg} torn {cust['sku_code']} bags at {cust['name']} ({cust['location']}). Routed to Priya Sharma under SOP-5.1.",
                },
            )
            self._append_audit_in_tx(
                tx,
                actor=driver_name,
                role="DRIVER",
                action="PROOF_ATTACHED",
                target_id=attached_to,
                summary=f"Created SOP-5.1 approval {attached_to} with visual proof for {cust['name']}",
                after_obj={"damaged_qty": dmg, "gcs_uri": gcs_uri},
            )
            return attached_to

        return _run(self.db.transaction())

    def tx_log_damaged_bags(
        self,
        *,
        customer_id: str,
        damaged_bags: int,
        driver_name: str,
        notes: str,
        proof_data_url: Optional[str],
    ) -> str:
        stored_img = proof_data_url
        gcs_uri = None
        if proof_data_url and proof_data_url.startswith("data:image/"):
            stored_img, gcs_uri = upload_proof_to_gcs(proof_data_url, customer_id)

        pending_docs = [
            d.to_dict()
            for d in self.db.collection("approvals").where("customer_id", "==", customer_id).stream()
            if d.to_dict().get("status") == "PENDING"
        ]
        pending_docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        existing_id = pending_docs[0]["approval_id"] if pending_docs else None

        @firestore.transactional
        def _run(tx: Any) -> str:
            cust = self.db.collection("customers").document(customer_id).get(transaction=tx).to_dict()
            inv_ref = self.db.collection("inventory").document(cust["sku_code"])
            inv = inv_ref.get(transaction=tx).to_dict()
            now = _now_iso()
            dmg = max(1, _safe_int(damaged_bags, 1))

            if existing_id:
                apr_ref = self.db.collection("approvals").document(existing_id)
                apr = apr_ref.get(transaction=tx).to_dict()
                prev_dmg = _safe_int(apr.get("damaged_qty"), 0)
                new_dmg = max(prev_dmg, dmg)
                dmg_delta = max(0, new_dmg - prev_dmg)
                updates: Dict[str, Any] = {
                    "damaged_qty": new_dmg,
                    "summary": f"{cust['name']} ({cust['pending_invoice_id']}): {notes}",
                }
                if not apr.get("proof_image") and stored_img:
                    updates["proof_image"] = stored_img
                    updates["proof_gcs_uri"] = gcs_uri
                tx.update(apr_ref, updates)
                if dmg_delta > 0:
                    tx.update(
                        inv_ref,
                        {
                            "warehouse_stock": max(0, int(inv["warehouse_stock"]) - dmg_delta),
                            "damaged_quarantine": int(inv["damaged_quarantine"]) + dmg_delta,
                            "updated_at": now,
                        },
                    )
                approval_id = existing_id
            else:
                approval_id = _short_id("APR")
                tx.set(
                    self.db.collection("approvals").document(approval_id),
                    {
                        "approval_id": approval_id,
                        "created_at": now,
                        "decided_at": None,
                        "driver_name": driver_name,
                        "customer_id": cust["customer_id"],
                        "customer_name": cust["name"],
                        "entry_id": None,
                        "exception_type": "DAMAGED_GOODS",
                        "policy_ref": "SOP-5.1",
                        "summary": f"{cust['name']} ({cust['pending_invoice_id']}): {notes}",
                        "discount_requested": 0,
                        "damaged_qty": dmg,
                        "proof_image": stored_img,
                        "proof_gcs_uri": gcs_uri,
                        "manager_name": "Priya Sharma (Area Manager)",
                        "status": "PENDING",
                    },
                )
                tx.update(
                    inv_ref,
                    {
                        "warehouse_stock": max(0, int(inv["warehouse_stock"]) - dmg),
                        "damaged_quarantine": int(inv["damaged_quarantine"]) + dmg,
                        "updated_at": now,
                    },
                )
                ins_id = int(datetime.now(timezone.utc).timestamp() * 1000) % 100000000
                tx.set(
                    self.db.collection("insights").document(f"INS-{ins_id}"),
                    {
                        "insight_id": ins_id,
                        "created_at": now,
                        "route": cust["route"],
                        "category": "DAMAGED_GOODS",
                        "severity": "HIGH",
                        "title": f"Damaged Bags Logged at {cust['name']} ({dmg} bags torn)",
                        "detail": f"{dmg} torn {cust['sku_code']} bags logged at {cust['name']} ({cust['location']}). Escalated under SOP-5.1.",
                    },
                )

            self._append_audit_in_tx(
                tx,
                actor=driver_name,
                role="DRIVER",
                action="DAMAGE_LOGGED",
                target_id=approval_id,
                summary=f"Logged {dmg} damaged bags at {cust['name']} (SOP-5.1)",
                after_obj={"damaged_bags": dmg, "approval_id": approval_id},
            )
            return approval_id

        return _run(self.db.transaction())

    def tx_record_delivery(
        self,
        *,
        customer_id: str,
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
        idem_key = idempotency_key or hashlib.sha256(
            f"{customer_id}|{delivered}|{damaged}|{cash}|{discount}|{channel}".encode("utf-8")
        ).hexdigest()[:24]

        stored_img = proof_data_url
        gcs_uri = None
        if proof_data_url and proof_data_url.startswith("data:image/"):
            stored_img, gcs_uri = upload_proof_to_gcs(proof_data_url, customer_id)

        unlinked_docs = [
            d.to_dict()
            for d in self.db.collection("approvals").where("customer_id", "==", customer_id).stream()
            if d.to_dict().get("status") == "PENDING"
            and d.to_dict().get("entry_id") is None
            and d.to_dict().get("exception_type") == "DAMAGED_GOODS"
        ]
        unlinked_docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        unlinked_id = unlinked_docs[0]["approval_id"] if unlinked_docs else None

        @firestore.transactional
        def _run(tx: Any) -> Dict[str, Any]:
            idem_ref = self.db.collection("idempotency_keys").document(idem_key)
            idem_snap = idem_ref.get(transaction=tx)
            if idem_snap.exists:
                cached = idem_snap.to_dict() or {}
                age_sec = datetime.now(timezone.utc).timestamp() - float(cached.get("created_ts") or 0)
                if age_sec < 12.0 and cached.get("result"):
                    res = dict(cached["result"])
                    res["idempotent_replay"] = True
                    return res

            cust_ref = self.db.collection("customers").document(customer_id)
            cust = cust_ref.get(transaction=tx).to_dict()
            inv_ref = self.db.collection("inventory").document(cust["sku_code"])
            inv = inv_ref.get(transaction=tx).to_dict()

            unlinked_apr = (
                self.db.collection("approvals").document(unlinked_id).get(transaction=tx).to_dict()
                if unlinked_id
                else None
            )
            already_quarantined = _safe_int(unlinked_apr.get("damaged_qty"), 0) if unlinked_apr else 0
            net_new_damaged = max(0, damaged - already_quarantined)

            needs_approval = discount > 200 or damaged > 0
            now = _now_iso()
            entry_id = _short_id("TALLY")
            tally_status = "PARTIAL_PENDING_APPROVAL" if needs_approval else "SYNCED_TALLY"

            tx.set(
                self.db.collection("ledger_entries").document(entry_id),
                {
                    "entry_id": entry_id,
                    "timestamp": now,
                    "driver_name": driver_name,
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "invoice_id": cust["pending_invoice_id"],
                    "sku_code": cust["sku_code"],
                    "delivered_qty": delivered,
                    "damaged_qty": damaged,
                    "cash_received": cash,
                    "discount_amount": 0 if needs_approval else discount,
                    "channel": channel,
                    "tally_status": tally_status,
                    "notes": notes,
                },
            )

            tx.update(
                inv_ref,
                {
                    "warehouse_stock": max(0, int(inv["warehouse_stock"]) - (delivered + net_new_damaged)),
                    "damaged_quarantine": int(inv["damaged_quarantine"]) + net_new_damaged,
                    "updated_at": now,
                },
            )

            applied_discount = 0 if needs_approval else discount
            prev_balance = int(cust["balance_due"])
            new_balance = max(0, prev_balance - cash - applied_discount)
            new_status = (
                "PENDING_MANAGER_APPROVAL"
                if needs_approval
                else ("SETTLED" if new_balance == 0 else "PARTIAL_PAID")
            )
            tx.update(cust_ref, {"balance_due": new_balance, "status": new_status})

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
                    apr_ref = self.db.collection("approvals").document(approval_id)
                    updates: Dict[str, Any] = {
                        "driver_name": driver_name,
                        "entry_id": entry_id,
                        "exception_type": exc_type,
                        "policy_ref": policy_ref,
                        "summary": summary,
                        "discount_requested": discount,
                        "damaged_qty": effective_damaged,
                    }
                    if not unlinked_apr.get("proof_image") and stored_img:
                        updates["proof_image"] = stored_img
                        updates["proof_gcs_uri"] = gcs_uri
                    tx.update(apr_ref, updates)
                else:
                    approval_id = _short_id("APR")
                    tx.set(
                        self.db.collection("approvals").document(approval_id),
                        {
                            "approval_id": approval_id,
                            "created_at": now,
                            "decided_at": None,
                            "driver_name": driver_name,
                            "customer_id": cust["customer_id"],
                            "customer_name": cust["name"],
                            "entry_id": entry_id,
                            "exception_type": exc_type,
                            "policy_ref": policy_ref,
                            "summary": summary,
                            "discount_requested": discount,
                            "damaged_qty": effective_damaged,
                            "proof_image": stored_img,
                            "proof_gcs_uri": gcs_uri,
                            "manager_name": "Priya Sharma (Area Manager)",
                            "status": "PENDING",
                        },
                    )
                approval_payload = {
                    "approval_id": approval_id,
                    "policy_ref": policy_ref,
                    "summary": summary,
                    "manager": "Priya Sharma (Area Manager)",
                    "status": "PENDING",
                }
                if net_new_damaged > 0:
                    ins_id = int(datetime.now(timezone.utc).timestamp() * 1000) % 100000000
                    tx.set(
                        self.db.collection("insights").document(f"INS-{ins_id}"),
                        {
                            "insight_id": ins_id,
                            "created_at": now,
                            "route": cust["route"],
                            "category": "DAMAGED_GOODS",
                            "severity": "HIGH",
                            "title": f"Recurring Damage Alert on {cust['route']} ({damaged} more bags torn)",
                            "detail": f"Driver {driver_name} reported {damaged} damaged {cust['sku_code']} bags at {cust['name']}. Pattern detected — recommend auditing Warehouse Loader Shift B.",
                        },
                    )
            else:
                receipt_id = _short_id("RCPT")
                msg = (
                    f"DeliverEx Official Receipt ({receipt_id})\n"
                    f"Shop: {cust['name']} ({cust['pending_invoice_id']})\n"
                    f"Delivered: {delivered} bags | Cash: Rs {cash:,} | Discount: Rs {discount:,}\n"
                    f"Balance Due: Rs {new_balance:,} | Tally Ref: {entry_id}"
                )
                tx.set(
                    self.db.collection("receipts").document(receipt_id),
                    {
                        "receipt_id": receipt_id,
                        "created_at": now,
                        "driver_name": driver_name,
                        "customer_name": cust["name"],
                        "invoice_id": cust["pending_invoice_id"],
                        "delivered_qty": delivered,
                        "damaged_qty": damaged,
                        "cash_received": cash,
                        "discount_approved": discount,
                        "balance_remaining": new_balance,
                        "channel": channel,
                        "message_text": msg,
                    },
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

            self._append_audit_in_tx(
                tx,
                actor=driver_name,
                role="DRIVER",
                action="DELIVERY_RECORDED",
                target_id=entry_id,
                summary=f"{cust['name']}: {delivered} ok, {damaged} dmg, Rs {cash} cash ({tally_status})",
                before_obj={"balance_due": prev_balance, "warehouse_stock": int(inv["warehouse_stock"])},
                after_obj={"balance_due": new_balance, "tally_entry_id": entry_id, "status": tally_status},
            )
            tx.set(
                idem_ref,
                {"created_ts": datetime.now(timezone.utc).timestamp(), "result": result},
            )
            return result

        return _run(self.db.transaction())

    def tx_queue_handoff(
        self,
        *,
        customer_id: str,
        customer_name: str,
        driver_name: str,
        reason: str,
        proof_data_url: Optional[str],
    ) -> str:
        stored_img = proof_data_url
        gcs_uri = None
        if proof_data_url and proof_data_url.startswith("data:image/"):
            stored_img, gcs_uri = upload_proof_to_gcs(proof_data_url, customer_id)

        @firestore.transactional
        def _run(tx: Any) -> str:
            approval_id = _short_id("HANDOFF")
            now = _now_iso()
            tx.set(
                self.db.collection("approvals").document(approval_id),
                {
                    "approval_id": approval_id,
                    "created_at": now,
                    "decided_at": None,
                    "driver_name": driver_name,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "entry_id": None,
                    "exception_type": "LIVE_HANDOFF",
                    "policy_ref": "SOP-6.0",
                    "summary": reason,
                    "discount_requested": 0,
                    "damaged_qty": 0,
                    "proof_image": stored_img,
                    "proof_gcs_uri": gcs_uri,
                    "manager_name": "Priya Sharma (Area Manager)",
                    "status": "PENDING",
                },
            )
            self._append_audit_in_tx(
                tx,
                actor=driver_name,
                role="DRIVER",
                action="HANDOFF_REQUESTED",
                target_id=approval_id,
                summary=f"SOP-6.0 live handoff queued for {customer_name}: {reason}",
            )
            return approval_id

        return _run(self.db.transaction())

    def tx_decide_approval(self, approval_id: str, decision: str, actor: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        @firestore.transactional
        def _run(tx: Any) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
            apr_ref = self.db.collection("approvals").document(approval_id)
            apr_snap = apr_ref.get(transaction=tx)
            if not apr_snap.exists:
                raise ValueError(f"Approval {approval_id} not found")
            apr = apr_snap.to_dict()
            if apr.get("status") != "PENDING":
                raise ValueError(f"Approval {approval_id} is already {apr.get('status')}")

            now = _now_iso()
            tx.update(apr_ref, {"status": decision, "decided_at": now})
            apr["status"] = decision
            apr["decided_at"] = now

            receipt_payload = None
            cust_ref = self.db.collection("customers").document(apr["customer_id"])
            cust_snap = cust_ref.get(transaction=tx)
            cust = cust_snap.to_dict() if cust_snap.exists else None

            ledger_ref = self.db.collection("ledger_entries").document(apr["entry_id"]) if apr.get("entry_id") else None
            ledger_snap = ledger_ref.get(transaction=tx) if ledger_ref else None
            ledger = ledger_snap.to_dict() if (ledger_snap and ledger_snap.exists) else None

            if decision == "APPROVED" and cust and ledger:
                discount = int(apr.get("discount_requested") or 0)
                prev_bal = int(cust["balance_due"])
                new_balance = max(0, prev_bal - discount)
                tx.update(ledger_ref, {"discount_amount": discount, "tally_status": "SYNCED_TALLY_APPROVED"})
                tx.update(
                    cust_ref,
                    {"balance_due": new_balance, "status": "SETTLED" if new_balance == 0 else "PARTIAL_PAID"},
                )
                receipt_id = _short_id("RCPT")
                msg = (
                    f"DeliverEx Official Receipt ({receipt_id}) ✅\n"
                    f"Shop: {cust['name']} | Invoice: {cust['pending_invoice_id']}\n"
                    f"Delivered: {ledger['delivered_qty']} intact bags (Quarantined: {ledger['damaged_qty']})\n"
                    f"Cash Received: Rs {ledger['cash_received']:,} | Approved Discount: Rs {discount:,}\n"
                    f"Approved By: {actor}\n"
                    f"Balance Remaining: Rs {new_balance:,} | Tally Ref: {apr['entry_id']}"
                )
                tx.set(
                    self.db.collection("receipts").document(receipt_id),
                    {
                        "receipt_id": receipt_id,
                        "created_at": now,
                        "driver_name": apr["driver_name"],
                        "customer_name": cust["name"],
                        "invoice_id": cust["pending_invoice_id"],
                        "delivered_qty": ledger["delivered_qty"],
                        "damaged_qty": ledger["damaged_qty"],
                        "cash_received": ledger["cash_received"],
                        "discount_approved": discount,
                        "balance_remaining": new_balance,
                        "channel": "WHATSAPP_RECEIPT",
                        "message_text": msg,
                    },
                )
                receipt_payload = {"receipt_id": receipt_id, "message": msg, "balance_remaining": new_balance}
            elif decision == "REJECTED" and cust and ledger:
                tx.update(ledger_ref, {"tally_status": "DISCOUNT_REJECTED_BALANCE_OPEN"})
                tx.update(cust_ref, {"status": "PARTIAL_BALANCE_OPEN"})

            self._append_audit_in_tx(
                tx,
                actor=actor,
                role="OWNER",
                action="APPROVAL_DECIDED",
                target_id=approval_id,
                summary=f"{actor} {decision} {approval_id} for {apr['customer_name']}",
                before_obj={"status": "PENDING"},
                after_obj={"status": decision, "receipt_id": receipt_payload["receipt_id"] if receipt_payload else None},
            )
            return apr, receipt_payload

        return _run(self.db.transaction())
