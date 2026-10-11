import random

from synthetic_apps.modeling.dossier_model import DossierModel, SubdocumentDistribution


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
