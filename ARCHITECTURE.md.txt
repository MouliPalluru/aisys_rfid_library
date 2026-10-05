# Modular Architecture & Technical Design Document
## AISYS RFID Library Management System

### 1. Executive Summary
The AISYS RFID Library Management System provides real-time circulation tracking, RFID middleware security enforcement, protocol integration (SIP2 / NCIP 2.0), and automated inventory auditing.

---

### 2. Modular 7-Layer Architecture

1. **Presentation / API Layer (`FastAPI`):**
   - Implements OpenAPI REST endpoints for Catalog, Circulation, RFID Tag Association, and Admin operations.
   - Enforces Role-Based Access Control (RBAC) via custom request headers (`X-Role`).

2. **Protocol Adapter Layer (`NCIPAdapter` & `SIP2Adapter`):**
   - **NCIP 2.0 Mock:** Provides standard XML/JSON request and response envelopes for `CheckOutItem`, `CheckInItem`, and `LookupItem`.
   - **SIP2 Mock:** Handles fixed-width frame strings (Commands `11`, `09`, `17`) with standard checksum and field identifiers (`AO`, `AA`, `AB`).

3. **Business Rules & Circulation Layer (`CirculationService`):**
   - Enforces fine thresholds (Max Limit: ₹500.00).
   - Enforces loan caps (Max 5 active items per patron).
   - Blocks non-circulating reference items from checkout.

4. **RFID Security & Middleware Layer (`GateService`):**
   - Monitored security bit checks at physical exit gates.
   - Triggers real-time security alerts and CCTV snapshot reference generation (`cctv://mock/...`) upon unissued item detection.

5. **Inventory Audit Layer (`InventoryService`):**
   - Reconciles shelf batch scans from handheld RFID readers.
   - Categorizes catalog discrepancies into `found`, `missing`, `misplaced`, and `issued_but_on_shelf`.

6. **Notification Layer:**
   - Asynchronous background email queue (`deliver_pending_emails`) dispatching alerts to security personnel upon gate security breach events.

7. **Persistence Layer (`Store` Repository):**
   - In-memory entity repository holding Members, Titles, Copies, Loans, and Alarm events.
   - Pre-configured schema structures mapped for PostgreSQL / SQLAlchemy migration.



### 3. Verification & Compliance
- **Test Suite:** `pytest` / `test_acceptance.py`
- **Coverage Status:** 49/49 Acceptance Tests Passed (100% Pass Rate).
