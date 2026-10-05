"""
Acceptance tests for the RFID Library System, aligned to the SOP scenarios
==========================================================================
Run:  pip install pytest httpx fastapi pandas sqlalchemy
      pytest -v test_acceptance.py          (main.py and migrate.py in same folder)

Test class -> SOP acceptance scenario
  TestAC01SpreadsheetImport, TestAC01ValidationAndDuplicates   AC 01 import / reject / duplicates / reconcile
  TestAC02TagAssociation                                       AC 02 tag association (partial: no item-create API)
  TestAC03NCIP, TestAC03SIP2                                   AC 03 checkout / check-in (renewal and audit history NOT built)
  TestAC04CirculationBlocking                                  AC 04 reference / blocked member / fine limit
  TestAC05InventoryAudit                                       AC 05 handheld audit (no audible/visible confirmation yet)
  TestAC06GateEvent                                            AC 06 gate event, accession, CCTV mock, queued email
  TestAC07RoleAccess                                           AC 07 (partial: RBAC enforced; smart-card login NOT built)
  TestAC10BackupRestore                                        AC 10 restore from backup after failed migration
  TestMigrationRollback                                        FR 10 rollback / NFR 01 no corruption
  TestPerformance                                              NFR 05 performance (20,000-row import)
SOP AC 08 (dashboard/reports) and AC 09 (offline update) have no automated test; see
REQUIREMENTS_TRACEABILITY_MATRIX.md.
"""
import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import main
import migrate

ADMIN = {"X-Role": "admin"}
LIBRARIAN = {"X-Role": "librarian"}

CHECKOUT = "/circulation/checkout"
CHECKIN = "/circulation/checkin"
NCIP = "/api/v1/ncip"
SIP2 = "/api/v1/sip2"
GATE = "/api/v1/gate/event"
SCAN = "/api/v1/inventory/scan"

# Seeded data in main.py: members 1 (clean), 2 (fines at limit), 3 (blocked);
# copies ACC-1001/1002 (A-01), ACC-2001 (A-02), ACC-3001 (reference, R-01).


# =============================================================================
# FIXTURES & HELPERS
# =============================================================================
@pytest.fixture()
def client():
    main.store.__init__()            # reset seed data in place (services share this object)
    return TestClient(main.app)


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'library.db'}"


def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
    return path


def run_mig(entity, csv_path, db_url, tmp_path, rollback=False):
    return migrate.run_migration(
        csv_path, entity, db_url,
        error_log=tmp_path / "error_log.csv",
        report_path=tmp_path / "report.txt",
        rollback_on_error=rollback)


def count(db_url, table):
    engine = create_engine(db_url)
    try:
        with engine.connect() as c:
            return c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
    finally:
        engine.dispose()


def error_log(tmp_path):
    return pd.read_csv(tmp_path / "error_log.csv", dtype=str, keep_default_na=False)


def member(code, name="Test User", email="t@example.com", phone="", mtype="STUDENT"):
    return {"member_code": code, "full_name": name, "email": email,
            "phone": phone, "member_type": mtype}


def book(acc, tag, isbn="9780132126953", shelf="A-02", title="Computer Networks"):
    return {"isbn": isbn, "title": title, "author": "Author", "publisher": "Pub",
            "pub_year": "2010", "category": "CS", "accession_no": acc,
            "tag_uid": tag, "shelf_location": shelf}


GOOD_MEMBERS = [member("M001", "Asha Rao", "asha@example.com", "9876543210"),
                member("M002", "Ravi Kumar", "ravi@example.com", "+919876543211", "FACULTY"),
                member("M003", "Meena Iyer", "meena@example.com", "", "STAFF")]

GOOD_BOOKS = [book("ACC-1001", "E2000001", "9780262033848", "A-01", "Introduction to Algorithms"),
              book("ACC-1002", "E2000002", "9780262033848", "A-01", "Introduction to Algorithms"),
              book("ACC-2001", "E2000003")]

# SIP2 message builders (fixed-length header + variable fields)
SIP_DATE = "20261005    120000"       # 18 chars


