import os
import sys
import psycopg2
from psycopg2 import sql

TARGET_DB = os.environ.get("DATABASE_URL")

SOURCE_DBS = {
    "heatmap": os.environ.get("OLD_HEATMAP_DATABASE_URL"),
    "attendance": os.environ.get("OLD_ATTENDANCE_DATABASE_URL"),
    "manuals": os.environ.get("OLD_MANUALS_DATABASE_URL"),
    "claims": os.environ.get("OLD_CLAIMS_DATABASE_URL"),
}

TABLES = [
    # Heatmap
    "heatmap_records",

    # Attendance
    "attendance_staff",
    "attendance_offices",
    "attendance_events",
    "attendance_leave_requests",

    # Manuals
    "mff_manuals",
    "mff_manual_versions",
    "mff_manual_acknowledgements",
    "mff_index_documents",

    # Insurance Claims
    "insurance_claim_cases",
    "insurance_claim_notes",
    "insurance_claim_attachments",
    "insurance_policydata_detail_raw",
    "insurance_policy_monthly_raw",
    "insurance_claims_monthly_raw",
    "insurance_import_history",
    "insurance_franchise_mapping",
    "insurance_claim_document_types",
    "insurance_claim_document_rules",
]


def connect(url):
    return psycopg2.connect(url)


def table_exists(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = %s
            )
            """,
            (table,),
        )
        return cur.fetchone()[0]


def get_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def get_primary_key(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
            """,
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def copy_table(source_conn, target_conn, table):
    if not table_exists(source_conn, table):
        print(f"SKIP source missing: {table}")
        return

    if not table_exists(target_conn, table):
        print(f"SKIP target missing: {table}")
        return

    source_cols = get_columns(source_conn, table)
    target_cols = get_columns(target_conn, table)
    common_cols = [c for c in source_cols if c in target_cols]

    if not common_cols:
        print(f"SKIP no matching columns: {table}")
        return

    pk_cols = get_primary_key(target_conn, table)

    with source_conn.cursor() as src, target_conn.cursor() as tgt:
        src.execute(
            sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(map(sql.Identifier, common_cols)),
                sql.Identifier(table),
            )
        )

        rows = src.fetchall()
        if not rows:
            print(f"OK empty source: {table}")
            return

        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in common_cols)

        if pk_cols:
            update_cols = [c for c in common_cols if c not in pk_cols]

            if update_cols:
                update_sql = sql.SQL(", ").join(
                    sql.SQL("{} = EXCLUDED.{}").format(
                        sql.Identifier(c), sql.Identifier(c)
                    )
                    for c in update_cols
                )

                insert_sql = sql.SQL("""
                    INSERT INTO {} ({})
                    VALUES ({})
                    ON CONFLICT ({})
                    DO UPDATE SET {}
                """).format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, common_cols)),
                    placeholders,
                    sql.SQL(", ").join(map(sql.Identifier, pk_cols)),
                    update_sql,
                )
            else:
                insert_sql = sql.SQL("""
                    INSERT INTO {} ({})
                    VALUES ({})
                    ON CONFLICT ({})
                    DO NOTHING
                """).format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, common_cols)),
                    placeholders,
                    sql.SQL(", ").join(map(sql.Identifier, pk_cols)),
                )
        else:
            insert_sql = sql.SQL("""
                INSERT INTO {} ({})
                VALUES ({})
            """).format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, common_cols)),
                placeholders,
            )

        tgt.executemany(insert_sql, rows)
        target_conn.commit()

        print(f"OK copied {len(rows)} rows into {table}")


def reset_sequences(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_default LIKE 'nextval%%'
            """
        )
        rows = cur.fetchall()

        for table, column in rows:
            cur.execute(
                sql.SQL("""
                    SELECT setval(
                        pg_get_serial_sequence(%s, %s),
                        COALESCE((SELECT MAX({}) FROM {}), 1),
                        true
                    )
                """).format(
                    sql.Identifier(column),
                    sql.Identifier(table),
                ),
                (table, column),
            )

    conn.commit()
    print("OK sequences reset")


def main():
    if not TARGET_DB:
        print("ERROR: DATABASE_URL is missing")
        sys.exit(1)

    target_conn = connect(TARGET_DB)

    try:
        for source_name, source_url in SOURCE_DBS.items():
            if not source_url:
                print(f"SKIP no env var for {source_name}")
                continue

            print(f"\n=== Importing from {source_name} ===")
            source_conn = connect(source_url)

            try:
                for table in TABLES:
                    copy_table(source_conn, target_conn, table)
            finally:
                source_conn.close()

        reset_sequences(target_conn)

    finally:
        target_conn.close()

    print("\nDONE")


if __name__ == "__main__":
    main()