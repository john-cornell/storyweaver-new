"""Tests for working/interactive/ui.py - interactive mode HTML rendering."""

from __future__ import annotations

import pytest

from working.interactive.ui import build_interactive_prose_html


class TestBuildInteractiveProseHtml:
    """Tests for build_interactive_prose_html function."""

    def test_empty_prose_returns_placeholder(self):
        """Empty or None prose shows placeholder message."""
        assert "<em>No story yet.</em>" in build_interactive_prose_html("")
        assert "<em>No story yet.</em>" in build_interactive_prose_html(None)
        assert "<em>No story yet.</em>" in build_interactive_prose_html("   ")

    def test_single_paragraph(self):
        """Single paragraph wrapped in p tag."""
        result = build_interactive_prose_html("Hello world.")
        assert "<p" in result
        assert "Hello world." in result
        assert "</p>" in result

    def test_multiple_paragraphs_separated(self):
        """Multiple paragraphs each get their own p tag."""
        result = build_interactive_prose_html("First para.\n\nSecond para.")
        assert result.count("<p") == 2
        assert "First para." in result
        assert "Second para." in result

    def test_xss_prevention_prose(self):
        """HTML in prose is escaped to prevent XSS."""
        result = build_interactive_prose_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_prevention_choices(self):
        """HTML in choices is escaped to prevent XSS."""
        result = build_interactive_prose_html(
            "Story text",
            choice_a="<img onerror='alert(1)'>",
            choice_b="<a href='javascript:alert(1)'>click</a>",
        )
        assert "<img" not in result
        assert "<a href" not in result
        assert "&lt;img" in result
        assert "&lt;a href" in result

    def test_choice_a_only(self):
        """Only Choice A displayed when choice_b is empty."""
        result = build_interactive_prose_html("Story", choice_a="Option A", choice_b="")
        assert "Choice A:" in result
        assert "Option A" in result
        assert "Choice B:" not in result

    def test_choice_b_only(self):
        """Only Choice B displayed when choice_a is empty."""
        result = build_interactive_prose_html("Story", choice_a="", choice_b="Option B")
        assert "Choice B:" in result
        assert "Option B" in result
        assert "Choice A:" not in result

    def test_both_choices(self):
        """Both choices displayed when both provided."""
        result = build_interactive_prose_html(
            "Story", choice_a="Option A", choice_b="Option B"
        )
        assert "Choice A:" in result
        assert "Choice B:" in result
        assert "Option A" in result
        assert "Option B" in result

    def test_no_choices_no_separator(self):
        """No horizontal rule when no choices provided."""
        result = build_interactive_prose_html("Just story text")
        assert "<hr" not in result

    def test_choices_have_separator(self):
        """Horizontal rule appears before choices box."""
        result = build_interactive_prose_html("Story", choice_a="A", choice_b="B")
        assert "<hr" in result

    def test_choices_have_aria_label(self):
        """Choices container has ARIA label for accessibility."""
        result = build_interactive_prose_html("Story", choice_a="A")
        assert 'aria-label="Story choices"' in result
        assert 'role="region"' in result

    def test_none_choices_handled(self):
        """None values for choices don't cause errors."""
        result = build_interactive_prose_html("Story", choice_a=None, choice_b=None)
        assert "Story" in result
        assert "Choice A:" not in result
        assert "Choice B:" not in result

    def test_whitespace_only_choices_ignored(self):
        """Whitespace-only choices treated as empty."""
        result = build_interactive_prose_html("Story", choice_a="   ", choice_b="\t\n")
        assert "Choice A:" not in result
        assert "Choice B:" not in result
        assert "<hr" not in result

    def test_unicode_content(self):
        """Unicode characters in prose and choices handled correctly."""
        result = build_interactive_prose_html(
            "日本語テスト 🎭",
            choice_a="选项A 中文",
            choice_b="Вариант Б",
        )
        assert "日本語テスト" in result
        assert "🎭" in result
        assert "选项A 中文" in result
        assert "Вариант Б" in result

    def test_very_long_paragraph_not_truncated(self):
        """Long paragraphs are not truncated (full content displayed)."""
        long_text = "A" * 5000
        result = build_interactive_prose_html(long_text)
        assert long_text in result

    def test_styling_constants_used(self):
        """Verify styling uses the defined constants."""
        result = build_interactive_prose_html("Story", choice_a="A", choice_b="B")
        assert "#d35400" in result  # CHOICE_A_COLOR
        assert "#2980b9" in result  # CHOICE_B_COLOR
        assert "#f5f5f5" in result  # CHOICE_BOX_BG
