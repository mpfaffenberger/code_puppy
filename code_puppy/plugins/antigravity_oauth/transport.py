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


def _flatten_union_to_object(union_items: list, defs: dict, resolve_fn) -> dict:
    """Flatten a union of object types into a single object with all properties.

    For discriminated unions like EditFilePayload (ContentPayload | ReplacementsPayload | DeleteSnippetPayload),
    we merge all object types into one with all properties marked as optional.
    """
    merged_properties = {}
    has_string_type = False

    for item in union_items:
        if not isinstance(item, dict):
            continue

        # Resolve $ref first
        if "$ref" in item:
            ref_path = item["$ref"]
            ref_name = None
            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path[8:]
            elif ref_path.startswith("#/definitions/"):
                ref_name = ref_path[14:]
            if ref_name and ref_name in defs:
                item = copy.deepcopy(defs[ref_name])
            else:
                continue

        # Check for string type (common fallback)
        if item.get("type") == "string":
            has_string_type = True
            continue

        # Skip null types
        if item.get("type") == "null":
            continue

        # Merge properties from object types
        if item.get("type") == "object" or "properties" in item:
            props = item.get("properties", {})
            for prop_name, prop_schema in props.items():
                if prop_name not in merged_properties:
                    # Resolve the property schema
                    merged_properties[prop_name] = resolve_fn(
                        copy.deepcopy(prop_schema)
                    )

    if not merged_properties:
        # No object properties found, return string type as fallback
        return {"type": "string"} if has_string_type else {"type": "object"}

    # Build merged object - no required fields since any subset is valid
    result = {
        "type": "object",
        "properties": merged_properties,
    }

    return result


