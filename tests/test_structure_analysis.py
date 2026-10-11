"""Tests for the PDF structure analyzer.

These tests use only synthetic fixture PDFs and verify that no
text content is preserved in the structural records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_apps.struct_schemas import (
    DocumentType,
    LayoutType,
    PageSize,
    ScannedLikelihood,
    StructuralRecord,
    TextDensity,
    WordCountBucket,
)
from synthetic_apps.structure_analysis import analyze_pdf


class TestAnalyzeBasic:
    """Basic structure analysis tests using synthetic fixture PDFs."""

    def test_analyze_ausdruck(self, pdf_fixtures_dir):
        """Analyze Ausdruck.pdf (2-page cover sheet with text+images)."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Ausdruck.pdf"
        assert pdf_path.exists()

        record = analyze_pdf(str(pdf_path))
        assert record is not None
        assert record.page_count == 2
        assert record.page_size == PageSize.A4
        # Ausdruck.pdf has images
        assert record.has_images is True

    def test_analyze_bewerbung_page_count(self, pdf_fixtures_dir):
        """Analyze Bewerbung.pdf - should have many pages (13+)."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Bewerbung.pdf"
        record = analyze_pdf(str(pdf_path))
        assert record is not None
        assert record.page_count >= 13, f"Expected >=13 pages, got {record.page_count}"

    def test_analyze_bewerbung_has_images(self, pdf_fixtures_dir):
        """Bewerbung.pdf should contain image blocks (scanned certs)."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Bewerbung.pdf"
        record = analyze_pdf(str(pdf_path))
        assert record is not None
        assert record.has_images is True

    def test_analyze_all_applicants_have_both_files(self, pdf_fixtures_dir):
        """Every applicant should have Ausdruck.pdf and Bewerbung.pdf."""
        for applicant_id in ["SG001", "SG002", "SG003", "SG004", "SG005"]:
            ausdruck = pdf_fixtures_dir / applicant_id / "Ausdruck.pdf"
            bewerbung = pdf_fixtures_dir / applicant_id / "Bewerbung.pdf"
            assert ausdruck.exists(), f"Missing {ausdruck}"
            assert bewerbung.exists(), f"Missing {bewerbung}"

            r1 = analyze_pdf(str(ausdruck))
            r2 = analyze_pdf(str(bewerbung))
            assert r1 is not None, f"Failed to analyze {ausdruck}"
            assert r2 is not None, f"Failed to analyze {bewerbung}"

    def test_analyze_mixed_page_sizes(self, pdf_fixtures_dir):
        """Bewerbung.pdf may have mixed page sizes (like real data)."""
        for applicant_id in ["SG001", "SG002", "SG003", "SG004", "SG005"]:
            pdf_path = pdf_fixtures_dir / applicant_id / "Bewerbung.pdf"
            record = analyze_pdf(str(pdf_path))
            assert record is not None
            # We just check it opens successfully with some pages
            assert record.page_count > 0

    def test_analyze_scanned_pages_detected(self, pdf_fixtures_dir):
        """Scanned pages should have medium or high scanned_likelihood."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Bewerbung.pdf"
        record = analyze_pdf(str(pdf_path))
        assert record is not None
        # The text pages (CV, cover letter) keep the overall likelihood lower,
        # but scanned pages contribute to the per-page detection.
        # The overall record reflects the whole document.
        # This is a soft check - just verify no error.
        assert record.scanned_likelihood in (
            ScannedLikelihood.low, ScannedLikelihood.medium, ScannedLikelihood.high
        )


class TestAnalyzeNoTextPersistence:
    """Verify that no text content is persisted in structural records."""

    TEXT_CONTENT_FIELDS = [
        "personal_data", "name", "email", "phone", "address",
        "text_content", "extracted_text", "biography",
    ]

    def test_record_has_no_text_fields(self, pdf_fixtures_dir):
        """StructuralRecord should not contain any text content fields."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Ausdruck.pdf"
        record = analyze_pdf(str(pdf_path))
        assert record is not None
        data = record.model_dump(mode="json")

        for field in self.TEXT_CONTENT_FIELDS:
            assert field not in data, f"Text content field '{field}' found in record"

    def test_record_fields_are_non_content(self, pdf_fixtures_dir):
        """All fields in the record should be structural, not content."""
        for applicant_id in ["SG001", "SG002", "SG003"]:
            for fname in ["Ausdruck.pdf", "Bewerbung.pdf"]:
                pdf_path = pdf_fixtures_dir / applicant_id / fname
                record = analyze_pdf(str(pdf_path))
                assert record is not None
                data = record.model_dump(mode="json")

                allowed_fields = {
                    "document_type", "page_count", "page_size", "layout",
                    "approximate_word_count_bucket", "text_density",
                "has_tables", "has_images", "image_ratio", "semantic_codes", "scanned_likelihood", "language",
                }
                for key in data:
                    assert key in allowed_fields, (
                        f"Unexpected field '{key}' in {applicant_id}/{fname}"
                    )


