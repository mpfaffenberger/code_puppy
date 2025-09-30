"""Monkey patches for Walmart-specific URL redirections.

This module patches HTTP request libraries to redirect GitHub releases
to Walmart's internal artifactory mirror for camoufox and other tools.
"""

import functools
import os
import ssl
import urllib.request
from pathlib import Path

from code_puppy.messaging import emit_info

# URL transformation constants
GITHUB_BASE = "https://github.com/"
WALMART_ARTIFACTORY_BASE = "https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/"

# Alternative artifactory base URLs to try if primary fails
ALTERNATIVE_ARTIFACTORY_BASES = [
    "https://artifactory.walmart.com/artifactory/github-releases-generic-release-remote/",
    "https://artifacts.walmart.com/artifactory/github-releases-generic-release-remote/",
    "https://pypi.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/",
]

# Walmart proxy settings for DNS resolution
WALMART_PROXY_SETTINGS = {
    "HTTP_PROXY": "http://sysproxy.wal-mart.com:8080",
    "HTTPS_PROXY": "http://sysproxy.wal-mart.com:8080",
    "http_proxy": "http://sysproxy.wal-mart.com:8080",
    "https_proxy": "http://sysproxy.wal-mart.com:8080",
}

# Walmart internal domains that should skip SSL verification
WALMART_INTERNAL_DOMAINS = {
    "walmart.com",
    "wal-mart.com",
    "ci.artifacts.walmart.com",
    "pypi.ci.artifacts.walmart.com",
    "generic.ci.artifacts.walmart.com",
    "artifactory.walmart.com",
    "artifacts.walmart.com",
    "sysproxy.wal-mart.com",
}

# External domains that commonly have SSL issues behind corporate firewalls
# These will get unverified SSL context when behind corporate proxy
KNOWN_PROBLEMATIC_DOMAINS = {
    "github.com",
    "raw.githubusercontent.com",
    "api.github.com",
    "releases.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
}

# Track if patches have been applied
_patches_applied = False
_original_functions = {}


def set_proxy_environment():
    """Set proxy environment variables for DNS resolution in corporate environment."""
    for key, value in WALMART_PROXY_SETTINGS.items():
        if key not in os.environ:
            os.environ[key] = value
            emit_info(f"[dim]🌐 Set proxy env {key}={value}[/dim]")


def transform_github_url(url: str) -> str:
    """Transform GitHub release URLs to Walmart artifactory mirror.

    Args:
        url: Original URL that might be a GitHub release URL

    Returns:
        Transformed URL if it's a GitHub release, otherwise original URL

    Example:
        >>> transform_github_url("https://github.com/astral-sh/uv/releases/download/0.7.21/uv-aarch64-apple-darwin.tar.gz")
        "https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/astral-sh/uv/releases/download/0.7.21/uv-aarch64-apple-darwin.tar.gz"
    """
    if not isinstance(url, str):
        return url

    if url.startswith(GITHUB_BASE):
        # Set proxy environment for DNS resolution
        set_proxy_environment()

        # Replace the base GitHub URL with Walmart artifactory
        transformed_url = url.replace(GITHUB_BASE, WALMART_ARTIFACTORY_BASE, 1)
        emit_info(f"[cyan]🔀 Redirecting GitHub download:[/cyan] {url[:60]}...")
        emit_info(f"[cyan]   → Walmart mirror:[/cyan] {transformed_url[:60]}...")
        return transformed_url

    return url


