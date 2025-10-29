from __future__ import annotations

import pytest

# Safety override: skip this entire module to guarantee no real keyboard/mouse input.
pytestmark = pytest.mark.skip(reason="Safety: skipping keyboard/mouse control tests to avoid any real input events")

# Intentionally left minimal to avoid real input events.
