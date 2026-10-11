import fitz

from synthetic_apps.validator import _validate_applicant


def test_validator_rejects_repeated_substantial_page_content(tmp_path):
    applicant = tmp_path / "SG001"
    applicant.mkdir()
    pdf = fitz.open()
    repeated = "\n".join(
        [f"Absatz {i}: Dies ist ein ausführlicher Profilabschnitt mit konkreten Angaben." for i in range(12)]
    )
    for _ in range(2):
        page = pdf.new_page()
        page.insert_textbox((72, 72, 520, 700), repeated)
    pdf.save(applicant / "Bewerbung.pdf")
    pdf.close()

    result = _validate_applicant(applicant)
    assert any("duplicate page content" in error for error in result["errors"])
