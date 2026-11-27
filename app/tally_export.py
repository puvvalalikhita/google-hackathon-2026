import csv
import io
from html import escape
from typing import Any, Dict, List


def build_tally_prime_xml(ledger_entries: List[Dict[str, Any]], company_name: str = "DeliverEx Wholesale Pvt Ltd") -> str:
    """
    Generates a TallyPrime-compatible XML Import Envelope containing Receipt & Sales
    vouchers for all synced/approved ledger entries.
    """
    vouchers: List[str] = []
    for row in ledger_entries:
        status = str(row.get("tally_status") or "")
        if "REJECTED" in status:
            continue
        ts_raw = str(row.get("timestamp") or "2026-11-21 00:00:00")
        tally_date = ts_raw[:10].replace("-", "")
        party = escape(str(row.get("customer_name") or "Cash Customer"))
        invoice_id = escape(str(row.get("invoice_id") or ""))
        entry_id = escape(str(row.get("entry_id") or ""))
        driver = escape(str(row.get("driver_name") or "Raju Kumar"))
        cash = int(row.get("cash_received") or 0)
        discount = int(row.get("discount_amount") or 0)
        delivered = int(row.get("delivered_qty") or 0)
        damaged = int(row.get("damaged_qty") or 0)
        narration = escape(
            f"DeliverEx Auto-Sync [{entry_id}] | Inv: {invoice_id} | Driver: {driver} | "
            f"Intact: {delivered} bags, Damaged: {damaged} bags | Status: {status}"
        )

        vouchers.append(
            f"""      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="Receipt" ACTION="Create" OBJVIEW="Accounting Voucher View">
          <DATE>{tally_date}</DATE>
          <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
          <VOUCHERNUMBER>{entry_id}</VOUCHERNUMBER>
          <REFERENCE>{invoice_id}</REFERENCE>
          <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
          <NARRATION>{narration}</NARRATION>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{party}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>{cash + discount:.2f}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Cash-in-Hand (Field Route)</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>-{cash:.2f}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Spot Cash Discount Allowed</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>-{discount:.2f}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>"""
        )

    body = "\n".join(vouchers)
    return (
        f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape(company_name)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
{body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>
"""
    )


def build_ledger_csv(ledger_entries: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Entry ID",
            "Timestamp",
            "Driver",
            "Customer ID",
            "Customer Name",
            "Invoice ID",
            "SKU Code",
            "Delivered Qty",
            "Damaged Qty",
            "Cash Received (INR)",
            "Discount (INR)",
            "Channel",
            "Tally Status",
            "Notes",
        ]
    )
    for row in ledger_entries:
        writer.writerow(
            [
                row.get("entry_id", ""),
                row.get("timestamp", ""),
                row.get("driver_name", ""),
                row.get("customer_id", ""),
                row.get("customer_name", ""),
                row.get("invoice_id", ""),
                row.get("sku_code", ""),
                row.get("delivered_qty", 0),
                row.get("damaged_qty", 0),
                row.get("cash_received", 0),
                row.get("discount_amount", 0),
                row.get("channel", ""),
                row.get("tally_status", ""),
                row.get("notes", ""),
            ]
        )
    return buf.getvalue()
