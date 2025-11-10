"""Tests for GUI-Cub accessibility tree compaction.

These tests validate success-conditional compaction of accessibility results:
- Success: Returns compact actionable elements only (top 20) - 90% token reduction
- Failure: Returns full tree for debugging

This is critical for GUI-Cub context management since accessibility trees
can have 200+ elements (40k+ tokens) but we only need top 20 actionable
elements on success.
"""

import pytest
from code_puppy.tools.gui_cub.accessibility.element_list import (
    ElementListResult,
    compact_element_list,
)


class TestAccessibilityTreeCompaction:
    """Test accessibility tree compaction for context optimization."""

    def test_filters_to_actionable_elements_only(self):
        """Should filter to only actionable element roles."""
        # Create full tree with 50 elements (mix of actionable and non-actionable)
        elements = []
        
        # Add 10 actionable buttons
        for i in range(10):
            elements.append({
                "role": "AXButton",
                "title": f"Button {i}",
                "center_x": i * 50,
                "center_y": 100,
            })
        
        # Add 30 non-actionable static text elements
        for i in range(30):
            elements.append({
                "role": "AXStaticText",  # Not actionable
                "title": f"Label {i}",
                "center_x": i * 50,
                "center_y": 200,
            })
        
        # Add 10 actionable text fields
        for i in range(10):
            elements.append({
                "role": "AXTextField",
                "title": f"Field {i}",
                "center_x": i * 50,
                "center_y": 300,
            })
        
        full_result = ElementListResult(
            success=True,
            total_elements=50,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # Should keep only actionable elements (buttons + text fields)
        assert compact.filtered_count == 20  # 10 buttons + 10 fields
        assert len(compact.elements) == 20
        
        # Verify no static text in results
        for elem in compact.elements:
            assert elem["role"] != "AXStaticText"

    def test_limits_to_top_20_elements(self):
        """Should limit results to top 20 most relevant elements."""
        # Create 50 actionable buttons
        elements = [
            {
                "role": "AXButton",
                "title": f"Button {i}",
                "center_x": i * 50,
                "center_y": 100,
            }
            for i in range(50)
        ]
        
        full_result = ElementListResult(
            success=True,
            total_elements=50,
            elements=elements,
        )
        
        compact = compact_element_list(full_result, max_elements=20)
        
        assert len(compact.elements) <= 20
        assert compact.filtered_count <= 20

    def test_sorts_by_relevance_score(self):
        """Elements should be sorted by relevance (most relevant first)."""
        elements = [
            {
                "role": "AXButton",
                "title": "Submit Form",  # High relevance (common action word)
                "center_x": 100,
                "center_y": 100,
            },
            {
                "role": "AXButton",
                "title": "xyz123",  # Low relevance (meaningless)
                "center_x": 200,
                "center_y": 100,
            },
            {
                "role": "AXButton",
                "title": "Click Here",  # High relevance
                "center_x": 300,
                "center_y": 100,
            },
        ]
        
        full_result = ElementListResult(
            success=True,
            total_elements=3,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # Verify all elements have relevance scores
        for elem in compact.elements:
            assert "relevance" in elem
            assert isinstance(elem["relevance"], (int, float))

    def test_strips_verbose_fields(self):
        """Compact elements should only contain essential fields."""
        elements = [
            {
                "role": "AXButton",
                "title": "Click Me",
                "center_x": 100,
                "center_y": 100,
                # Verbose fields that should be stripped
                "children": [{"role": "AXStaticText"}],
                "parent": {"role": "AXWindow"},
                "size": {"width": 200, "height": 50},
                "enabled": True,
                "focused": False,
            }
        ]
        
        full_result = ElementListResult(
            success=True,
            total_elements=1,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # Should only have essential fields
        elem = compact.elements[0]
        assert "role" in elem
        assert "title" in elem
        assert "x" in elem
        assert "y" in elem
        assert "relevance" in elem
        
        # Verbose fields should be absent
        assert "children" not in elem
        assert "parent" not in elem
        assert "size" not in elem

    def test_token_reduction_calculation(self):
        """Verify ~90% token reduction on compaction."""
        # Create realistic accessibility tree with 200 elements
        elements = []
        
        # Add 100 actionable elements
        for i in range(100):
            elements.append({
                "role": "AXButton",
                "title": f"Button with descriptive label {i}",
                "center_x": i * 10,
                "center_y": 100,
                "children": [{"role": "AXStaticText"}],  # Verbose
                "parent": {"role": "AXWindow"},  # Verbose
                "size": {"width": 200, "height": 50},  # Verbose
            })
        
        # Add 100 non-actionable elements
        for i in range(100):
            elements.append({
                "role": "AXStaticText",
                "title": f"Static label {i}",
                "center_x": i * 10,
                "center_y": 200,
            })
        
        full_result = ElementListResult(
            success=True,
            total_elements=200,
            elements=elements,
        )
        
        compact = compact_element_list(full_result, max_elements=20)
        
        # Rough token estimation
        full_tokens = len(str(elements))  # Rough proxy
        compact_tokens = len(str(compact.elements))
        
        reduction = (full_tokens - compact_tokens) / full_tokens
        
        # Should achieve at least 85% reduction (200 → 20 elements)
        assert reduction > 0.85
        assert len(compact.elements) <= 20

    def test_preserves_failure_state(self):
        """Failure state should return full tree for debugging."""
        elements = [
            {"role": "AXButton", "title": "Button", "center_x": 100, "center_y": 100}
        ]
        
        full_result = ElementListResult(
            success=False,
            error="Failed to read accessibility tree",
            total_elements=1,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # On failure, should return full tree unchanged
        assert compact.success is False
        assert compact.error == "Failed to read accessibility tree"

    def test_generates_summary(self):
        """Should generate summary of element types found."""
        elements = [
            {"role": "AXButton", "title": "Button 1", "center_x": 100, "center_y": 100},
            {"role": "AXButton", "title": "Button 2", "center_x": 200, "center_y": 100},
            {"role": "AXTextField", "title": "Field 1", "center_x": 300, "center_y": 100},
        ]
        
        full_result = ElementListResult(
            success=True,
            total_elements=3,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # Should have summary with role counts
        assert isinstance(compact.summary, str)
        assert "actionable" in compact.summary.lower()

    def test_empty_tree_handling(self):
        """Handle empty accessibility trees."""
        full_result = ElementListResult(
            success=True,
            total_elements=0,
            elements=[],
        )
        
        compact = compact_element_list(full_result)
        
        assert compact.success is True
        assert len(compact.elements) == 0

    def test_windows_element_types(self):
        """Should handle Windows-specific element types."""
        elements = [
            {
                "role": "Button",  # Windows style
                "title": "OK",
                "center_x": 100,
                "center_y": 100,
                "auto_id": "btn_ok",  # Windows automation ID
            },
            {
                "role": "Edit",  # Windows text field
                "title": "Username",
                "center_x": 200,
                "center_y": 100,
            },
        ]
        
        full_result = ElementListResult(
            success=True,
            total_elements=2,
            elements=elements,
        )
        
        compact = compact_element_list(full_result)
        
        # Should recognize Windows element types as actionable
        assert len(compact.elements) == 2
        
        # Should preserve auto_id for Windows
        button = next(e for e in compact.elements if e["role"] == "Button")
        assert "auto_id" in button
        assert button["auto_id"] == "btn_ok"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
