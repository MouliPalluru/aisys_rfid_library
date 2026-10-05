# AISYS RFID Library Management System — License Inventory & SBOM

| Field | Value |
|---|---|
| Document | `LICENSE_INVENTORY.md` |
| Fulfils | SOP Deliverable D4; addresses NFR 04 (third-party licensing) |
| Version / date | 1.0 / 2026-10-05 |
| Scope | Every third-party package needed to run, migrate data for, and test the system |
| Evidence basis | Versions resolved with `pip` and read back via `importlib.metadata` on **Python 3.12.3 (Linux x86-64)**, the environment in which the **full acceptance suite passes (53/53)**. Licenses are taken from each package's own metadata (`License-Expression`, `License`, trove classifiers). This is an engineering inventory, **not a legal opinion**. |

---

## 1. Python baseline — read this first

The resolved versions below declare these minimum Python versions:

| Package | Pinned version | `Requires-Python` |
|---|---|---|
| pandas | 3.0.2 | ≥ 3.11 |
| SQLAlchemy | 2.1.3 | ≥ 3.11 |
| numpy | 2.4.4 | ≥ 3.11 |
| FastAPI / uvicorn / pytest | 0.142.2 / 0.54.0 / 9.1.1 | ≥ 3.10 |

**Consequence:** this pin set supports **Python 3.11 or newer** (tested on 3.12.3). It does **not** install on Python 3.9. The application source (`main.py`, `migrate.py`) uses no syntax newer than 3.9, but a Python 3.9 deployment would need older, separately pinned releases and a full re-run of the acceptance suite, after which this inventory must be regenerated. No 3.9 pin set has been tested, so none is claimed here.

Recommended supported baseline for deployment: **Python 3.12.x, 64-bit (win_amd64)**.

---

## 2. Direct dependencies

| Package | Pinned | License (SPDX) | Role | Used by |
|---|---|---|---|---|
| fastapi | 0.142.2 | MIT | Runtime | `main.py` — REST API, routing, dependency injection |
| uvicorn | 0.54.0 | BSD-3-Clause | Runtime | ASGI server (`uvicorn main:app`) |
| pandas | 3.0.2 | BSD-3-Clause | Migration | `migrate.py` — CSV/XLSX loading and error-log output |
| openpyxl | 3.1.5 | MIT | Migration | `pandas.read_excel` for `.xlsx` input |
| SQLAlchemy | 2.1.3 | MIT | Migration | `migrate.py` — SQLite schema, transactions, inserts |
| pytest | 9.1.1 | MIT | Test only | `test_acceptance.py` |
| httpx | 0.28.1 | BSD-3-Clause | Test only | Backend of FastAPI/Starlette `TestClient` |

`SQLAlchemy` and `httpx` are not on the original short list but are imported (directly or via `TestClient`) by the delivered code, so they are part of the Bill of Materials.

## 3. Transitive dependencies

| Package | Pinned | License (SPDX) | Pulled in by | Role |
|---|---|---|---|---|
| starlette | 1.7.0 | BSD-3-Clause | fastapi | Runtime |
| pydantic | 2.13.5 | MIT | fastapi | Runtime |
| pydantic-core | 2.46.5 | MIT | pydantic | Runtime (compiled) |
| annotated-types | 0.8.0 | MIT | pydantic | Runtime |
| annotated-doc | 0.0.5 | MIT | fastapi | Runtime |
| typing-extensions | 4.16.0 | PSF-2.0 | fastapi, pydantic, SQLAlchemy, others | Runtime |
| typing-inspection | 0.4.4 | MIT | fastapi, pydantic | Runtime |
| opentelemetry-api | 1.45.0 | Apache-2.0 | fastapi | Runtime (API only, see §7) |
| anyio | 4.15.1 | MIT | starlette, httpx | Runtime |
| idna | 3.11 | BSD-3-Clause | anyio, httpx | Runtime |
| click | 8.3.1 | BSD-3-Clause | uvicorn | Runtime |
| h11 | 0.16.0 | MIT | uvicorn, httpcore | Runtime |
| numpy | 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | pandas | Migration (compiled) |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause / Apache-2.0 (dual) | pandas | Migration |
| six | 1.17.0 | MIT | python-dateutil | Migration |
| et-xmlfile | 2.0.0 | MIT | openpyxl | Migration |
| pluggy | 1.6.0 | MIT | pytest | Test only |
| iniconfig | 2.3.0 | MIT | pytest | Test only |
| packaging | 26.0 | Apache-2.0 OR BSD-2-Clause | pytest | Test only |
| pygments | 2.20.0 | BSD-2-Clause | pytest | Test only |
| httpcore | 1.0.9 | BSD-3-Clause | httpx | Test only |
| certifi | 2026.2.25 | **MPL-2.0** | httpx / httpcore | Test only |
| colorama | 0.4.6 | BSD-3-Clause | pytest, click — **Windows only** | Runtime + test (Windows) |
| tzdata | 2026.5 | Apache-2.0 | pandas — **Windows only** | Migration (Windows) |

