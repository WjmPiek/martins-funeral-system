cat > merge_legacy_data_to_martins.py <<'PY'
import os
import psycopg2
from psycopg2.extras import RealDictCursor

TARGET_URL = os.environ["DATABASE_URL"]
OLD_CLAIMS_URL = os.environ["OLD_CLAIMS_DATABASE_URL"]
OLD_HEATMAP_URL = os.environ["OLD_HEATMAP_DATABASE_URL"]
OLD_ATTENDANCE_URL = os.environ["OLD_ATTENDANCE_DATABASE_URL"]


def connect(url):
    return psycopg2.connect(url)


def upsert(cur, table, row):
    row = {k: v for k, v in row.items() if v is not None}
    cols = list(row.keys())
    placeholders = [f"%({c})s" for c in cols]
    updates = [f"{c}=EXCLUDED.{c}" for c in cols if c != "id"]

    sql = f"""
        INSERT INTO {table} ({", ".join(cols)})
        VALUES ({", ".join(placeholders)})
        ON CONFLICT (id) DO UPDATE SET {", ".join(updates)}
    """
    cur.execute(sql, row)


def copy_claims(target):
    source = connect(OLD_CLAIMS_URL)

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM app_claim_cases ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            row = {
                "id": r.get("id"),
                "claim_ref": r.get("claim_ref"),
                "franchise_name": r.get("franchise_name"),
                "claimant_name": r.get("claimant_name"),
                "policy_number": r.get("policy_number"),
                "id_number": r.get("deceased_id_number"),
                "claim_type": "Legacy Import",
                "claim_date": r.get("claim_date"),
                "date_of_death": None,
                "claim_amount": r.get("claim_amount"),
                "status": r.get("status"),
                "priority": r.get("priority"),
                "assigned_to_id": None,
                "created_by_id": None,
                "archived": r.get("archived"),
                "notes": r.get("description"),
                "closed_at": r.get("closed_at"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            upsert(t, "insurance_claim_cases", row)

    target.commit()
    source.close()
    print(f"Claims copied: {len(rows)}")


def copy_claim_notes(target):
    source = connect(OLD_CLAIMS_URL)

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM app_claim_notes ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            row = {
                "id": r.get("id"),
                "claim_id": r.get("claim_id"),
                "user_id": r.get("user_id"),
                "user_email": r.get("user_email"),
                "note": r.get("note") or r.get("body") or r.get("text"),
                "created_at": r.get("created_at"),
            }
            upsert(t, "insurance_claim_notes", row)

    target.commit()
    source.close()
    print(f"Claim notes copied: {len(rows)}")


def copy_claim_attachments(target):
    source = connect(OLD_CLAIMS_URL)

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM app_claim_attachments ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            row = {
                "id": r.get("id"),
                "claim_id": r.get("claim_id"),
                "filename": r.get("filename") or r.get("original_filename"),
                "stored_filename": r.get("stored_filename") or r.get("filename"),
                "file_path": r.get("file_path") or r.get("path"),
                "content_type": r.get("content_type") or r.get("mime_type"),
                "size_bytes": r.get("size_bytes"),
                "uploaded_by_id": r.get("uploaded_by_id") or r.get("user_id"),
                "created_at": r.get("created_at"),
            }
            upsert(t, "insurance_claim_attachments", row)

    target.commit()
    source.close()
    print(f"Claim attachments copied: {len(rows)}")


def copy_heatmap(target):
    source = connect(OLD_HEATMAP_URL)

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM record ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            row = {
                "id": r.get("id"),
                "franchise_id": None,
                "mf_file": r.get("mf_file"),
                "deceased_name": r.get("deceased_name"),
                "deceased_surname": r.get("deceased_surname"),
                "dod": r.get("dod"),
                "address": r.get("address"),
                "city": r.get("city"),
                "province": r.get("province"),
                "country": r.get("country"),
                "full_address": r.get("full_address"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "weight": r.get("weight"),
                "next_of_kin_name": r.get("next_of_kin_name"),
                "next_of_kin_surname": r.get("next_of_kin_surname"),
                "relationship": r.get("relationship"),
                "relation": r.get("relationship"),
                "contact_number": r.get("contact_number"),
                "source_filename": "legacy_heatmap_import",
                "created_by_id": None,
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            upsert(t, "heatmap_records", row)

    target.commit()
    source.close()
    print(f"Heatmap copied: {len(rows)}")


def copy_attendance(target):
    source = connect(OLD_ATTENDANCE_URL)
    user_to_staff = {}

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM employee_users ORDER BY id")
        staff_rows = s.fetchall()

        for r in staff_rows:
            user_to_staff[r.get("user_id")] = r.get("id")

            row = {
                "id": r.get("id"),
                "franchise_id": r.get("franchise_user_id"),
                "first_name": r.get("name"),
                "surname": r.get("surname"),
                "email": r.get("email"),
                "phone": r.get("contact_number"),
                "id_number": r.get("id_number"),
                "employee_number": r.get("employee_number"),
                "position": r.get("employee_role"),
                "staff_type": "employee",
                "website_url": None,
                "is_active": r.get("is_active"),
                "notes": "Imported from legacy attendance system",
                "created_by_id": None,
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            upsert(t, "attendance_staff", row)

        s.execute("SELECT * FROM attendance_events ORDER BY id")
        event_rows = s.fetchall()
        copied = 0

        for r in event_rows:
            staff_id = user_to_staff.get(r.get("user_id"))
            if not staff_id:
                continue

            def to_float(value):
                if value in (None, ""):
                    return None
                return float(value)

            row = {
                "id": r.get("id"),
                "staff_id": staff_id,
                "franchise_id": None,
                "office_id": None,
                "action": r.get("action"),
                "event_time": r.get("created_at"),
                "latitude": to_float(r.get("latitude")),
                "longitude": to_float(r.get("longitude")),
                "accuracy_meters": to_float(r.get("accuracy_meters")),
                "distance_from_site_m": r.get("distance_from_site_m"),
                "gps_status": r.get("gps_status"),
                "work_location_type": r.get("work_location_type"),
                "source": r.get("source"),
                "device_info": r.get("device_info"),
                "employee_note": r.get("employee_note"),
                "manager_note": r.get("manager_note"),
                "approval_status": r.get("approval_status"),
                "approved_by_id": r.get("approved_by_user_id"),
                "approved_at": r.get("approved_at"),
                "rejected_reason": r.get("rejected_reason"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            upsert(t, "attendance_events", row)
            copied += 1

    target.commit()
    source.close()
    print(f"Attendance staff copied: {len(staff_rows)}")
    print(f"Attendance events copied: {copied}")


def reset_sequences(target):
    with target.cursor() as cur:
        for table in [
            "insurance_claim_cases",
            "insurance_claim_notes",
            "insurance_claim_attachments",
            "heatmap_records",
            "attendance_staff",
            "attendance_events",
        ]:
            cur.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    true
                )
            """)
    target.commit()
    print("Sequences reset")


def main():
    target = connect(TARGET_URL)

    copy_claims(target)
    copy_claim_notes(target)
    copy_claim_attachments(target)
    copy_heatmap(target)
    copy_attendance(target)
    reset_sequences(target)

    target.close()
    print("DONE")


if __name__ == "__main__":
    main()
PY