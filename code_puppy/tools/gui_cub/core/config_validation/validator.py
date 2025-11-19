"""Pure config validation logic."""

from __future__ import annotations


def validate_resolution_match(
    cached: list[int] | None,
    current: list[int],
) -> tuple[bool, str]:
    """
    Validate resolution hasn't changed.

    Args:
        cached: Cached resolution [width, height]
        current: Current resolution [width, height]

    Returns:
        Tuple of (is_valid, message)

    Examples:
        >>> validate_resolution_match([1920, 1080], [1920, 1080])
        (True, 'Resolution matches')
        >>> validate_resolution_match([1920, 1080], [2560, 1440])
        (False, 'Resolution changed: [1920, 1080] → [2560, 1440]')
    """
    if cached is None:
        return (False, "No cached resolution")

    if cached == current:
        return (True, "Resolution matches")

    return (False, f"Resolution changed: {cached} → {current}")


def validate_platform_match(
    cached: str | None,
    current: str,
) -> tuple[bool, str]:
    """
    Validate platform hasn't changed.

    Args:
        cached: Cached platform ("darwin", "win32", "linux")
        current: Current platform

    Returns:
        Tuple of (is_valid, message)

    Examples:
        >>> validate_platform_match("darwin", "darwin")
        (True, 'Platform matches')
        >>> validate_platform_match("darwin", "win32")
        (False, 'Platform changed: darwin → win32')
    """
    if cached is None:
        return (False, "No cached platform")

    if cached == current:
        return (True, "Platform matches")

    return (False, f"Platform changed: {cached} → {current}")


def validate_scale_factor(scale: float | int | None) -> tuple[bool, str]:
    """
    Validate scale factor is reasonable.

    Args:
        scale: Scale factor value

    Returns:
        Tuple of (is_valid, message)

    Examples:
        >>> validate_scale_factor(1.0)
        (True, 'Valid scale factor')
        >>> validate_scale_factor(2.0)
        (True, 'Valid scale factor')
        >>> validate_scale_factor(5.0)
        (False, 'Scale factor out of range: 5.0 (must be 0.5-4.0)')
        >>> validate_scale_factor(None)
        (False, 'No scale factor provided')
    """
    if scale is None:
        return (False, "No scale factor provided")

    if not isinstance(scale, (int, float)):
        return (False, f"Scale factor must be number, got {type(scale).__name__}")

    if scale < 0.5 or scale > 4.0:
        return (False, f"Scale factor out of range: {scale} (must be 0.5-4.0)")

    return (True, "Valid scale factor")
