# AISYS RFID Library Management System

### Candidate Exercise Presentation — SOP Deliverable D9

Offline-first prototype: circulation, RFID gate security, shelf audit, spreadsheet migration

Release 1.0.0 · 5 October 2026

---

# 1 · Executive Summary

- **What was built:** a modular FastAPI backend and a Pandas/SQLAlchemy migration utility covering circulation, NCIP 2.0 / SIP2 adapters, RFID tag association, gate alarms, handheld shelf audit and role-based access
- **Proven by tests:** **53 of 53 automated tests pass**, including a 20,000-record import in about 3 seconds
- **SOP position:** of 31 requirements, **7 are fully met**, **22 are partially met**, **2 are not yet built**
- **Strongest areas:** data migration with rollback, circulation rules, gate event workflow, backup-and-restore integrity
- **Main gaps:** persistence in the API, real authentication, reports and dashboard, renewals, update-package tooling
- **Deliverables supplied:** traceability matrix, operations runbook, licence inventory, source code, test suite

---

# 2 · Scope and Approach

- **Brief:** build a prototype RFID library system that runs offline on Windows 11 and Windows Server 2022 and satisfies the AISYS SOP
- **Approach:** build the riskiest flows first and prove each with an automated test aligned to the SOP acceptance scenarios
- **Mocked on purpose:** handheld reader, security gate, CCTV, e-mail provider, identity provider — each behind a replaceable adapter boundary
- **Stack:** Python, FastAPI, Pandas, SQLAlchemy, SQLite, Pytest
- **Evidence standard:** every claim in this deck traces to a named test or document in the traceability matrix

---

# 3 · Architecture — Seven Layers

| # | Layer | Responsibility | Realised in |
|---|---|---|---|
| 1 | API | REST routes, request validation, role checks | FastAPI routes, Pydantic models, `require_role` |
| 2 | Protocol Interoperability | NCIP 2.0 and SIP2 adapter boundary | `NCIPAdapter`, `SIP2Adapter` |
| 3 | Circulation Logic | Check-out, check-in, fines, blocking, reference rules | `CirculationService` |
| 4 | RFID Middleware & Gate Security | Tag association, security-bit check, alarm, CCTV capture | `associate_tag`, `GateService` |
| 5 | Inventory Audit | Missing, misplaced and unknown-tag detection | `InventoryService` |
| 6 | Notifications | Queued alarm e-mail through a mock worker | e-mail queue, `deliver_pending_emails` |
| 7 | Persistence Data Layer | Relational schema, staging, migration, backup | SQLite schema in `migrate.py` |

Business rules sit in the services, never in the protocol adapters, so REST, NCIP and SIP2 apply identical rules.

---

# 4 · Key Technical Decisions

- **One rule engine, three front doors.** REST, NCIP and SIP2 call the same circulation service, so a blocked member is refused identically everywhere
- **Fail-secure gate.** An unknown or armed item raises an alarm; the security-bit check uses local data only, so it works with the LMS offline
- **All-or-nothing migration.** One database transaction per batch; `--rollback` reverts everything if any row is rejected
- **Staging table for duplicates.** Every row's outcome is recorded; rows migrated by earlier batches are detected and never overwritten
- **Insert-only imports.** Existing records are never updated or deleted, which protects the data already in the library
- **Offline by design.** No outbound network calls in the code; dependencies pinned and installed from a local wheelhouse

---

# 5 · Capabilities Demonstrated

| Capability | What happens |
|---|---|
| Circulation | Check-out sets a 14-day due date and disarms the tag; check-in re-arms it and charges overdue fines |
| Circulation blocking | Reference books, blocked members and members at the fine limit (500.00) are refused with clear reason codes |
| NCIP 2.0 / SIP2 | Check-out, check-in and item information through both mock protocols |
| Tag association | One tag per copy; duplicate tags rejected; UIDs normalised |
| Gate event | Unissued item → alarm with accession number → mock CCTV reference → queued e-mail |
| Shelf audit | Bulk tag list compared with shelf records: found, missing, misplaced, issued-but-on-shelf, unknown |
| Role-based access | Blocking and the alarm log are admin-only; tag association needs librarian or admin |

---

# 6 · Data Migration and Integrity

- **Input:** CSV or XLSX; members and book copies with RFID tags
- **Validation:** required columns, email, phone, ISBN, tag format, year range, corrupted characters
- **Rejects:** every bad or duplicate row goes to `error_log.csv` with its row number and reason
- **Reconciliation report:** Total Read, Valid, Rejected, Inserted, plus an automatic consistency check
- **Volume:** 20,000 rows imported in about 3 seconds (test host, SQLite, CSV)
- **Failure safety:** a simulated mid-load crash leaves every existing record unchanged; restoring a backup after deliberate damage returns the original records and passes SQLite's integrity check

---

# 7 · Security and Access Control

