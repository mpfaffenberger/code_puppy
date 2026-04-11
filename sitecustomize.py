"""Runtime compatibility patches loaded automatically by Python."""


def _patch_pydantic_ai_tool_schema_none() -> None:
    try:
        from pydantic_ai.function_signature import FunctionSignature
    except Exception:
        return

    original = FunctionSignature.from_schema
    if getattr(original, "_code_puppy_none_schema_patch", False):
        return

    def patched(cls, *, name, parameters_schema, return_schema=None):
        if parameters_schema is None:
            parameters_schema = {"type": "object", "properties": {}}
        return original.__func__(
            cls,
            name=name,
            parameters_schema=parameters_schema,
            return_schema=return_schema,
        )

    patched = classmethod(patched)
    setattr(patched, "_code_puppy_none_schema_patch", True)
    FunctionSignature.from_schema = patched


_patch_pydantic_ai_tool_schema_none()