def sip_checkout(patron, item):
    return "11NN" + SIP_DATE + " " * 18 + f"AOLIB|AA{patron}|AB{item}|AC|"


def sip_checkin(item):
    return "09N" + SIP_DATE + SIP_DATE + f"APLIB|AOLIB|AB{item}|AC|"


def sip_item_info(item):
    return "17" + SIP_DATE + f"AOLIB|AB{item}|AC|"


def sip(client, msg):
    return client.post(SIP2, content=msg).text


def checkout(client, member_id, acc):
    return client.post(CHECKOUT, json={"member_id": member_id, "accession_no": acc})


# =============================================================================
# SOP AC 01 - Spreadsheet import
# =============================================================================
class TestAC01SpreadsheetImport:
    def test_member_file_imported_and_reconciled(self, tmp_path, db_url):
        csv = write_csv(tmp_path / "members.csv", GOOD_MEMBERS)
        rep = run_mig("members", csv, db_url, tmp_path)
        assert rep["status"] == "COMMITTED"
        assert (rep["total_read"], rep["valid"], rep["rejected"], rep["inserted"]) == (3, 3, 0, 3)
        assert rep["reconciled"] is True
        assert count(db_url, "members") == 3
        assert "RECONCILIATION SUMMARY" in (tmp_path / "report.txt").read_text()

    def test_book_file_creates_titles_copies_and_tags(self, tmp_path, db_url):
        csv = write_csv(tmp_path / "books.csv", GOOD_BOOKS)
        rep = run_mig("books", csv, db_url, tmp_path)
        assert rep["inserted"] == 3
        assert rep["details"] == {"titles_created": 2, "copies_created": 3, "tags_mapped": 3}
        assert count(db_url, "titles") == 2          # two copies share one ISBN
        assert count(db_url, "book_copies") == 3
        assert count(db_url, "rfid_tag_mappings") == 3

    def test_cli_exit_code_zero_on_success(self, tmp_path, db_url):
        csv = write_csv(tmp_path / "members.csv", GOOD_MEMBERS)
        code = migrate.main([str(csv), "--entity", "members", "--db", db_url,
                             "--error-log", str(tmp_path / "e.csv"),
                             "--report", str(tmp_path / "r.txt")])
        assert code == 0

    def test_xlsx_spreadsheet_is_imported(self, tmp_path, db_url):
        pytest.importorskip("openpyxl")
        xlsx = tmp_path / "members.xlsx"
        pd.DataFrame(GOOD_MEMBERS).to_excel(xlsx, index=False)
        rep = run_mig("members", xlsx, db_url, tmp_path)
        assert (rep["total_read"], rep["valid"], rep["inserted"]) == (3, 3, 3)
        assert count(db_url, "members") == 3