- **Enforced today:** role checks on member blocking, alarm log and tag association; request-body validation on every endpoint; case-insensitive role matching
- **Gate decisions** use locally held data only and fail secure, so they never depend on the network
- **Deployment pattern:** API bound to loopback behind a trusted proxy that authenticates staff and sets the role header
- **Honest limits:** the role arrives as a plain header, so it is only safe behind that proxy; there is no TLS configuration, no audit log and no smart-card login yet
- **Priority fix:** replace the header with verified identity from the institution's smart-card provider, and add an audit trail

---

# 8 · Test Results

| Measure | Result |
|---|---|
| Automated tests | **49 passed, 0 failed** |
| Test host | Python 3.12.3, Linux, SQLite 3.45.1 |
| Suite run time | about 5 seconds |
| 20,000-row import | about 3 seconds |

| Test group | Tests |
|---|---:|
| Spreadsheet import, validation and duplicates (AC 01) | 8 |
| Tag association (AC 02) | 4 |
| NCIP and SIP2 flows (AC 03) | 7 |
| Circulation blocking (AC 04) | 6 |
| Handheld audit (AC 05) | 3 |
| Gate event (AC 06) | 4 |
| Role access (AC 07) | 12 |
| Migration rollback, backup-restore, performance | 9 |

---

# 9 · Compliance with SOP Requirements

| Group | Total | Met | Partial | Not met |
|---|---:|---:|---:|---:|
| Functional (FR 01–12) | 12 | 1 | 10 | 1 |
| Non-functional (NFR 01–09) | 9 | 2 | 7 | 0 |
| Acceptance (AC 01–10) | 10 | 4 | 5 | 1 |
| **Total** | **31** | **7** | **22** | **2** |

- **Fully met:** FR 10 (migration), NFR 01 (data protection), NFR 04 (licences and pinning), AC 01, AC 04, AC 06, AC 10
- **Not met:** FR 08 and AC 08 (reports and dashboard)
- **Partial** items each list their exact gap in the traceability matrix

---

# 10 · Acceptance Scenario Status

| AC | Scenario | Status | Note |
|---|---|:---:|---|
| 01 | Spreadsheet import and reconciliation | **Met** | Includes XLSX and duplicates against staging |
| 02 | Tag-to-item association | Partial | No item-create API or relationship display endpoint |
| 03 | Check-out / renew / check-in via NCIP and SIP2 | Partial | Renewal and audit-history query missing |
| 04 | Block reference, blocked and over-limit | **Met** | Verified through REST, NCIP and SIP2 |
| 05 | Handheld inventory audit | Partial | No audible or visible confirmation |
| 06 | Gate event, CCTV, e-mail | **Met** | Mock devices |
| 07 | Smart-card login with RBAC | Partial | RBAC enforced; no smart-card login |
| 08 | Dashboard and reports | **Not met** | Not built |
| 09 | Offline run, update, rollback | Partial | Procedures documented, not executed |
| 10 | Restore after failed migration | **Met** | Original data proven intact |

---

# 11 · Known Limitations

- **Operational data is in memory.** The API resets to demo data on restart and the migration database is not yet read by the API; run a single instance
- **Authentication is simulated.** Role header, no smart-card provider, no TLS, no audit log
- **Reporting is missing.** No statistics, dashboard or filterable reports
- **Circulation gaps.** No renewals, due-date enquiry or patron-card personalisation
- **Integrations are mocks.** Offline gate check is simulated by local data; CCTV and e-mail are placeholders; NCIP is JSON rather than XML; SIP2 handles three message types
- **Platform evidence.** Tests ran on Linux; Windows 11 and Server 2022 procedures are documented but unexecuted; pinned packages need Python 3.11 or newer
- **Operations.** Configuration is in code and logs are unstructured text

---

# 12 · Production Readiness Backlog and Next Steps

| Priority | Item | SOP link | Size |
|---|---|---|:---:|
| **P0** | Replace in-memory store with the SQLite/PostgreSQL persistence layer | FR 11, NFR 01 | M |
| **P0** | Verified identity (smart-card provider), TLS, audit log | AC 07, NFR 02 | L |
| **P0** | Execute the install, update and rollback procedures on Windows 11 and Server 2022 | AC 09, NFR 03 | M |
| **P1** | Renewals, due-date enquiry, circulation audit-history endpoint | FR 04, AC 03 | M |
| **P1** | Dashboard and filterable reports | FR 08, AC 08 | L |
| **P1** | Tag-to-item display, item creation, handheld confirmation signals | AC 02, AC 05, FR 06 | S |
| **P1** | Update-package builder with rollback instructions | FR 12 | M |
| **P1** | Externalised configuration, structured logs, version reporting | NFR 06, NFR 07, FR 11 | M |
| **P2** | Web interface and search engine | FR 02 | L |
| **P2** | SMS and print adapters; real e-mail, CCTV and reader drivers | FR 09, FR 03 | L |
| **P2** | Security, load and user-acceptance testing | NFR 05 | M |

Sizes are relative effort estimates: **S** a few days, **M** one to two weeks, **L** several weeks.

**Next step:** agree the P0 items, then re-run the traceability matrix to show the compliance count move.