def try_github_fallback(
    original_github_url: str, transformed_url: str, original_function, *args, **kwargs
):
    """Try original GitHub URL as fallback when all artifactory mirrors fail.

    Args:
        original_github_url: The original GitHub URL before transformation
        transformed_url: The transformed artifactory URL that failed
        original_function: The original HTTP function to call
        *args, **kwargs: Arguments to pass to the function

    Returns:
        Result of successful download or raises the last exception
    """
    if original_github_url and original_github_url.startswith(GITHUB_BASE):
        try:
            emit_info(
                "[yellow]🔄 All artifactory mirrors failed, trying original GitHub URL as fallback...[/yellow]"
            )
            emit_info(f"[cyan]   → Fallback: {original_github_url[:60]}...[/cyan]")

            # For requests-style calls where URL is first positional arg or in kwargs
            if len(args) > 0:
                # Replace the first argument (URL) with the original GitHub URL
                new_args = list(args)
                new_args[0] = original_github_url
                return original_function(*new_args, **kwargs)
            else:
                # For requests-style calls where URL might be passed directly
                return original_function(original_github_url, **kwargs)

        except Exception as fallback_e:
            emit_info(f"[red]❌ GitHub fallback also failed: {fallback_e}[/red]")
            raise
    else:
        raise ValueError(f"Not a GitHub URL: {original_github_url}")


def is_walmart_internal_url(url: str) -> bool:
    """Check if URL is to a Walmart internal domain that needs SSL verification disabled.

    Args:
        url: URL to check

    Returns:
        True if URL is to Walmart internal domain, False otherwise
    """
    if not isinstance(url, str):
        return False

    # Parse domain from URL
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check if domain ends with any of our internal domains
        return any(
            domain.endswith(internal_domain)
            for internal_domain in WALMART_INTERNAL_DOMAINS
        )
    except Exception:
        return False


def should_skip_ssl_verification(url: str) -> bool:
    """Check if URL should skip SSL verification due to corporate firewall issues.

    Args:
        url: URL to check

    Returns:
        True if SSL verification should be skipped, False otherwise
    """
    if not isinstance(url, str):
        return False

    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Skip SSL verification for Walmart internal domains
        if any(
            domain.endswith(internal_domain)
            for internal_domain in WALMART_INTERNAL_DOMAINS
        ):
            return True

        # Also skip for known problematic external domains when behind corporate proxy
        # This helps with browserforge and other external downloads
        if any(
            domain.endswith(problematic_domain)
            for problematic_domain in KNOWN_PROBLEMATIC_DOMAINS
        ):
            return True

        return False
    except Exception:
        return False


def get_ssl_context_for_url(url: str) -> ssl.SSLContext | None:
    """Get appropriate SSL context for URL, disabling verification for problematic domains.

    Args:
        url: URL to get SSL context for

    Returns:
        SSL context with verification disabled for problematic URLs, None for others
    """
    if should_skip_ssl_verification(url):
        # Create unverified SSL context for problematic domains
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # Try to load Walmart cert bundle if available for internal domains
        if is_walmart_internal_url(url):
            try:
                cert_path = Path(__file__).parent / "certs" / "walmart-bundle.pem"
                if cert_path.exists():
                    context.load_verify_locations(cert_path)
                    emit_info(
                        f"[dim]🔒 Using Walmart cert bundle for: {url[:50]}...[/dim]"
                    )
            except Exception as e:
                emit_info(f"[dim]⚠️  Could not load Walmart cert bundle: {e}[/dim]")
        else:
            emit_info(f"[dim]🔓 Skipping SSL verification for: {url[:50]}...[/dim]")

        return context

    return None  # Use default for other URLs


