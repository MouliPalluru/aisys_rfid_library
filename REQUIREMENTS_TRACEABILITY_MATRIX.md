# AISYS RFID Library Management System — Requirements Traceability Matrix

| Field | Value |
|---|---|
| Document | `REQUIREMENTS_TRACEABILITY_MATRIX.md` |
| Fulfils | SOP Deliverable D1 |
| Version / date | 1.0 / 2026-10-05 |
| Requirement source | AISYS Software Development SOP — FR 01–12, NFR 01–09, AC 01–10 (exact text as supplied by the project) |
| Code under trace | `main.py` (API, adapters, services), `migrate.py` (migration utility; named `migrate_excel.py` in the submission repository if renamed — function names are identical) |
| Test evidence | `test_acceptance.py` — **53 tests, 53 passed** (Python 3.12.3, Linux; SQLite 3.45.1) |
| Companion documents | `OPERATIONS_AND_RUNBOOK.md` (D7/D8), `LICENSE_INVENTORY.md` (D4), `PRESENTATION.md` (D9) |

---

## 1. How to read this matrix

| Status | Meaning |
|---|---|
| **Met** | Every element of the requirement text is implemented or documented, and verified by automated tests or by a named document section |
| **Partial** | Some elements are implemented and verified; the **Gap** column lists exactly what is missing |
| **Not met** | No substantive implementation in release 1.0.0 |

Test references use `Class::test_name`. A class name alone means every test in that class. Documents are cited by section (`RUNBOOK §x` = `OPERATIONS_AND_RUNBOOK.md`, `LICENSE §x` = `LICENSE_INVENTORY.md`).

**Evidence limits.** All tests ran on Linux; nothing has been executed on Windows 11 or Windows Server 2022. All external devices, the e-mail provider, CCTV and the identity provider are mocks. The API holds its operational data in memory; only `migrate.py` writes to SQLite.

---

## 2. Compliance scoreboard

| Group | Total | Met | Partial | Not met |
|---|---:|---:|---:|---:|
| Functional requirements (FR) | 12 | 1 | 10 | 1 |
| Non-functional requirements (NFR) | 9 | 2 | 7 | 0 |
| Acceptance scenarios (AC) | 10 | 4 | 5 | 1 |
| **All requirements** | **31** | **7** | **22** | **2** |

Fully met: FR 10, NFR 01, NFR 04, AC 01, AC 04, AC 06, AC 10. Not met: FR 08 (reports/statistics), AC 08 (dashboard and filterable reports).

---

## 3. Functional requirements

