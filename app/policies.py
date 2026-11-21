from typing import Any, Dict, List

COMPANY_POLICIES: List[Dict[str, Any]] = [
    {
        "id": "SOP-4.2",
        "title": "Spot Discount & Settlement Authority",
        "category": "discount",
        "keywords": ["discount", "chhoot", "less", "settle", "rebate", "500", "200", "price", "maaf"],
        "rule": (
            "Field delivery agents may auto-approve spot cash discounts up to Rs 200 per invoice. "
            "Any discount above Rs 200 MUST be escalated to Area Manager Priya Sharma for 1-tap approval "
            "before closing the invoice in Tally/SAP."
        ),
        "auto_limit_inr": 200,
        "escalation_owner": "Priya Sharma (Area Manager)",
    },
    {
        "id": "SOP-5.1",
        "title": "Damaged Goods & Short Delivery Protocol",
        "category": "damage",
        "keywords": ["damage", "damaged", "phata", "phate", "torn", "broken", "kharab", "short", "missing", "leak"],
        "rule": (
            "If 1 or more bags are damaged/torn during transit, log only intact delivered bags against "
            "the customer invoice, move damaged bags to Warehouse Quarantine stock, and trigger a "
            "Manager Approval & Quality Insight flag for Route QA."
        ),
        "escalation_owner": "Priya Sharma (Area Manager)",
    },
    {
        "id": "SOP-2.3",
        "title": "Cash Collection & Ledger Posting",
        "category": "cash",
        "keywords": ["cash", "payment", "paise", "rupees", "ledger", "tally", "sap", "invoice", "credit"],
        "rule": (
            "Cash collections up to Rs 50,000 that match or partially settle an open invoice are "
            "posted immediately to Tally/SAP Ledger. An official WhatsApp confirmation receipt must "
            "be sent to both the driver and customer within 10 seconds."
        ),
        "auto_limit_inr": 50000,
        "escalation_owner": "Accounts Desk",
    },
    {
        "id": "SOP-6.0",
        "title": "Live Human Handoff & Dispute Escalation",
        "category": "handoff",
        "keywords": ["dispute", "angry", "manager", "baat", "complaint", "escalate", "handoff", "supervisor"],
        "rule": (
            "If a shop owner disputes pricing, refuses payment, or sounds frustrated, immediately "
            "offer a warm handoff to Area Manager Priya Sharma with full call summary attached."
        ),
        "escalation_owner": "Priya Sharma (Area Manager)",
    },
]


def lookup_policies(query: str) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    matched = []
    for p in COMPANY_POLICIES:
        if any(k in q for k in p["keywords"]) or p["category"] in q or p["id"].lower() in q:
            matched.append(p)
    if not matched:
        # Return core discount + damage policies as default grounding
        return COMPANY_POLICIES[:2]
    return matched
