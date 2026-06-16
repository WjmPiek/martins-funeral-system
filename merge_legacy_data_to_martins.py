import os
import psycopg2
from psycopg2.extras import RealDictCursor

TARGET_URL = os.environ["DATABASE_URL"]

OLD_CLAIMS_URL = os.environ.get("OLD_CLAIMS_DATABASE_URL")
OLD_HEATMAP_URL = os.environ.get("OLD_HEATMAP_DATABASE_URL")
OLD_ATTENDANCE_URL = os.environ.get("OLD_ATTENDANCE_DATABASE_URL")


def conn(url):
    return psycopg2.connect(url)


def copy_claims(target):
    if not OLD_CLAIMS_URL:
        print("Skipping claims: OLD_CLAIMS_DATABASE_URL missing")
        return

    source = conn(OLD_CLAIMS_URL)
    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM app_claim_cases ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            t.execute("""
                INSERT INTO insurance_claim_cases (
                    id, claim_ref, franchise_name, claimant_name, policy_number,
                    claim_date, claim_amount, status, priority, assigned_to_email,
                    created_by_email, created_at, updated_at, closed_at, description,
                    created_by_id, due_date, archived, deceased_name, deceased_id_number,
                    member_verification_status, member_verification_details, verified_policy_row_id
                )
                VALUES (
                    %(id)s, %(claim_ref)s, %(franchise_name)s, %(claimant_name)s, %(policy_number)s,
                    %(claim_date)s, %(claim_amount)s, %(status)s, %(priority)s, %(assigned_to_email)s,
                    %(created_by_email)s, %(created_at)s, %(updated_at)s, %(closed_at)s, %(description)s,
                    %(created_by_id)s, %(due_date)s, %(archived)s, %(deceased_name)s, %(deceased_id_number)s,
                    %(member_verification_status)s, %(member_verification_details)s, %(verified_policy_row_id)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    claim_ref = EXCLUDED.claim_ref,
                    franchise_name = EXCLUDED.franchise_name,
                    claimant_name = EXCLUDED.claimant_name,
                    policy_number = EXCLUDED.policy_number,
                    claim_date = EXCLUDED.claim_date,
                    claim_amount = EXCLUDED.claim_amount,
                    status = EXCLUDED.status,
                    priority = EXCLUDED.priority,
                    assigned_to_email = EXCLUDED.assigned_to_email,
                    created_by_email = EXCLUDED.created_by_email,
                    updated_at = EXCLUDED.updated_at,
                    closed_at = EXCLUDED.closed_at,
                    description = EXCLUDED.description,
                    due_date = EXCLUDED.due_date,
                    archived = EXCLUDED.archived,
                    deceased_name = EXCLUDED.deceased_name,
                    deceased_id_number = EXCLUDED.deceased_id_number,
                    member_verification_status = EXCLUDED.member_verification_status,
                    member_verification_details = EXCLUDED.member_verification_details,
                    verified_policy_row_id = EXCLUDED.verified_policy_row_id
            """, r)

    source.close()
    target.commit()
    print(f"Claims copied: {len(rows)}")


def copy_heatmap(target):
    if not OLD_HEATMAP_URL:
        print("Skipping heatmap: OLD_HEATMAP_DATABASE_URL missing")
        return

    source = conn(OLD_HEATMAP_URL)
    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM record ORDER BY id")
        rows = s.fetchall()

        for r in rows:
            t.execute("""
                INSERT INTO heatmap_records (
                    id, franchise_id, mf_file, deceased_name, deceased_surname, dod,
                    address, city, province, country, full_address, latitude, longitude,
                    weight, next_of_kin_name, next_of_kin_surname, relationship, relation,
                    contact_number, source_filename, created_by_id, created_at, updated_at
                )
                VALUES (
                    %(id)s, NULL, %(mf_file)s, %(deceased_name)s, %(deceased_surname)s, %(dod)s,
                    %(address)s, %(city)s, %(province)s, %(country)s, %(full_address)s, %(latitude)s, %(longitude)s,
                    %(weight)s, %(next_of_kin_name)s, %(next_of_kin_surname)s, %(relationship)s, %(relationship)s,
                    %(contact_number)s, 'legacy_heatmap_import', NULL, %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    mf_file = EXCLUDED.mf_file,
                    deceased_name = EXCLUDED.deceased_name,
                    deceased_surname = EXCLUDED.deceased_surname,
                    dod = EXCLUDED.dod,
                    address = EXCLUDED.address,
                    city = EXCLUDED.city,
                    province = EXCLUDED.province,
                    country = EXCLUDED.country,
                    full_address = EXCLUDED.full_address,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    weight = EXCLUDED.weight,
                    next_of_kin_name = EXCLUDED.next_of_kin_name,
                    next_of_kin_surname = EXCLUDED.next_of_kin_surname,
                    relationship = EXCLUDED.relationship,
                    relation = EXCLUDED.relation,
                    contact_number = EXCLUDED.contact_number,
                    updated_at = EXCLUDED.updated_at
            """, r)

    source.close()
    target.commit()
    print(f"Heatmap copied: {len(rows)}")


