"""Theme dataclass for Code Puppy's messaging system.

This module provides the Theme dataclass that defines the color scheme
for different message types in Code Puppy's terminal output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List


@dataclass(slots=True)
class Theme:
    """A visual theme for Code Puppy's messaging system.

    Each field represents a Rich color string for a different message type.
    Valid Rich color strings include:
    - Basic colors: "red", "green", "blue", "yellow", etc.
    - Styled: "bold red", "dim white", "italic blue"
    - Bright: "bright_red", "bright_green", etc.
    - Hex: "#FF0000", "rgb(255,0,0)", etc.

    Attributes:
        error_color: Color for error messages
        warning_color: Color for warning messages
        success_color: Color for success messages
        info_color: Color for informational messages
        debug_color: Color for debug messages
        tool_output_color: Color for tool output (file ops, grep, etc.)
        agent_reasoning_color: Color for agent reasoning blocks
        agent_response_color: Color for agent response text
        system_color: Color for system messages and status updates
        _name: Internal theme name (for serialization)
        _description: Internal theme description (for serialization)
        _created_at: Internal creation timestamp (for serialization)
        _author: Internal theme author (for serialization)
        _version: Internal theme version (for serialization)
        _tags: Internal theme tags list (for serialization)
        author: Theme author name
        version: Theme version string
        tags: List of theme tags for categorization
    """

    # Message level colors (from MessageLevel enum)
    error_color: str = "bold red"
    warning_color: str = "yellow"
    success_color: str = "green"
    info_color: str = "white"
    debug_color: str = "dim"

    # Message category colors (from MessageCategory enum)
    tool_output_color: str = "cyan"
    agent_reasoning_color: str = "magenta"
    agent_response_color: str = "blue"
    system_color: str = "bright_black"

    # Internal metadata fields (for serialization)
    _name: str | None = None
    _description: str | None = None
    _created_at: str | None = None
    _author: str | None = None
    _version: str | None = None
    _tags: List[str] = field(default_factory=list)

    # Public metadata fields
    author: str | None = None
    version: str | None = None
    tags: List[str] = field(default_factory=list)

    # Class variable for known valid Rich colors (comprehensive set for validation)
    _VALID_COLORS: ClassVar[set[str]] = {
        # Standard ANSI colors
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        # Bright variants
        "bright_black",
        "bright_red",
        "bright_green",
        "bright_yellow",
        "bright_blue",
        "bright_magenta",
        "bright_cyan",
        "bright_white",
        # Additional named colors (Rich supports many)
        "grey0",
        "grey11",
        "grey15",
        "grey19",
        "grey23",
        "grey27",
        "grey30",
        "grey35",
        "grey39",
        "grey42",
        "grey46",
        "grey50",
        "grey54",
        "grey58",
        "grey62",
        "grey66",
        "grey70",
        "grey74",
        "grey78",
        "grey82",
        "grey85",
        "grey89",
        "grey93",
        "snow",
        "ghost_white",
        "white_smoke",
        "gainsboro",
        "floral_white",
        "old_lace",
        "linen",
        "antique_white",
        "papaya_whip",
        "blanched_almond",
        "bisque",
        "peach_puff",
        "navajo_white",
        "moccasin",
        "cornsilk",
        "ivory",
        "lemon_chiffon",
        "seashell",
        "honeydew",
        "mint_cream",
        "azure",
        "alice_blue",
        "lavender",
        "lavender_blush",
        "misty_rose",
        "dark_slate_grey",
        "dim_grey",
        "slate_grey",
        "light_slate_grey",
        "grey",
        "light_grey",
        "midnight_blue",
        "navy",
        "navy_blue",
        "cornflower_blue",
        "dark_slate_blue",
        "slate_blue",
        "medium_slate_blue",
        "light_slate_blue",
        "medium_blue",
        "royal_blue",
        "blue",
        "dodger_blue",
        "deep_sky_blue",
        "sky_blue",
        "light_sky_blue",
        "steel_blue",
        "light_steel_blue",
        "light_blue",
        "powder_blue",
        "pale_turquoise",
        "dark_turquoise",
        "medium_turquoise",
        "turquoise",
        "cyan",
        "light_cyan",
        "cadet_blue",
        "medium_aquamarine",
        "aquamarine",
        "dark_green",
        "dark_olive_green",
        "dark_sea_green",
        "sea_green",
        "medium_sea_green",
        "light_sea_green",
        "pale_green",
        "spring_green",
        "lawn_green",
        "medium_spring_green",
        "green_yellow",
        "lime_green",
        "yellow_green",
        "forest_green",
        "olive_drab",
        "dark_khaki",
        "khaki",
        "pale_goldenrod",
        "light_goldenrod_yellow",
        "light_yellow",
        "yellow",
        "gold",
        "light_goldenrod",
        "goldenrod",
        "dark_goldenrod",
        "rosy_brown",
        "indian_red",
        "saddle_brown",
        "sienna",
        "peru",
        "burlywood",
        "beige",
        "wheat",
        "sandy_brown",
        "tan",
        "chocolate",
        "firebrick",
        "brown",
        "dark_salmon",
        "salmon",
        "light_salmon",
        "orange",
        "dark_orange",
        "coral",
        "light_coral",
        "tomato",
        "orange_red",
        "red",
        "hot_pink",
        "deep_pink",
        "pink",
        "light_pink",
        "pale_violet_red",
        "maroon",
        "medium_violet_red",
        "violet_red",
        "magenta",
        "violet",
        "plum",
        "orchid",
        "medium_orchid",
        "dark_orchid",
        "dark_violet",
        "blue_violet",
        "purple",
        "medium_purple",
        "thistle",
        "snow1",
        "snow2",
        "snow3",
        "snow4",
        "seashell1",
        "seashell2",
        "seashell3",
        "seashell4",
        "antique_white1",
        "antique_white2",
        "antique_white3",
        "antique_white4",
        "bisque1",
        "bisque2",
        "bisque3",
        "bisque4",
        "peach_puff1",
        "peach_puff2",
        "peach_puff3",
        "peach_puff4",
        "navajo_white1",
        "navajo_white2",
        "navajo_white3",
        "navajo_white4",
        "lemon_chiffon1",
        "lemon_chiffon2",
        "lemon_chiffon3",
        "lemon_chiffon4",
        "cornsilk1",
        "cornsilk2",
        "cornsilk3",
        "cornsilk4",
        "ivory1",
        "ivory2",
        "ivory3",
        "ivory4",
        "honeydew1",
        "honeydew2",
        "honeydew3",
        "honeydew4",
        "lavender_blush1",
        "lavender_blush2",
        "lavender_blush3",
        "lavender_blush4",
        "misty_rose1",
        "misty_rose2",
        "misty_rose3",
        "misty_rose4",
        "azure1",
        "azure2",
        "azure3",
        "azure4",
        "slate_blue1",
        "slate_blue2",
        "slate_blue3",
        "slate_blue4",
        "royal_blue1",
        "royal_blue2",
        "royal_blue3",
        "royal_blue4",
        "blue1",
        "blue2",
        "blue3",
        "blue4",
        "dodger_blue1",
        "dodger_blue2",
        "dodger_blue3",
        "dodger_blue4",
        "steel_blue1",
        "steel_blue2",
        "steel_blue3",
        "steel_blue4",
        "deep_sky_blue1",
        "deep_sky_blue2",
        "deep_sky_blue3",
        "deep_sky_blue4",
        "sky_blue1",
        "sky_blue2",
        "sky_blue3",
        "sky_blue4",
        "light_sky_blue1",
        "light_sky_blue2",
        "light_sky_blue3",
        "light_sky_blue4",
        "slate_grey1",
        "slate_grey2",
        "slate_grey3",
        "slate_grey4",
        "light_steel_blue1",
        "light_steel_blue2",
        "light_steel_blue3",
        "light_steel_blue4",
        "light_blue1",
        "light_blue2",
        "light_blue3",
        "light_blue4",
        "light_cyan1",
        "light_cyan2",
        "light_cyan3",
        "light_cyan4",
        "pale_turquoise1",
        "pale_turquoise2",
        "pale_turquoise3",
        "pale_turquoise4",
        "cadet_blue1",
        "cadet_blue2",
        "cadet_blue3",
        "cadet_blue4",
        "turquoise1",
        "turquoise2",
        "turquoise3",
        "turquoise4",
        "cyan1",
        "cyan2",
        "cyan3",
        "cyan4",
        "dark_slate_gray1",
        "dark_slate_gray2",
        "dark_slate_gray3",
        "dark_slate_gray4",
        "aquamarine1",
        "aquamarine2",
        "aquamarine3",
        "aquamarine4",
        "dark_sea_green1",
        "dark_sea_green2",
        "dark_sea_green3",
        "dark_sea_green4",
        "sea_green1",
        "sea_green2",
        "sea_green3",
        "sea_green4",
        "pale_green1",
        "pale_green2",
        "pale_green3",
        "pale_green4",
        "spring_green1",
        "spring_green2",
        "spring_green3",
        "spring_green4",
        "green1",
        "green2",
        "green3",
        "green4",
        "chartreuse1",
        "chartreuse2",
        "chartreuse3",
        "chartreuse4",
        "olive_drab1",
        "olive_drab2",
        "olive_drab3",
        "olive_drab4",
        "dark_olive_green1",
        "dark_olive_green2",
        "dark_olive_green3",
        "dark_olive_green4",
        "khaki1",
        "khaki2",
        "khaki3",
        "khaki4",
        "light_goldenrod1",
        "light_goldenrod2",
        "light_goldenrod3",
        "light_goldenrod4",
        "light_yellow1",
        "light_yellow2",
        "light_yellow3",
        "light_yellow4",
        "yellow1",
        "yellow2",
        "yellow3",
        "yellow4",
        "gold1",
        "gold2",
        "gold3",
        "gold4",
        "goldenrod1",
        "goldenrod2",
        "goldenrod3",
        "goldenrod4",
        "dark_goldenrod1",
        "dark_goldenrod2",
        "dark_goldenrod3",
        "dark_goldenrod4",
        "rosy_brown1",
        "rosy_brown2",
        "rosy_brown3",
        "rosy_brown4",
        "indian_red1",
        "indian_red2",
        "indian_red3",
        "indian_red4",
        "sienna1",
        "sienna2",
        "sienna3",
        "sienna4",
        "burlywood1",
        "burlywood2",
        "burlywood3",
        "burlywood4",
        "wheat1",
        "wheat2",
        "wheat3",
        "wheat4",
        "tan1",
        "tan2",
        "tan3",
        "tan4",
        "chocolate1",
        "chocolate2",
        "chocolate3",
        "chocolate4",
        "firebrick1",
        "firebrick2",
        "firebrick3",
        "firebrick4",
        "brown1",
        "brown2",
        "brown3",
        "brown4",
        "salmon1",
        "salmon2",
        "salmon3",
        "salmon4",
        "light_salmon1",
        "light_salmon2",
        "light_salmon3",
        "light_salmon4",
        "orange1",
        "orange2",
        "orange3",
        "orange4",
        "dark_orange1",
        "dark_orange2",
        "dark_orange3",
        "dark_orange4",
        "coral1",
        "coral2",
        "coral3",
        "coral4",
        "tomato1",
        "tomato2",
        "tomato3",
        "tomato4",
        "orange_red1",
        "orange_red2",
        "orange_red3",
        "orange_red4",
        "red1",
        "red2",
        "red3",
        "red4",
        "deep_pink1",
        "deep_pink2",
        "deep_pink3",
        "deep_pink4",
        "hot_pink1",
        "hot_pink2",
        "hot_pink3",
        "hot_pink4",
        "pink1",
        "pink2",
        "pink3",
        "pink4",
        "light_pink1",
        "light_pink2",
        "light_pink3",
        "light_pink4",
        "pale_violet_red1",
        "pale_violet_red2",
        "pale_violet_red3",
        "pale_violet_red4",
        "maroon1",
        "maroon2",
        "maroon3",
        "maroon4",
        "violet_red1",
        "violet_red2",
        "violet_red3",
        "violet_red4",
        "magenta1",
        "magenta2",
        "magenta3",
        "magenta4",
        "orchid1",
        "orchid2",
        "orchid3",
        "orchid4",
        "plum1",
        "plum2",
        "plum3",
        "plum4",
        "medium_orchid1",
        "medium_orchid2",
        "medium_orchid3",
        "medium_orchid4",
        "dark_orchid1",
        "dark_orchid2",
        "dark_orchid3",
        "dark_orchid4",
        "purple1",
        "purple2",
        "purple3",
        "purple4",
        "medium_purple1",
        "medium_purple2",
        "medium_purple3",
        "medium_purple4",
        "thistle1",
        "thistle2",
        "thistle3",
        "thistle4",
        "grey0",
        "grey1",
        "grey2",
        "grey3",
        "grey4",
        "grey5",
        "grey6",
        "grey7",
        "grey8",
        "grey9",
        "grey10",
        "grey11",
        "grey12",
        "grey13",
        "grey14",
        "grey15",
        "grey16",
        "grey17",
        "grey18",
        "grey19",
        "grey20",
        "grey21",
        "grey22",
        "grey23",
        "grey24",
        "grey25",
        "grey26",
        "grey27",
        "grey28",
        "grey29",
        "grey30",
        "grey31",
        "grey32",
        "grey33",
        "grey34",
        "grey35",
        "grey36",
        "grey37",
        "grey38",
        "grey39",
        "grey40",
        "grey41",
        "grey42",
        "grey43",
        "grey44",
        "grey45",
        "grey46",
        "grey47",
        "grey48",
        "grey49",
        "grey50",
        "grey51",
        "grey52",
        "grey53",
        "grey54",
        "grey55",
        "grey56",
        "grey57",
        "grey58",
        "grey59",
        "grey60",
        "grey61",
        "grey62",
        "grey63",
        "grey64",
        "grey65",
        "grey66",
        "grey67",
        "grey68",
        "grey69",
        "grey70",
        "grey71",
        "grey72",
        "grey73",
        "grey74",
        "grey75",
        "grey76",
        "grey77",
        "grey78",
        "grey79",
        "grey80",
        "grey81",
        "grey82",
        "grey83",
        "grey84",
        "grey85",
        "grey86",
        "grey87",
        "grey88",
        "grey89",
        "grey90",
        "grey91",
        "grey92",
        "grey93",
        "grey94",
        "grey95",
        "grey96",
        "grey97",
        "grey98",
        "grey99",
        "grey100",
        "dark_grey",
        "dark_gray",
        "dark_blue",
        "dark_cyan",
        "dark_magenta",
        "dark_red",
        "light_green",
        # Styles
        "bold",
        "dim",
        "italic",
        "underline",
        "blink",
        "reverse",
        "strike",
        "link",
    }

    def to_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Convert theme to a dictionary for JSON serialization.

        Args:
            include_metadata: If True, includes name, description, and created_at

        Returns:
            Dictionary with color fields and optionally metadata
        """
        result: Dict[str, Any] = {
            "colors": {
                "error_color": self.error_color,
                "warning_color": self.warning_color,
                "success_color": self.success_color,
                "info_color": self.info_color,
                "debug_color": self.debug_color,
                "tool_output_color": self.tool_output_color,
                "agent_reasoning_color": self.agent_reasoning_color,
                "agent_response_color": self.agent_response_color,
                "system_color": self.system_color,
            }
        }

        if include_metadata:
            result["name"] = getattr(self, "_name", None)
            result["description"] = getattr(self, "_description", None)
            result["created_at"] = getattr(self, "_created_at", None)
            result["author"] = self.author
            result["version"] = self.version
            result["tags"] = self.tags

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Theme":
        """Create a Theme instance from a dictionary.

        Args:
            data: Dictionary with color fields and optionally metadata.
                  Can be in old format (flat color fields) or new format (nested colors)

        Returns:
            A new Theme instance

        Raises:
            KeyError: If required color fields are missing
        """
        # Support both old format (flat) and new format (nested "colors")
        if "colors" in data:
            colors = data["colors"]
        else:
            colors = data

        theme = cls(
            error_color=colors.get("error_color", "bold red"),
            warning_color=colors.get("warning_color", "yellow"),
            success_color=colors.get("success_color", "green"),
            info_color=colors.get("info_color", "white"),
            debug_color=colors.get("debug_color", "dim"),
            tool_output_color=colors.get("tool_output_color", "cyan"),
            agent_reasoning_color=colors.get("agent_reasoning_color", "magenta"),
            agent_response_color=colors.get("agent_response_color", "blue"),
            system_color=colors.get("system_color", "bright_black"),
        )

        # Store metadata as internal attributes (for backward compatibility)
        if "name" in data:
            theme._name = data["name"]
        if "description" in data:
            theme._description = data["description"]
        if "created_at" in data:
            theme._created_at = data["created_at"]
        if "author" in data:
            theme._author = data["author"]
            theme.author = data["author"]
        if "version" in data:
            theme._version = data["version"]
            theme.version = data["version"]
        if "tags" in data:
            theme._tags = data["tags"]
            theme.tags = data["tags"]

        return theme

    def validate_colors(self) -> List[str]:
        """Validate the theme's color strings comprehensively.

        Validates each color field against valid Rich color names and formats.
        Accepts:
        - Standard ANSI colors (red, green, blue, etc.)
        - Bright variants (bright_red, bright_green, etc.)
        - Named colors (cornflower_blue, salmon, etc.)
        - Hex colors (#FF0000, #F00)
        - RGB colors (rgb(255,0,0))
        - HSL colors (hsl(0,100%,50%))
        - Style modifiers (bold, dim, italic, underline, etc.)

        Rejects:
        - Empty strings
        - None values
        - Invalid color names
        - Malformed color strings

        Returns:
            List of validation errors (empty if valid). Each error describes
            the specific field and issue.
        """
        errors: List[str] = []

        # Get color fields from the theme
        color_fields = {
            "error_color": self.error_color,
            "warning_color": self.warning_color,
            "success_color": self.success_color,
            "info_color": self.info_color,
            "debug_color": self.debug_color,
            "tool_output_color": self.tool_output_color,
            "agent_reasoning_color": self.agent_reasoning_color,
            "agent_response_color": self.agent_response_color,
            "system_color": self.system_color,
        }

        for field_name, color_value in color_fields.items():
            # Check for None or empty string
            if color_value is None:
                errors.append(f"Field '{field_name}' cannot be None")
                continue

            if not isinstance(color_value, str):
                errors.append(
                    f"Field '{field_name}' must be a string, got {type(color_value).__name__}"
                )
                continue

            # Check for empty or whitespace-only string
            if not color_value.strip():
                errors.append(f"Field '{field_name}' cannot be empty")
                continue

            # Split on spaces to handle styled colors like "bold red"
            color_parts = color_value.strip().split()

            for part in color_parts:
                # Check if it's a hex color (#RRGGBB or #RGB)
                if part.startswith("#"):
                    if not self._validate_hex_color(part):
                        errors.append(
                            f"Invalid hex color '{part}' in {field_name}: '{color_value}'. "
                            f"Expected format: #RRGGBB or #RGB"
                        )
                    continue

                # Check if it's an rgb() color
                if part.startswith("rgb(") and part.endswith(")"):
                    if not self._validate_rgb_color(part):
                        errors.append(
                            f"Invalid rgb color '{part}' in {field_name}: '{color_value}'. "
                            f"Expected format: rgb(r,g,b) where values are 0-255"
                        )
                    continue

                # Check if it's an hsl() color
                if part.startswith("hsl(") and part.endswith(")"):
                    if not self._validate_hsl_color(part):
                        errors.append(
                            f"Invalid hsl color '{part}' in {field_name}: '{color_value}'. "
                            f"Expected format: hsl(h,s%,l%)"
                        )
                    continue

                # Check if it's a known color or style
                if part.lower() not in self._VALID_COLORS:
                    errors.append(
                        f"Invalid color '{part}' in {field_name}: '{color_value}'. "
                        f"Valid colors include: standard names (red, blue, green), "
                        f"bright variants (bright_red, etc.), hex colors (#FF0000), "
                        f"and rgb/hsl colors."
                    )

        return errors

    def validate(self) -> List[str]:
        """Validate the theme's color strings (alias for validate_colors).

        This method is kept for backward compatibility. New code should
        use validate_colors() which has more detailed documentation.

        Returns:
            List of validation errors (empty if valid)
        """
        return self.validate_colors()

    @staticmethod
    def _validate_hex_color(color_str: str) -> bool:
        """Validate a hex color string.

        Args:
            color_str: Hex color string (e.g., "#FF0000" or "#F00")

        Returns:
            True if valid hex color, False otherwise
        """
        hex_part = color_str[1:]  # Remove the #
        # Must be 3 or 6 hex digits
        if len(hex_part) not in (3, 6):
            return False
        # All characters must be hex digits
        try:
            int(hex_part, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_rgb_color(color_str: str) -> bool:
        """Validate an rgb() color string.

        Args:
            color_str: RGB color string (e.g., "rgb(255,0,0)")

        Returns:
            True if valid rgb color, False otherwise
        """
        # Extract the values between parentheses
        try:
            values_str = color_str[4:-1]  # Remove "rgb(" and ")"
            values = [v.strip() for v in values_str.split(",")]

            # Must have exactly 3 values
            if len(values) != 3:
                return False

            # All values must be integers 0-255
            for v in values:
                try:
                    num = int(v)
                    if not 0 <= num <= 255:
                        return False
                except ValueError:
                    return False

            return True
        except (ValueError, IndexError):
            return False


def validate_theme_name(name: str) -> bool:
    """Validate a theme name.

    Theme names must follow these rules:
    - Alphanumeric characters (a-z, A-Z, 0-9)
    - Hyphens (-) and underscores (_) only
    - Length: 1-50 characters
    - Not empty or whitespace-only

    Args:
        name: The theme name to validate

    Returns:
        True if the name is valid, False otherwise

    Examples:
        >>> validate_theme_name("my-theme")
        True
        >>> validate_theme_name("My Theme")
        False  # Contains space
        >>> validate_theme_name("theme@name")
        False  # Contains invalid character
        >>> validate_theme_name("")
        False  # Empty
        >>> validate_theme_name("a")
        True
        >>> validate_theme_name("a" * 51)
        False  # Too long
    """
    # Check if input is a string
    if not isinstance(name, str):
        return False

    # Check for empty string
    if not name:
        return False

    # Check length (1-50 characters)
    if len(name) < 1 or len(name) > 50:
        return False

    # Check for whitespace-only
    if name.strip() == "":
        return False

    # Check that all characters are valid
    # Valid: a-z, A-Z, 0-9, hyphen, underscore
    valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    return all(char in valid_chars for char in name)

    @staticmethod
    def _validate_hsl_color(color_str: str) -> bool:
        """Validate an hsl() color string.

        Args:
            color_str: HSL color string (e.g., "hsl(120,100%,50%)")

        Returns:
            True if valid hsl color, False otherwise
        """
        # Extract the values between parentheses
        try:
            values_str = color_str[4:-1]  # Remove "hsl(" and ")"
            values = [v.strip() for v in values_str.split(",")]

            # Must have exactly 3 values
            if len(values) != 3:
                return False

            # First value (hue) must be 0-360
            try:
                hue = int(values[0])
                if not 0 <= hue <= 360:
                    return False
            except ValueError:
                return False

            # Second and third values (saturation and lightness) must be percentages
            for v in values[1:]:
                if not v.endswith("%"):
                    return False
                try:
                    num = int(v[:-1])
                    if not 0 <= num <= 100:
                        return False
                except ValueError:
                    return False

            return True
        except (ValueError, IndexError):
            return False


def validate_theme_name(name: str) -> bool:
    """Validate a theme name.

    Theme names must follow these rules:
    - Alphanumeric characters (a-z, A-Z, 0-9)
    - Hyphens (-) and underscores (_) only
    - Length: 1-50 characters
    - Not empty or whitespace-only

    Args:
        name: The theme name to validate

    Returns:
        True if the name is valid, False otherwise

    Examples:
        >>> validate_theme_name("my-theme")
        True
        >>> validate_theme_name("My Theme")
        False  # Contains space
        >>> validate_theme_name("theme@name")
        False  # Contains invalid character
        >>> validate_theme_name("")
        False  # Empty
        >>> validate_theme_name("a")
        True
        >>> validate_theme_name("a" * 51)
        False  # Too long
    """
    # Check if input is a string
    if not isinstance(name, str):
        return False

    # Check for empty string
    if not name:
        return False

    # Check length (1-50 characters)
    if len(name) < 1 or len(name) > 50:
        return False

    # Check for whitespace-only
    if name.strip() == "":
        return False

    # Check that all characters are valid
    # Valid: a-z, A-Z, 0-9, hyphen, underscore
    valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    return all(char in valid_chars for char in name)