# =============================================================================
# SOP AC 01 (cont.) - Validation, error log, duplicates against staging
# =============================================================================
class TestAC01ValidationAndDuplicates:
    def test_bad_rows_logged_and_good_rows_imported(self, tmp_path, db_url):
        rows = [member("M001"),
                member("M002", email="not-an-email"),            # row 3
                member("M003", name=""),                         # row 4
                member("M001", name="Duplicate of row 2"),       # row 5
                member("M005", name="Bad\ufffdName")]            # row 6
        rep = run_mig("members", write_csv(tmp_path / "m.csv", rows), db_url, tmp_path)

        assert (rep["total_read"], rep["valid"], rep["rejected"], rep["inserted"]) == (5, 1, 4, 1)
        assert (rep["rejected_invalid"], rep["rejected_duplicate"]) == (3, 1)
        assert rep["reconciled"] is True

        log = error_log(tmp_path)
        assert len(log) == 4
        reasons = " | ".join(log["reason"])
        for code in ("INVALID_EMAIL", "MISSING_FULL_NAME", "DUPLICATE_IN_FILE", "CORRUPTED_VALUE"):
            assert code in reasons
        assert list(log["row_number"]) == ["3", "4", "5", "6"]   # spreadsheet row numbers

    def test_duplicates_detected_against_staging_on_rerun(self, tmp_path, db_url):
        run_mig("members", write_csv(tmp_path / "a.csv", [member("M001")]), db_url, tmp_path)
        rep = run_mig("members",
                      write_csv(tmp_path / "b.csv", [member("M001"), member("M009")]),
                      db_url, tmp_path)
        assert (rep["valid"], rep["rejected"], rep["inserted"]) == (1, 1, 1)
        assert error_log(tmp_path)["reason"].iloc[0] == "DUPLICATE_IN_STAGING"
        assert count(db_url, "members") == 2

    def test_book_validation_rules(self, tmp_path, db_url):
        rows = [book("ACC-1", "E2000001"),
                book("ACC-2", "ZZZ"),                       # bad tag
                book("ACC-3", "E2000003", isbn="123"),      # bad ISBN
                book("ACC-4", "E2000001"),                  # tag reused in file
                book("ACC-1", "E2000009")]                  # duplicate accession
        rep = run_mig("books", write_csv(tmp_path / "b.csv", rows), db_url, tmp_path)
        assert (rep["valid"], rep["rejected"], rep["inserted"]) == (1, 4, 1)
        reasons = " | ".join(error_log(tmp_path)["reason"])
        for code in ("INVALID_TAG_UID", "INVALID_ISBN", "DUPLICATE_TAG_IN_FILE", "DUPLICATE_IN_FILE"):
            assert code in reasons

    def test_missing_required_column_is_schema_error(self, tmp_path, db_url):
        csv = write_csv(tmp_path / "bad.csv", [{"member_code": "M001"}])   # no full_name
        with pytest.raises(migrate.SchemaError):
            run_mig("members", csv, db_url, tmp_path)
        assert migrate.main([str(csv), "--entity", "members", "--db", db_url,
                             "--error-log", str(tmp_path / "e.csv"),
                             "--report", str(tmp_path / "r.txt")]) == 2


# =============================================================================
# SOP AC 02 - RFID tag association
# =============================================================================
class TestAC02TagAssociation:
    def test_migrated_tags_are_linked_to_their_copies(self, tmp_path, db_url):
        run_mig("books", write_csv(tmp_path / "b.csv", GOOD_BOOKS), db_url, tmp_path)
        engine = create_engine(db_url)
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT c.accession_no, t.tag_uid, t.security_bit FROM rfid_tag_mappings t "
                "JOIN book_copies c ON c.copy_id = t.copy_id")).all()
        engine.dispose()
        assert {(a, t) for a, t, _ in rows} == {
            ("ACC-1001", "E2000001"), ("ACC-1002", "E2000002"), ("ACC-2001", "E2000003")}
        assert all(bit for _, _, bit in rows)          # new tags start armed

    def test_associate_tag_via_api_then_found_by_audit(self, client):
        r = client.post("/rfid/tags/associate", headers=LIBRARIAN,
                        json={"accession_no": "ACC-1002", "tag_uid": "e2000099"})
        assert r.status_code == 200
        assert r.json()["tag_uid"] == "E2000099"       # normalised to upper case
        audit = client.post(SCAN, json={"shelf_location": "A-01",
                                        "scanned_tags": ["E2000099"]}).json()
        assert "ACC-1002" in audit["found"]

    def test_tag_cannot_be_mapped_to_two_copies(self, client):
        r = client.post("/rfid/tags/associate", headers=ADMIN,
                        json={"accession_no": "ACC-1002", "tag_uid": "E2000001"})
        assert r.status_code == 409
        assert r.json()["error"] == "TAG_ALREADY_MAPPED"

    def test_unknown_item_returns_404(self, client):
        r = client.post("/rfid/tags/associate", headers=ADMIN,
                        json={"accession_no": "NOPE", "tag_uid": "E2000077"})
        assert r.status_code == 404


