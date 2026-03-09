"""Tests for VettingConfig.from_env()."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config import VettingConfig


def test_vetting_config_default() -> None:
    """Default (no env or invalid) -> consistency_mode is single."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": ""}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "single"


def test_vetting_config_full() -> None:
    """VET_CONSISTENCY_MODE=full -> consistency_mode is full."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "full"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "full"


def test_vetting_config_single() -> None:
    """VET_CONSISTENCY_MODE=single -> consistency_mode is single."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "single"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "single"


def test_vetting_config_multi() -> None:
    """VET_CONSISTENCY_MODE=multi -> consistency_mode is multi."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "multi"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "multi"


def test_vetting_config_case_insensitive_multi() -> None:
    """VET_CONSISTENCY_MODE=Multi (case) -> consistency_mode is multi."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "Multi"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "multi"


def test_vetting_config_case_insensitive_full() -> None:
    """VET_CONSISTENCY_MODE=FULL (case) -> consistency_mode is full."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "FULL"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "full"


def test_vetting_config_invalid_fallback() -> None:
    """Invalid/unknown value -> falls back to single."""
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "foo"}):
        cfg = VettingConfig.from_env()
        assert cfg.consistency_mode == "single"
