from pathlib import Path

from code_puppy.session_storage import get_session_file_path, save_session


def test_save_session_returns_json_file_path(tmp_path: Path):
    metadata = save_session(
        history=[{"role": "user", "content": "hello"}],
        session_name="demo",
        base_dir=tmp_path,
    )

    assert metadata.message_count == 1
    assert metadata.session_file_path == get_session_file_path(tmp_path, "demo")
    assert metadata.session_file_path.suffix == ".json"
    assert metadata.session_file_path.exists()
