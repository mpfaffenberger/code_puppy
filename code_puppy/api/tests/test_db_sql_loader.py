from pathlib import Path


def test_external_session_history_sql_files_exist_and_contain_expected_clauses():
    sql_dir = Path("code_puppy/api/db/sql")
    parity_sql = (sql_dir / "session_history_parity.sql").read_text(encoding="utf-8")
    no_compacted_sql = (sql_dir / "session_history_parity_no_compacted.sql").read_text(
        encoding="utf-8"
    )

    assert "FROM messages m" in parity_sql
    assert "FROM tool_calls tc" in parity_sql
    assert "ORDER BY seq" in parity_sql

    assert "m.compacted = 0" in no_compacted_sql
    assert "ORDER BY seq" in no_compacted_sql


def test_queries_module_uses_sql_loader_for_complex_session_query():
    queries_src = Path("code_puppy/api/db/queries.py").read_text(encoding="utf-8")
    assert 'load_sql("session_history_parity.sql")' in queries_src
    assert "session_history_parity_no_compacted.sql" in queries_src
