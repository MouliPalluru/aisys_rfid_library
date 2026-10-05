"""
RFID Library Management System - FastAPI prototype backend (single file)
=========================================================================
Run:     pip install fastapi uvicorn
         uvicorn main:app --reload
Docs:    http://127.0.0.1:8000/docs

Sections
  1. Config & business-rule constants
  2. Domain models + in-memory store (swap for SQLAlchemy / the SQL DDL later)
  3. Services (circulation, gate security, inventory audit)
  4. Protocol adapters (NCIP 2.0 mock, SIP2 mock)
  5. API routes

NOTE: the in-memory store is not thread-safe and resets on restart.
      It is a prototype stand-in for the PostgreSQL schema.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

# =============================================================================
# 1. CONFIG & BUSINESS RULES
# =============================================================================
LOAN_DAYS = 14                  # standard loan period
MAX_LOANS = 5                   # max simultaneous loans per member
FINE_PER_DAY = 2.0              # overdue fine per day
FINE_LIMIT = 500.0              # checkout denied once outstanding fines >= this
SECURITY_EMAIL = "security@library.example"
INSTITUTION_ID = "LIB01"        # SIP2 AO field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BusinessRuleError(Exception):
    """Raised when a business rule is violated; mapped to an HTTP error below."""

    def __init__(self, code: str, message: str, status_code: int = 409):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


# =============================================================================
# 2. DOMAIN MODELS + IN-MEMORY STORE
# =============================================================================
@dataclass
class Member:
    member_id: int
    name: str
    email: str
    blocked: bool = False
    block_reason: Optional[str] = None
    outstanding_fines: float = 0.0


@dataclass
class Title:
    title_id: int
    title: str
    author: str
    is_reference: bool = False  # reference books can never be checked out


@dataclass
class Copy:
    accession_no: str
    title_id: int
    tag_uid: str                # RFID tag UID mapped to this copy
    shelf_location: str
    status: str = "AVAILABLE"   # AVAILABLE | ISSUED | LOST
    security_armed: bool = True  # True = security bit ON (item not issued)


@dataclass
class Loan:
    loan_id: int
    member_id: int
    accession_no: str
    issued_at: datetime
    due_at: datetime
    returned_at: Optional[datetime] = None
    fine: float = 0.0


class Store:
    def __init__(self) -> None:
        self.members: dict[int, Member] = {}
        self.titles: dict[int, Title] = {}
        self.copies: dict[str, Copy] = {}          # keyed by accession_no
        self.loans: list[Loan] = []
        self.alarms: list[dict] = []
        self.email_queue: list[dict] = []
        self.loan_seq = itertools.count(1)
        self.alarm_seq = itertools.count(1)
        self.mail_seq = itertools.count(1)
        self._seed()

    # --- lookups -------------------------------------------------------------
    def copy_by_tag(self, tag_uid: str) -> Optional[Copy]:
        return next((c for c in self.copies.values() if c.tag_uid.upper() == tag_uid.upper()), None)

    def open_loans(self, member_id: int) -> list[Loan]:
        return [l for l in self.loans if l.member_id == member_id and not l.returned_at]

    def open_loan_for_copy(self, accession_no: str) -> Optional[Loan]:
        return next((l for l in self.loans
                     if l.accession_no == accession_no and not l.returned_at), None)

    # --- demo data -----------------------------------------------------------
    def _seed(self) -> None:
        self.members = {
            1: Member(1, "Asha Rao", "asha@example.com"),
            2: Member(2, "Ravi Kumar", "ravi@example.com", outstanding_fines=500.0),
            3: Member(3, "Meena Iyer", "meena@example.com", blocked=True,
                      block_reason="Lost item not paid"),
        }
        self.titles = {
            1: Title(1, "Introduction to Algorithms", "Cormen et al."),
            2: Title(2, "Computer Networks", "Tanenbaum"),
            3: Title(3, "Encyclopaedia of Computing", "Various", is_reference=True),
        }
        seed = [
            ("ACC-1001", 1, "E2000001", "A-01"),
            ("ACC-1002", 1, "E2000002", "A-01"),
            ("ACC-2001", 2, "E2000003", "A-02"),
            ("ACC-3001", 3, "E2000004", "R-01"),   # reference copy
        ]
        for acc, tid, tag, shelf in seed:
            self.copies[acc] = Copy(acc, tid, tag, shelf)


store = Store()


# =============================================================================
# 3. SERVICES
# =============================================================================
class CirculationService:
    """Checkout / checkin logic. Used by REST routes AND the NCIP/SIP2 adapters."""

    def __init__(self, s: Store):
        self.s = s

    def checkout(self, member_id: int, accession_no: str,
                 now: Optional[datetime] = None) -> Loan:
        now = now or utcnow()
        member = self.s.members.get(member_id)
        if not member:
            raise BusinessRuleError("MEMBER_NOT_FOUND", f"Member {member_id} not found", 404)
        copy = self.s.copies.get(accession_no)
        if not copy:
            raise BusinessRuleError("ITEM_NOT_FOUND", f"Item {accession_no} not found", 404)
        title = self.s.titles[copy.title_id]

        # --- business rules (order matters: most specific/serious first) ------
        if member.blocked:
            raise BusinessRuleError("MEMBER_BLOCKED",
                                    f"Member is blocked: {member.block_reason}", 403)
        if member.outstanding_fines >= FINE_LIMIT:
            raise BusinessRuleError(
                "FINE_LIMIT_EXCEEDED",
                f"Outstanding fines {member.outstanding_fines:.2f} >= limit {FINE_LIMIT:.2f}", 403)
        if title.is_reference:
            raise BusinessRuleError("REFERENCE_ONLY",
                                    "Reference books cannot be checked out", 409)
        if copy.status != "AVAILABLE":
            raise BusinessRuleError("ITEM_NOT_AVAILABLE", f"Item is {copy.status}", 409)
        if len(self.s.open_loans(member_id)) >= MAX_LOANS:
            raise BusinessRuleError("LOAN_LIMIT_REACHED",
                                    f"Max {MAX_LOANS} concurrent loans", 409)

        loan = Loan(next(self.s.loan_seq), member_id, accession_no,
                    issued_at=now, due_at=now + timedelta(days=LOAN_DAYS))
        self.s.loans.append(loan)
        copy.status = "ISSUED"
        copy.security_armed = False      # desensitize: item may now pass the gate
        return loan

    def checkin(self, accession_no: str, returned_at: Optional[datetime] = None) -> Loan:
        returned_at = returned_at or utcnow()
        copy = self.s.copies.get(accession_no)
        if not copy:
            raise BusinessRuleError("ITEM_NOT_FOUND", f"Item {accession_no} not found", 404)
        loan = self.s.open_loan_for_copy(accession_no)
        if not loan:
            raise BusinessRuleError("NOT_ON_LOAN", "Item is not currently on loan", 409)

        overdue_days = max(0, (returned_at.date() - loan.due_at.date()).days)
        loan.fine = round(overdue_days * FINE_PER_DAY, 2)
        loan.returned_at = returned_at
        self.s.members[loan.member_id].outstanding_fines += loan.fine

        copy.status = "AVAILABLE"
        copy.security_armed = True       # resensitize: gate will alarm if removed
        return loan


class GateService:
    """Security gate: checks the security bit, raises alarm, mock CCTV, queues email."""

    def __init__(self, s: Store):
        self.s = s

    @staticmethod
    def mock_cctv_capture(gate_id: str, ts: datetime) -> str:
        return f"cctv://mock/{gate_id}/{ts.strftime('%Y%m%dT%H%M%S')}.jpg"

    def handle_event(self, gate_id: str, accession_no: str) -> dict:
        now = utcnow()
        copy = self.s.copies.get(accession_no)

        if copy is None:
            bit_state, armed = "UNKNOWN", True
        else:
            bit_state, armed = ("ARMED" if copy.security_armed else "DISARMED"), copy.security_armed

        if not armed:
            return {"alarm": False, "security_bit": bit_state,
                    "message": "Item properly issued - gate clear"}

        snapshot = self.mock_cctv_capture(gate_id, now)
        alarm = {
            "alarm_id": next(self.s.alarm_seq),
            "gate_id": gate_id,
            "accession_no": accession_no,
            "security_bit": bit_state,
            "check_mode": "OFFLINE",
            "status": "OPEN",
            "cctv_snapshot_ref": snapshot,
            "detected_at": now.isoformat(),
        }
        self.s.alarms.append(alarm)

        email = {
            "queue_id": next(self.s.mail_seq),
            "alarm_id": alarm["alarm_id"],
            "recipient": SECURITY_EMAIL,
            "subject": f"[ALARM] Unissued item at {gate_id}: {accession_no}",
            "body": f"Security bit {bit_state} detected at {now.isoformat()}. "
                    f"CCTV: {snapshot}",
            "status": "PENDING",
            "queued_at": now.isoformat(),
        }
        self.s.email_queue.append(email)
        alarm["email_queue_id"] = email["queue_id"]
        return {"alarm": True, **alarm}


def deliver_pending_emails(s: Store) -> None:
    """Mock email worker; runs as a background task after the response is sent."""
    for mail in s.email_queue:
        if mail["status"] == "PENDING":
            mail["status"] = "SENT"
            mail["sent_at"] = utcnow().isoformat()


class InventoryService:
    """Handheld reader audit: compare scanned tags with shelf records."""

    def __init__(self, s: Store):
        self.s = s

    def audit(self, shelf_location: str, scanned_tags: list[str]) -> dict:
        tags = set(t.upper() for t in scanned_tags)
        found, misplaced, issued_on_shelf, unknown = [], [], [], []

        for tag in sorted(tags):
            copy = self.s.copy_by_tag(tag)
            if copy is None:
                unknown.append(tag)
            elif copy.status == "ISSUED":
                issued_on_shelf.append(copy.accession_no)
            elif copy.shelf_location != shelf_location:
                misplaced.append({"accession_no": copy.accession_no,
                                  "expected_shelf": copy.shelf_location,
                                  "found_on_shelf": shelf_location})
            else:
                found.append(copy.accession_no)

        missing = sorted(
            c.accession_no for c in self.s.copies.values()
            if c.shelf_location == shelf_location and c.status == "AVAILABLE"
            and c.tag_uid.upper() not in tags
        )
        return {
            "shelf_location": shelf_location,
            "scanned_count": len(tags),
            "found": found,
            "missing": missing,
            "misplaced": misplaced,
            "issued_but_on_shelf": issued_on_shelf,
            "unknown_tags": unknown,
        }


circulation = CirculationService(store)
gate_service = GateService(store)
inventory_service = InventoryService(store)


# =============================================================================
# 4. PROTOCOL ADAPTERS (MOCKS)
# =============================================================================
class NCIPAdapter:
    def __init__(self, circ: CirculationService, s: Store):
        self.circ, self.s = circ, s

    @staticmethod
    def _problem(code: str, detail: str) -> dict:
        return {"NCIPMessage": {"Problem": {"ProblemType": code, "ProblemDetail": detail}}}

    def handle(self, service: str, user_id: Optional[str], item_id: str) -> dict:
        try:
            if service == "CheckOutItem":
                loan = self.circ.checkout(int(user_id or 0), item_id)
                return {"NCIPMessage": {"CheckOutItemResponse": {
                    "UserId": user_id, "ItemId": item_id,
                    "DateDue": loan.due_at.isoformat()}}}
            if service == "CheckInItem":
                loan = self.circ.checkin(item_id)
                return {"NCIPMessage": {"CheckInItemResponse": {
                    "ItemId": item_id, "UserId": str(loan.member_id),
                    "FineAssessed": loan.fine}}}
            if service in ("LookupItem", "ItemInformation"):
                copy = self.s.copies.get(item_id)
                if not copy:
                    return self._problem("UNKNOWN_ITEM", f"Item {item_id} not found")
                title = self.s.titles[copy.title_id]
                return {"NCIPMessage": {"LookupItemResponse": {
                    "ItemId": item_id, "Title": title.title, "Author": title.author,
                    "CirculationStatus": copy.status, "Location": copy.shelf_location,
                    "ReferenceOnly": title.is_reference}}}
            return self._problem("UNSUPPORTED_SERVICE", service)
        except BusinessRuleError as e:
            return self._problem(e.code, e.message)
        except ValueError:
            return self._problem("INVALID_USER_ID", "user_id must be numeric in this mock")


class SIP2Adapter:
    def __init__(self, circ: CirculationService, s: Store):
        self.circ, self.s = circ, s

    @staticmethod
    def _date(dt: Optional[datetime] = None) -> str:
        return (dt or utcnow()).strftime("%Y%m%d    %H%M%S")

    @staticmethod
    def _fields(raw: str) -> dict[str, str]:
        return {p[:2]: p[2:] for p in raw.split("|") if len(p) >= 2}

    @staticmethod
    def _build(**fields: str) -> str:
        return "".join(f"{k}{v}|" for k, v in fields.items())

    def handle(self, raw: str) -> str:
        raw = raw.strip("\r\n")
        msg_id = raw[:2]
        if msg_id == "11":
            return self._checkout(self._fields(raw[40:]))
        if msg_id == "09":
            return self._checkin(self._fields(raw[39:]))
        if msg_id == "17":
            return self._item_info(self._fields(raw[20:]))
        return "96"

    def _checkout(self, f: dict) -> str:
        item, patron = f.get("AB", ""), f.get("AA", "")
        try:
            loan = self.circ.checkout(int(patron), item)
            title = self.s.titles[self.s.copies[item].title_id].title
            fixed = "1" + "N" + "N" + "Y" + self._date()
            return "12" + fixed + self._build(
                AO=INSTITUTION_ID, AA=patron, AB=item, AJ=title,
                AH=self._date(loan.due_at), AF="Checkout OK")
        except (BusinessRuleError, ValueError) as e:
            msg = e.message if isinstance(e, BusinessRuleError) else "Invalid patron id"
            fixed = "0" + "N" + "N" + "N" + self._date()
            return "12" + fixed + self._build(AO=INSTITUTION_ID, AA=patron, AB=item, AF=msg)

    def _checkin(self, f: dict) -> str:
        item = f.get("AB", "")
        try:
            loan = self.circ.checkin(item)
            copy = self.s.copies[item]
            title = self.s.titles[copy.title_id].title
            fixed = "1" + "Y" + "N" + "N" + self._date()
            return "10" + fixed + self._build(
                AO=INSTITUTION_ID, AB=item, AQ=copy.shelf_location, AJ=title,
                AF=f"Checkin OK, fine {loan.fine:.2f}")
        except BusinessRuleError as e:
            fixed = "0" + "N" + "N" + "N" + self._date()
            return "10" + fixed + self._build(AO=INSTITUTION_ID, AB=item, AF=e.message)

    def _item_info(self, f: dict) -> str:
        item = f.get("AB", "")
        copy = self.s.copies.get(item)
        if not copy:
            return "18" + "01" + "01" + "01" + self._date() + self._build(AB=item, AJ="")
        title = self.s.titles[copy.title_id].title
        circ_status = {"AVAILABLE": "03", "ISSUED": "04"}.get(copy.status, "01")
        security = "02" if copy.security_armed else "01"
        return "18" + circ_status + security + "01" + self._date() + self._build(
            AB=item, AJ=title, AQ=copy.shelf_location)


ncip = NCIPAdapter(circulation, store)
sip2 = SIP2Adapter(circulation, store)


# =============================================================================
# 5. API
# =============================================================================
app = FastAPI(title="RFID Library System (Prototype)", version="0.1.0")


@app.exception_handler(BusinessRuleError)
async def business_rule_handler(_: Request, exc: BusinessRuleError):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": exc.code, "detail": exc.message})


# ---- request schemas --------------------------------------------------------
class CheckoutRequest(BaseModel):
    member_id: int
    accession_no: str


class CheckinRequest(BaseModel):
    accession_no: str
    returned_at: Optional[datetime] = None


class BlockRequest(BaseModel):
    reason: str = Field(..., min_length=3)
    blocked: bool = True


class TagAssociationRequest(BaseModel):
    accession_no: str
    tag_uid: str


class NCIPRequest(BaseModel):
    service: str
    item_id: str
    user_id: Optional[str] = None


class GateEventRequest(BaseModel):
    gate_id: str = "GATE-01"
    accession_no: str


class ScanRequest(BaseModel):
    shelf_location: str
    scanned_tags: list[str]


# ---- core endpoints ---------------------------------------------------------
@app.get("/catalog")
def catalog(q: Optional[str] = Query(None, description="Search title/author"),
            available_only: bool = False):
    results = []
    for t in store.titles.values():
        if q and q.lower() not in f"{t.title} {t.author}".lower():
            continue
        copies = [c for c in store.copies.values() if c.title_id == t.title_id]
        if available_only:
            copies = [c for c in copies if c.status == "AVAILABLE"]
            if not copies or t.is_reference:
                continue
        results.append({
            "title_id": t.title_id, "title": t.title, "author": t.author,
            "reference_only": t.is_reference,
            "copies": [{"accession_no": c.accession_no, "status": c.status,
                        "shelf": c.shelf_location} for c in copies],
        })
    return {"count": len(results), "results": results}


@app.post("/circulation/checkout")
def checkout(req: CheckoutRequest):
    loan = circulation.checkout(req.member_id, req.accession_no)
    return {"loan_id": loan.loan_id, "accession_no": loan.accession_no,
            "due_at": loan.due_at.isoformat(), "security_bit": "DISARMED"}


@app.post("/circulation/checkin")
def checkin(req: CheckinRequest):
    loan = circulation.checkin(req.accession_no, req.returned_at)
    member = store.members[loan.member_id]
    return {"loan_id": loan.loan_id, "fine_assessed": loan.fine,
            "member_outstanding_fines": member.outstanding_fines,
            "security_bit": "ARMED"}


@app.post("/rfid/tags/associate")
@app.post("/api/v1/tags/associate")
def associate_tag(req: TagAssociationRequest, request: Request):
    role = request.headers.get("X-Role", request.headers.get("X-User-Role", "")).lower()
    if role not in ["admin", "librarian", "staff"]:
        raise BusinessRuleError("FORBIDDEN", "Insufficient permissions", 403)

    copy = store.copies.get(req.accession_no)
    if not copy:
        raise BusinessRuleError("ITEM_NOT_FOUND", f"Accession number {req.accession_no} not found", 404)

    tag_uid_upper = req.tag_uid.upper()
    existing_copy = store.copy_by_tag(tag_uid_upper)
    if existing_copy and existing_copy.accession_no != copy.accession_no:
        raise BusinessRuleError("TAG_ALREADY_MAPPED", "Tag already assigned to another item", 409)

    copy.tag_uid = tag_uid_upper
    return {"accession_no": copy.accession_no, "tag_uid": copy.tag_uid, "status": "ASSOCIATED"}


@app.post("/members/{member_id}/block")
def block_member(member_id: int, req: BlockRequest, request: Request):
    role = request.headers.get("X-Role", request.headers.get("X-User-Role", "")).lower()
    if role != "admin":
        raise BusinessRuleError("FORBIDDEN", "Admin role required", 403)

    member = store.members.get(member_id)
    if not member:
        raise BusinessRuleError("MEMBER_NOT_FOUND", f"Member {member_id} not found", 404)
    member.blocked = req.blocked
    member.block_reason = req.reason if req.blocked else None
    return {"member_id": member_id, "blocked": member.blocked, "reason": member.block_reason}


@app.post("/members/{member_id}/fines/pay")
def pay_fines(member_id: int, amount: float = Query(..., gt=0)):
    member = store.members.get(member_id)
    if not member:
        raise BusinessRuleError("MEMBER_NOT_FOUND", f"Member {member_id} not found", 404)
    member.outstanding_fines = max(0.0, round(member.outstanding_fines - amount, 2))
    return {"member_id": member_id, "outstanding_fines": member.outstanding_fines}


# ---- protocol adapters ------------------------------------------------------
@app.post("/api/v1/ncip")
def ncip_endpoint(req: NCIPRequest):
    return ncip.handle(req.service, req.user_id, req.item_id)


@app.post("/api/v1/sip2", response_class=PlainTextResponse)
async def sip2_endpoint(request: Request):
    raw = (await request.body()).decode()
    return sip2.handle(raw)


# ---- RFID middleware endpoints ---------------------------------------------
@app.post("/api/v1/gate/event")
def gate_event(req: GateEventRequest, background: BackgroundTasks):
    result = gate_service.handle_event(req.gate_id, req.accession_no)
    if result.get("alarm"):
        background.add_task(deliver_pending_emails, store)
    return result


@app.get("/api/v1/gate/alarms")
def list_alarms(request: Request):
    role = request.headers.get("X-Role", request.headers.get("X-User-Role", "")).lower()
    if role != "admin":
        raise BusinessRuleError("FORBIDDEN", "Admin role required", 403)

    return {"alarms": store.alarms, "email_queue": store.email_queue}


@app.post("/api/v1/inventory/scan")
def inventory_scan(req: ScanRequest):
    return inventory_service.audit(req.shelf_location, req.scanned_tags)


@app.get("/health")
def health():
    return {"status": "ok"}