# =============================================================================
# SOP AC 03 - NCIP 2.0 flow
# =============================================================================
class TestAC03NCIP:
    def test_checkout_item(self, client):
        r = client.post(NCIP, json={"service": "CheckOutItem", "user_id": "1", "item_id": "ACC-1001"})
        body = r.json()["NCIPMessage"]["CheckOutItemResponse"]
        assert body["ItemId"] == "ACC-1001" and "DateDue" in body
        assert main.store.copies["ACC-1001"].status == "ISSUED"
        assert main.store.copies["ACC-1001"].security_armed is False

    def test_item_information(self, client):
        r = client.post(NCIP, json={"service": "ItemInformation", "item_id": "ACC-1001"})
        info = r.json()["NCIPMessage"]["LookupItemResponse"]
        assert info["CirculationStatus"] == "AVAILABLE" and info["Location"] == "A-01"

    def test_checkin_item(self, client):
        client.post(NCIP, json={"service": "CheckOutItem", "user_id": "1", "item_id": "ACC-1001"})
        r = client.post(NCIP, json={"service": "CheckInItem", "item_id": "ACC-1001"})
        assert r.json()["NCIPMessage"]["CheckInItemResponse"]["FineAssessed"] == 0.0
        assert main.store.copies["ACC-1001"].security_armed is True

    def test_denied_checkout_returns_problem_element(self, client):
        r = client.post(NCIP, json={"service": "CheckOutItem", "user_id": "3", "item_id": "ACC-1001"})
        assert r.json()["NCIPMessage"]["Problem"]["ProblemType"] == "MEMBER_BLOCKED"


# =============================================================================
# SOP AC 03 - SIP2 flow
# =============================================================================
class TestAC03SIP2:
    def test_checkout_info_checkin_cycle(self, client):
        assert sip(client, sip_checkout(1, "ACC-1001")).startswith("121")     # 12 + ok=1
        info = sip(client, sip_item_info("ACC-1001"))
        assert info.startswith("18") and info[2:4] == "04"                    # 04 = charged out
        assert sip(client, sip_checkin("ACC-1001")).startswith("101")         # 10 + ok=1
        assert sip(client, sip_item_info("ACC-1001"))[2:4] == "03"            # 03 = available

    def test_denied_checkout_reports_reason(self, client):
        resp = sip(client, sip_checkout(1, "ACC-3001"))                       # reference book
        assert resp.startswith("120") and "Reference books cannot" in resp

    def test_unknown_message_requests_resend(self, client):
        assert sip(client, "99garbage") == "96"


# =============================================================================
# SOP AC 04 - Circulation blocking (member block, fine limit, reference books)
# =============================================================================
class TestAC04CirculationBlocking:
    def test_blocked_member_cannot_check_out(self, client):
        r = checkout(client, 3, "ACC-1001")
        assert r.status_code == 403 and r.json()["error"] == "MEMBER_BLOCKED"

    def test_member_at_fine_limit_cannot_check_out(self, client):
        r = checkout(client, 2, "ACC-1001")
        assert r.status_code == 403 and r.json()["error"] == "FINE_LIMIT_EXCEEDED"

    def test_reference_book_cannot_be_checked_out(self, client):
        r = checkout(client, 1, "ACC-3001")
        assert r.status_code == 409 and r.json()["error"] == "REFERENCE_ONLY"

    def test_admin_block_and_unblock_member(self, client):
        assert checkout(client, 1, "ACC-1001").status_code == 200
        client.post(CHECKIN, json={"accession_no": "ACC-1001"})
        r = client.post("/members/1/block", headers=ADMIN, json={"reason": "Lost item"})
        assert r.status_code == 200 and r.json()["blocked"] is True
        assert checkout(client, 1, "ACC-1002").json()["error"] == "MEMBER_BLOCKED"
        client.post("/members/1/block", headers=ADMIN, json={"reason": "cleared", "blocked": False})
        assert checkout(client, 1, "ACC-1002").status_code == 200

    def test_overdue_fine_pushes_member_over_limit(self, client):
        main.store.members[1].outstanding_fines = 495.0
        assert checkout(client, 1, "ACC-1001").status_code == 200
        late = (datetime.now(timezone.utc) + timedelta(days=17)).isoformat()   # ~3 days overdue
        r = client.post(CHECKIN, json={"accession_no": "ACC-1001", "returned_at": late})
        assert r.json()["fine_assessed"] >= 6.0
        assert r.json()["member_outstanding_fines"] >= main.FINE_LIMIT
        assert checkout(client, 1, "ACC-1002").json()["error"] == "FINE_LIMIT_EXCEEDED"

    def test_item_already_issued_cannot_be_checked_out_again(self, client):
        checkout(client, 1, "ACC-1001")
        r = checkout(client, 1, "ACC-1001")
        assert r.status_code == 409 and r.json()["error"] == "ITEM_NOT_AVAILABLE"


