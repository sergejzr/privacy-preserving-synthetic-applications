"""Pytest configuration and fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pdf_fixtures_dir(fixtures_dir) -> Path:
    """Path to the fixture PDFs directory."""
    path = fixtures_dir / "pdfs"
    if not path.exists():
        pytest.skip("Fixture PDFs not found. Run `python -m tests.fixtures.create_fixtures` first.")
    return path


@pytest.fixture
def sample_structural_record_data() -> dict:
    """Sample structural record for schema testing."""
    return {
        "document_type": "cv",
        "page_count": 2,
        "page_size": "A4",
        "layout": "two_column",
        "approximate_word_count_bucket": "800-1100",
        "text_density": "medium",
        "has_tables": False,
        "has_images": False,
        "scanned_likelihood": "low",
        "language": "de",
    }
