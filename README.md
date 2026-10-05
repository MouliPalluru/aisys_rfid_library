# AISYS RFID-Enabled Library Management System

An enterprise-grade, RFID-integrated Library Management System built with Python and FastAPI. The system features a 7-layer architecture, real-time security gate middleware, protocol interoperability (NCIP 2.0 / SIP2), automated inventory auditing, and data migration utilities.

---

## 📑 System Architecture

The project follows a **Modular 7-Layer Architecture**:
1. **Presentation / API Layer (`FastAPI`):** RESTful endpoints with Role-Based Access Control (RBAC) via `X-Role` headers.
2. **Protocol Interoperability Layer:** Mock adapters for **NCIP 2.0** and **SIP2** protocols.
3. **Circulation Logic Layer:** Rules engine enforcing loan caps (max 5 items), fine thresholds (₹500 limit), and reference item restrictions.
4. **RFID Middleware & Gate Security:** Physical exit gate monitoring, alarm logging, and CCTV snapshot generation upon unauthorized item removal.
5. **Inventory Audit Layer:** Batch reconciliation of handheld RFID shelf scans (identifying missing, misplaced, or unissued items).
6. **Notification Services:** Asynchronous background email dispatching for security breach alerts.
7. **Persistence Repository:** In-memory transactional data store configured for relational DB migration.

---

## 🛠️ Project Deliverables

* **`main.py`**: Core FastAPI application, business rules, and RFID gate services.
* **`test_acceptance.py`**: Complete automated acceptance test suite (49/49 passed).
* **`migrate_excel.py`**: Data ingestion & reconciliation script for Excel/CSV spreadsheet imports.
* **`ARCHITECTURE.md`**: Detailed technical specification and system architecture document.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.9 or higher
* `pip` package manager

### 1. Installation
Clone the repository and install required dependencies:
```bash
git clone https://github.com/MouliPalluru/aisys_rfid_library.git
cd aisys_rfid_library
pip install -r requirements.txt
```

### 2. Running the API Server
Start the FastAPI server locally using Uvicorn:
```bash
uvicorn main:app --reload
```
Once running, access the interactive API documentation (Swagger UI) at `http://127.0.0.1:8000/docs`.

### 3. Running Acceptance Tests
Execute the full test suite via `pytest`:
```bash
pytest -v test_acceptance.py
```

### 4. Running Data Migration
Import member profiles or book records from spreadsheets:
```bash
python migrate_excel.py sample_data.csv
```

---

## 🔒 Security & Verification
* **Acceptance Suite Pass Rate:** 100% (49/49 tests passed)
* **RBAC Controls:** Endpoints protected with standard role checks (`admin`, `staff`).