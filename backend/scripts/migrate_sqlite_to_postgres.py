from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row


SQLITE_DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'enterprise_delivery.db'
TABLE_ORDER = ['customers', 'projects', 'requirements', 'issues', 'ai_analysis_logs']


@dataclass(frozen=True)
class TableStats:
    count: int
    min_id: int | None
    max_id: int | None


CUSTOMER_COLUMNS = ['id', 'name', 'industry', 'contact', 'status', 'owner', 'created_at', 'updated_at']
PROJECT_COLUMNS = ['id', 'customer_id', 'name', 'status', 'health', 'risk_level', 'delivery_stage', 'created_at', 'updated_at']
REQUIREMENT_COLUMNS = ['id', 'project_id', 'title', 'status', 'priority', 'owner', 'due_date', 'created_at', 'updated_at']
ISSUE_COLUMNS = ['id', 'project_id', 'title', 'description', 'issue_type', 'status', 'severity', 'owner', 'created_at', 'updated_at']
AI_ANALYSIS_COLUMNS = [
    'id',
    'issue_id',
    'analysis_type',
    'provider',
    'model_name',
    'prompt_version',
    'issue_summary',
    'possible_root_cause',
    'recommended_actions_json',
    'customer_update_draft',
    'risk_level',
    'project_impact',
    'feedback_status',
    'feedback_note',
    'edited_output',
    'created_at',
    'updated_at',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Migrate Delivery Copilot data from SQLite to PostgreSQL.')
    parser.add_argument('--sqlite-path', default=str(SQLITE_DEFAULT_PATH), help='Path to the SQLite database file.')
    parser.add_argument(
        '--postgres-url',
        default=os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('POSTGRESQL_URL'),
        help='PostgreSQL connection URL.',
    )
    parser.add_argument('--dry-run', action='store_true', help='Validate source, target, and mappings only.')
    parser.add_argument(
        '--replace-target',
        action='store_true',
        help='Allow clearing existing target rows inside one transaction before migration.',
    )
    return parser.parse_args()


def _mask_database_url(url: str | None) -> str:
    if not url:
        return '<missing>'
    parsed = urlparse(url)
    host = parsed.hostname or '<unknown-host>'
    port = f':{parsed.port}' if parsed.port else ''
    path = parsed.path or ''
    scheme = parsed.scheme or '<unknown-scheme>'
    return f'{scheme}://<redacted>@{host}{port}{path}'


def _sqlite_uri(sqlite_path: Path) -> str:
    resolved = sqlite_path.resolve()
    return urlunparse(('file', '', str(resolved).replace('\\', '/'), '', 'mode=ro', ''))


def _open_sqlite(sqlite_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f'file:{sqlite_path.resolve()}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fetchone_sqlite(conn: sqlite3.Connection, query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    cursor = conn.execute(query, params)
    return cursor.fetchone()


def _fetchall_sqlite(conn: sqlite3.Connection, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    cursor = conn.execute(query, params)
    return cursor.fetchall()


def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = _fetchone_sqlite(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    )
    return row is not None


def _get_sqlite_stats(conn: sqlite3.Connection, table: str) -> TableStats:
    row = _fetchone_sqlite(
        conn,
        f'SELECT COUNT(*) AS count, MIN(id) AS min_id, MAX(id) AS max_id FROM {table}',
    )
    if row is None:
        return TableStats(count=0, min_id=None, max_id=None)
    return TableStats(count=int(row['count']), min_id=row['min_id'], max_id=row['max_id'])


def _check_sqlite_foreign_keys(conn: sqlite3.Connection) -> None:
    checks = {
        'projects.customer_id': "SELECT COUNT(*) AS bad_count FROM projects p LEFT JOIN customers c ON p.customer_id = c.id WHERE p.customer_id IS NOT NULL AND c.id IS NULL",
        'requirements.project_id': "SELECT COUNT(*) AS bad_count FROM requirements r LEFT JOIN projects p ON r.project_id = p.id WHERE r.project_id IS NOT NULL AND p.id IS NULL",
        'issues.project_id': "SELECT COUNT(*) AS bad_count FROM issues i LEFT JOIN projects p ON i.project_id = p.id WHERE i.project_id IS NOT NULL AND p.id IS NULL",
        'ai_analysis_logs.issue_id': "SELECT COUNT(*) AS bad_count FROM ai_analysis_logs a LEFT JOIN issues i ON a.issue_id = i.id WHERE a.issue_id IS NOT NULL AND i.id IS NULL",
    }
    for label, query in checks.items():
        row = _fetchone_sqlite(conn, query)
        bad_count = int((row or {'bad_count': 0})['bad_count'])
        if bad_count:
            raise RuntimeError(f'SQLite foreign key validation failed for {label}: {bad_count} orphaned rows')


def _validate_sqlite_source(conn: sqlite3.Connection) -> dict[str, TableStats]:
    print(f'[sqlite] source database: {sqlite_path_display(conn)}')
    stats: dict[str, TableStats] = {}
    for table in TABLE_ORDER:
        if not _sqlite_table_exists(conn, table):
            raise RuntimeError(f'SQLite source table missing: {table}')
        stats[table] = _get_sqlite_stats(conn, table)
        print(f'[sqlite] {table}: count={stats[table].count}, min_id={stats[table].min_id}, max_id={stats[table].max_id}')
    _check_sqlite_foreign_keys(conn)
    print('[sqlite] foreign key validation passed')
    return stats


def sqlite_path_display(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute('PRAGMA database_list').fetchone()
        if row and len(row) >= 3:
            return str(row[2])
    except Exception:
        pass
    return '<sqlite>'


def _connect_postgres(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _pg_table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    return cur.fetchone() is not None


def _get_pg_stats(cur, table: str) -> TableStats:
    cur.execute(f'SELECT COUNT(*) AS count, MIN(id) AS min_id, MAX(id) AS max_id FROM {table}')
    row = cur.fetchone() or {'count': 0, 'min_id': None, 'max_id': None}
    return TableStats(count=int(row['count']), min_id=row['min_id'], max_id=row['max_id'])


def _check_foreign_keys(cur) -> None:
    checks = {
        'projects.customer_id': "SELECT COUNT(*) AS bad_count FROM projects p LEFT JOIN customers c ON p.customer_id = c.id WHERE p.customer_id IS NOT NULL AND c.id IS NULL",
        'requirements.project_id': "SELECT COUNT(*) AS bad_count FROM requirements r LEFT JOIN projects p ON r.project_id = p.id WHERE r.project_id IS NOT NULL AND p.id IS NULL",
        'issues.project_id': "SELECT COUNT(*) AS bad_count FROM issues i LEFT JOIN projects p ON i.project_id = p.id WHERE i.project_id IS NOT NULL AND p.id IS NULL",
        'ai_analysis_logs.issue_id': "SELECT COUNT(*) AS bad_count FROM ai_analysis_logs a LEFT JOIN issues i ON a.issue_id = i.id WHERE a.issue_id IS NOT NULL AND i.id IS NULL",
    }
    for label, query in checks.items():
        cur.execute(query)
        bad_count = int((cur.fetchone() or {'bad_count': 0})['bad_count'])
        if bad_count:
            raise RuntimeError(f'Foreign key validation failed for {label}: {bad_count} orphaned rows')


def _print_pg_stats(cur) -> dict[str, TableStats]:
    stats: dict[str, TableStats] = {}
    for table in TABLE_ORDER:
        stats[table] = _get_pg_stats(cur, table)
        print(f'[postgres] {table}: count={stats[table].count}, min_id={stats[table].min_id}, max_id={stats[table].max_id}')
    return stats


def _validate_target_tables_exist(cur) -> None:
    for table in TABLE_ORDER:
        if not _pg_table_exists(cur, table):
            raise RuntimeError(f'PostgreSQL target table missing: {table}')


def _reject_nonempty_target(cur) -> None:
    nonempty = []
    for table in TABLE_ORDER:
        stats = _get_pg_stats(cur, table)
        if stats.count > 0:
            nonempty.append(f'{table}={stats.count}')
    if nonempty:
        raise RuntimeError('PostgreSQL target is not empty. Use --replace-target to clear smoke test data. Found: ' + ', '.join(nonempty))


def _clear_target_tables(cur) -> None:
    for table in reversed(TABLE_ORDER):
        cur.execute(f'DELETE FROM {table}')


def _reset_sequence(cur, table: str) -> None:
    cur.execute(
        "SELECT pg_get_serial_sequence(%s, 'id') AS seq_name",
        (table,),
    )
    row = cur.fetchone() or {'seq_name': None}
    seq_name = row['seq_name']
    if not seq_name:
        return
    cur.execute(f'SELECT COALESCE(MAX(id), 0) AS max_id FROM {table}')
    max_id = int((cur.fetchone() or {'max_id': 0})['max_id'])
    if max_id > 0:
        cur.execute('SELECT setval(%s, %s, %s)', (seq_name, max_id, True))
    else:
        cur.execute('SELECT setval(%s, %s, %s)', (seq_name, 1, False))


def _normalize_project_status(status: str | None) -> str:
    if status == 'blocked':
        return 'on_hold'
    if status == 'at_risk':
        return 'active'
    if status in {'planning', 'active', 'on_hold', 'completed', 'cancelled'}:
        return status
    raise RuntimeError(f'Unsupported project status encountered during migration: {status!r}')


def _normalize_project_health(risk_level: str | None) -> str:
    if not risk_level:
        raise RuntimeError('Project risk_level is required and cannot be empty during migration')
    if risk_level == 'low':
        return 'healthy'
    if risk_level == 'medium':
        return 'at_risk'
    if risk_level == 'high':
        return 'critical'
    raise RuntimeError(f'Unsupported project risk_level encountered during migration: {risk_level!r}')


def _validate_project_source_rows(sqlite_conn: sqlite3.Connection) -> None:
    rows = _fetchall_sqlite(sqlite_conn, 'SELECT id, status, risk_level FROM projects ORDER BY id')
    for row in rows:
        _normalize_project_status(row['status'])
        _normalize_project_health(row['risk_level'])


def _copy_rows_sqlite_to_pg(sqlite_conn: sqlite3.Connection, pg_cur) -> None:
    customers = _fetchall_sqlite(sqlite_conn, f'SELECT {", ".join(CUSTOMER_COLUMNS)} FROM customers ORDER BY id')
    for row in customers:
        pg_cur.execute(
            f"INSERT INTO customers ({', '.join(CUSTOMER_COLUMNS)}) VALUES ({', '.join(['%s'] * len(CUSTOMER_COLUMNS))})",
            [row[col] for col in CUSTOMER_COLUMNS],
        )

    projects = _fetchall_sqlite(sqlite_conn, f'SELECT {", ".join(PROJECT_COLUMNS)} FROM projects ORDER BY id')
    for row in projects:
        values = [
            row['id'],
            row['customer_id'],
            row['name'],
            _normalize_project_status(row['status']),
            _normalize_project_health(row['risk_level']),
            row['risk_level'],
            row['delivery_stage'],
            row['created_at'],
            row['updated_at'],
        ]
        pg_cur.execute(
            f"INSERT INTO projects ({', '.join(PROJECT_COLUMNS)}) VALUES ({', '.join(['%s'] * len(PROJECT_COLUMNS))})",
            values,
        )

    requirements = _fetchall_sqlite(sqlite_conn, f'SELECT {", ".join(REQUIREMENT_COLUMNS)} FROM requirements ORDER BY id')
    for row in requirements:
        pg_cur.execute(
            f"INSERT INTO requirements ({', '.join(REQUIREMENT_COLUMNS)}) VALUES ({', '.join(['%s'] * len(REQUIREMENT_COLUMNS))})",
            [row[col] for col in REQUIREMENT_COLUMNS],
        )

    issues = _fetchall_sqlite(sqlite_conn, f'SELECT {", ".join(ISSUE_COLUMNS)} FROM issues ORDER BY id')
    for row in issues:
        pg_cur.execute(
            f"INSERT INTO issues ({', '.join(ISSUE_COLUMNS)}) VALUES ({', '.join(['%s'] * len(ISSUE_COLUMNS))})",
            [row[col] for col in ISSUE_COLUMNS],
        )

    analyses = _fetchall_sqlite(sqlite_conn, f'SELECT {", ".join(AI_ANALYSIS_COLUMNS)} FROM ai_analysis_logs ORDER BY id')
    for row in analyses:
        pg_cur.execute(
            f"INSERT INTO ai_analysis_logs ({', '.join(AI_ANALYSIS_COLUMNS)}) VALUES ({', '.join(['%s'] * len(AI_ANALYSIS_COLUMNS))})",
            [row[col] for col in AI_ANALYSIS_COLUMNS],
        )


def _validate_post_migration(cur, source_stats: dict[str, TableStats]) -> None:
    target_stats = _print_pg_stats(cur)
    for table in TABLE_ORDER:
        source = source_stats[table]
        target = target_stats[table]
        if source.count != target.count:
            raise RuntimeError(f'Row count mismatch for {table}: source={source.count}, target={target.count}')
        if source.min_id != target.min_id:
            raise RuntimeError(f'MIN(id) mismatch for {table}: source={source.min_id}, target={target.min_id}')
        if source.max_id != target.max_id:
            raise RuntimeError(f'MAX(id) mismatch for {table}: source={source.max_id}, target={target.max_id}')
    _check_foreign_keys(cur)
    print('[postgres] foreign key validation passed')


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f'SQLite database not found: {sqlite_path}')
    if not args.postgres_url:
        raise SystemExit('PostgreSQL URL is required via --postgres-url or DATABASE_URL/POSTGRES_URL/POSTGRESQL_URL')

    print(f'[config] sqlite_path={sqlite_path}')
    print(f'[config] postgres_url={_mask_database_url(args.postgres_url)}')
    print(f'[config] dry_run={args.dry_run}')
    print(f'[config] replace_target={args.replace_target}')

    with _open_sqlite(sqlite_path) as sqlite_conn:
        source_stats = _validate_sqlite_source(sqlite_conn)
        _validate_project_source_rows(sqlite_conn)

        with _connect_postgres(args.postgres_url) as pg_conn:
            with pg_conn.cursor() as pg_cur:
                _validate_target_tables_exist(pg_cur)
                print('[postgres] target tables verified')
                target_stats = _print_pg_stats(pg_cur)

                if args.dry_run:
                    if args.replace_target:
                        print('[dry-run] formal migration would clear target tables before copying data')
                    _check_foreign_keys(pg_cur)
                    print('[dry-run] foreign key validation passed against current PostgreSQL data')
                    for table in TABLE_ORDER:
                        source = source_stats[table]
                        target = target_stats[table]
                        print(
                            f'[dry-run] {table}: source_count={source.count}, target_count={target.count}, source_min_id={source.min_id}, target_min_id={target.min_id}, source_max_id={source.max_id}, target_max_id={target.max_id}'
                        )
                    return 0

                if any(stats.count > 0 for stats in target_stats.values()):
                    if not args.replace_target:
                        nonempty = ', '.join(f'{table}={stats.count}' for table, stats in target_stats.items() if stats.count > 0)
                        raise RuntimeError('PostgreSQL target is not empty. Use --replace-target to clear smoke test data. Found: ' + nonempty)
                    print('[postgres] replace-target enabled; existing target rows will be cleared in the same transaction')

                try:
                    if args.replace_target:
                        _clear_target_tables(pg_cur)
                        print('[postgres] target tables cleared')

                    _copy_rows_sqlite_to_pg(sqlite_conn, pg_cur)
                    print('[postgres] data copied from SQLite to PostgreSQL')

                    for table in TABLE_ORDER:
                        _reset_sequence(pg_cur, table)
                    print('[postgres] sequences reset to current MAX(id)')

                    _validate_post_migration(pg_cur, source_stats)

                    pg_conn.commit()
                    print('[postgres] migration committed successfully')
                except Exception:
                    pg_conn.rollback()
                    print('[postgres] migration rolled back due to error')
                    raise

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
