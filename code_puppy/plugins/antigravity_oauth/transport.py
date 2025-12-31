"""Custom httpx client for Antigravity API.

Wraps Gemini API requests in the Antigravity envelope format and
unwraps responses (including streaming SSE events).
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from typing import Any, Dict, Optional

import httpx

from .constants import (
    ANTIGRAVITY_DEFAULT_PROJECT_ID,
    ANTIGRAVITY_ENDPOINT_FALLBACKS,
    ANTIGRAVITY_HEADERS,
)

logger = logging.getLogger(__name__)


def _inline_refs(
    schema: dict, convert_unions: bool = False, simplify_for_claude: bool = False
) -> dict:
    """Inline $ref references and transform schema for Antigravity compatibility.

    - Inlines $ref references
    - Removes $defs, definitions, $schema, $id
    - Optionally converts anyOf/oneOf/allOf to any_of/one_of/all_of (only for Gemini)
    - Removes unsupported fields like 'default', 'examples', 'const'
    - For Claude: simplifies anyOf unions to single types

    Args:
        convert_unions: If True, convert anyOf->any_of etc. (for Gemini).
        simplify_for_claude: If True, simplify anyOf to single types.
    """
    if not isinstance(schema, dict):
        return schema

    # Make a deep copy to avoid modifying original
    schema = copy.deepcopy(schema)

    # Extract $defs for reference resolution
    defs = schema.pop("$defs", schema.pop("definitions", {}))

    def resolve_refs(
        obj, convert_unions=convert_unions, simplify_for_claude=simplify_for_claude
    ):
        """Recursively resolve $ref references and transform schema."""
        if isinstance(obj, dict):
            # For Claude: simplify anyOf/oneOf unions to first non-null type
            if simplify_for_claude:
                for union_key in ["anyOf", "oneOf"]:
                    if union_key in obj:
                        union = obj[union_key]
                        if isinstance(union, list):
                            # Find first non-null type
                            for item in union:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") != "null"
                                ):
                                    # Replace the whole object with this type
                                    result = dict(item)
                                    # Keep description if present
                                    if "description" in obj:
                                        result["description"] = obj["description"]
                                    return resolve_refs(
                                        result, convert_unions, simplify_for_claude
                                    )

            # Check for $ref
            if "$ref" in obj:
                ref_path = obj["$ref"]
                ref_name = None

                # Parse ref like "#/$defs/SomeType" or "#/definitions/SomeType"
                if ref_path.startswith("#/$defs/"):
                    ref_name = ref_path[8:]
                elif ref_path.startswith("#/definitions/"):
                    ref_name = ref_path[14:]

                if ref_name and ref_name in defs:
                    # Return the resolved definition (recursively resolve it too)
                    resolved = resolve_refs(copy.deepcopy(defs[ref_name]))
                    # Merge any other properties from the original object
                    other_props = {k: v for k, v in obj.items() if k != "$ref"}
                    if other_props:
                        resolved.update(resolve_refs(other_props))
                    return resolved
                else:
                    # Can't resolve - return a generic object type instead of empty
                    return {"type": "object"}

            # Recursively process all values and transform keys
            result = {}
            for key, value in obj.items():
                # Skip unsupported fields
                if key in (
                    "$defs",
                    "definitions",
                    "$schema",
                    "$id",
                    "default",
                    "examples",
                    "const",
                ):
                    continue

                # For Claude: skip additionalProperties
                if simplify_for_claude and key == "additionalProperties":
                    continue

                # Optionally transform union types for Gemini
                new_key = key
                if convert_unions:
                    if key == "anyOf":
                        new_key = "any_of"
                    elif key == "oneOf":
                        new_key = "one_of"
                    elif key == "allOf":
                        new_key = "all_of"
                    elif key == "additionalProperties":
                        new_key = "additional_properties"

                result[new_key] = resolve_refs(
                    value, convert_unions, simplify_for_claude
                )
            return result
        elif isinstance(obj, list):
            return [
                resolve_refs(item, convert_unions, simplify_for_claude) for item in obj
            ]
        else:
            return obj

    return resolve_refs(schema, convert_unions, simplify_for_claude)


class UnwrappedResponse(httpx.Response):
    """A response wrapper that unwraps Antigravity JSON format for non-streaming.

    Must be created AFTER calling aread() on the original response.
    """

    def __init__(self, original_response: httpx.Response):
        # DON'T copy __dict__ - it contains wrapped _content!
        # Instead, unwrap immediately since content is already read
        self._original = original_response
        self.status_code = original_response.status_code
        self.headers = original_response.headers
        self.stream = original_response.stream
        self.is_closed = original_response.is_closed
        self.is_stream_consumed = original_response.is_stream_consumed

        # Unwrap the content NOW
        raw_content = original_response.content
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict) and "response" in data:
                unwrapped = data["response"]
                self._unwrapped_content = json.dumps(unwrapped).encode("utf-8")
            else:
                self._unwrapped_content = raw_content
        except json.JSONDecodeError:
            self._unwrapped_content = raw_content

    @property
    def content(self) -> bytes:
        """Return unwrapped content."""
        return self._unwrapped_content

    @property
    def text(self) -> str:
        """Return unwrapped content as text."""
        return self._unwrapped_content.decode("utf-8")

    def json(self) -> Any:
        """Parse and return unwrapped JSON."""
        return json.loads(self._unwrapped_content)

    async def aread(self) -> bytes:
        """Return unwrapped content."""
        return self._unwrapped_content

    def read(self) -> bytes:
        """Return unwrapped content."""
        return self._unwrapped_content


class UnwrappedSSEResponse(httpx.Response):
    """A response wrapper that unwraps Antigravity SSE format."""

    def __init__(self, original_response: httpx.Response):
        # Copy all attributes from original
        self.__dict__.update(original_response.__dict__)
        self._original = original_response

    async def aiter_lines(self):
        """Iterate over SSE lines, unwrapping Antigravity format."""
        async for line in self._original.aiter_lines():
            if line.startswith("data: "):
                try:
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str.strip() == "[DONE]":
                        yield line
                        continue

                    data = json.loads(data_str)

                    # Unwrap Antigravity format: {"response": {...}} -> {...}
                    if "response" in data:
                        unwrapped = data["response"]
                        yield f"data: {json.dumps(unwrapped)}"
                    else:
                        yield line
                except json.JSONDecodeError:
                    yield line
            else:
                yield line

    async def aiter_text(self, chunk_size: int | None = None):
        """Iterate over response text, unwrapping Antigravity format for SSE."""
        buffer = ""
        async for chunk in self._original.aiter_text(chunk_size):
            buffer += chunk

            # Process complete lines
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)

                if line.startswith("data: "):
                    try:
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            yield line + "\n"
                            continue

                        data = json.loads(data_str)

                        # Unwrap Antigravity format
                        if "response" in data:
                            unwrapped = data["response"]
                            yield f"data: {json.dumps(unwrapped)}\n"
                        else:
                            yield line + "\n"
                    except json.JSONDecodeError:
                        yield line + "\n"
                else:
                    yield line + "\n"

        # Yield any remaining data
        if buffer:
            yield buffer

    async def aiter_bytes(self, chunk_size: int | None = None):
        """Iterate over response bytes, unwrapping Antigravity format for SSE."""
        async for text_chunk in self.aiter_text(chunk_size):
            yield text_chunk.encode("utf-8")


class AntigravityClient(httpx.AsyncClient):
    """Custom httpx client that handles Antigravity request/response wrapping."""

    def __init__(
        self,
        project_id: str = "",
        model_name: str = "",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.project_id = project_id
        self.model_name = model_name

    def _wrap_request(self, content: bytes, url: str) -> tuple[bytes, str, str]:
        """Wrap request body in Antigravity envelope and transform URL.

        Returns: (wrapped_content, new_path, new_query)
        """
        try:
            original_body = json.loads(content)

            # Extract model name from URL
            model = self.model_name
            if "/models/" in url:
                parts = url.split("/models/")[-1]
                model = parts.split(":")[0] if ":" in parts else model

            # Transform Claude model names: remove tier suffix, it goes in thinkingBudget
            # claude-sonnet-4-5-thinking-low -> claude-sonnet-4-5-thinking
            # claude-opus-4-5-thinking-high -> claude-opus-4-5-thinking
            claude_tier = None
            if "claude" in model and "-thinking-" in model:
                for tier in ["low", "medium", "high"]:
                    if model.endswith(f"-{tier}"):
                        claude_tier = tier
                        model = model.rsplit(f"-{tier}", 1)[0]  # Remove tier suffix
                        break

            # Use default project_id if not set
            effective_project_id = self.project_id or ANTIGRAVITY_DEFAULT_PROJECT_ID

            # Generate unique IDs (matching OpenCode's format)
            request_id = f"agent-{uuid.uuid4()}"
            session_id = f"-{uuid.uuid4()}:{model}:{effective_project_id}:seed-{uuid.uuid4().hex[:16]}"

            # Add sessionId to inner request (required by Antigravity)
            if isinstance(original_body, dict):
                original_body["sessionId"] = session_id

                # Fix systemInstruction - remove "role" field (Antigravity doesn't want it)
                sys_instruction = original_body.get("systemInstruction", {})
                if isinstance(sys_instruction, dict) and "role" in sys_instruction:
                    del sys_instruction["role"]

                # Fix tools - rename parameters_json_schema to parameters and inline $refs
                tools = original_body.get("tools", [])
                if isinstance(tools, list):
                    for tool in tools:
                        if isinstance(tool, dict) and "functionDeclarations" in tool:
                            for func_decl in tool["functionDeclarations"]:
                                if isinstance(func_decl, dict):
                                    # Rename parameters_json_schema to parameters
                                    if "parameters_json_schema" in func_decl:
                                        func_decl["parameters"] = func_decl.pop(
                                            "parameters_json_schema"
                                        )

                                    # Inline $refs and remove $defs from parameters
                                    # Convert unions (anyOf->any_of) only for Gemini
                                    # Simplify schemas for Claude (no anyOf, no additionalProperties)
                                    if "parameters" in func_decl:
                                        is_gemini = "gemini" in model.lower()
                                        is_claude = "claude" in model.lower()
                                        func_decl["parameters"] = _inline_refs(
                                            func_decl["parameters"],
                                            convert_unions=is_gemini,
                                            simplify_for_claude=is_claude,
                                        )

                # Fix generationConfig for Antigravity compatibility
                gen_config = original_body.get("generationConfig", {})
                if isinstance(gen_config, dict):
                    # Remove responseModalities - Antigravity doesn't support it!
                    if "responseModalities" in gen_config:
                        del gen_config["responseModalities"]

                    # Add thinkingConfig for Gemini 3 models (uses thinkingLevel string)
                    if "gemini-3" in model:
                        # Extract thinking level from model name (e.g., gemini-3-pro-high -> high)
                        thinking_level = "medium"  # default
                        if model.endswith("-low"):
                            thinking_level = "low"
                        elif model.endswith("-high"):
                            thinking_level = "high"

                        gen_config["thinkingConfig"] = {
                            "includeThoughts": True,
                            "thinkingLevel": thinking_level,
                        }

                    # Add thinkingConfig for Claude thinking models (uses thinkingBudget number)
                    elif claude_tier and "thinking" in model:
                        # Claude thinking budgets by tier
                        claude_budgets = {"low": 8192, "medium": 16384, "high": 32768}
                        thinking_budget = claude_budgets.get(claude_tier, 8192)

                        gen_config["thinkingConfig"] = {
                            "includeThoughts": True,
                            "thinkingBudget": thinking_budget,
                        }

                    # Add topK and topP if not present (OpenCode uses these)
                    if "topK" not in gen_config:
                        gen_config["topK"] = 64
                    if "topP" not in gen_config:
                        gen_config["topP"] = 0.95

                    # Set maxOutputTokens to 64000 for all models
                    # This ensures it's always > thinkingBudget for thinking models
                    gen_config["maxOutputTokens"] = 64000

                    original_body["generationConfig"] = gen_config

            # Wrap in Antigravity envelope
            wrapped_body = {
                "project": effective_project_id,
                "model": model,
                "request": original_body,
                "userAgent": "antigravity",
                "requestId": request_id,
            }

            # Transform URL to Antigravity format
            new_path = url
            new_query = ""
            if ":streamGenerateContent" in url:
                new_path = "/v1internal:streamGenerateContent"
                new_query = "alt=sse"
            elif ":generateContent" in url:
                new_path = "/v1internal:generateContent"

            return json.dumps(wrapped_body).encode(), new_path, new_query

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to wrap request: %s", e)
            return content, url, ""

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        """Override send to intercept at the lowest level with endpoint fallback."""
        # Transform POST requests to Antigravity format
        if request.method == "POST" and request.content:
            new_content, new_path, new_query = self._wrap_request(
                request.content, str(request.url.path)
            )
            if new_path != str(request.url.path):
                # Remove SDK headers that we need to override (case-insensitive)
                headers_to_remove = {
                    "content-length",
                    "user-agent",
                    "x-goog-api-client",
                    "x-goog-api-key",
                    "client-metadata",
                    "accept",
                }
                new_headers = {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in headers_to_remove
                }

                # Add Antigravity headers (matching OpenCode exactly)
                new_headers["user-agent"] = "antigravity/1.11.5 windows/amd64"
                new_headers["x-goog-api-client"] = (
                    "google-cloud-sdk vscode_cloudshelleditor/0.1"
                )
                new_headers["client-metadata"] = (
                    '{"ideType":"IDE_UNSPECIFIED","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}'
                )
                new_headers["x-goog-api-key"] = ""  # Must be present but empty!
                new_headers["accept"] = "text/event-stream"

                # Try each endpoint in fallback order
                last_response = None

                # Check for rate limit
                import asyncio

                # Try endpoints logic...
                max_retries = 3

                for attempt in range(max_retries):
                    for endpoint in ANTIGRAVITY_ENDPOINT_FALLBACKS:
                        # Build URL with current endpoint
                        new_url = httpx.URL(
                            scheme="https",
                            host=endpoint.replace("https://", ""),
                            path=new_path,
                            query=new_query.encode() if new_query else b"",
                        )

                        req = httpx.Request(
                            method=request.method,
                            url=new_url,
                            headers=new_headers,
                            content=new_content,
                        )

                        response = await super().send(req, **kwargs)
                        last_response = response

                        # Handle rate limit (429)
                        if response.status_code == 429:
                            try:
                                # Need to read response to get reset time
                                await response.aread()
                                error_data = json.loads(response.content)

                                # Extract reset delay from metadata
                                reset_delay = 2.0  # Default fallback
                                if isinstance(error_data, dict):
                                    error_info = error_data.get("error", {})
                                    if isinstance(error_info, dict):
                                        details = error_info.get("details", [])
                                        for detail in details:
                                            metadata = detail.get("metadata", {})
                                            if "quotaResetDelay" in metadata:
                                                delay_str = metadata["quotaResetDelay"]
                                                if delay_str.endswith("s"):
                                                    reset_delay = float(delay_str[:-1])
                                                break

                                # Only retry if delay is reasonable (< 60s)
                                if reset_delay < 60:
                                    # Add small buffer
                                    wait_time = reset_delay + 0.5
                                    from code_puppy.messaging import emit_warning

                                    emit_warning(
                                        f"⏳ Rate limited on {endpoint}. Waiting {wait_time:.1f}s..."
                                    )
                                    await asyncio.sleep(wait_time)
                                    continue  # Retry same endpoint
                                else:
                                    emit_warning(
                                        f"❌ Rate limit reset too long ({reset_delay}s). Aborting."
                                    )
                                    return UnwrappedResponse(response)
                            except Exception:
                                pass  # Failed to parse error, treat as normal error

                        # Retry on 403, 404, 5xx errors
                        if (
                            response.status_code in (403, 404)
                            or response.status_code >= 500
                        ):
                            logger.debug(
                                "Endpoint %s returned %d, trying next...",
                                endpoint,
                                response.status_code,
                            )
                            continue

                        # Success or non-retriable error
                        # Wrap response to unwrap Antigravity format
                        if "alt=sse" in new_query:
                            return UnwrappedSSEResponse(response)

                        # Non-streaming also needs unwrapping!
                        # Must read response before wrapping (async requirement)
                        await response.aread()
                        return UnwrappedResponse(response)

                # All endpoints failed, return last response
                if last_response and last_response.status_code == 429:
                    await last_response.aread()
                    return UnwrappedResponse(last_response)

                return last_response

        return await super().send(request, **kwargs)


def create_antigravity_client(
    access_token: str,
    project_id: str = "",
    model_name: str = "",
    base_url: str = "https://daily-cloudcode-pa.sandbox.googleapis.com",
    headers: Optional[Dict[str, str]] = None,
) -> AntigravityClient:
    """Create an httpx client configured for Antigravity API."""
    # Start with Antigravity-specific headers
    default_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        **ANTIGRAVITY_HEADERS,
    }
    if headers:
        default_headers.update(headers)

    return AntigravityClient(
        project_id=project_id,
        model_name=model_name,
        base_url=base_url,
        headers=default_headers,
        timeout=httpx.Timeout(180.0, connect=30.0),
    )