def copy_attendance(target):
    if not OLD_ATTENDANCE_URL:
        print("Skipping attendance: OLD_ATTENDANCE_DATABASE_URL missing")
        return

    source = conn(OLD_ATTENDANCE_URL)

    user_to_staff = {}

    with source.cursor(cursor_factory=RealDictCursor) as s, target.cursor() as t:
        s.execute("SELECT * FROM employee_users ORDER BY id")
        staff_rows = s.fetchall()

        for r in staff_rows:
            user_to_staff[r["user_id"]] = r["id"]

            t.execute("""
                INSERT INTO attendance_staff (
                    id, franchise_id, first_name, surname, email, phone, id_number,
                    employee_number, position, staff_type, website_url, is_active,
                    notes, created_by_id, created_at, updated_at
                )
                VALUES (
                    %(id)s, %(franchise_user_id)s, %(name)s, %(surname)s, %(email)s, %(contact_number)s, %(id_number)s,
                    %(employee_number)s, %(employee_role)s, 'employee', NULL, %(is_active)s,
                    'Imported from legacy attendance_register employee_users', NULL, %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    franchise_id = EXCLUDED.franchise_id,
                    first_name = EXCLUDED.first_name,
                    surname = EXCLUDED.surname,
                    email = EXCLUDED.email,
                    phone = EXCLUDED.phone,
                    id_number = EXCLUDED.id_number,
                    employee_number = EXCLUDED.employee_number,
                    position = EXCLUDED.position,
                    is_active = EXCLUDED.is_active,
                    updated_at = EXCLUDED.updated_at
            """, r)

        s.execute("SELECT * FROM attendance_events ORDER BY id")
        event_rows = s.fetchall()

        copied_events = 0

        for r in event_rows:
            staff_id = user_to_staff.get(r["user_id"])
            if not staff_id:
                continue

            t.execute("""
                INSERT INTO attendance_events (
                    id, staff_id, franchise_id, office_id, action, event_time,
                    latitude, longitude, accuracy_meters, distance_from_site_m,
                    gps_status, work_location_type, source, device_info,
                    employee_note, manager_note, approval_status, approved_by_id,
                    approved_at, rejected_reason, created_at, updated_at
                )
                VALUES (
                    %(id)s, %s, NULL, NULL, %(action)s, COALESCE(%(created_at)s, NOW()),
                    NULLIF(%(latitude)s, '')::double precision,
                    NULLIF(%(longitude)s, '')::double precision,
                    NULLIF(%(accuracy_meters)s, '')::double precision,
                    %(distance_from_site_m)s,
                    %(gps_status)s, %(work_location_type)s, %(source)s, %(device_info)s,
                    %(employee_note)s, %(manager_note)s, %(approval_status)s, %(approved_by_user_id)s,
                    %(approved_at)s, %(rejected_reason)s, %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    staff_id = EXCLUDED.staff_id,
                    action = EXCLUDED.action,
                    event_time = EXCLUDED.event_time,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    accuracy_meters = EXCLUDED.accuracy_meters,
                    distance_from_site_m = EXCLUDED.distance_from_site_m,
                    gps_status = EXCLUDED.gps_status,
                    work_location_type = EXCLUDED.work_location_type,
                    source = EXCLUDED.source,
                    device_info = EXCLUDED.device_info,
                    employee_note = EXCLUDED.employee_note,
                    manager_note = EXCLUDED.manager_note,
                    approval_status = EXCLUDED.approval_status,
                    approved_by_id = EXCLUDED.approved_by_id,
                    approved_at = EXCLUDED.approved_at,
                    rejected_reason = EXCLUDED.rejected_reason,
                    updated_at = EXCLUDED.updated_at
            """, (staff_id, *r.values()))

            copied_events += 1

    source.close()
    target.commit()
    print(f"Attendance staff copied: {len(staff_rows)}")
    print(f"Attendance events copied: {copied_events}")


def reset_sequences(target):
    with target.cursor() as cur:
        for table in [
            "insurance_claim_cases",
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
    target = conn(TARGET_URL)

    copy_claims(target)
    copy_heatmap(target)
    copy_attendance(target)
    reset_sequences(target)

    target.close()
    print("DONE")


if __name__ == "__main__":
    main()