| ID and requirement | Status | Implemented in | Verified by | Gap |
|---|:---:|---|---|---|
| **FR 01** Acquisition, cataloguing, serials, circulation, OPAC, barcode/spine-label workflows, reports | Partial | `catalog()` (OPAC-style listing of titles and copies); `CirculationService.checkout` / `checkin`; `migrate.insert_books` (cataloguing by bulk load) | `TestAC04CirculationBlocking`; `TestAC03NCIP`; `TestAC01SpreadsheetImport::test_book_file_creates_titles_copies_and_tags` | Acquisition, serials, barcode and spine-label workflows, and report generation are not built |
| **FR 02** Web interface, full-text search, search engine, real-time indexing, net cataloguing, virtual bookshelf | Partial | `catalog(q, available_only)` — case-insensitive substring search over title and author | No automated test (manual via `/docs`) | No web interface (FastAPI's `/docs` page is a developer tool), no search engine or indexing, no net cataloguing, no virtual bookshelf |
| **FR 03** Middleware integration of staff station, handheld reader, gate, smart card, item tags; NCIP 2.0; SIP2 adapter boundary | Partial | `NCIPAdapter.handle`; `SIP2Adapter.handle` / `_checkout` / `_checkin` / `_item_info`; `GateService.handle_event`; `InventoryService.audit`; `associate_tag`; routes `/api/v1/ncip`, `/api/v1/sip2`, `/api/v1/gate/event`, `/api/v1/inventory/scan` | `TestAC03NCIP`; `TestAC03SIP2`; `TestAC05InventoryAudit`; `TestAC06GateEvent` | Smart-card integration absent; all devices are mocks; NCIP is a JSON simplification, not XML; SIP2 covers message types 09, 11, 17 only |
| **FR 04** Check-out, check-in, renewal, due-date enquiry, patron-card personalisation, reference restrictions, member blocking, configurable fine limits, role-based circulation rights | Partial | `CirculationService.checkout` (blocked member, fine limit, reference book, availability, loan limit); `CirculationService.checkin` (fine accrual); `block_member`; `pay_fines`; constants `LOAN_DAYS`, `MAX_LOANS`, `FINE_PER_DAY`, `FINE_LIMIT` | `TestAC04CirculationBlocking` (6 tests); `TestAC03NCIP`; `TestAC03SIP2` | Renewal not implemented; no due-date enquiry (due date is returned only at checkout); no patron-card personalisation; role rights enforced only on blocking, not on checkout/checkin; fine limit is a code constant, not runtime-configurable |
| **FR 05** Validate title/member records before tagging; associate tag with item record; tag monitoring | Partial | `associate_tag` (item must exist; one tag per copy, one copy per tag; UID normalised); `migrate.validate_row` + `insert_books` (tag format, uniqueness, mapping created with the copy) | `TestAC02TagAssociation`; `TestAC01ValidationAndDuplicates::test_book_validation_rules` | No member-record tagging (smart cards); no tag monitoring (last-seen tracking); no separate title-record validation step |
| **FR 06** Stock verification, shelf management, misplaced/missing identification, bulk reading, audible/visible confirmation | Partial | `InventoryService.audit` (found, missing, misplaced, issued-but-on-shelf, unknown tags; repeated reads collapsed); `inventory_scan` | `TestAC05InventoryAudit` | No audible or visible confirmation signal in the handheld response; no shelf master data or capacity management |
| **FR 07** Detect unissued items; read security bit while LMS offline; record accession numbers; alarm, footfall, CCTV photo, e-mail events | Partial | `GateService.handle_event` (security-bit check, fail-secure for unknown items, alarm with accession number); `GateService.mock_cctv_capture`; e-mail enqueue; `deliver_pending_emails`; `list_alarms` | `TestAC06GateEvent` (4 tests) | "Offline" is simulated: the check reads the local record that stands in for an offline cache, with no store-and-forward buffer; footfall counting not built; CCTV and e-mail are mocks |
| **FR 08** Usage statistics and reports: tagged items, members, circulation, operator/RFID-client activity, fines, gate events | **Not met** | Only the raw alarm list `list_alarms` | `TestAC07RoleAccess::test_alarm_log_is_admin_only` (access control only) | No statistics or reports of any kind |
| **FR 09** Configurable e-mail, SMS, print notifications per user via provider-neutral adapters | Partial | E-mail queue records created in `GateService.handle_event`; mock delivery in `deliver_pending_emails` | `TestAC06GateEvent::test_unissued_item_triggers_alarm_cctv_and_email` | Single notification type, e-mail only; no SMS or print; no provider-neutral adapter interface; no per-user configuration |
| **FR 10** Import ≈20,000 records from spreadsheets with validation, duplicate handling, error logs, reconciliation, rollback | **Met** | `migrate.load_dataframe` (CSV and XLSX); `validate_row`; `normalise_row`; `run_migration` (duplicates vs. file, staging table and database; single transaction; rollback); `format_report`; `main` (CLI, `--rollback`); `SchemaError`; `MigrationAborted` | `TestAC01SpreadsheetImport` (incl. `test_xlsx_spreadsheet_is_imported`); `TestAC01ValidationAndDuplicates`; `TestMigrationRollback`; `TestPerformance::test_twenty_thousand_member_rows_import_within_budget` (20,000 rows ≈ 3 s on the test host) | Members and books only; no loans, fines or serials import |
| **FR 11** User/role management, configuration, audit logs, software-version reporting, system health | Partial | `require_role` (role enforcement); `health` (`/health`) | `TestAC07RoleAccess` (12 tests) | No user or role management (roles are request-header values); no configuration interface; no audit log; no version reporting; `/health` reports liveness only |
| **FR 12** Offline activation, updates, upgrades, patches, security updates; installable update package with rollback instructions | Partial | None in code | `RUNBOOK §3.2–3.8` (offline install, versioned releases, update steps, rollback R1–R3); `LICENSE §7` | Procedure is documented but there is no automated package builder, no activation mechanism, and nothing was exercised on Windows |

---

## 4. Non-functional requirements

| ID and requirement | Status | Implemented in | Verified by | Gap |
|---|:---:|---|---|---|
| **NFR 01** Back up existing database; do not modify, delete or corrupt existing records | **Met** | `run_migration` issues only `SELECT` and `INSERT` against existing tables and runs in one transaction; SQLite online backup (`Connection.backup`) | `TestAC10BackupRestore` (both tests); `TestMigrationRollback::test_book_rollback_leaves_no_orphan_titles_copies_or_tags`; `RUNBOOK §4.2–4.3` | The API's in-memory operational data is not backed up (`RUNBOOK §0`) |
| **NFR 02** Least privilege, secure secrets, audit logging, input validation, encrypted transport | Partial | Input validation: Pydantic request models (`CheckoutRequest`, `CheckinRequest`, `BlockRequest`, `NCIPRequest`, `GateEventRequest`, `ScanRequest`, `TagAssociation`) and `migrate.validate_row`; least privilege: `require_role` | `TestAC07RoleAccess`; `TestAC01ValidationAndDuplicates` | No audit logging; the role comes from an unauthenticated `X-Role` header (needs a trusted proxy, `RUNBOOK §1.1`); no TLS configured; no secrets management |
| **NFR 03** Windows 11 clients, Windows Server 2022+, Ethernet, isolated deployment | Partial | No OS-specific code | `RUNBOOK §1.1, §3` (loopback binding, proxy, offline install on Windows) | Evidence is from Linux only; the Windows procedures are unexecuted; isolation and Ethernet are deployment properties not verified here |
| **NFR 04** Identify dependencies and licences, pin versions, document offline-use restrictions | **Met** | — | `LICENSE_INVENTORY.md` (SBOM, pinned `requirements.txt`, §7 offline compatibility) | Pins require Python ≥ 3.11 (`LICENSE §1`) |
| **NFR 05** Functional, integration, performance, migration, security, regression and UAT test evidence | Partial | — | Functional/integration/migration: the 53-test suite; performance: `TestPerformance`; regression: the suite is repeatable with `pytest` | No security testing beyond RBAC; no API load test; no UAT evidence |
| **NFR 06** Modular adapters, configuration outside code, structured logs, versioned migrations, documented builds, rollback | Partial | Adapters and services as classes: `NCIPAdapter`, `SIP2Adapter`, `CirculationService`, `GateService`, `InventoryService`; migration `--rollback` | `TestAC03NCIP`, `TestAC03SIP2`, `TestMigrationRollback`; `RUNBOOK §3.5–3.8` | Business rules are code constants; logs are unstructured text; schema versioning is a documented `PRAGMA user_version` convention without tooling; builds are documented, not scripted |
| **NFR 07** Diagnostics, health checks, structured logs, runbooks for software/integration incidents | Partial | `health` (`/health`) | `RUNBOOK §1.2–1.3` (`check_health.ps1`), `§4.5` (troubleshooting table) | No structured logs; `/health` does not probe dependencies; no diagnostics endpoint |
| **NFR 08** Architecture, device config, API docs, software versions, install steps, admin/user procedures, troubleshooting | Partial | FastAPI generates OpenAPI documentation at `/docs` | 7-layer architecture, ER and sequence diagrams (Mermaid); `OPERATIONS_AND_RUNBOOK.md`; `LICENSE_INVENTORY.md` | No device-configuration guide (readers, gates, handhelds); API documentation is auto-generated only |
| **NFR 09** Complete exercise D0–D10 and identify remaining production work | Partial | — | This matrix; `PRESENTATION.md` slides 10–12 (limitations and backlog) | The deliverables other than D1, D4, D7, D8, D9 were not assessed because their definitions are not in the supplied SOP text |

---

## 5. Acceptance scenarios

| ID and scenario | Status | Implemented in | Verified by | Gap |
|---|:---:|---|---|---|
| **AC 01** Import spreadsheet, reject invalid rows, identify duplicates, migrate valid records, reconcile counts | **Met** | `migrate.run_migration`, `validate_row`, `format_report` | `TestAC01SpreadsheetImport::test_member_file_imported_and_reconciled`; `::test_book_file_creates_titles_copies_and_tags`; `::test_xlsx_spreadsheet_is_imported`; `TestAC01ValidationAndDuplicates::test_bad_rows_logged_and_good_rows_imported`; `::test_duplicates_detected_against_staging_on_rerun` | — |
| **AC 02** Create/locate bibliographic item, validate, associate mock RFID tag, display tag-to-item relationship | Partial | `associate_tag`; `catalog()` (locate); `migrate.insert_books` (create, by import); `Store.copy_by_tag` | `TestAC02TagAssociation` (4 tests) | No API to create a bibliographic item; no endpoint that displays the tag-to-item relationship (visible in the association response, and as a database join in `test_migrated_tags_are_linked_to_their_copies`) |
| **AC 03** Check out, renew, check in via mocked NCIP/SIP2 with audit history | Partial | `NCIPAdapter.handle`; `SIP2Adapter._checkout` / `_checkin` / `_item_info`; `CirculationService` | `TestAC03NCIP` (4 tests); `TestAC03SIP2` (3 tests) | Renewal not implemented; loan records are kept in `Store.loans` but no audit-history query is exposed |
| **AC 04** Block circulation for reference items, blocked members, members over fine limits | **Met** | `CirculationService.checkout`; `block_member`; `pay_fines` | `TestAC04CirculationBlocking` (6 tests); `TestAC03NCIP::test_denied_checkout_returns_problem_element`; `TestAC03SIP2::test_denied_checkout_reports_reason` | — |
| **AC 05** Handheld mock inventory reporting missing/misplaced items with visible/audible confirmation | Partial | `InventoryService.audit`; `inventory_scan` | `TestAC05InventoryAudit` (3 tests) | No visible or audible confirmation in the response |
| **AC 06** Gate mock generates unauthorised-removal event, records accession number, attaches mock CCTV image, queues e-mail | **Met** | `GateService.handle_event`, `mock_cctv_capture`, `deliver_pending_emails`; `gate_event`; `list_alarms` | `TestAC06GateEvent` (4 tests) | — |
| **AC 07** Staff smart-card login through mock provider enforcing RBAC | Partial | `require_role` and its use on blocking, alarm log and tag association | `TestAC07RoleAccess` (12 tests) | No smart-card login and no mock identity provider; the role is supplied by header |
| **AC 08** Dashboard statistics and filterable reports for items, members, circulation, operators, RFID clients, gate events | **Not met** | — | — | Not implemented (see FR 08) |
| **AC 09** Run without internet, apply offline update, complete documented rollback | Partial | No outbound network call exists in `main.py` or `migrate.py` | `RUNBOOK §3.3–3.8`; `LICENSE §7` | The offline update and rollback are procedures that were not exercised; no update package exists; no automated test |
| **AC 10** Restore from backup after simulated failed migration/integration change, proving original data intact | **Met** | `run_migration` (transactional rollback); SQLite online backup | `TestAC10BackupRestore::test_failed_migration_then_restore_proves_original_data_intact`; `::test_migration_never_modifies_existing_records`; `TestMigrationRollback` (6 tests) | Covers the migration path; the integration-change path is not separately simulated |

---

## 6. Test inventory (53 tests)

| Test class | Tests | Primary requirement(s) |
|---|---:|---|
| `TestAC01SpreadsheetImport` | 4 | AC 01, FR 10 |
| `TestAC01ValidationAndDuplicates` | 4 | AC 01, FR 10, FR 05 |
| `TestAC02TagAssociation` | 4 | AC 02, FR 05 |
| `TestAC03NCIP` | 4 | AC 03, AC 04, FR 03, FR 04 |
| `TestAC03SIP2` | 3 | AC 03, AC 04, FR 03, FR 04 |
| `TestAC04CirculationBlocking` | 6 | AC 04, FR 04 |
| `TestAC05InventoryAudit` | 3 | AC 05, FR 06 |
| `TestAC06GateEvent` | 4 | AC 06, FR 07, FR 09 |
| `TestAC07RoleAccess` | 12 | AC 07, FR 11, NFR 02 |
| `TestMigrationRollback` | 6 | FR 10, NFR 01, AC 10 |
| `TestAC10BackupRestore` | 2 | AC 10, NFR 01 |
| `TestPerformance` | 1 | NFR 05, FR 10 |
| **Total** | **53** | |

Requirements with **no automated test**: FR 02, FR 12, NFR 03, NFR 04 (document evidence only), NFR 07, NFR 08, AC 08, AC 09.

---

## 7. Data dictionary

### 7.1 Persistent tables (SQLite, created by `migrate.py`)

| Table | Column | Type | Rules |
|---|---|---|---|
| `members` | `member_id` | integer, PK | Auto-generated |
| | `member_code` | string(30) | Required, unique; natural key for duplicate detection |
| | `full_name` | string(150) | Required |
| | `email`, `phone` | string | Optional; email pattern and 7–15 digit phone checked on import |
| | `member_type` | string(20) | `STUDENT`, `FACULTY`, `STAFF`, `GUEST`; default `STUDENT` |
| | `status` | string(15) | Default `ACTIVE` |
| `titles` | `title_id` | integer, PK | Auto-generated |
| | `isbn` | string(20) | Unique; 10 or 13 digits after removing hyphens; shared by all copies |
| | `title` | string(300) | Required |
| | `author`, `publisher`, `category` | string | Optional |
| | `pub_year` | integer | Optional; 1400 to current year + 1 |
| `book_copies` | `copy_id` | integer, PK | Auto-generated |
| | `title_id` | integer, FK → `titles` | Required |
| | `accession_no` | string(40) | Required, unique; natural key |
| | `status` | string(15) | Default `AVAILABLE` |
| | `shelf_location` | string(50) | Optional |
| `rfid_tag_mappings` | `mapping_id` | integer, PK | Auto-generated |
| | `tag_uid` | string(64) | Required, unique; 8–24 hexadecimal characters, stored upper-case |
| | `copy_id` | integer, FK → `book_copies` | Unique (one tag per copy) |
| | `security_bit` | boolean | `True` = armed (not issued); default `True` |
| | `tag_status` | string(15) | Default `ACTIVE` |
| | `encoded_at` | datetime | Set at import |
| `migration_staging` | `stage_id` | integer, PK | Auto-generated |
| | `batch_id` | string(40) | Identifies one migration run |
| | `entity_type` | string(20) | `members` or `books` |
| | `natural_key` | string(80) | `member_code` or `accession_no` |
| | `raw_payload` | text | Source row as JSON |
| | `validation_status` | string(12) | `MIGRATED`, `INVALID`, `DUPLICATE` |
| | `error_message` | text | Reason code(s) for rejected rows |
| | `loaded_at` | datetime | Batch timestamp |

### 7.2 Runtime entities (in-memory, `main.py`)

| Entity | Fields | Notes |
|---|---|---|
| `Member` | `member_id`, `name`, `email`, `blocked`, `block_reason`, `outstanding_fines` | Blocking and fine limit are enforced at checkout |
| `Title` | `title_id`, `title`, `author`, `is_reference` | `is_reference` forbids checkout |
| `Copy` | `accession_no`, `title_id`, `tag_uid`, `shelf_location`, `status`, `security_armed` | `status`: `AVAILABLE`, `ISSUED`, `LOST`; `security_armed` toggled by checkout/checkin |
| `Loan` | `loan_id`, `member_id`, `accession_no`, `issued_at`, `due_at`, `returned_at`, `fine` | `fine` = overdue days × `FINE_PER_DAY` at check-in |
| Gate alarm | `alarm_id`, `gate_id`, `accession_no`, `security_bit` (`ARMED`/`UNKNOWN`), `check_mode`, `status`, `cctv_snapshot_ref`, `detected_at`, `email_queue_id` | Created only when the item is armed or unknown |
| Email queue entry | `queue_id`, `alarm_id`, `recipient`, `subject`, `body`, `status` (`PENDING`/`SENT`), `queued_at`, `sent_at` | Mock delivery |

### 7.3 Business-rule constants (`main.py`)

| Constant | Value | Rule |
|---|---|---|
| `LOAN_DAYS` | 14 | Loan period |
| `MAX_LOANS` | 5 | Concurrent loans per member |
| `FINE_PER_DAY` | 2.0 | Overdue fine per day |
| `FINE_LIMIT` | 500.0 | Checkout refused at or above this outstanding amount |

---

## 8. System assumptions

1. **Mocked integrations.** Handheld readers, gates, smart-card provider, CCTV, e-mail and the legacy LMS are simulated; behaviour on real hardware is unproven.
2. **One physical copy per tag.** A tag maps to exactly one copy and a copy carries one tag.
3. **Security-bit semantics.** Armed (`True`) means not issued; checkout disarms and check-in re-arms. An unknown item at a gate is treated as armed (fail-secure).
4. **Offline security check.** The gate decision uses locally held data and never calls out; this stands in for the offline cache required by FR 07.
5. **Role transport.** Roles arrive in the `X-Role` header from a trusted front end that authenticates users and strips client-supplied values.
6. **Single instance.** The API runs one process, because its operational data lives in memory.
7. **Migration scope.** Spreadsheet imports cover members and book copies with tags; each row is one record; the first row is the header; text is read as strings.
8. **Duplicate keys.** Members duplicate on `member_code`; books on `accession_no` and `tag_uid`. Rows already migrated by an earlier batch are detected through the staging table.
9. **Currency and dates.** Fines are plain numbers in the library's currency; all timestamps are UTC.
10. **Platform.** Target platform is Windows 11 / Server 2022 on an isolated network; test evidence comes from Linux with Python 3.12.3.
11. **Source of requirements.** FR, NFR and AC text is the SOP wording supplied by the project team; the definitions of deliverables D0, D2, D3, D5, D6 and D10 were not supplied.

---

## 9. Document control

| Version | Date | Description |
|---|---|---|
| 1.0 | 2026-10-05 | Initial traceability of all 31 SOP requirements against release 1.0.0 (53/53 tests passing) |
