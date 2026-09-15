"""vLLM ``/add_model`` path: point at a server, list its models, pick one.

vLLM (and any OpenAI-compatible server) exposes ``GET {base}/v1/models``.
This module turns that into a first-class provider option in the model
browser: prompt for the base URL, query the endpoint, let the user choose a
served model, then persist a ``custom_openai`` entry pointing at
``{base}/v1``.

Kept out of :mod:`code_puppy.command_line.add_model_menu` (already near the
600-line cap); it reuses that module's generic ``extra_models.json`` writer
and TextInput helper via lazy imports to avoid an import cycle.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import httpx

from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.provider_credentials import (
    credential_display,
    credential_env_var_names,
    get_credential_value,
    is_credential_set,
    save_credential,
)

# Persisted provider identity + default credential env var for vLLM models.
VLLM_PROVIDER_ID = "vllm"
VLLM_API_KEY_ENV = "VLLM_API_KEY"
# vLLM ignores the key when started without --api-key, but the OpenAI SDK
# refuses to build a client without *some* value; this is the documented
# placeholder vLLM itself prints in its curl examples.
VLLM_PLACEHOLDER_API_KEY = "EMPTY"

_FETCH_TIMEOUT_S = 10.0
_MODEL_SUFFIXES = ("/v1/models", "/models", "/v1")

# API-key menu sentinels; anything else selected is a saved env var name.
_KEY_NONE = "__no_key__"
_KEY_NEW = "__new_key__"


class VllmFetchError(Exception):
    """Raised when the vLLM ``/v1/models`` endpoint cannot be read."""


def normalize_base_url(text: str) -> str:
    """Trim a user-entered vLLM URL down to ``scheme://host[:port]``.

    Tolerates ``http://host:8000``, a trailing slash, and URLs that already
    carry ``/v1`` or even ``/v1/models`` -- those suffixes are stripped so we
    can rebuild the exact endpoints we need without doubling them up.
    """
    url = (text or "").strip().rstrip("/")
    for suffix in _MODEL_SUFFIXES:
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


def openai_endpoint(base_url: str) -> str:
    """The OpenAI-compatible base (``{base}/v1``) stored in the model config."""
    return f"{normalize_base_url(base_url)}/v1"


def models_endpoint(base_url: str) -> str:
    """The ``/v1/models`` listing endpoint for a vLLM base URL."""
    return f"{openai_endpoint(base_url)}/models"


def _is_http_url(text: str) -> bool:
    return normalize_base_url(text).startswith(("http://", "https://"))


def resolve_api_key_ref(api_key_ref: str) -> Optional[str]:
    """The secret behind a ``custom_endpoint.api_key`` value, or None.

    ``$ENV`` resolves through the credential store; the ``EMPTY`` placeholder
    (or anything blank) means "send no Authorization header".
    """
    if not api_key_ref or api_key_ref == VLLM_PLACEHOLDER_API_KEY:
        return None
    if api_key_ref.startswith("$"):
        return get_credential_value(api_key_ref[1:])
    return api_key_ref


def fetch_vllm_model_ids(
    base_url: str,
    *,
    api_key: Optional[str] = None,
    http_get: Optional[Callable] = None,
) -> List[str]:
    """Query ``{base}/v1/models`` and return the served model ids.

    ``api_key`` is sent as a bearer token when given (servers started with
    ``--api-key`` gate the listing too). ``http_get`` is injectable for tests.
    Raises :class:`VllmFetchError` on any transport error, non-2xx status,
    non-JSON body, or unexpected shape.
    """
    url = models_endpoint(base_url)
    getter = http_get or httpx.get
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = getter(url, timeout=_FETCH_TIMEOUT_S, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise VllmFetchError(str(exc)) from exc
    except ValueError as exc:  # body was not valid JSON
        raise VllmFetchError(str(exc)) from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise VllmFetchError("response has no 'data' list")
    ids: List[str] = []
    for entry in data:
        model_id = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(model_id, str) and model_id.strip():
            ids.append(model_id.strip())
    return ids


def build_vllm_model_config(model_id: str, base_url: str, api_key_ref: str) -> dict:
    """A Code Puppy ``custom_openai`` config for one vLLM model.

    ``api_key_ref`` is either ``$VLLM_API_KEY`` (a real key was supplied) or
    the literal :data:`VLLM_PLACEHOLDER_API_KEY` for an unauthenticated server.
    """
    return {
        "type": "custom_openai",
        "provider": VLLM_PROVIDER_ID,
        "name": model_id,
        "custom_endpoint": {
            "url": openai_endpoint(base_url),
            "api_key": api_key_ref,
        },
        "supported_settings": ["temperature", "seed", "top_p"],
    }


# -- UI -----------------------------------------------------------------------


def vllm_model_details(base_url: str, model_id: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    from code_puppy.command_line.tui_style import menu_style

    style = menu_style()
    head = getattr(style, "head", "cyan") if style else "cyan"
    grey = getattr(style, "grey", "bright_black") if style else "bright_black"
    bright = getattr(style, "bright", "bright_white") if style else "bright_white"

    def ansi(color: str, text: str) -> str:
        return f"{fg_color(color)}{text}{RESET}"

    return "\n".join(
        [
            ansi(bright, "MODEL DETAILS"),
            "",
            ansi(head, model_id),
            ansi(grey, "vLLM (OpenAI-compatible)"),
            "",
            ansi(head, "Endpoint:"),
            ansi(grey, f"  {openai_endpoint(base_url)}"),
        ]
    )


def prompt_for_vllm_url(**overrides) -> Optional[str]:
    """Prompt for the vLLM base URL. Normalized URL, or ``None`` if cancelled."""
    from code_puppy.command_line.add_model_menu import _text_input

    result = (
        _text_input(
            t("model_menu.vllm.url_title"),
            prompt=t("model_menu.vllm.url_prompt"),
            placeholder="http://localhost:8000",
            validator=lambda text: (
                None if _is_http_url(text) else t("model_menu.vllm.url_invalid")
            ),
            footer_hint=t("model_menu.vllm.url_footer"),
            **overrides,
        )
        .build()
        .run()
    )
    if result.cancelled or not result.value:
        emit_warning(t("model_menu.vllm.cancelled"))
        return None
    return normalize_base_url(result.value)


def build_vllm_models_menu(base_url: str, model_ids: List[str], **overrides):
    """Searchable list of the models the server reported."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(model_id, value=model_id, description="vLLM") for model_id in model_ids
    ]
    builder = themed(
        MenuBuilder(t("model_menu.vllm.models_title"))
        .items(items)
        .searchable()
        .list_width(40)
        .alt_screen(False)
        .preview(lambda item: vllm_model_details(base_url, item.value))
        .footer_hint(t("model_menu.vllm.models_footer"))
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


# -- API key selection --------------------------------------------------------


def saved_credential_names() -> List[str]:
    """Every credential env var Code Puppy knows about that currently resolves.

    Keyring backends cannot enumerate, so "saved keys" is the union of the
    well-known provider vars and every configured model's ``$ENV`` reference,
    filtered to the ones that actually have a value right now.
    """
    return sorted(
        name for name in credential_env_var_names() if is_credential_set(name)
    )


def build_vllm_api_key_menu(saved: List[str], **overrides):
    """None / new key / one entry per saved credential."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(t("model_menu.vllm.api_key_none"), value=_KEY_NONE),
        MenuItem(t("model_menu.vllm.api_key_new"), value=_KEY_NEW),
    ]
    items += [
        MenuItem(name, value=name, description=credential_display(name))
        for name in saved
    ]
    builder = themed(
        MenuBuilder(t("model_menu.vllm.api_key_title"))
        .items(items)
        .searchable()
        .list_width(40)
        .alt_screen(False)
        .footer_hint(t("model_menu.vllm.api_key_menu_footer"))
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def prompt_for_new_vllm_api_key(**overrides) -> Optional[str]:
    """Prompt once, then save under the first unused VLLM_API_KEY<number>."""
    from code_puppy.command_line.add_model_menu import _text_input

    key_result = (
        _text_input(
            t("model_menu.vllm.api_key_title"),
            prompt=t("model_menu.vllm.api_key_prompt"),
            placeholder=t("model_menu.vllm.api_key_placeholder"),
            mask="*",
            footer_hint=t("model_menu.vllm.api_key_footer"),
            **overrides,
        )
        .build()
        .run()
    )
    if key_result.cancelled or not key_result.value.strip():
        return None

    # Check both configured references and stored values: an orphaned key
    # from a cancelled setup must not be overwritten either.
    reserved = credential_env_var_names()
    index = 0
    while True:
        env_var = f"{VLLM_API_KEY_ENV}{index}"
        if env_var not in reserved and not is_credential_set(env_var):
            break
        index += 1
    save_credential(env_var, key_result.value.strip())
    emit_info(t("model_menu.vllm.api_key_saved", env_var=env_var))
    return env_var


def choose_vllm_api_key(
    *,
    menu_factory: Callable = build_vllm_api_key_menu,
    new_key_prompt: Callable = prompt_for_new_vllm_api_key,
    saved: Optional[List[str]] = None,
) -> Optional[str]:
    """Return the ``custom_endpoint.api_key`` value to persist, or None if cancelled.

    ``$ENV_VAR`` for a saved or freshly entered key, the literal ``EMPTY``
    placeholder for an unauthenticated server.
    """
    saved_names = saved_credential_names() if saved is None else saved
    result = menu_factory(saved_names).run()
    if result.cancelled or result.item is None:
        return None
    choice = result.item.value
    if choice == _KEY_NONE:
        return VLLM_PLACEHOLDER_API_KEY
    if choice == _KEY_NEW:
        env_var = new_key_prompt()
        return f"${env_var}" if env_var else None
    emit_info(t("model_menu.vllm.api_key_using", env_var=choice))
    return f"${choice}"


def _auth_failure_hint(error_text: str, *, authenticated: bool) -> Optional[str]:
    """Translate a 401/403 on the listing into a next step for the user.

    vLLM (and the proxies people put in front of it) answer ``401`` when no
    credentials arrived and ``403`` when the credentials were wrong.
    """
    if "401" in error_text:
        return t(
            "model_menu.vllm.hint_401_authed"
            if authenticated
            else "model_menu.vllm.hint_401_anon"
        )
    if "403" in error_text:
        return t("model_menu.vllm.hint_403")
    return None


# -- orchestration ------------------------------------------------------------


def run_vllm_flow(
    *,
    url_prompt: Callable = prompt_for_vllm_url,
    fetch_models: Callable = fetch_vllm_model_ids,
    models_menu_factory: Callable = build_vllm_models_menu,
    api_key_prompt: Callable = choose_vllm_api_key,
) -> bool:
    """URL -> key (none/new/saved) -> /v1/models -> pick -> persist.

    The key comes *before* the listing because a server started with
    ``--api-key`` 401s on ``/v1/models`` too. Collaborators are injectable
    so tests can script every stage.
    """
    base_url = url_prompt()
    if not base_url:
        return False

    api_key_ref = api_key_prompt()
    if api_key_ref is None:
        emit_warning(t("model_menu.vllm.cancelled"))
        return False
    if api_key_ref == VLLM_PLACEHOLDER_API_KEY:
        emit_info(t("model_menu.vllm.no_auth", url=openai_endpoint(base_url)))

    api_key = resolve_api_key_ref(api_key_ref)
    if api_key_ref.startswith("$") and not api_key:
        # A chosen-but-empty saved key would silently go out unauthenticated
        # and surface as a baffling 401. Say so instead.
        emit_error(t("model_menu.vllm.api_key_empty", env_var=api_key_ref[1:]))
        return False

    listing = models_endpoint(base_url)
    try:
        model_ids = fetch_models(base_url, api_key=api_key)
    except VllmFetchError as exc:
        emit_error(t("model_menu.vllm.fetch_failed", url=listing, error=exc))
        hint = _auth_failure_hint(str(exc), authenticated=bool(api_key))
        if hint:
            emit_warning(hint)
        return False
    if not model_ids:
        emit_warning(t("model_menu.vllm.no_models", url=listing))
        return False

    result = models_menu_factory(base_url, model_ids).run()
    if result.cancelled or result.item is None:
        return False
    model_id = result.item.value

    from code_puppy.command_line.add_model_menu import add_config_to_extra_config
    from code_puppy.models_dev_parser import extra_model_key

    model_key = extra_model_key(VLLM_PROVIDER_ID, model_id)
    return add_config_to_extra_config(
        model_key, build_vllm_model_config(model_id, base_url, api_key_ref)
    )