Platform markers confirmed from package metadata: `colorama` is required on `sys_platform == "win32"` (pytest) and `platform_system == "Windows"` (click); `tzdata` is required by pandas on `sys_platform == "win32"`. Both **must** be in the offline wheelhouse for Windows targets even though they do not appear in a Linux resolution.

## 4. Platform components (not installed from PyPI)

| Component | License | Notes |
|---|---|---|
| CPython 3.12.x | PSF-2.0 | Installed from the offline `python-3.12.x-amd64.exe`; verify its SHA-256 against python.org's published value before transfer |
| SQLite (bundled in CPython's `sqlite3`) | Public domain | Provides the `library.db` engine; tested with SQLite 3.45.1 |

---

## 5. Pinned requirement files

`requirements.txt` — production (API + migration):

```text
fastapi==0.142.2
starlette==1.7.0
pydantic==2.13.5
pydantic-core==2.46.5
annotated-types==0.8.0
annotated-doc==0.0.5
typing-extensions==4.16.0
typing-inspection==0.4.4
opentelemetry-api==1.45.0
anyio==4.15.1
idna==3.11
click==8.3.1
h11==0.16.0
uvicorn==0.54.0
pandas==3.0.2
numpy==2.4.4
python-dateutil==2.9.0.post0
six==1.17.0
openpyxl==3.1.5
et-xmlfile==2.0.0
SQLAlchemy==2.1.3
colorama==0.4.6; sys_platform == "win32"
tzdata==2026.5; sys_platform == "win32"
```

`requirements-dev.txt` — adds the test tooling (install only on build/QA hosts):

```text
-r requirements.txt
pytest==9.1.1
pluggy==1.6.0
iniconfig==2.3.0
packaging==26.0
pygments==2.20.0
httpx==0.28.1
httpcore==1.0.9
certifi==2026.2.25
```

Keeping `certifi` (MPL-2.0) and the other test-only packages out of `requirements.txt` means the production virtual environment contains **no MPL-licensed code**.

### Regenerating this inventory

```powershell
python -m pip freeze > freeze.txt          # exact resolved set
python -m pip show fastapi uvicorn pandas openpyxl SQLAlchemy pytest httpx   # version, license, Requires
python -m pip check                        # confirms no broken requirements
```

Re-verify the license column from each package's `*.dist-info/METADATA` whenever a pin changes.

---

## 6. License obligations and redistribution notes

| License | Packages | What you must do when redistributing (source or wheels) |
|---|---|---|
| MIT | fastapi, pydantic, pydantic-core, annotated-types, annotated-doc, typing-inspection, anyio, h11, SQLAlchemy, openpyxl, et-xmlfile, six, pluggy, iniconfig, pytest | Keep the copyright notice and permission notice with the software. Each wheel carries its `LICENSE` in `*.dist-info`; do not strip it. |
| BSD-3-Clause | uvicorn, starlette, pandas, httpx, httpcore, click, idna, colorama, numpy (primary) | Keep the copyright notice, conditions and disclaimer; do not use the project or contributor names to endorse derived products. |
| BSD-2-Clause | pygments, packaging (alternative) | Keep the copyright notice and disclaimer. |
| Apache-2.0 | opentelemetry-api, tzdata, python-dateutil (alternative), packaging (alternative) | Include the license text; preserve any `NOTICE` file; mark modified files if you modify them. Includes an express patent grant. |
| PSF-2.0 | typing-extensions, CPython | Keep the PSF license text and copyright notice; the name "Python" may not be used to endorse derived products. |
| MPL-2.0 | certifi (test only) | File-level copyleft: if you modify certifi's MPL-covered files and distribute them, those files must remain under MPL-2.0 with source available. Unmodified redistribution only requires the license text. Not present in the production environment. |
| 0BSD, Zlib, CC0-1.0 | portions bundled in numpy wheels | Permissive; numpy's `dist-info/licenses` folder holds the full set — ship it intact. |

**Practical redistribution rules**

1. **Ship the licenses with the wheels.** An offline wheelhouse is a redistribution of third-party binaries; keep every wheel unmodified so its `dist-info` license files travel with it.
2. **Do not modify third-party code.** No patches are applied to any package in this inventory, so no copyleft source-disclosure duty is triggered.
3. **No copyleft (GPL/LGPL/AGPL) packages** appear in the resolved tree. The only weak-copyleft item is MPL-2.0 `certifi`, and it is test-only.
4. **First-party code** (`main.py`, `migrate.py`, `test_acceptance.py`) is the project's own; its licensing is decided by the institution and is independent of the permissive licenses above.
5. **Third-party notice file:** when delivering a package outside the institution, include this document plus the `dist-info` license files from the wheelhouse as the attribution notice.

---

## 7. Air-gapped / offline installation compatibility

| Item | Assessment |
|---|---|
| Runtime network access | The application code makes **no outbound network calls**. Email notification is a local mock queue; CCTV capture returns a mock reference string. |
| Telemetry | `opentelemetry-api` is the interface-only package. Without an SDK and exporter configured, it emits nothing. None is installed or configured. |
| Package fetching at runtime | None. All dependencies are installed ahead of time from the wheelhouse with `--no-index`. |
| Compiled wheels | `pydantic-core`, `numpy` and `pandas` are binary wheels. The wheelhouse must contain the **`win_amd64` build matching the target Python** (for example `cp312`). Pure-Python packages are `py3-none-any` and platform-independent. |
| Source-only packages | None required; always download with `--only-binary=:all:` so a missing wheel fails loudly instead of triggering a compile on the target. |
| Windows 11 / Server 2022 | Wheels exist for `win_amd64`; no compiler or Visual Studio installation is needed on the target. |
| Integrity | Record SHA-256 hashes of the Python installer and every wheel at staging; verify on the target before install. |

**Staging (internet-connected build machine — same OS, Python version and architecture as the target):**

```powershell
python -m venv C:\staging\venv
C:\staging\venv\Scripts\python -m pip download -r requirements.txt -r requirements-dev.txt `
    -d C:\staging\wheelhouse --only-binary=:all:
Get-ChildItem C:\staging\wheelhouse | Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash)  $(Split-Path $_.Path -Leaf)" } |
    Set-Content C:\staging\wheelhouse\SHA256SUMS.txt
```

**Install (air-gapped target):**

```powershell
C:\AISYS\venv\Scripts\python -m pip install --no-index --find-links C:\AISYS\wheelhouse -r C:\AISYS\app\requirements.txt
C:\AISYS\venv\Scripts\python -m pip check
```

---

## 8. Summary

| Metric | Count |
|---|---|
| Direct third-party packages | 7 |
| Transitive packages (incl. 2 Windows-only) | 24 |
| Distinct license families | MIT, BSD-2, BSD-3, Apache-2.0, PSF-2.0, MPL-2.0 (test-only), plus 0BSD/Zlib/CC0 bundled in numpy |
| Strong-copyleft packages (GPL/AGPL) | 0 |
| Weak-copyleft packages in production environment | 0 |
| Packages needing network access at runtime | 0 |