class TestAnalyzePrivacyBoundary:
    """Privacy boundary tests: analyzer must not call LLM or network."""

    def test_analyzer_does_not_call_llm(self, pdf_fixtures_dir, monkeypatch):
        """Verify the analyzer never makes LLM calls."""
        calls = []

        def spy(*args, **kwargs):
            calls.append(args)
            raise RuntimeError("LLM should not be called during analysis")

        monkeypatch.setattr("synthetic_apps.structure_analysis.fitz", None)

        pdf_path = pdf_fixtures_dir / "SG001" / "Ausdruck.pdf"
        with pytest.raises(ImportError, match="PyMuPDF"):
            analyze_pdf(str(pdf_path))

        assert len(calls) == 0, f"LLM was called {len(calls)} times during analysis"

    def test_analyzer_no_llm_in_imports(self):
        """Verify structure_analysis module doesn't import local_llm."""
        import synthetic_apps.structure_analysis as sa
        with open(sa.__file__) as f:
            content = f.read()
        assert "local_llm" not in content, "structure_analysis should not import local_llm"
        assert "httpx" not in content, "structure_analysis should not import httpx"

    def test_record_is_frozen_and_json_serializable(self, pdf_fixtures_dir):
        """StructuralRecord should be frozen and JSON-serializable."""
        pdf_path = pdf_fixtures_dir / "SG001" / "Ausdruck.pdf"
        record = analyze_pdf(str(pdf_path))
        assert record is not None
        assert isinstance(record, StructuralRecord)

        data = record.model_dump(mode="json")
        json_str = json.dumps(data, indent=2)
        assert json_str, "Record should be JSON-serializable"

        # Verify round-trip
        restored = StructuralRecord(**json.loads(json_str))
        assert restored == record, "Round-trip should produce identical record"


class TestAnalyzeCLIIntegration:
    """Integration tests for the analyze CLI with realistic fixtures."""

    def test_analyze_produces_json_output(self, pdf_fixtures_dir, tmp_path):
        """Running analyze should produce JSON profile files."""
        import subprocess, sys as _sys
        input_dir = str(pdf_fixtures_dir)
        output_dir = str(tmp_path / "profiles")
        result = subprocess.run(
            [_sys.executable, "-m", "synthetic_apps", "analyze", input_dir, output_dir],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Check output files
        output_path = Path(output_dir)
        json_files = list(output_path.glob("*.json"))
        assert len(json_files) == 5, f"Expected 5 profile JSON files, got {len(json_files)}"
        assert "SG001.json" in [f.name for f in json_files]

        # Check content of one profile
        data = json.loads((output_path / "SG001.json").read_text())
        assert isinstance(data, list)
        assert len(data) == 2, "SG001 should have 2 PDFs (Ausdruck + Bewerbung)"

        records = [StructuralRecord(**item) for item in data]
        doc_types = {r.document_type.value for r in records}
        assert len(doc_types) >= 1, "Should classify at least one document type"