def patch_urllib_urlopen():
    """Patch urllib.request.urlopen to redirect GitHub URLs."""
    if "urllib_urlopen" in _original_functions:
        return  # Already patched

    original_urlopen = urllib.request.urlopen
    _original_functions["urllib_urlopen"] = original_urlopen

    @functools.wraps(original_urlopen)
    def patched_urlopen(url, data=None, timeout=None, *args, **kwargs):
        """Patched urlopen that transforms GitHub URLs and handles SSL for internal domains."""
        final_url = url
        original_github_url = None

        if isinstance(url, str):
            original_github_url = url if url.startswith(GITHUB_BASE) else None
            final_url = transform_github_url(url)
        elif hasattr(url, "full_url"):  # urllib.request.Request object
            original_github_url = (
                url.full_url if url.full_url.startswith(GITHUB_BASE) else None
            )
            url.full_url = transform_github_url(url.full_url)
            final_url = url.full_url
        elif hasattr(url, "get_full_url"):  # urllib.request.Request object
            original_url = url.get_full_url()
            original_github_url = (
                original_url if original_url.startswith(GITHUB_BASE) else None
            )
            transformed_url = transform_github_url(original_url)
            if transformed_url != original_url:
                # Create new request with transformed URL
                new_url = urllib.request.Request(
                    transformed_url,
                    data=url.data,
                    headers=url.headers,
                    origin_req_host=url.origin_req_host,
                    unverifiable=url.unverifiable,
                )
                url = new_url
            final_url = transformed_url

        # Add SSL context for problematic domains if not already provided
        if "context" not in kwargs:
            ssl_context = get_ssl_context_for_url(final_url)
            if ssl_context:
                kwargs["context"] = ssl_context

        # Try multiple artifactory URLs if DNS resolution fails
        if (
            isinstance(final_url, str)
            and "generic.ci.artifacts.walmart.com" in final_url
        ):
            # Try primary URL first
            try:
                return original_urlopen(url, data, timeout, *args, **kwargs)
            except (OSError, urllib.error.URLError) as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = final_url.replace(
                                WALMART_ARTIFACTORY_BASE, alt_base, 1
                            )
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )

                            if isinstance(url, str):
                                return original_urlopen(
                                    alt_url, data, timeout, *args, **kwargs
                                )
                            else:
                                # Update request object with alternative URL
                                if hasattr(url, "full_url"):
                                    url.full_url = alt_url
                                else:
                                    # Create new request with alternative URL
                                    url = urllib.request.Request(
                                        alt_url,
                                        data=url.data if hasattr(url, "data") else data,
                                        headers=url.headers
                                        if hasattr(url, "headers")
                                        else {},
                                    )
                                return original_urlopen(
                                    url, data, timeout, *args, **kwargs
                                )
                        except (OSError, urllib.error.URLError) as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url,
                                final_url,
                                original_urlopen,
                                url,
                                data,
                                timeout,
                                *args,
                                **kwargs,
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_urlopen(url, data, timeout, *args, **kwargs)

    urllib.request.urlopen = patched_urlopen


