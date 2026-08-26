"""SPIKE (Phase 1, Red-team #1): verify DuckDB single-process topology.

Finding from first attempt: opening the SAME file with mixed configurations
(read-write + read_only=True) hard-fails even within one process
("Can't open a connection to same database file with a different configuration").
Therefore the app architecture is: exactly ONE read-write DuckDB connection,
shared via multiple cursors (thread-safe for concurrent reads).

Result: PASS — see README.md "Architecture spike" section.
"""
import duckdb


def main() -> None:
    db_path = "spike.duckdb"
    conn = duckdb.connect(db_path)
    conn.execute("SET TimeZone='UTC'")
    conn.execute(
        "CREATE TABLE klines (open_time TIMESTAMPTZ, symbol VARCHAR, close DOUBLE)"
    )
    conn.execute("INSERT INTO klines VALUES ('2026-01-01 00:00:00+00', 'BTCUSDT', 40000.0)")

    cur_a = conn.cursor()
    cur_b = conn.cursor()
    row = cur_a.execute("SELECT count(*), max(close) FROM klines").fetchone()
    assert row == (1, 40000.0), f"unexpected: {row}"

    # write through one cursor, visible immediately through the other
    conn.execute("INSERT INTO klines VALUES ('2026-01-01 01:00:00+00', 'BTCUSDT', 40100.0)")
    row = cur_b.execute("SELECT count(*) FROM klines").fetchone()
    assert row == (2,), f"cursor did not see writer insert: {row}"

    # timezone setting does NOT propagate from base connection to cursors
    # (host is UTC+7 → Asia/Saigon by default) — must SET on every cursor.
    cur_a.execute("SET TimeZone='UTC'")
    tz = cur_a.execute("SELECT current_setting('TimeZone')").fetchone()[0]
    assert tz.upper() == "UTC", f"TimeZone not UTC: {tz}"

    cur_a.close()
    cur_b.close()
    conn.close()
    print("SPIKE PASS — single connection + multi-cursor topology OK")


if __name__ == "__main__":
    main()
