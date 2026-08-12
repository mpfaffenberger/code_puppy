import os
import json

from code_puppy.plugins.claude_code_hooks.config import load_hooks_config


def test_hooks_expansion(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    mock_plugin_dir.mkdir(parents=True)

    mock_hooks_file = tmp_path / "hooks.json"
    hooks_data = {
        "hooks": {
            "PreToolUse": [
                {
                    "commands": [
                        "node ${CLAUDE_PLUGIN_ROOT}/test-plugin/dist/index.js",
                        "echo $CLAUDE_PLUGIN_ROOT/other",
                    ]
                }
            ]
        }
    }
    with open(mock_hooks_file, "w") as f:
        json.dump(hooks_data, f)

    monkeypatch.setattr(
        "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
        str(mock_hooks_file),
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_code_hooks.config.PROJECT_HOOKS_FILE",
        "nonexistent.json",
    )

    # Mock expanduser so it thinks ~/.code_puppy/claude_plugins is our tmp mock_plugin_dir
    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~/.code_puppy/claude_plugins":
            return str(mock_plugin_dir)
        return original_expanduser(path)

    monkeypatch.setattr("os.path.expanduser", mock_expanduser)

    config = load_hooks_config()

    cmds = config["PreToolUse"][0]["commands"]
    assert cmds[0] == f"node {mock_plugin_dir}/test-plugin/dist/index.js"
    assert cmds[1] == f"echo {mock_plugin_dir}/other"
