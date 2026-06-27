from pathlib import Path


def test_chat_template_handles_session_meta_and_config_frames():
    html = Path("code_puppy/api/templates/chat.html").read_text()

    assert "case 'session_meta':" in html
    assert "case 'session_meta_updated':" in html
    assert "case 'session_restored':" in html
    assert "case 'session_switched':" in html
    assert "case 'config_value':" in html
    assert "function handleSessionMeta(message)" in html
    assert "window.codePuppyConfig = sessionState.config;" in html
