import random

from synthetic_apps.modeling.dossier_model import DossierModel, SubdocumentDistribution
from synthetic_apps.modeling.output_plan import DossierOutputPlan


def test_sampled_dossier_always_starts_with_cover_letter():
    model = DossierModel(
        schema_version="test",
        n_dossiers=3,
        document_count_distribution={"3": 3},
        document_presence={"cv": 1.0},
        page_count_by_type={"cv": {"1": 1}},
        semantic_code_presence={},
        calibrated={},
        subdocuments=SubdocumentDistribution(
            sequence_patterns=[["unknown", "cv"], ["cv", "reference_letter"]],
            sequence_weights=[1.0, 1.0],
            subdoc_page_counts={
                "unknown": {"1": 1}, "cv": {"1": 1}, "reference_letter": {"1": 1},
            },
        ),
    )
    for seed in range(20):
        sample = model._sample_subdoc_sequence(random.Random(seed))
        assert sample[0]["type"] == "cover_letter"
        assert sample[0]["page_target"] <= 2


def test_single_cover_letter_does_not_absorb_entire_package():
    plan = DossierOutputPlan.from_samples(
        {
            "ausdruck": {"page_count": 2, "layout": "two_column"},
            "bewerbung": {"page_count": 11, "layout": "standard"},
            "documents": [],
        },
        {"synthetic_id": "SG0001", "subdocuments": [{"type": "cover_letter", "page_target": 1}]},
        0,
    )
    subdocs = plan.documents[1].subdocuments
    assert subdocs[0].subdoc_type == "cover_letter"
    assert subdocs[0].page_target == 2
    assert all(s.subdoc_type != "cover_letter" or s.page_target <= 2 for s in subdocs)
    assert sum(s.page_target for s in subdocs) == 11


def test_subdocuments_are_pruned_when_package_has_too_few_pages():
    plan = DossierOutputPlan.from_samples(
        {
            "ausdruck": {"page_count": 2, "layout": "two_column"},
            "bewerbung": {"page_count": 2, "layout": "standard"},
            "documents": [],
        },
        {"synthetic_id": "SG0001", "subdocuments": [
            {"type": "cover_letter", "page_target": 1},
            {"type": "cv", "page_target": 1},
            {"type": "certificate", "page_target": 1},
        ]},
        0,
    )
    subdocs = plan.documents[1].subdocuments
    assert len(subdocs) == 2
    assert sum(s.page_target for s in subdocs) == 2
