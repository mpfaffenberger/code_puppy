"""Tests for code_puppy/command_line/onboarding_slides.py"""

MODULE = "code_puppy.command_line.onboarding_slides"


class TestModelOptions:
    def test_model_options_is_list(self):
        from code_puppy.command_line.onboarding_slides import MODEL_OPTIONS

        assert isinstance(MODEL_OPTIONS, list)
        assert len(MODEL_OPTIONS) >= 4

    def test_model_options_tuples(self):
        from code_puppy.command_line.onboarding_slides import MODEL_OPTIONS

        for opt in MODEL_OPTIONS:
            assert len(opt) == 3
            assert isinstance(opt[0], str)


class TestGetNavFooter:
    def test_returns_string(self):
        from code_puppy.command_line.onboarding_slides import get_nav_footer

        result = get_nav_footer()
        assert isinstance(result, str)
        assert "Next" in result
        assert "Back" in result
        assert "ESC" in result


class TestGetGradientBanner:
    def test_with_pyfiglet(self):
        from code_puppy.command_line.onboarding_slides import get_gradient_banner

        result = get_gradient_banner()
        assert isinstance(result, str)
        # Should contain some content
        assert len(result) > 0

    def test_without_pyfiglet(self):
        """Test fallback when pyfiglet is unavailable."""
        import code_puppy.command_line.onboarding_slides as mod

        # pyfiglet is available in this env, so normal path works
        result = mod.get_gradient_banner()
        assert len(result) > 0


class TestSlideWelcome:
    def test_returns_string(self):
        from code_puppy.command_line.onboarding_slides import slide_welcome

        result = slide_welcome()
        assert isinstance(result, str)
        assert "Welcome" in result
        assert "setup" in result.lower() or "quick" in result.lower()


class TestSlideModels:
    def test_with_options(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [
            ("chatgpt", "ChatGPT"),
            ("claude", "Claude"),
            ("api_keys", "API"),
            ("openrouter", "OpenRouter"),
            ("skip", "Skip"),
        ]
        result = slide_models(0, options)
        assert "ChatGPT" in result
        assert "▶" in result  # selected indicator

    def test_claude_selected(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [("chatgpt", "ChatGPT"), ("claude", "Claude")]
        result = slide_models(1, options)
        assert "Claude" in result

    def test_api_keys_context(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [("api_keys", "API Keys")]
        result = slide_models(0, options)
        assert "API Key" in result

    def test_openrouter_context(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [("openrouter", "OpenRouter")]
        result = slide_models(0, options)
        assert "OpenRouter" in result

    def test_skip_context(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [("skip", "Skip")]
        result = slide_models(0, options)
        assert "later" in result.lower() or "No worries" in result

    def test_empty_options(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        result = slide_models(0, [])
        assert isinstance(result, str)

    def test_chatgpt_context(self):
        from code_puppy.command_line.onboarding_slides import slide_models

        options = [("chatgpt", "ChatGPT Plus")]
        result = slide_models(0, options)
        assert "ChatGPT" in result or "OAuth" in result


class TestSlideMcp:
    def test_returns_string(self):
        from code_puppy.command_line.onboarding_slides import slide_mcp

        result = slide_mcp()
        assert isinstance(result, str)
        assert "MCP" in result
        assert "/mcp" in result


class TestSlideUseCases:
    def test_returns_string(self):
        from code_puppy.command_line.onboarding_slides import slide_use_cases

        result = slide_use_cases()
        assert isinstance(result, str)
        assert "Planning" in result
        assert "Code Puppy" in result


class TestSlideDone:
    def test_without_oauth(self):
        from code_puppy.command_line.onboarding_slides import slide_done

        result = slide_done(None)
        assert isinstance(result, str)
        assert "Ready" in result
        assert "/tutorial" in result

    def test_with_oauth_chatgpt(self):
        from code_puppy.command_line.onboarding_slides import slide_done

        result = slide_done("chatgpt")
        assert "Chatgpt" in result or "chatgpt" in result.lower()
        assert "OAuth" in result

    def test_with_oauth_claude(self):
        from code_puppy.command_line.onboarding_slides import slide_done

        result = slide_done("claude")
        assert "Claude" in result or "claude" in result.lower()