# =============================================================================
# SOP AC 05 - Handheld inventory audit
# =============================================================================
class TestAC05InventoryAudit:
    def test_flags_missing_misplaced_and_unknown(self, client):
        r = client.post(SCAN, json={"shelf_location": "A-01",
                                    "scanned_tags": ["E2000001", "E2000003", "E9999999"]})
        res = r.json()
        assert res["found"] == ["ACC-1001"]
        assert res["missing"] == ["ACC-1002"]                       # expected on A-01, not scanned
        assert res["misplaced"] == [{"accession_no": "ACC-2001",
                                     "expected_shelf": "A-02", "found_on_shelf": "A-01"}]
        assert res["unknown_tags"] == ["E9999999"]

    def test_duplicate_reads_are_collapsed(self, client):
        res = client.post(SCAN, json={"shelf_location": "A-01",
                                      "scanned_tags": ["E2000001"] * 5 + ["E2000002"]}).json()
        assert res["scanned_count"] == 2 and res["missing"] == []

    def test_issued_item_on_shelf_is_flagged_not_missing(self, client):
        checkout(client, 1, "ACC-1001")
        res = client.post(SCAN, json={"shelf_location": "A-01",
                                      "scanned_tags": ["E2000001", "E2000002"]}).json()
        assert res["issued_but_on_shelf"] == ["ACC-1001"]
        assert res["found"] == ["ACC-1002"] and res["missing"] == []


# =============================================================================
# SOP AC 06 - Gate event trigger
# =============================================================================
class TestAC06GateEvent:
    def test_unissued_item_triggers_alarm_cctv_and_email(self, client):
        r = client.post(GATE, json={"gate_id": "GATE-01", "accession_no": "ACC-1002"}).json()
        assert r["alarm"] is True and r["security_bit"] == "ARMED"
        assert r["check_mode"] == "OFFLINE"
        assert r["cctv_snapshot_ref"].startswith("cctv://mock/GATE-01/")

        log = client.get("/api/v1/gate/alarms", headers=ADMIN).json()
        assert len(log["alarms"]) == 1
        mail = log["email_queue"][0]
        assert mail["alarm_id"] == r["alarm_id"] and "ACC-1002" in mail["subject"]
        assert mail["status"] == "SENT"                  # background worker delivered it

    def test_properly_issued_item_passes_silently(self, client):
        checkout(client, 1, "ACC-1001")
        r = client.post(GATE, json={"gate_id": "GATE-01", "accession_no": "ACC-1001"}).json()
        assert r["alarm"] is False and r["security_bit"] == "DISARMED"
        assert client.get("/api/v1/gate/alarms", headers=ADMIN).json()["alarms"] == []

    def test_returned_item_re_arms_and_alarms(self, client):
        checkout(client, 1, "ACC-1001")
        client.post(CHECKIN, json={"accession_no": "ACC-1001"})
        assert client.post(GATE, json={"gate_id": "G2", "accession_no": "ACC-1001"}).json()["alarm"]

    def test_unknown_item_fails_secure(self, client):
        r = client.post(GATE, json={"gate_id": "GATE-01", "accession_no": "GHOST"}).json()
        assert r["alarm"] is True and r["security_bit"] == "UNKNOWN"