def patch_requests():
    """Patch requests library if available."""
    try:
        import requests
    except ImportError:
        return  # requests not available, skip

    if "requests_get" in _original_functions:
        return  # Already patched

    original_get = requests.get
    original_post = requests.post
    original_request = requests.request

    _original_functions["requests_get"] = original_get
    _original_functions["requests_post"] = original_post
    _original_functions["requests_request"] = original_request

    @functools.wraps(original_get)
    def patched_get(url, **kwargs):
        """Patched requests.get that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for requests.get: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_get(url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_get(alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url, url, original_get, **kwargs
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_get(url, **kwargs)

    @functools.wraps(original_post)
    def patched_post(url, **kwargs):
        """Patched requests.post that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for requests.post: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_post(url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_post(alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url, url, original_post, **kwargs
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_post(url, **kwargs)

    @functools.wraps(original_request)
    def patched_request(method, url, **kwargs):
        """Patched requests.request that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for requests.{method.lower()}: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_request(method, url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_request(method, alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url,
                                url,
                                original_request,
                                method,
                                **kwargs,
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_request(method, url, **kwargs)

    requests.get = patched_get
    requests.post = patched_post
    requests.request = patched_request


def patch_httpx():
    """Patch httpx library if available."""
    try:
        import httpx
    except ImportError:
        return  # httpx not available, skip

    if "httpx_get" in _original_functions:
        return  # Already patched

    original_get = httpx.get
    original_post = httpx.post
    original_request = httpx.request

    _original_functions["httpx_get"] = original_get
    _original_functions["httpx_post"] = original_post
    _original_functions["httpx_request"] = original_request

    @functools.wraps(original_get)
    def patched_get(url, **kwargs):
        """Patched httpx.get that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for httpx.get: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_get(url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_get(alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url, url, original_get, **kwargs
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_get(url, **kwargs)

    @functools.wraps(original_post)
    def patched_post(url, **kwargs):
        """Patched httpx.post that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for httpx.post: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_post(url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_post(alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url, url, original_post, **kwargs
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_post(url, **kwargs)

    @functools.wraps(original_request)
    def patched_request(method, url, **kwargs):
        """Patched httpx.request that transforms GitHub URLs and handles SSL for internal domains."""
        original_github_url = url if url.startswith(GITHUB_BASE) else None
        url = transform_github_url(url)

        # Disable SSL verification for problematic domains if not explicitly set
        if "verify" not in kwargs and should_skip_ssl_verification(url):
            kwargs["verify"] = False
            emit_info(
                f"[dim]🔓 Disabled SSL verification for httpx.{method.lower()}: {url[:50]}...[/dim]"
            )

        # Try multiple artifactory URLs if DNS resolution fails
        if "generic.ci.artifacts.walmart.com" in url:
            # Try primary URL first
            try:
                return original_request(method, url, **kwargs)
            except Exception as e:
                if "getaddrinfo failed" in str(e) or "Name or service not known" in str(
                    e
                ):
                    emit_info(
                        "[yellow]⚠️  DNS failed for primary artifactory, trying alternatives...[/yellow]"
                    )

                    # Try alternative artifactory URLs
                    for alt_base in ALTERNATIVE_ARTIFACTORY_BASES:
                        try:
                            alt_url = url.replace(WALMART_ARTIFACTORY_BASE, alt_base, 1)
                            emit_info(
                                f"[cyan]🔄 Trying alternative: {alt_url[:60]}...[/cyan]"
                            )
                            return original_request(method, alt_url, **kwargs)
                        except Exception as alt_e:
                            emit_info(f"[red]❌ Alternative failed: {alt_e}[/red]")
                            continue

                    # If all alternatives fail, try original GitHub URL as fallback
                    if original_github_url:
                        try:
                            return try_github_fallback(
                                original_github_url,
                                url,
                                original_request,
                                method,
                                **kwargs,
                            )
                        except Exception:
                            pass  # Fall through to re-raise original exception

                    # If all alternatives and fallback fail, re-raise original exception
                    raise e
                else:
                    # For non-DNS errors, re-raise immediately
                    raise

        return original_request(method, url, **kwargs)

    httpx.get = patched_get
    httpx.post = patched_post
    httpx.request = patched_request


def apply_github_redirect_patches():
    """Apply all GitHub URL redirect patches.

    This function patches common HTTP libraries to redirect GitHub release
    URLs to Walmart's internal artifactory mirror.
    """
    global _patches_applied

    if _patches_applied:
        return  # Already applied

    emit_info("[yellow]🔧 Applying Walmart GitHub redirect and SSL patches...[/yellow]")

    # Patch urllib (always available)
    patch_urllib_urlopen()

    # Patch requests if available
    patch_requests()

    # Patch httpx if available
    patch_httpx()

    _patches_applied = True
    emit_info("[green]✅ GitHub redirect and SSL patches applied successfully[/green]")


def remove_github_redirect_patches():
    """Remove all GitHub URL redirect patches and restore original functions.

    This is mainly for testing and cleanup purposes.
    """
    global _patches_applied

    if not _patches_applied:
        return  # No patches applied

    emit_info("[yellow]🔧 Removing GitHub redirect and SSL patches...[/yellow]")

    # Restore urllib
    if "urllib_urlopen" in _original_functions:
        urllib.request.urlopen = _original_functions["urllib_urlopen"]

    # Restore requests if patched
    if "requests_get" in _original_functions:
        try:
            import requests

            requests.get = _original_functions["requests_get"]
            requests.post = _original_functions["requests_post"]
            requests.request = _original_functions["requests_request"]
        except ImportError:
            pass

    # Restore httpx if patched
    if "httpx_get" in _original_functions:
        try:
            import httpx

            httpx.get = _original_functions["httpx_get"]
            httpx.post = _original_functions["httpx_post"]
            httpx.request = _original_functions["httpx_request"]
        except ImportError:
            pass

    _original_functions.clear()
    _patches_applied = False
    emit_info("[green]✅ GitHub redirect and SSL patches removed[/green]")


def is_github_redirect_active() -> bool:
    """Check if GitHub redirect and SSL patches are currently active.

    Returns:
        True if patches are applied, False otherwise
    """
    return _patches_applied
