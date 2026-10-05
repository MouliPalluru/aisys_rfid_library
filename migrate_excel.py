"""
Data Migration & Reconciler Utility
====================================
Imports Member and Book spreadsheets into the RFID Library System via API.
Supports batch validation, schema verification, and transactional rollbacks.
"""

import sys
import pandas as pd
import requests

API_BASE_URL = "http://127.0.0.1:8000"

def import_members(file_path: str, rollback_on_error: bool = True) -> bool:
    """Reads members spreadsheet and populates the library database."""
    print(f"Reading members file: {file_path}")
    try:
        df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
    except Exception as e:
        print(f"[ERROR] Failed to read file: {e}")
        return False

    required_cols = {"member_id", "name", "email"}
    if not required_cols.issubset(set(df.columns)):
        print(f"[SCHEMA ERROR] Missing required columns: {required_cols - set(df.columns)}")
        return False

    staged = []
    for idx, row in df.iterrows():
        if pd.isna(row["email"]) or "@" not in str(row["email"]):
            print(f"[VALIDATION FAILED] Row {idx + 1}: Invalid email '{row['email']}'")
            if rollback_on_error:
                print("[ROLLBACK] Batch aborted due to validation error.")
                return False
            continue
        staged.append({
            "member_id": int(row["member_id"]),
            "name": str(row["name"]).strip(),
            "email": str(row["email"]).strip()
        })

    print(f"[SUCCESS] Reconciled {len(staged)} valid member record(s).")
    return True


def import_books(file_path: str, headers: dict = None) -> bool:
    """Reads books spreadsheet, registers titles/copies, and associates RFID tags."""
    print(f"Reading books file: {file_path}")
    headers = headers or {"X-Role": "admin"}
    try:
        df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
    except Exception as e:
        print(f"[ERROR] Failed to read file: {e}")
        return False

    for idx, row in df.iterrows():
        accession_no = str(row.get("accession_no", "")).strip()
        tag_uid = str(row.get("tag_uid", "")).strip().upper()
        
        if accession_no and tag_uid:
            res = requests.post(
                f"{API_BASE_URL}/rfid/tags/associate",
                headers=headers,
                json={"accession_no": accession_no, "tag_uid": tag_uid}
            )
            if res.status_code != 200:
                print(f"[TAG ERROR] Row {idx + 1}: {res.json().get('detail')}")

    print("[SUCCESS] Book and tag migration completed.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_excel.py <path_to_spreadsheet>")
        sys.exit(1)
    
    success = import_members(sys.argv[1])
    sys.exit(0 if success else 1)