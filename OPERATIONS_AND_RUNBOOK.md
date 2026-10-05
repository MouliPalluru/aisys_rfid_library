# AISYS RFID Library Management System — Operations Guide & Runbook

| Field | Value |
|---|---|
| Document | `OPERATIONS_AND_RUNBOOK.md` |
| Fulfils | SOP Deliverables D7 and D8 |
| Version / date | 1.0 / 2026-10-05 |
| Audience | System administrators, library staff, on-call engineers |
| Target platforms | Windows 11, Windows Server 2022 (air-gapped) |
| Software baseline | Python 3.12.x (64-bit), pinned packages in `LICENSE_INVENTORY.md` §5 |

---

## 0. Release scope and operating constraints

This runbook describes the system **as delivered in release 1.0.0**. Four characteristics of that release shape every procedure below; they are stated up front so no procedure over-promises.

| # | Characteristic | Operational consequence |
|---|---|---|
| 1 | The API keeps catalog, members, loans, alarms and the email queue **in process memory** (`Store` class in `main.py`), seeded with demo data at start-up. | API state is **lost on restart**. Run **exactly one** uvicorn worker (several workers would each hold a different copy of the data). |
| 2 | `migrate.py` writes to a **SQLite** file (`library.db`). The API does not yet read that file. | Backups protect migrated data and migration evidence. Restoring API runtime state means restarting the service; persistence wiring is in the production-readiness backlog. |
| 3 | RBAC reads the caller's role from the **`X-Role` request header** (`admin`, `librarian`, `patron`). | The header is trustworthy only when a **trusted front end sets it** and clients cannot (§1.1). Never expose the service port directly to untrusted networks. |
| 4 | Notifications are a **mock queue**; CCTV capture returns a **mock reference string**. | Alarm e-mails are queued and marked `SENT` without leaving the host. Real SMTP/ONVIF integration is out of scope for 1.0.0. |

Tunable business rules are constants at the top of `main.py` (no environment configuration exists):

| Constant | Value | Meaning |
|---|---|---|
| `LOAN_DAYS` | 14 | Standard loan period |
| `MAX_LOANS` | 5 | Concurrent loans per member |
| `FINE_PER_DAY` | 2.0 | Overdue fine per day |
| `FINE_LIMIT` | 500.0 | Checkout refused once outstanding fines reach this value |
| `SECURITY_EMAIL` | `security@library.example` | Alarm notification recipient |
| `INSTITUTION_ID` | `LIB01` | SIP2 `AO` institution field |

Changing a constant is a code change: follow the update procedure in §3.6.

---

## 1. Administrator Guide

### 1.1 Role-Based Access Control (RBAC)

**Roles and permissions**

| Endpoint | Method | `admin` | `librarian` | `patron` / none |
|---|---|:---:|:---:|:---:|
| `/members/{id}/block` | POST | ✔ | ✘ 403 | ✘ 403 |
| `/api/v1/gate/alarms` | GET | ✔ | ✘ 403 | ✘ 403 |
| `/rfid/tags/associate` | POST | ✔ | ✔ | ✘ 403 |
| `/catalog`, `/circulation/checkout`, `/circulation/checkin` | GET / POST | open | open | open |
| `/members/{id}/fines/pay` | POST | open | open | open |
| `/api/v1/ncip`, `/api/v1/sip2` | POST | open | open | open |
| `/api/v1/gate/event`, `/api/v1/inventory/scan` | POST | open | open | open |
| `/health` | GET | open | open | open |

Role matching is case-insensitive. A missing or unknown role returns `403` with `{"error":"FORBIDDEN"}`. "Open" endpoints are intended for kiosks, the circulation desk, security gates and handheld readers on the **internal network only**.

**Required deployment pattern (trusted front end)**

1. Bind the API to the loopback interface only (`--host 127.0.0.1`, as in §3.4).
2. Place a reverse proxy on the same host (for example IIS with URL Rewrite and Application Request Routing) that authenticates staff against the institution's directory.
3. Configure the proxy to **delete any client-supplied `X-Role` header** and then set it from the authenticated user's directory group (`LMS-Admins` → `admin`, `LMS-Librarians` → `librarian`).
4. Allow unauthenticated access only from known device addresses (gates, kiosks, handhelds) and forward those requests **without** an `X-Role` header.