# =============================================================================
# SOP AC 07 (partial) - Role-based access control
# =============================================================================
class TestAC07RoleAccess:
    @pytest.mark.parametrize("headers,expected", [
        ({}, 403), ({"X-Role": "patron"}, 403), (LIBRARIAN, 403), (ADMIN, 200)])
    def test_block_member_is_admin_only(self, client, headers, expected):
        r = client.post("/members/1/block", headers=headers, json={"reason": "policy breach"})
        assert r.status_code == expected
        if expected == 403:
            assert r.json()["error"] == "FORBIDDEN"
            assert main.store.members[1].blocked is False      # state untouched

    @pytest.mark.parametrize("headers,expected", [
        ({}, 403), (LIBRARIAN, 403), (ADMIN, 200)])
    def test_alarm_log_is_admin_only(self, client, headers, expected):
        assert client.get("/api/v1/gate/alarms", headers=headers).status_code == expected

    @pytest.mark.parametrize("headers,expected", [
        ({}, 403), ({"X-Role": "patron"}, 403), (LIBRARIAN, 200), (ADMIN, 200)])
    def test_tag_association_needs_staff_role(self, client, headers, expected):
        r = client.post("/rfid/tags/associate", headers=headers,
                        json={"accession_no": "ACC-1002", "tag_uid": "E2000055"})
        assert r.status_code == expected

    def test_role_check_is_case_insensitive(self, client):
        r = client.post("/members/1/block", headers={"X-Role": "ADMIN"}, json={"reason": "test run"})
        assert r.status_code == 200


# =============================================================================
# FR 10 / NFR 01 - Migration rollback
# =============================================================================
class TestMigrationRollback:
    MIXED = [member("M001"), member("M002", email="broken"), member("M003")]

    def test_rollback_flag_reverts_entire_batch_when_any_row_rejected(self, tmp_path, db_url):
        rep = run_mig("members", write_csv(tmp_path / "m.csv", self.MIXED),
                      db_url, tmp_path, rollback=True)
        assert rep["status"] == "ROLLED_BACK" and rep["inserted"] == 0
        assert rep["valid"] == 2 and rep["rejected"] == 1 and rep["reconciled"] is True
        assert count(db_url, "members") == 0              # nothing survived
        assert count(db_url, "migration_staging") == 0    # staging reverted too
        assert len(error_log(tmp_path)) == 1              # rejected row still reported

    def test_without_flag_valid_rows_are_committed(self, tmp_path, db_url):
        rep = run_mig("members", write_csv(tmp_path / "m.csv", self.MIXED), db_url, tmp_path)
        assert rep["status"] == "COMMITTED" and rep["inserted"] == 2
        assert count(db_url, "members") == 2

    def test_cli_exit_code_one_on_rollback(self, tmp_path, db_url):
        csv = write_csv(tmp_path / "m.csv", self.MIXED)
        code = migrate.main([str(csv), "--entity", "members", "--db", db_url, "--rollback",
                             "--error-log", str(tmp_path / "e.csv"),
                             "--report", str(tmp_path / "r.txt")])
        assert code == 1
        assert count(db_url, "members") == 0

    @pytest.mark.parametrize("flag", [True, False])
    def test_unexpected_error_mid_load_reverts_everything(self, tmp_path, db_url, monkeypatch, flag):
        real_insert = migrate.insert_members

        def explode_after_insert(conn, rows):
            real_insert(conn, rows)                        # rows ARE inserted...
            raise RuntimeError("simulated disk failure")   # ...then the load fails

        monkeypatch.setattr(migrate, "insert_members", explode_after_insert)
        rep = run_mig("members", write_csv(tmp_path / "m.csv", GOOD_MEMBERS),
                      db_url, tmp_path, rollback=flag)
        assert rep["status"] == "ROLLED_BACK"
        assert "simulated disk failure" in rep["fatal_error"]
        assert count(db_url, "members") == 0 and count(db_url, "migration_staging") == 0

    def test_book_rollback_leaves_no_orphan_titles_copies_or_tags(self, tmp_path, db_url):
        rows = GOOD_BOOKS + [book("ACC-9", "ZZZ")]         # one invalid tag
        rep = run_mig("books", write_csv(tmp_path / "b.csv", rows), db_url, tmp_path, rollback=True)
        assert rep["status"] == "ROLLED_BACK"
        for table in ("titles", "book_copies", "rfid_tag_mappings", "migration_staging"):
            assert count(db_url, table) == 0, table


