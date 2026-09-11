"""Shared Gemini wire-format helpers.

Consolidates logic that was previously duplicated (and had drifted) across
`gemini_model.py::GeminiModel` and `gemini_code_assist.py::GeminiCodeAssistModel`.

Wire-format knowledge for the Gemini API should live in exactly one place.
"""

from typing import Any

from pydantic_ai.tools import ToolDefinition
from pydantic_ai.settings import ModelSettings


def _flatten_union_to_object_gemini(union_items: list, defs: dict, resolve_fn) -> dict:
    """Flatten a union of object types into a single object with all properties.

    For discriminated unions like EditFilePayload, we merge all object types
    into one with all properties (Gemini doesn't support anyOf/oneOf).
    """
    import copy as copy_module

    merged_properties = {}
    has_string_type = False

    for item in union_items:
        if not isinstance(item, dict):
            continue

        # Resolve $ref first.
        if "$ref" in item:
            ref_path = item["$ref"]
            ref_name = None

            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path[8:]

            elif ref_path.startswith("#/definitions/"):
                ref_name = ref_path[14:]

            if ref_name and ref_name in defs:
                item = copy_module.deepcopy(defs[ref_name])

            else:
                continue

        if item.get("type") == "string":
            has_string_type = True
            continue

        if item.get("type") == "null":
            continue

        if item.get("type") == "object" or "properties" in item:
            props = item.get("properties", {})
            for prop_name, prop_schema in props.items():
                if prop_name not in merged_properties:
                    merged_properties[prop_name] = resolve_fn(
                        copy_module.deepcopy(prop_schema)
                    )

    if not merged_properties:
        return {"type": "string"} if has_string_type else {"type": "object"}

    return {
        "type": "object",
        "properties": merged_properties,
    }


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Sanitize JSON schema for Gemini API compatibility.

    Removes/transforms fields that Gemini doesn't support:
    - $defs, definitions, $schema, $id
    - additionalProperties
    - $ref (inlined)
    - anyOf/oneOf/allOf (flattened - Gemini doesn't support unions!)
      - For unions of objects: merges into single object with all properties
      - For simple unions (string | null): picks first non-null type
    """
    import copy

    if not isinstance(schema, dict):
        return schema

    # Make a deep copy to avoid modifying original.
    schema = copy.deepcopy(schema)

    # Extract $defs for reference resolution.
    defs = schema.pop("$defs", schema.pop("definitions", {}))

    def resolve_refs(obj):
        """Recursively resolve $ref references and clean schema."""
        if isinstance(obj, dict):
            # Handle anyOf/oneOf unions.
            for union_key in ["anyOf", "oneOf"]:
                if union_key in obj:
                    union = obj[union_key]

                    if isinstance(union, list):
                        # Check if this is a complex union of objects.
                        object_count = 0
                        has_refs = False

                        for item in union:
                            if isinstance(item, dict):
                                if "$ref" in item:
                                    has_refs = True
                                    object_count += 1

                                elif (
                                    item.get("type") == "object" or "properties" in item
                                ):
                                    object_count += 1

                        # If multiple objects or has refs, flatten to single object.
                        if object_count > 1 or has_refs:
                            flattened = _flatten_union_to_object_gemini(
                                union, defs, resolve_refs
                            )

                            if "description" in obj:
                                flattened["description"] = obj["description"]
                            return flattened

                        # Simple union — pick first non-null type.
                        for item in union:
                            if isinstance(item, dict) and item.get("type") != "null":
                                result = dict(item)

                                if "description" in obj:
                                    result["description"] = obj["description"]
                                return resolve_refs(result)

            # Handle allOf by merging all schemas.
            if "allOf" in obj:
                all_of = obj["allOf"]

                if isinstance(all_of, list):
                    merged = {}
                    merged_properties = {}

                    for item in all_of:
                        if isinstance(item, dict):
                            resolved_item = resolve_refs(item)

                            if "properties" in resolved_item:
                                merged_properties.update(
                                    resolved_item.pop("properties")
                                )
                            merged.update(resolved_item)

                    if merged_properties:
                        merged["properties"] = merged_properties

                    for key, value in obj.items():
                        if key != "allOf":
                            merged[key] = value

                    return resolve_refs(merged)

            # Check for $ref.
            if "$ref" in obj:
                ref_path = obj["$ref"]
                ref_name = None

                # Parse ref like "#/$defs/SomeType" or "#/definitions/SomeType".
                if ref_path.startswith("#/$defs/"):
                    ref_name = ref_path[8:]

                elif ref_path.startswith("#/definitions/"):
                    ref_name = ref_path[14:]

                if ref_name and ref_name in defs:
                    resolved = resolve_refs(copy.deepcopy(defs[ref_name]))
                    other_props = {k: v for k, v in obj.items() if k != "$ref"}

                    if other_props:
                        resolved.update(resolve_refs(other_props))
                    return resolved

                else:
                    return {"type": "object"}

            # Recursively process and transform.
            result = {}

            for key, value in obj.items():
                # Skip unsupported fields.
                if key in (
                    "$defs",
                    "definitions",
                    "$schema",
                    "$id",
                    "additionalProperties",
                    "default",
                    "examples",
                    "const",
                    "anyOf",  # Skip any remaining union types.
                    "oneOf",
                    "allOf",
                ):
                    continue

                result[key] = resolve_refs(value)
            return result

        elif isinstance(obj, list):
            return [resolve_refs(item) for item in obj]

        else:
            return obj

    return resolve_refs(schema)


def _build_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Build tool definitions for the API."""
    function_declarations = []

    for tool in tools:
        func_decl: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description or "",
        }

        if tool.parameters_json_schema:
            # Sanitize schema for Gemini compatibility.
            func_decl["parameters"] = _sanitize_schema_for_gemini(
                tool.parameters_json_schema
            )

        function_declarations.append(func_decl)

    return [{"functionDeclarations": function_declarations}]


def _build_generation_config(model_settings: ModelSettings | None) -> dict[str, Any]:
    """Build generation config from model settings."""
    config: dict[str, Any] = {}

    if model_settings:
        # ModelSettings is a TypedDict, so use .get() for all access.
        temperature = model_settings.get("temperature")
        if temperature is not None:
            config["temperature"] = temperature

        top_p = model_settings.get("top_p")
        if top_p is not None:
            config["topP"] = top_p

        max_tokens = model_settings.get("max_tokens")
        if max_tokens is not None:
            config["maxOutputTokens"] = max_tokens

        # Handle Gemini 3 Pro thinking settings.
        thinking_enabled = model_settings.get("thinking_enabled")
        thinking_level = model_settings.get("thinking_level")

        # Build thinkingConfig if thinking settings are present.
        if thinking_enabled is False:
            # Disable thinking by not including thinkingConfig.
            pass

        elif thinking_level is not None:
            # Gemini 3 Pro uses thinkingLevel with values "low" or "high".
            # `includeThoughts=True` is required to surface the thinking in response.
            config["thinkingConfig"] = {
                "thinkingLevel": thinking_level,
                "includeThoughts": True,
            }

    return config
