"""Tests for the pydantic serializer-warning filter.

Context: some OpenAI-compatible gateways return a ``ChatCompletion`` whose
``metadata`` object carries non-string values (e.g.
``weight_versions=[{'version': 'default', 'start': 0, 'end': 57}]``). The
OpenAI schema declares that object string-valued, so pydantic-ai's response
round-trip (``_ChatCompletion.model_validate(response.model_dump())``) emits a
multi-line ``UserWarning`` on every single model request.

``patch_silence_pydantic_serializer_warnings`` swallows exactly that warning
family (the ``"Pydantic serializer warnings:"`` prefix) and nothing else.
"""

import warnings

import pytest

from code_puppy import pydantic_patches

# The real message, verbatim, as pydantic prints it to the console.
REAL_WARNING = (
    "Pydantic serializer warnings:\n"
    "  PydanticSerializationUnexpectedValue(Expected `str` - serialized value "
    "may not be as expected [field_name='metadata', input_value=[{'version': "
    "'default', 'start': 0, 'end': 57}], input_type=list])\n"
    "  return self.__pydantic_serializer__.to_python("
)


class TestSerializerWarningFilter:
    def test_registered_in_all_patches(self):
        assert pydantic_patches.patch_silence_pydantic_serializer_warnings in (
            pydantic_patches._ALL_PATCHES
        )

    def test_returns_true(self):
        assert pydantic_patches.patch_silence_pydantic_serializer_warnings() is True

    def test_suppresses_the_real_message(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_pydantic_serializer_warnings()
            warnings.warn(REAL_WARNING, UserWarning, stacklevel=2)
        assert caught == []

    @pytest.mark.parametrize(
        "message",
        [
            REAL_WARNING,
            "Pydantic serializer warnings:\n  something else entirely",
        ],
    )
    def test_suppresses_the_whole_warning_family(self, message):
        """Any serializer warning is noise for us -- the family is filtered."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_pydantic_serializer_warnings()
            warnings.warn(message, UserWarning, stacklevel=2)
        assert caught == []

    def test_leaves_other_user_warnings_alone(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_pydantic_serializer_warnings()
            warnings.warn("Something else entirely", UserWarning, stacklevel=2)
        assert len(caught) == 1
        assert str(caught[0].message) == "Something else entirely"

    def test_leaves_other_categories_alone(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_pydantic_serializer_warnings()
            warnings.warn(REAL_WARNING, DeprecationWarning, stacklevel=2)
        assert len(caught) == 1


class TestEndToEndOpenAICompletionDump:
    """The exact call pydantic-ai makes on every OpenAI-compatible response."""

    @staticmethod
    def _completion_with_off_schema_metadata():
        from openai.types.chat import ChatCompletion

        return ChatCompletion.model_construct(
            id="chatcmpl-test",
            choices=[],
            created=0,
            model="test-model",
            object="chat.completion",
            metadata={
                "weight_version": "default",
                "weight_versions": [{"version": "default", "start": 0, "end": 57}],
            },
        )

    def test_warns_without_the_filter(self):
        completion = self._completion_with_off_schema_metadata()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            completion.model_dump()
        assert any(
            str(w.message).startswith("Pydantic serializer warnings:") for w in caught
        ), "expected the off-schema metadata to warn; repro has drifted"

    def test_silent_with_the_filter(self):
        completion = self._completion_with_off_schema_metadata()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_pydantic_serializer_warnings()
            completion.model_dump()
        assert caught == []