# =============================================================================
# SOP AC 10 - Restore from backup after a simulated failed migration
# =============================================================================
def members_snapshot(db_url):
    engine = create_engine(db_url)
    try:
        with engine.connect() as c:
            return [tuple(r) for r in c.execute(text(
                "SELECT member_code, full_name, email, phone, member_type, status "
                "FROM members ORDER BY member_code")).all()]
    finally:
        engine.dispose()


def sqlite_backup(src_file, dest_file):
    """Same online-backup call used by the runbook's backup.ps1."""
    src, dst = sqlite3.connect(src_file), sqlite3.connect(dest_file)
    src.backup(dst)
    dst.close()
    src.close()


class TestAC10BackupRestore:
    def test_failed_migration_then_restore_proves_original_data_intact(
            self, tmp_path, db_url, monkeypatch):
        db_file = tmp_path / "library.db"
        run_mig("members", write_csv(tmp_path / "orig.csv", GOOD_MEMBERS), db_url, tmp_path)
        original = members_snapshot(db_url)
        assert len(original) == 3

        backup = tmp_path / "backup.db"
        sqlite_backup(db_file, backup)                         # 1. back up first

        real_insert = migrate.insert_members                   # 2. simulate a failed migration
        def explode(conn, rows):
            real_insert(conn, rows)
            raise RuntimeError("simulated integration failure")
        monkeypatch.setattr(migrate, "insert_members", explode)
        rep = run_mig("members",
                      write_csv(tmp_path / "new.csv", [member("M100"), member("M101")]),
                      db_url, tmp_path)
        assert rep["status"] == "ROLLED_BACK"
        assert members_snapshot(db_url) == original            # 3. nothing changed

        c = sqlite3.connect(db_file)                           # 4. simulate worse damage
        c.execute("DELETE FROM members")
        c.commit()
        c.close()
        assert members_snapshot(db_url) == []

        shutil.copyfile(backup, db_file)                       # 5. restore from backup
        assert members_snapshot(db_url) == original            # original data intact
        c = sqlite3.connect(db_file)
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()

    def test_migration_never_modifies_existing_records(self, tmp_path, db_url):
        run_mig("members", write_csv(tmp_path / "orig.csv", GOOD_MEMBERS), db_url, tmp_path)
        original = members_snapshot(db_url)
        clash = [member("M001", name="Overwrite Attempt", email="evil@example.com"),
                 member("M200", name="New Member")]
        rep = run_mig("members", write_csv(tmp_path / "clash.csv", clash), db_url, tmp_path)
        assert rep["inserted"] == 1 and rep["rejected_duplicate"] == 1
        after = members_snapshot(db_url)
        assert [r for r in after if r[0] != "M200"] == original  # existing rows untouched


# =============================================================================
# NFR 05 - Performance: ~20,000-record import (FR 10 volume)
# =============================================================================
class TestPerformance:
    def test_twenty_thousand_member_rows_import_within_budget(self, tmp_path, db_url):
        rows = [member(f"M{i:06d}", f"Member {i}", f"m{i}@example.com", "9876543210")
                for i in range(20000)]
        csv = write_csv(tmp_path / "bulk.csv", rows)
        start = time.perf_counter()
        rep = run_mig("members", csv, db_url, tmp_path)
        elapsed = time.perf_counter() - start
        assert rep["inserted"] == 20000 and rep["rejected"] == 0 and rep["reconciled"]
        assert count(db_url, "members") == 20000
        assert elapsed < 60, f"20,000-row import took {elapsed:.1f}s"