Without steps 2–3, any client able to reach the port can send `X-Role: admin`. Treat that as an open system.

**Verifying RBAC after any deployment**

```powershell
$base = "http://127.0.0.1:8000"
# Expect 403 (no role)
try { Invoke-RestMethod -Method Post "$base/members/1/block" -ContentType application/json `
      -Body (@{reason="rbac check"} | ConvertTo-Json) } catch { $_.Exception.Response.StatusCode.value__ }
# Expect 403 (librarian cannot block)
try { Invoke-RestMethod -Method Post "$base/members/1/block" -Headers @{"X-Role"="librarian"} -ContentType application/json `
      -Body (@{reason="rbac check"} | ConvertTo-Json) } catch { $_.Exception.Response.StatusCode.value__ }
# Expect 200 (admin) — then unblock
Invoke-RestMethod -Method Post "$base/members/1/block" -Headers @{"X-Role"="admin"} -ContentType application/json `
      -Body (@{reason="rbac check"} | ConvertTo-Json)
Invoke-RestMethod -Method Post "$base/members/1/block" -Headers @{"X-Role"="admin"} -ContentType application/json `
      -Body (@{reason="rbac check complete"; blocked=$false} | ConvertTo-Json)
```

The same behaviour is asserted automatically by the role-access tests (`pytest -k AC07`).

**Administrative actions**

| Task | Call | Notes |
|---|---|---|
| Block a member | `POST /members/{id}/block` body `{"reason":"…"}` | `reason` must be ≥ 3 characters; checkout then returns `MEMBER_BLOCKED` (403) |
| Unblock a member | same endpoint, body `{"reason":"…","blocked":false}` | Clears the stored block reason |
| Record a fine payment | `POST /members/{id}/fines/pay?amount=50` | Reduces outstanding fines, floor 0 |
| Review gate alarms and queued e-mails | `GET /api/v1/gate/alarms` with `X-Role: admin` | Returns `alarms` and `email_queue` |

### 1.2 System health checks

**Quick check** (run after every start, restart or update):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health          # expect: status = ok
```

**Full functional check** — `C:\AISYS\bin\check_health.ps1`:

```powershell
$base = "http://127.0.0.1:8000"; $fail = 0
function Check($name, [scriptblock]$test) {
    try { if (& $test) { "PASS  $name" } else { "FAIL  $name"; $script:fail++ } }
    catch { "FAIL  $name  ($($_.Exception.Message))"; $script:fail++ }
}
Check "health endpoint"      { (Invoke-RestMethod "$base/health").status -eq "ok" }
Check "catalog readable"     { (Invoke-RestMethod "$base/catalog").count -ge 0 }
Check "admin alarm log"      { (Invoke-RestMethod "$base/api/v1/gate/alarms" -Headers @{"X-Role"="admin"}).PSObject.Properties.Name -contains "alarms" }
Check "RBAC rejects anonymous" {
    try { Invoke-RestMethod "$base/api/v1/gate/alarms" | Out-Null; $false }
    catch { $_.Exception.Response.StatusCode.value__ -eq 403 } }
Check "database file present" { Test-Path C:\AISYS\data\library.db }
Check "database integrity"   {
    (& C:\AISYS\venv\Scripts\python.exe -c "import sqlite3;print(sqlite3.connect('C:/AISYS/data/library.db').execute('PRAGMA integrity_check').fetchone()[0])") -eq "ok" }
Check "free disk > 5 GB"     { (Get-PSDrive C).Free -gt 5GB }
exit $fail
```

Schedule it every 5 minutes with Task Scheduler and alert the on-call administrator on a non-zero exit code. The process exit code is the number of failed checks.

**Deep verification (maintenance window only):** run the acceptance suite from the application folder: `C:\AISYS\venv\Scripts\python -m pytest -q C:\AISYS\app\test_acceptance.py`. Expected result: **53 passed**. The suite runs in its own Python process against an in-process copy of the application and temporary SQLite files, so it does not touch the live service's data; run it off-peak because it uses CPU on the same host.

### 1.3 Logging

| Log | Location | Content |
|---|---|---|
| Service log | `C:\AISYS\logs\uvicorn.log` | Start-up/shutdown messages, access log (method, path, status), unhandled exceptions with stack traces |
| Migration error log | `C:\AISYS\data\migrations\<batch>_error_log.csv` | One row per rejected record: row number, reason code, raw row |
| Migration report | `C:\AISYS\data\migrations\<batch>_report.txt` | Reconciliation summary: Total Read, Valid, Rejected, Inserted, status |
| Gate alarm record | In memory — read via `GET /api/v1/gate/alarms` | Gate ID, accession number, security-bit state, `OFFLINE` check mode, CCTV reference, timestamps |
| Task Scheduler history | Windows Task Scheduler → `AISYS-LMS` | Whether the service wrapper started or exited |

The service redirects uvicorn's stdout/stderr into `uvicorn.log` (§3.4). The application code emits no custom log lines; business-rule rejections appear in the access log as `403`/`404`/`409` responses.

**Reading the log**

```powershell
Get-Content C:\AISYS\logs\uvicorn.log -Tail 100
Select-String -Path C:\AISYS\logs\uvicorn.log -Pattern " 403 | 409 | 500 "
```

**Rotation (weekly maintenance window).** The log file is held open by the running process, so rotate while the service is stopped:

```powershell
schtasks /End /TN "AISYS-LMS"; C:\AISYS\bin\stop_aisys.ps1
$ts = Get-Date -Format "yyyyMMdd"
Move-Item C:\AISYS\logs\uvicorn.log "C:\AISYS\logs\uvicorn-$ts.log"
Compress-Archive "C:\AISYS\logs\uvicorn-$ts.log" "C:\AISYS\logs\uvicorn-$ts.zip"; Remove-Item "C:\AISYS\logs\uvicorn-$ts.log"
Get-ChildItem C:\AISYS\logs\uvicorn-*.zip | Where-Object LastWriteTime -lt (Get-Date).AddDays(-90) | Remove-Item
schtasks /Run /TN "AISYS-LMS"
```

Retention: keep 90 days of service logs; keep migration logs and reports for the life of the data they describe.

**Security-relevant events to review weekly:** repeated `403` on `/members/*/block` or `/api/v1/gate/alarms` (probing); `500` responses; alarms outside opening hours; unexpected `POST /rfid/tags/associate` calls. The access log does not record request headers, so role-spoofing attempts are visible only in the reverse proxy's logs.

---

## 2. User Guide

All examples use PowerShell; the staff desktop application or kiosk software issues the same calls. Set once per session:

```powershell
$base = "http://127.0.0.1:8000"
$json = "application/json"
```

### 2.1 Circulation operations

**Search the catalog**

```powershell
Invoke-RestMethod "$base/catalog?q=algorithms"
Invoke-RestMethod "$base/catalog?q=networks&available_only=true"
```
Each title lists its copies (`accession_no`, `status`, `shelf`). Reference titles are marked `reference_only: true` and are never returned by `available_only=true`.

**Check out**

```powershell
Invoke-RestMethod -Method Post "$base/circulation/checkout" -ContentType $json `
  -Body (@{member_id=1; accession_no="ACC-1001"} | ConvertTo-Json)
```
Success returns `loan_id`, `due_at` (14 days out) and `security_bit: DISARMED`: the item can now pass the gate. Checkout is refused, with these codes:

| Code | HTTP | Cause | Staff action |
|---|---|---|---|
| `MEMBER_BLOCKED` | 403 | Member is blocked | Refer to an administrator; the reason is in the message |
| `FINE_LIMIT_EXCEEDED` | 403 | Outstanding fines ≥ 500.00 | Collect payment (§1.1), then retry |
| `REFERENCE_ONLY` | 409 | Reference book | Item is for in-library use only |
| `ITEM_NOT_AVAILABLE` | 409 | Copy is already issued or otherwise unavailable | Check the shelf/return queue |
| `LOAN_LIMIT_REACHED` | 409 | Member holds 5 loans | Ask the member to return an item |
| `MEMBER_NOT_FOUND` / `ITEM_NOT_FOUND` | 404 | Unknown ID or accession number | Re-scan; check the member record or tag mapping |

**Check in**

```powershell
Invoke-RestMethod -Method Post "$base/circulation/checkin" -ContentType $json `
  -Body (@{accession_no="ACC-1001"} | ConvertTo-Json)
```
The response gives `fine_assessed` (2.00 per overdue day), the member's `member_outstanding_fines`, and `security_bit: ARMED`. A `NOT_ON_LOAN` (409) error means the item was not issued; check for a missed checkout or a duplicate scan.

**Kiosk / third-party systems.** Self-service kiosks use SIP2 (`POST /api/v1/sip2`, messages `11` checkout, `09` checkin, `17` item information) and integrated systems use NCIP (`POST /api/v1/ncip`, services `CheckOutItem`, `CheckInItem`, `LookupItem`/`ItemInformation`). Both apply identical rules. A SIP2 response beginning `120` or `100` is a refusal with the reason in the `AF` field; `96` means the message was not recognised and should be resent.

### 2.2 RFID tagging workflows

Each physical copy has one tag; each tag maps to one copy. New tags are **armed** (security bit ON) until the item is checked out.

**A. Bulk tagging at onboarding (preferred).** Prepare a CSV/XLSX with columns `isbn, title, accession_no, tag_uid` (optional: `author, publisher, pub_year, category, shelf_location`). One row is one physical copy. Run the migration (§3.7); every imported copy gets its tag mapping in the same transaction. `tag_uid` must be 8–24 hexadecimal characters and is stored upper-case.

**B. Tag a single copy (librarian or admin).**

```powershell
Invoke-RestMethod -Method Post "$base/rfid/tags/associate" -Headers @{"X-Role"="librarian"} -ContentType $json `
  -Body (@{accession_no="ACC-1002"; tag_uid="E2000099"} | ConvertTo-Json)
```
A tag already mapped to another copy returns `TAG_ALREADY_MAPPED` (409): scan the tag again, and if it is genuinely in use, find which copy holds it before reassigning.

**C. Replace a damaged tag.** Encode the new tag, then associate the **new** UID to the **same accession number** (workflow B). The old UID is released. The copy is re-armed unless it is currently on loan.

**D. Verify a tag's security state.** SIP2 message `17` (or NCIP `LookupItem`) returns the item's status; in the SIP2 reply, security marker `02` means armed and `01` means not armed. An item sitting on the shelf must be armed; an issued item must not be.

### 2.3 Shelf audit (handheld reader)

1. **Choose one shelf** and note its location code exactly as catalogued (for example `A-01`). Audit one shelf at a time.
2. **Scan** the shelf with the handheld reader and export the list of tag UIDs, one per line (`tags.txt`). Duplicate reads are harmless; they are collapsed.
3. **Submit** the scan:

```powershell
$tags = Get-Content .\tags.txt
Invoke-RestMethod -Method Post "$base/api/v1/inventory/scan" -ContentType $json `
  -Body (@{shelf_location="A-01"; scanned_tags=$tags} | ConvertTo-Json)
```
4. **Act on each result list.** The audit is read-only: it never alters records.

| Result field | Meaning | Action |
|---|---|---|
| `found` | Copies on the correct shelf | None |
| `missing` | Catalogued as available on this shelf but not scanned | Re-scan the shelf; search nearby shelves and the return trolley; if still absent, record as lost per library policy |
| `misplaced` | Copy scanned here but catalogued for another shelf (`expected_shelf` is given) | Move the item to `expected_shelf` |
| `issued_but_on_shelf` | System shows the item on loan, yet it is physically here | Check the item in (§2.1) — usually a missed return |
| `unknown_tags` | Tag UID with no catalogue record | Inspect the item; tag it with workflow B, or remove a stray tag |
| `scanned_count` | Distinct tags read | Compare with the expected shelf count as a sanity check |

### 2.4 Gate alarms (security staff)

When an unissued item passes a gate, the gate software posts `POST /api/v1/gate/event` with `gate_id` and `accession_no`. The system checks the security bit; if the bit is armed (or the item is unknown — treated as armed, the fail-secure rule) it records an alarm, captures a CCTV reference (`cctv://mock/<gate>/<timestamp>.jpg`) and queues a notification to `SECURITY_EMAIL`. An administrator can review alarms and the e-mail queue through `GET /api/v1/gate/alarms`. Release 1.0.0 has no alarm-closure endpoint: record the disposition (false alarm, recovered item, escalation) in the institution's incident log.

---

## 3. Offline Deployment & Update Runbook (Windows 11 / Server 2022, air-gapped)

### 3.1 Target layout

```text
C:\AISYS\
├── releases\1.0.0\        main.py, migrate.py, test_acceptance.py, requirements.txt, requirements-dev.txt
├── app\                   junction → releases\<current version>
├── venv\                  Python virtual environment
├── wheelhouse\            offline wheels + SHA256SUMS.txt
├── installers\            python-3.12.x-amd64.exe + its SHA-256 record
├── data\                  library.db, migrations\
├── backups\               library-<timestamp>.db and .sha256 files
├── logs\                  uvicorn.log and archives
└── bin\                   start_aisys.cmd, stop_aisys.ps1, check_health.ps1, backup.ps1
```

### 3.2 Build the offline media kit (internet-connected staging machine)

The staging machine must match the target in OS family, Python minor version and architecture (Windows, 3.12, 64-bit).

1. Download the Python 3.12 Windows 64-bit installer and compute its hash: `Get-FileHash .\python-3.12.x-amd64.exe -Algorithm SHA256`. Compare it with the value published by python.org.
2. Build the wheelhouse and hash list exactly as in `LICENSE_INVENTORY.md` §7 (`pip download … --only-binary=:all:` then `Get-FileHash`).
3. Copy to the media: installer, wheelhouse (with `SHA256SUMS.txt`), release folder `1.0.0`, this runbook, `LICENSE_INVENTORY.md`.
4. Scan the media with the institution's approved malware scanner and hand it over per the site's removable-media procedure.

### 3.3 Install on the target

```powershell
# 1. Create folders
"installers","wheelhouse","releases\1.0.0","data\migrations","backups","logs","bin" |
  ForEach-Object { New-Item -ItemType Directory -Force "C:\AISYS\$_" | Out-Null }

# 2. Copy media contents into those folders, then verify every wheel hash
Get-Content C:\AISYS\wheelhouse\SHA256SUMS.txt | ForEach-Object {
    $h,$f = $_ -split "\s+",2
    if ((Get-FileHash "C:\AISYS\wheelhouse\$f" -Algorithm SHA256).Hash -ne $h) { throw "HASH MISMATCH: $f" } }
Get-FileHash C:\AISYS\installers\python-3.12.*-amd64.exe -Algorithm SHA256   # compare with the recorded value

# 3. Install Python silently for all users (no internet needed)
Start-Process C:\AISYS\installers\python-3.12.x-amd64.exe -Wait `
  -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0"

# 4. Create the venv and install from the wheelhouse only
py -3.12 -m venv C:\AISYS\venv
C:\AISYS\venv\Scripts\python -m pip install --no-index --find-links C:\AISYS\wheelhouse `
  -r C:\AISYS\releases\1.0.0\requirements.txt -r C:\AISYS\releases\1.0.0\requirements-dev.txt
C:\AISYS\venv\Scripts\python -m pip check

# 5. Activate the release
cmd /c mklink /J C:\AISYS\app C:\AISYS\releases\1.0.0

# 6. Prove the build before it serves anyone
C:\AISYS\venv\Scripts\python -m pytest -q C:\AISYS\app\test_acceptance.py     # expect 53 passed
```

Replace `python-3.12.x-amd64.exe` with the exact installer file name on the media. If any hash comparison fails, **stop**; do not install from that media.

### 3.4 Run as a start-up task

`C:\AISYS\bin\start_aisys.cmd`:

```bat
@echo off
cd /d C:\AISYS\app
C:\AISYS\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info >> C:\AISYS\logs\uvicorn.log 2>&1
```

`C:\AISYS\bin\stop_aisys.ps1`:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "uvicorn main:app" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Register and start (elevated prompt):

```powershell
schtasks /Create /TN "AISYS-LMS" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "C:\AISYS\bin\start_aisys.cmd" /F
schtasks /Run /TN "AISYS-LMS"
Start-Sleep 5; Invoke-RestMethod http://127.0.0.1:8000/health
```

Stop: `schtasks /End /TN "AISYS-LMS"; C:\AISYS\bin\stop_aisys.ps1`. Keep `--workers 1` (see §0). Do not use `--reload` in production. If the reverse proxy runs on a different host, add a Windows Firewall rule restricted to that host's address, for example:
`New-NetFirewallRule -DisplayName "AISYS LMS (proxy only)" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress 192.168.10.5 -Action Allow` and change `--host` to the server's internal address.

### 3.5 Database versioning

The database file is `C:\AISYS\data\library.db`. Its **schema version** is tracked in SQLite's built-in `user_version` header field, a procedural convention used by this runbook. `migrate.py` creates tables but does not set it, so a freshly created database reads `0`.

| `user_version` | Schema content |
|---|---|
| 0 | No version recorded (state immediately after `migrate.py` creates it) |
| 1 | Baseline: `members`, `titles`, `book_copies`, `rfid_tag_mappings`, `migration_staging` |

```powershell
# Read the version
C:\AISYS\venv\Scripts\python -c "import sqlite3;print(sqlite3.connect('C:/AISYS/data/library.db').execute('PRAGMA user_version').fetchone()[0])"
# Baseline a newly created database (once)
C:\AISYS\venv\Scripts\python -c "import sqlite3;c=sqlite3.connect('C:/AISYS/data/library.db');c.execute('PRAGMA user_version=1');c.commit()"
```

Each future schema change ships as a numbered SQL script in the release folder (for example `schema\002_add_x.sql`) that ends by setting `PRAGMA user_version = 2`, so the version advances only if the whole script succeeds.

### 3.6 Update procedure (new release `1.1.0`)

1. **Announce a maintenance window.** Circulation state is in memory, so an update ends in-flight sessions.
2. **Stage** the new media on the target: copy `releases\1.1.0`, any new wheels to `wheelhouse`, verify hashes as in §3.3 step 2.
3. **Back up** (§4.2) and note the pre-update `user_version` and the currently active release (`(Get-Item C:\AISYS\app).Target`).
4. **Install new dependencies** if `requirements.txt` changed: `pip install --no-index --find-links C:\AISYS\wheelhouse -r C:\AISYS\releases\1.1.0\requirements.txt`, then `pip check`.
5. **Test before switching:** `python -m pytest -q C:\AISYS\releases\1.1.0\test_acceptance.py` must report all tests passing.
6. **Apply schema scripts** in order, if any: `python -c "import sqlite3;c=sqlite3.connect('C:/AISYS/data/library.db');c.executescript(open(r'C:/AISYS/releases/1.1.0/schema/002_add_x.sql').read())"`. Confirm `user_version` advanced.
7. **Switch and restart:**
   ```powershell
   schtasks /End /TN "AISYS-LMS"; C:\AISYS\bin\stop_aisys.ps1
   cmd /c rmdir C:\AISYS\app                       # removes only the junction, not the release
   cmd /c mklink /J C:\AISYS\app C:\AISYS\releases\1.1.0
   schtasks /Run /TN "AISYS-LMS"
   ```
8. **Verify** with `check_health.ps1` and the RBAC check in §1.1. Record the outcome in the change log.

### 3.7 Running a data migration

```powershell
$batch = Get-Date -Format "yyyyMMdd-HHmm"
C:\AISYS\bin\backup.ps1                                    # always back up first (§4.2)
C:\AISYS\venv\Scripts\python C:\AISYS\app\migrate.py C:\AISYS\data\migrations\books.xlsx `
  --entity books --db C:/AISYS/data/library.db `
  --error-log "C:\AISYS\data\migrations\$batch`_error_log.csv" `
  --report    "C:\AISYS\data\migrations\$batch`_report.txt" --rollback
echo "exit=$LASTEXITCODE"
```

| Exit code | Meaning | Next step |
|---|---|---|
| 0 | Committed | Check the report: `Reconciled : YES`, `Inserted` equals `Valid` |
| 1 | Rolled back — nothing was imported | Open the error log, correct the source file, re-run |
| 2 | File or schema error (missing columns, unreadable or unsupported file) | Fix the file structure and re-run |

`--rollback` makes the batch **all-or-nothing**: one rejected row reverts everything, including the staging records. Omit the flag to import the valid rows and log the rejects. Any unexpected error mid-load always reverts the entire transaction, with or without the flag.

### 3.8 Rollback procedures

**R1 — Failed migration batch.** Nothing to do for exit code 1: the transaction was reverted. If a batch committed but proved wrong, restore the pre-migration backup (§4.3); no per-batch undo exists in 1.0.0.

**R2 — Bad application release.**
```powershell
schtasks /End /TN "AISYS-LMS"; C:\AISYS\bin\stop_aisys.ps1
cmd /c rmdir C:\AISYS\app
cmd /c mklink /J C:\AISYS\app C:\AISYS\releases\1.0.0        # previous known-good release
# If a schema script ran, also restore the pre-update database snapshot (§4.3)
schtasks /Run /TN "AISYS-LMS"
C:\AISYS\bin\check_health.ps1
```
Previous release folders stay on disk precisely so this takes minutes; delete a release only after its successor has run cleanly for one full month.

**R3 — Dependency problem.** Re-create the venv from the previous release's `requirements.txt` using `--no-index --find-links` (the wheelhouse retains older wheels), then redo R2.

---

## 4. Backup, Disaster Recovery & Incident Troubleshooting Runbook

### 4.1 What is protected

| Asset | Location | Backup method | Frequency |
|---|---|---|---|
| SQLite database | `C:\AISYS\data\library.db` | SQLite online backup (consistent while in use) | Daily 02:00, plus before every migration/update |
| Migration inputs, logs, reports | `C:\AISYS\data\migrations\` | File copy | Daily |
| Release folders and `requirements*.txt` | `C:\AISYS\releases\` | File copy | After every release |
| Offline media kit (installer, wheelhouse, hashes) | `C:\AISYS\installers\`, `wheelhouse\` | File copy | After every dependency change |
| Service scripts | `C:\AISYS\bin\` | File copy | After every change |
| API runtime state (loans, alarms, queue) | Process memory | **Not backed up** (see §0, item 1) | — |

**Recommended objectives** (adjust to institutional policy): recovery point ≤ 24 hours for the database; recovery time ≤ 4 hours for a full host rebuild from the media kit.

### 4.2 Backup procedure

`C:\AISYS\bin\backup.ps1`:

```powershell
$ts   = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = "C:\AISYS\backups\library-$ts.db"
C:\AISYS\venv\Scripts\python.exe -c "import sqlite3,sys; s=sqlite3.connect('C:/AISYS/data/library.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" $dest
$ok = C:\AISYS\venv\Scripts\python.exe -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" $dest
if ($ok -ne "ok") { Remove-Item $dest; throw "Backup failed integrity check" }
(Get-FileHash $dest -Algorithm SHA256).Hash | Set-Content "$dest.sha256"
Copy-Item C:\AISYS\data\migrations "C:\AISYS\backups\migrations-$ts" -Recurse
# Retention: 14 daily snapshots, then keep the newest per week for 8 weeks
Get-ChildItem C:\AISYS\backups\library-*.db | Where-Object LastWriteTime -lt (Get-Date).AddDays(-14) |
  Group-Object { $_.LastWriteTime.ToString("yyyy-ww") } | ForEach-Object { $_.Group | Sort-Object LastWriteTime | Select-Object -SkipLast 1 | Remove-Item }
Get-ChildItem C:\AISYS\backups\library-*.db | Where-Object LastWriteTime -lt (Get-Date).AddDays(-56) | Remove-Item
```

Schedule daily with `schtasks /Create /TN "AISYS-Backup" /SC DAILY /ST 02:00 /RU SYSTEM /TR "powershell -File C:\AISYS\bin\backup.ps1" /F`. At least weekly, copy `C:\AISYS\backups` to **separate removable media kept in a different location**; a backup on the same disk does not survive disk loss.

### 4.3 Restore procedure

```powershell
schtasks /End /TN "AISYS-LMS"; C:\AISYS\bin\stop_aisys.ps1
$snap = "C:\AISYS\backups\library-20261005-020000.db"            # choose the snapshot
if ((Get-FileHash $snap -Algorithm SHA256).Hash -ne (Get-Content "$snap.sha256")) { throw "Snapshot corrupt" }
Move-Item C:\AISYS\data\library.db C:\AISYS\data\library.db.damaged-$(Get-Date -Format yyyyMMddHHmm)
Copy-Item $snap C:\AISYS\data\library.db
C:\AISYS\venv\Scripts\python -c "import sqlite3;print(sqlite3.connect('C:/AISYS/data/library.db').execute('PRAGMA integrity_check').fetchone()[0])"   # must print ok
schtasks /Run /TN "AISYS-LMS"; C:\AISYS\bin\check_health.ps1
```
Keep the `.damaged-*` file until the incident is closed. **Test a restore into a scratch folder quarterly**: an untested backup is not evidence of recoverability.

### 4.4 Disaster recovery scenarios

| Scenario | Recovery |
|---|---|
| **Service will not start** | Read the tail of `uvicorn.log`. Common causes: port 8000 already in use, broken junction `C:\AISYS\app`, missing package. Fix, or roll back the release (R2). |
| **Database corrupt** (`integrity_check` ≠ `ok`) | Restore the latest verified snapshot (§4.3); re-run any migration batches performed since, using the retained input files. |
| **Host lost** (hardware, ransomware, disk failure) | Build a new Windows host; install from the media kit (§3.3); copy the latest backups and `releases\` from off-site media; restore the database (§4.3); run the acceptance suite and `check_health.ps1`; re-point the proxy. Target ≤ 4 hours. |
| **Bad release** | Roll back with R2. |
| **Failed or wrong migration** | Failed: reverted automatically. Wrong but committed: restore the pre-migration snapshot, correct the source file, re-run. |
| **Suspected unauthorised access** | Stop exposing the service (disable the proxy rule), preserve `uvicorn.log` and proxy logs, review `/api/v1/gate/alarms` and member block states for tampering, restore from a snapshot older than the first suspicious event, rebuild the proxy trust rules (§1.1), then re-enable. |

### 4.5 Incident troubleshooting reference

| Symptom | Likely cause | Check / fix |
|---|---|---|
| `/health` unreachable | Task not running; port conflict; crash at start | `schtasks /Query /TN "AISYS-LMS"`; `Get-NetTCPConnection -LocalPort 8000`; tail the log |
| Data back to demo values after reboot | Expected: in-memory state (§0) | Not a fault in 1.0.0; escalate persistence work |
| `403 FORBIDDEN` for staff | Proxy not setting `X-Role`, or wrong group mapping | Test with an explicit header (§1.1); inspect proxy rules |
| `403 MEMBER_BLOCKED` at checkout | Member blocked | Review reason; admin unblocks after resolution |
| `403 FINE_LIMIT_EXCEEDED` | Fines ≥ 500.00 | Record payment, retry |
| `409 TAG_ALREADY_MAPPED` | Tag UID bound to another copy, or duplicate tag on two items | Identify the holder; correct the wrong mapping |
| `409 NOT_ON_LOAN` at checkin | Item not issued | Verify checkout history; item may have been returned already |
| `404 ITEM_NOT_FOUND` on scan | Accession missing or mistyped; tag never associated | Associate the tag (§2.2 B) or re-key |
| Gate alarms on items that were properly issued | Item was checked in again or never checked out; tag swapped | Query `LookupItem`; confirm security marker `01` after checkout |
| Alarm for an unknown tag at the gate | Item not catalogued (treated as armed by design) | Catalogue and tag it, or confiscate per policy |
| SIP2 reply `96` | Message malformed or unsupported type | Check fixed-field widths and the message ID (`09`, `11`, `17`) |
| SIP2 reply `120…` / `100…` | Business rule refusal | Read the `AF` text, then treat as the REST codes in §2.1 |
| `422 Unprocessable Entity` | Request body missing a field or wrong type | Compare against the field lists in §2 |
| Migration exit `2` | Missing required column, unreadable or unsupported file type | Required columns: members `member_code, full_name`; books `isbn, title, accession_no, tag_uid` |
| Migration exit `1` | Rows rejected under `--rollback`, or an error during load | Open the error log; reason codes: `INVALID_EMAIL`, `INVALID_PHONE`, `INVALID_MEMBER_TYPE`, `INVALID_ISBN`, `INVALID_TAG_UID`, `INVALID_PUB_YEAR`, `MISSING_<FIELD>`, `CORRUPTED_VALUE:<field>`, `DUPLICATE_IN_FILE`, `DUPLICATE_IN_STAGING`, `DUPLICATE_IN_DATABASE`, `DUPLICATE_TAG_IN_FILE`, `TAG_ALREADY_MAPPED` |
| `.xlsx` import fails with a missing-module error | `openpyxl` not installed | Reinstall from the wheelhouse (`pip install --no-index --find-links … openpyxl`) |
| `pip install` tries the network | `--no-index` omitted | Always use `--no-index --find-links C:\AISYS\wheelhouse` |
| Disk full | Logs or backups unrotated | Run rotation (§1.3) and retention (§4.2) |

**Escalation record.** For every incident capture: time detected, symptom, log excerpts, actions taken, restore point used (if any), and root cause. Keep it with the change log for audit.

---

## 5. Document control

| Version | Date | Description |
|---|---|---|
| 1.0 | 2026-10-05 | Initial release covering release 1.0.0 of the AISYS RFID Library Management System |