def _inline_refs(schema: dict, simplify_unions: bool = False) -> dict:
    """Inline $ref references and transform schema for Antigravity compatibility.

    - Inlines $ref references
    - Removes $defs, definitions, $schema, $id
    - Removes unsupported fields like 'default', 'examples', 'const'
    - When simplify_unions=True: flattens anyOf/oneOf unions:
      - For unions of objects: merges into single object with all properties
      - For simple unions (string | null): picks first non-null type
      (required for both Gemini AND Claude - neither supports union types in function schemas!)

    Args:
        simplify_unions: If True, simplify anyOf/oneOf unions.
                         Required for Gemini and Claude models.
    """
    if not isinstance(schema, dict):
        return schema

    # Make a deep copy to avoid modifying original
    schema = copy.deepcopy(schema)

    # Extract $defs for reference resolution
    defs = schema.pop("$defs", schema.pop("definitions", {}))

    def resolve_refs(obj, simplify_unions=simplify_unions):
        """Recursively resolve $ref references and transform schema."""
        if isinstance(obj, dict):
            # Handle anyOf/oneOf unions
            if simplify_unions:
                for union_key in ["anyOf", "oneOf"]:
                    if union_key in obj:
                        union = obj[union_key]
                        if isinstance(union, list):
                            # Check if this is a complex union of objects (discriminated union)
                            # vs a simple nullable type (string | null)
                            object_count = 0
                            has_refs = False
                            for item in union:
                                if isinstance(item, dict):
                                    if "$ref" in item:
                                        has_refs = True
                                        object_count += 1
                                    elif (
                                        item.get("type") == "object"
                                        or "properties" in item
                                    ):
                                        object_count += 1

                            # If multiple objects or has refs, flatten to single object
                            if object_count > 1 or has_refs:
                                flattened = _flatten_union_to_object(
                                    union, defs, resolve_refs
                                )
                                # Keep description if present
                                if "description" in obj:
                                    flattened["description"] = obj["description"]
                                return flattened

                            # Simple union - pick first non-null type
                            for item in union:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") != "null"
                                ):
                                    result = dict(item)
                                    if "description" in obj:
                                        result["description"] = obj["description"]
                                    return resolve_refs(result, simplify_unions)

            # Also handle allOf by merging all schemas
            if simplify_unions and "allOf" in obj:
                all_of = obj["allOf"]
                if isinstance(all_of, list):
                    merged = {}
                    merged_properties = {}
                    for item in all_of:
                        if isinstance(item, dict):
                            resolved_item = resolve_refs(item, simplify_unions)
                            # Deep merge properties dicts
                            if "properties" in resolved_item:
                                merged_properties.update(
                                    resolved_item.pop("properties")
                                )
                            merged.update(resolved_item)
                    if merged_properties:
                        merged["properties"] = merged_properties
                    # Keep other fields from original object (except allOf)
                    for k, v in obj.items():
                        if k != "allOf":
                            merged[k] = v
                    return resolve_refs(merged, simplify_unions)

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

                # Skip additionalProperties (not supported by Gemini or Claude)
                if simplify_unions and key == "additionalProperties":
                    continue

                # Skip any remaining union type keys that weren't simplified above
                # (This shouldn't happen normally, but just in case)
                if simplify_unions and key in ("anyOf", "oneOf", "allOf"):
                    continue

                result[key] = resolve_refs(value, simplify_unions)
            return result
        elif isinstance(obj, list):
            return [resolve_refs(item, simplify_unions) for item in obj]
        else:
            return obj

    return resolve_refs(schema, simplify_unions)


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
    """Custom httpx client that handles Antigravity request/response wrapping.

    Supports proactive token refresh to prevent expiry during long sessions.
    """

    def __init__(
        self,
        project_id: str = "",
        model_name: str = "",
        refresh_token: str = "",
        expires_at: Optional[float] = None,
        on_token_refreshed: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.project_id = project_id
        self.model_name = model_name
        self._refresh_token = refresh_token
        self._expires_at = expires_at
        self._on_token_refreshed = on_token_refreshed
        self._refresh_lock = None  # Lazy init for async lock

    async def _ensure_valid_token(self) -> None:
        """Proactively refresh the access token if it's expired or about to expire.

        This prevents 401 errors during long-running sessions by checking and
        refreshing the token BEFORE making requests, not after they fail.
        """
        import asyncio

        from .token import is_token_expired, refresh_access_token

        # Skip if no refresh token configured
        if not self._refresh_token:
            return

        # Check if token needs refresh (includes 60-second buffer)
        if not is_token_expired(self._expires_at):
            return

        # Lazy init the async lock
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()

        async with self._refresh_lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            if not is_token_expired(self._expires_at):
                return

            logger.debug("Proactively refreshing Antigravity access token...")

            try:
                # Run the synchronous refresh in a thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                new_tokens = await loop.run_in_executor(
                    None, refresh_access_token, self._refresh_token
                )

                if new_tokens:
                    # Update internal state
                    new_access_token = new_tokens.access_token
                    self._expires_at = new_tokens.expires_at
                    self._refresh_token = new_tokens.refresh_token

                    # Update the Authorization header
                    self.headers["Authorization"] = f"Bearer {new_access_token}"

                    logger.info(
                        "Proactively refreshed Antigravity token (expires in %ds)",
                        int(self._expires_at - __import__("time").time()),
                    )

                    # Notify callback (e.g., to persist updated tokens)
                    if self._on_token_refreshed:
                        try:
                            self._on_token_refreshed(new_tokens)
                        except Exception as e:
                            logger.warning("Token refresh callback failed: %s", e)
                else:
                    logger.warning(
                        "Failed to proactively refresh token - request may fail with 401"
                    )

            except Exception as e:
                logger.warning("Proactive token refresh error: %s", e)

    def _wrap_request(self, content: bytes, url: str) -> tuple[bytes, str, str, bool]:
        """Wrap request body in Antigravity envelope and transform URL.

        Returns: (wrapped_content, new_path, new_query, is_claude_thinking)
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
                                    # Simplify union types (anyOf/oneOf/allOf) for BOTH Gemini and Claude
                                    # Neither API supports union types in function schemas!
                                    if "parameters" in func_decl:
                                        is_gemini = "gemini" in model.lower()
                                        is_claude = "claude" in model.lower()
                                        func_decl["parameters"] = _inline_refs(
                                            func_decl["parameters"],
                                            simplify_unions=(is_gemini or is_claude),
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
                "requestType": "agent",
            }

            # Transform URL to Antigravity format
            new_path = url
            new_query = ""
            if ":streamGenerateContent" in url:
                new_path = "/v1internal:streamGenerateContent"
                new_query = "alt=sse"
            elif ":generateContent" in url:
                new_path = "/v1internal:generateContent"

            # Determine if this is a Claude thinking model (for interleaved thinking header)
            is_claude_thinking = (
                "claude" in model.lower() and "thinking" in model.lower()
            )

            return (
                json.dumps(wrapped_body).encode(),
                new_path,
                new_query,
                is_claude_thinking,
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to wrap request: %s", e)
            return content, url, "", False

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        """Override send to intercept at the lowest level with endpoint fallback."""
        import asyncio

        # Proactively refresh token BEFORE making the request
        await self._ensure_valid_token()

        # Transform POST requests to Antigravity format
        if request.method == "POST" and request.content:
            new_content, new_path, new_query, is_claude_thinking = self._wrap_request(
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

                # Add anthropic-beta header for Claude thinking models (interleaved thinking)
                # This enables real-time streaming of thinking tokens between tool calls
                if is_claude_thinking:
                    interleaved_header = "interleaved-thinking-2025-05-14"
                    existing = new_headers.get("anthropic-beta", "")
                    if existing:
                        if interleaved_header not in existing:
                            new_headers["anthropic-beta"] = (
                                f"{existing},{interleaved_header}"
                            )
                    else:
                        new_headers["anthropic-beta"] = interleaved_header

                # Try each endpoint with rate limit retry logic
                last_response = None
                max_rate_limit_retries = 5  # Max retries for 429s per endpoint

                for endpoint in ANTIGRAVITY_ENDPOINT_FALLBACKS:
                    # Build URL with current endpoint
                    new_url = httpx.URL(
                        scheme="https",
                        host=endpoint.replace("https://", ""),
                        path=new_path,
                        query=new_query.encode() if new_query else b"",
                    )

                    # Retry loop for rate limits on this endpoint
                    for rate_limit_attempt in range(max_rate_limit_retries):
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
                            wait_time = await self._extract_rate_limit_delay(response)

                            if wait_time is not None and wait_time < 60:
                                # Add small buffer to wait time
                                wait_time = wait_time + 0.1
                                try:
                                    from code_puppy.messaging import emit_warning

                                    emit_warning(
                                        f"⏳ Rate limited (attempt {rate_limit_attempt + 1}/{max_rate_limit_retries}). "
                                        f"Waiting {wait_time:.2f}s..."
                                    )
                                except ImportError:
                                    logger.warning(
                                        "Rate limited, waiting %.2fs...", wait_time
                                    )

                                await asyncio.sleep(wait_time)
                                continue  # Retry same endpoint
                            else:
                                # Wait time too long or couldn't parse, try next endpoint
                                logger.debug(
                                    "Rate limit wait too long (%.1fs) on %s, trying next endpoint...",
                                    wait_time or 0,
                                    endpoint,
                                )
                                break  # Break inner loop, try next endpoint

                        # Retry on 403, 404, 5xx errors - try next endpoint
                        if (
                            response.status_code in (403, 404)
                            or response.status_code >= 500
                        ):
                            logger.debug(
                                "Endpoint %s returned %d, trying next...",
                                endpoint,
                                response.status_code,
                            )
                            break  # Try next endpoint

                        # Success or non-retriable error (4xx except 429)
                        # Wrap response to unwrap Antigravity format
                        if "alt=sse" in new_query:
                            return UnwrappedSSEResponse(response)

                        # Non-streaming also needs unwrapping!
                        # Must read response before wrapping (async requirement)
                        await response.aread()
                        return UnwrappedResponse(response)

                # All endpoints/retries exhausted, return last response
                if last_response:
                    # Ensure response is read for proper error handling
                    if not last_response.is_stream_consumed:
                        try:
                            await last_response.aread()
                        except Exception:
                            pass
                    return UnwrappedResponse(last_response)

        return await super().send(request, **kwargs)

    async def _extract_rate_limit_delay(self, response: httpx.Response) -> float | None:
        """Extract the retry delay from a 429 rate limit response.

        Parses the Antigravity/Google API error format to find:
        - retryDelay from RetryInfo (e.g., "0.088325827s")
        - quotaResetDelay from ErrorInfo metadata (e.g., "88.325827ms")

        Returns the delay in seconds, or None if parsing fails.
        """
        try:
            # Read response body if not already read
            if not response.is_stream_consumed:
                await response.aread()

            error_data = json.loads(response.content)

            if not isinstance(error_data, dict):
                return 2.0  # Default fallback

            error_info = error_data.get("error", {})
            if not isinstance(error_info, dict):
                return 2.0

            details = error_info.get("details", [])
            if not isinstance(details, list):
                return 2.0

            # Look for RetryInfo first (most precise)
            for detail in details:
                if not isinstance(detail, dict):
                    continue

                detail_type = detail.get("@type", "")

                # Check for RetryInfo (e.g., "0.088325827s")
                if "RetryInfo" in detail_type:
                    retry_delay = detail.get("retryDelay", "")
                    parsed = self._parse_duration(retry_delay)
                    if parsed is not None:
                        return parsed

                # Check for ErrorInfo with quotaResetDelay in metadata
                if "ErrorInfo" in detail_type:
                    metadata = detail.get("metadata", {})
                    if isinstance(metadata, dict):
                        quota_delay = metadata.get("quotaResetDelay", "")
                        parsed = self._parse_duration(quota_delay)
                        if parsed is not None:
                            return parsed

            return 2.0  # Default if no delay found

        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Failed to parse rate limit response: %s", e)
            return 2.0  # Default fallback

    def _parse_duration(self, duration_str: str) -> float | None:
        """Parse a duration string like '0.088s' or '88.325827ms' to seconds."""
        if not duration_str or not isinstance(duration_str, str):
            return None

        duration_str = duration_str.strip()

        try:
            # Handle milliseconds (e.g., "88.325827ms")
            if duration_str.endswith("ms"):
                return float(duration_str[:-2]) / 1000.0

            # Handle seconds (e.g., "0.088325827s")
            if duration_str.endswith("s"):
                return float(duration_str[:-1])

            # Try parsing as raw number (assume seconds)
            return float(duration_str)

        except ValueError:
            return None


# Type alias for token refresh callback
TokenRefreshCallback = Any  # Callable[[OAuthTokens], None]


def create_antigravity_client(
    access_token: str,
    project_id: str = "",
    model_name: str = "",
    base_url: str = "https://daily-cloudcode-pa.sandbox.googleapis.com",
    headers: Optional[Dict[str, str]] = None,
    refresh_token: str = "",
    expires_at: Optional[float] = None,
    on_token_refreshed: Optional[TokenRefreshCallback] = None,
) -> AntigravityClient:
    """Create an httpx client configured for Antigravity API.

    Args:
        access_token: The OAuth access token for authentication
        project_id: The GCP project ID
        model_name: The model name being used
        base_url: The API base URL
        headers: Additional headers to include
        refresh_token: The OAuth refresh token for proactive token refresh
        expires_at: Unix timestamp when the access token expires
        on_token_refreshed: Callback called when token is proactively refreshed,
                           receives OAuthTokens object to persist the new tokens

    Returns:
        An AntigravityClient configured for API requests with proactive token refresh
    """
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
        refresh_token=refresh_token,
        expires_at=expires_at,
        on_token_refreshed=on_token_refreshed,
        base_url=base_url,
        headers=default_headers,
        timeout=httpx.Timeout(180.0, connect=30.0),
    )
