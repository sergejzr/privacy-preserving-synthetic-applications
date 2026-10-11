import json

from synthetic_apps.modeling.tabular_model import (
    fit_structural_table_model, load_structural_table_model,
    save_structural_table_model,
)


def test_structural_table_model_preserves_conditional_features(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "A.json").write_text(json.dumps([
        {"document_type": "cover_letter", "page_count": 8, "layout": "two_column", "has_images": True, "has_photo": True},
        {"document_type": "certificate", "page_count": 1, "has_images": True},
    ]))
    (profiles / "B.json").write_text(json.dumps([
        {"document_type": "cover_letter", "page_count": 2, "layout": "standard", "has_images": False, "has_photo": False},
    ]))

    model = fit_structural_table_model(profiles)
    assert model.n_applicants == 2
    rows = model.sample(20, seed=7)
    assert {row["page_bucket"] for row in rows} <= {"1-2", "6-10"}
    assert all("photo" in row and "document_count" in row for row in rows)


def test_structural_table_model_round_trip(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "A.json").write_text(json.dumps([
        {"document_type": "cover_letter", "page_count": 3, "layout": "standard"},
    ]))
    model = fit_structural_table_model(profiles)
    path = tmp_path / "model.json"
    save_structural_table_model(model, path)
    loaded = load_structural_table_model(path)
    assert loaded.to_dict() == model.to_dict()
