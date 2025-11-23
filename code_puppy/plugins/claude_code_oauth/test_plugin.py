#!/usr/bin/env python3
"""Manual sanity checks for the Claude Code OAuth plugin."""

import os
import sys
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Switch to project root for predictable relative paths
os.chdir(PROJECT_ROOT)


def test_plugin_imports() -> bool:
    """Verify the plugin modules import correctly."""
    print("\n=== Testing Plugin Imports ===")

    try:
        from code_puppy.plugins.claude_code_oauth.config import (
            CLAUDE_CODE_OAUTH_CONFIG,
            get_token_storage_path,
        )

        print("✅ Config import successful")
        print(f"✅ Token storage path: {get_token_storage_path()}")
        print(f"✅ Known auth URL: {CLAUDE_CODE_OAUTH_CONFIG['auth_url']}")
    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ Config import failed: {exc}")
        return False

    try:
        from code_puppy.plugins.claude_code_oauth.utils import (
            add_models_to_extra_config,
            build_authorization_url,
            exchange_code_for_tokens,
            fetch_claude_code_models,
            load_claude_models,
            load_stored_tokens,
            parse_authorization_code,
            prepare_oauth_context,
            remove_claude_code_models,
            save_claude_models,
            save_tokens,
        )

        _ = (
            add_models_to_extra_config,
            build_authorization_url,
            exchange_code_for_tokens,
            fetch_claude_code_models,
            load_claude_models,
            load_stored_tokens,
            parse_authorization_code,
            prepare_oauth_context,
            remove_claude_code_models,
            save_claude_models,
            save_tokens,
        )
        print("✅ Utils import successful")
    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ Utils import failed: {exc}")
        return False

    try:
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _custom_help,
            _handle_custom_command,
        )

        commands = _custom_help()
        print("✅ Callback registration import successful")
        for name, description in commands:
            print(f"  /{name} - {description}")
        # Ensure handler callable exists
        _ = _handle_custom_command
    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ Callback import failed: {exc}")
        return False

    return True


def test_oauth_helpers() -> bool:
    """Exercise helper functions without performing network requests."""
    print("\n=== Testing OAuth Helper Functions ===")

    try:
        from urllib.parse import parse_qs, urlparse

        from code_puppy.plugins.claude_code_oauth.utils import (
            assign_redirect_uri,
            build_authorization_url,
            parse_authorization_code,
            prepare_oauth_context,
        )

        context = prepare_oauth_context()
        assert context.state, "Expected non-empty OAuth state"
        assert context.code_verifier, "Expected PKCE code verifier"
        assert context.code_challenge, "Expected PKCE code challenge"

        assign_redirect_uri(context, 8765)
        auth_url = build_authorization_url(context)
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)
        print(f"✅ Authorization URL: {auth_url}")
        assert parsed.scheme == "https", "Authorization URL must use https"
        assert params.get("client_id", [None])[0], "client_id missing"
        assert params.get("code_challenge_method", [None])[0] == "S256"
        assert params.get("state", [None])[0] == context.state
        assert params.get("code_challenge", [None])[0] == context.code_challenge

        sample_code = f"MYCODE#{context.state}"
        parsed_code, parsed_state = parse_authorization_code(sample_code)
        assert parsed_code == "MYCODE", "Code parsing failed"
        assert parsed_state == context.state, "State parsing failed"
        print("✅ parse_authorization_code handled state suffix correctly")

        parsed_code, parsed_state = parse_authorization_code("SINGLECODE")
        assert parsed_code == "SINGLECODE" and parsed_state is None
        print("✅ parse_authorization_code handled bare code correctly")

        return True

    except AssertionError as exc:
        print(f"❌ Assertion failed: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ OAuth helper test crashed: {exc}")
        import traceback

        traceback.print_exc()
        return False


def test_file_operations() -> bool:
    """Ensure token/model storage helpers behave sanely."""
    print("\n=== Testing File Operations ===")

    try:
        from code_puppy.plugins.claude_code_oauth.config import (
            get_claude_models_path,
            get_token_storage_path,
        )
        from code_puppy.plugins.claude_code_oauth.utils import (
            load_claude_models,
            load_stored_tokens,
        )

        tokens = load_stored_tokens()
        print(f"✅ Token load result: {'present' if tokens else 'none'}")

        models = load_claude_models()
        print(f"✅ Loaded {len(models)} Claude models")
        for name, config in models.items():
            print(f"  - {name}: {config.get('type', 'unknown type')}")

        token_path = get_token_storage_path()
        models_path = get_claude_models_path()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        models_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"✅ Token path: {token_path}")
        print(f"✅ Models path: {models_path}")

        return True

    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ File operations test failed: {exc}")
        import traceback

        traceback.print_exc()
        return False


def test_command_handlers() -> bool:
    """Smoke-test command handler routing without simulating authentication."""
    print("\n=== Testing Command Handlers ===")

    from code_puppy.plugins.claude_code_oauth.register_callbacks import (
        _handle_custom_command,
    )

    unknown = _handle_custom_command("/bogus", "bogus")
    print(f"✅ Unknown command returned: {unknown}")

    partial = _handle_custom_command("/claude-code", "claude-code")
    print(f"✅ Partial command returned: {partial}")

    # Do not invoke the real auth command here because it prompts for input.
    return True


def test_configuration() -> bool:
    """Validate configuration keys and basic formats."""
    print("\n=== Testing Configuration ===")

    try:
        from code_puppy.plugins.claude_code_oauth.config import CLAUDE_CODE_OAUTH_CONFIG

        required_keys = [
            "auth_url",
            "token_url",
            "api_base_url",
            "client_id",
            "scope",
            "redirect_host",
            "redirect_path",
            "callback_port_range",
            "callback_timeout",
            "token_storage",
            "prefix",
            "default_context_length",
            "api_key_env_var",
        ]

        missing = [key for key in required_keys if key not in CLAUDE_CODE_OAUTH_CONFIG]
        if missing:
            print(f"❌ Missing configuration keys: {missing}")
            return False

        for key in required_keys:
            value = CLAUDE_CODE_OAUTH_CONFIG[key]
            print(f"✅ {key}: {value}")

        for url_key in ["auth_url", "token_url", "api_base_url"]:
            url = CLAUDE_CODE_OAUTH_CONFIG[url_key]
            if not str(url).startswith("https://"):
                print(f"❌ URL must use HTTPS: {url_key} -> {url}")
                return False
            print(f"✅ {url_key} uses HTTPS")

        return True

    except Exception as exc:  # pragma: no cover - manual harness
        print(f"❌ Configuration test crashed: {exc}")
        import traceback

        traceback.print_exc()
        return False


def main() -> bool:
    """Run all manual checks."""
    print("Claude Code OAuth Plugin Test Suite")
    print("=" * 40)

    tests = [
        test_plugin_imports,
        test_oauth_helpers,
        test_file_operations,
        test_command_handlers,
        test_configuration,
    ]

    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print("\n❌ Test failed")
        except Exception as exc:  # pragma: no cover - manual harness
            print(f"\n❌ Test crashed: {exc}")

    print("\n=== Test Results ===")
    print(f"Passed: {passed}/{len(tests)}")

    if passed == len(tests):
        print("✅ All sanity checks passed!")
        print("Next steps:")
        print("1. Restart Code Puppy if it was running")
        print("2. Run /claude-code-auth")
        print("3. Paste the Claude Console authorization code when prompted")
        return True

    print("❌ Some checks failed. Investigate before using the plugin.")
    return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
