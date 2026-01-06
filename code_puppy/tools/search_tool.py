import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Optional
from urllib import error as url_error
from urllib import request as url_request

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import RunContext

from code_puppy.config import CACHE_DIR

SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "tavily")
DEFAULT_TIMEOUT_SECONDS = 10
CACHE_TTL_SECONDS = 3600
CACHE_SUBDIR = "search_cache"
MAX_RESULTS_LIMIT = 20
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.5
MAX_DOMAIN_LIST = 25
ALLOWED_DEPTHS = {"basic", "advanced"}
ALLOWED_TOPICS = {
    "general",
    "news",
    "finance",
    "health",
    "science",
    "sports",
    "technology",
}
ALLOWED_TIME_RANGES = {"day", "week", "month", "year", "d", "w", "m", "y"}


class SearchError(RuntimeError):
    """Base class for search-related errors."""


class MissingApiKey(SearchError):
    """Raised when the search API key is missing."""


class RateLimited(SearchError):
    """Raised when the provider rate limits requests."""


class UpstreamError(SearchError):
    """Raised for provider or network errors."""


class SearchResult(BaseModel):
    title: str = Field(..., description="The title of the search result")
    url: str = Field(..., description="The direct link to the content")
    snippet: str = Field(..., description="A short summary or snippet of the content")
    published: Optional[str] = Field(None, description="Publication date if available")
    score: Optional[float] = Field(None, description="Relevance score")


class SearchOutput(BaseModel):
    results: list[SearchResult]
    total: Optional[int] = None
    has_more: bool
    source: str


@dataclass(frozen=True, slots=True)
class SearchParams:
    max_results: int = 5
    safe_search: bool = True
    search_depth: str = "basic"
    topic: Optional[str] = None
    time_range: Optional[str] = None
    include_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    include_raw_content: bool = False
    include_images: bool = False
    include_answer: bool = False

    def to_cache_dict(self, query: str, provider: str) -> dict:
        payload = asdict(self)
        payload["query"] = query
        payload["provider"] = provider
        return payload

    def validated(self) -> "SearchParams":
        search_depth = (
            self.search_depth if self.search_depth in ALLOWED_DEPTHS else "basic"
        )
        topic = self.topic if self.topic in ALLOWED_TOPICS else None
        time_range = self.time_range if self.time_range in ALLOWED_TIME_RANGES else None

        return replace(
            self,
            max_results=_clamp_int(self.max_results, 1, MAX_RESULTS_LIMIT),
            search_depth=search_depth,
            topic=topic,
            time_range=time_range,
            include_domains=_sanitize_domains(self.include_domains),
            exclude_domains=_sanitize_domains(self.exclude_domains),
        )


def _normalize_query(query: str) -> str:
    return query.strip()


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _get_cache_dir() -> str:
    cache_dir = os.path.join(CACHE_DIR, CACHE_SUBDIR)
    os.makedirs(cache_dir, mode=0o700, exist_ok=True)
    return cache_dir


def _cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_cache(cache_key: str) -> Optional[SearchOutput]:
    cache_path = os.path.join(_get_cache_dir(), f"{cache_key}.json")
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
        created_at = payload.get("created_at")
        if created_at is None or (time.time() - created_at) > CACHE_TTL_SECONDS:
            return None
        return SearchOutput.model_validate(payload.get("data", {}))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _save_cache(cache_key: str, data: SearchOutput) -> None:
    cache_path = os.path.join(_get_cache_dir(), f"{cache_key}.json")
    payload = {"created_at": time.time(), "data": data.model_dump(mode="json")}
    try:
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file)
    except OSError as exc:
        logging.getLogger(__name__).debug("Cache write failed: %s", exc)
        return


def _request_json(url: str, payload: dict, timeout: int) -> dict:
    encoded = json.dumps(payload).encode("utf-8")
    req = url_request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_error: Optional[Exception] = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            with url_request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    return json.loads(body)
                except json.JSONDecodeError as exc:
                    last_error = UpstreamError(f"Invalid JSON from provider: {exc}")
                    break
        except url_error.HTTPError as exc:
            if exc.code == 429:
                last_error = RateLimited("Search rate limit exceeded.")
            elif 500 <= exc.code < 600:
                last_error = UpstreamError(f"Search provider error: {exc}")
            else:
                raise UpstreamError(f"Search provider error: {exc}") from exc
        except url_error.URLError as exc:
            last_error = UpstreamError(f"Search provider error: {exc}")

        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_BASE_DELAY_SECONDS * (2**attempt))

    if isinstance(last_error, SearchError):
        raise last_error
    raise UpstreamError("Search provider error.")


def _sanitize_domains(domains: Optional[list[str]]) -> list[str]:
    if not domains:
        return []
    cleaned: list[str] = []
    for domain in domains:
        domain = domain.strip().lower()
        if domain and domain not in cleaned:
            cleaned.append(domain)
        if len(cleaned) >= MAX_DOMAIN_LIST:
            break
    return cleaned


def _search_tavily(query: str, params: SearchParams) -> dict:
    api_key = os.environ.get("SEARCH_API_KEY")
    if not api_key:
        raise MissingApiKey("SEARCH_API_KEY environment variable not found.")

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": params.search_depth,
        "max_results": params.max_results,
        "include_answer": params.include_answer,
        "include_raw_content": params.include_raw_content,
        "include_images": params.include_images,
        "safe_search": params.safe_search,
    }

    if params.topic:
        payload["topic"] = params.topic
    if params.time_range:
        payload["time_range"] = params.time_range
    if params.include_domains:
        payload["include_domains"] = params.include_domains
    if params.exclude_domains:
        payload["exclude_domains"] = params.exclude_domains

    return _request_json(
        "https://api.tavily.com/search", payload, DEFAULT_TIMEOUT_SECONDS
    )


def _safe_build_result(item: dict) -> Optional[SearchResult]:
    if not item.get("title") or not item.get("url"):
        return None
    try:
        return SearchResult(
            title=item.get("title") or "",
            url=item.get("url") or "",
            snippet=item.get("content") or item.get("snippet") or "",
            published=item.get("published"),
            score=item.get("score"),
        )
    except ValidationError:
        return None


def _build_output(
    raw_results: list[dict],
    max_results: int,
    source: str,
) -> SearchOutput:
    results: list[SearchResult] = []
    for item in raw_results:
        result = _safe_build_result(item)
        if result:
            results.append(result)
        if len(results) >= max_results:
            break

    has_more = len(raw_results) > max_results
    return SearchOutput(
        results=results,
        total=len(raw_results),
        has_more=has_more,
        source=source,
    )


PROVIDERS = {
    "tavily": _search_tavily,
}


def _search_provider(query: str, params: SearchParams) -> dict:
    provider = PROVIDERS.get(SEARCH_PROVIDER)
    if not provider:
        raise UpstreamError(f"Unsupported search provider: {SEARCH_PROVIDER}")
    return provider(query, params)


def _search(
    _context: RunContext,
    query: str,
    params: SearchParams | None = None,
) -> SearchOutput:
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return SearchOutput(results=[], total=0, has_more=False, source="local")

    params = (params or SearchParams()).validated()

    cache_key = _cache_key(params.to_cache_dict(normalized_query, SEARCH_PROVIDER))
    cached = _load_cache(cache_key)
    if cached:
        return cached

    raw = _search_provider(normalized_query, params)
    raw_results = raw.get("results", []) if isinstance(raw, dict) else []
    output = _build_output(
        raw_results=raw_results,
        max_results=params.max_results,
        source=SEARCH_PROVIDER,
    )
    _save_cache(cache_key, output)
    return output


def register_search(agent) -> None:
    """Register the search tool."""

    @agent.tool
    def search(
        context: RunContext,
        query: str,
        max_results: int = 5,
        safe_search: bool = True,
        search_depth: str = "basic",
        topic: Optional[str] = None,
        time_range: Optional[str] = None,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        include_raw_content: bool = False,
        include_images: bool = False,
        include_answer: bool = False,
    ) -> SearchOutput:
        """Search the web and return structured results.

        Args:
            context: PydanticAI runtime context.
            query: Search query text.
            max_results: Max number of results returned (1-20).
            safe_search: Whether to enable safe search filtering.
            search_depth: "basic" or "advanced".
            topic: Optional topic hint (e.g. "news", "finance").
            time_range: Optional recency window (e.g. "day", "week").
            include_domains: Optional allowlist of domains.
            exclude_domains: Optional blocklist of domains.
            include_raw_content: Whether to request full content.
            include_images: Whether to request image results.
            include_answer: Whether to request a quick provider answer.

        Returns:
            SearchOutput with normalized results.
        """
        params = SearchParams(
            max_results=max_results,
            safe_search=safe_search,
            search_depth=search_depth,
            topic=topic,
            time_range=time_range,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            include_raw_content=include_raw_content,
            include_images=include_images,
            include_answer=include_answer,
        )
        return _search(
            context=context,
            query=query,
            params=params,
        )
