"""Aggregate structural records into publishable distributions.

No individual structural records are exposed. Only aggregate statistics
with coarse buckets and minimum-group thresholds are computed.
"""

from __future__ import annotations

from .struct_schemas import (
    CategoryDistribution,
    NumericDistribution,
    StructuralAggregation,
    StructuralRecord,
)


def aggregate(records: list[StructuralRecord], min_group_size: int = 5) -> StructuralAggregation:
    """Aggregate structural records into distribution statistics.

    Args:
        records: List of individual structural records.
        min_group_size: Minimum count for a group to be included in distributions.
                        Groups below this threshold are lumped into 'other'.

    Returns:
        StructuralAggregation with only aggregate statistics.
    """
    if not records:
        return StructuralAggregation()

    agg = StructuralAggregation()
    agg.total_documents = len(records)
    agg.total_pages = sum(r.page_count for r in records)

    # Categorical distributions
    doc_type_counts: dict[str, int] = {}
    page_size_counts: dict[str, int] = {}
    layout_counts: dict[str, int] = {}
    word_bucket_counts: dict[str, int] = {}
    density_counts: dict[str, int] = {}
    scan_counts: dict[str, int] = {}
    lang_counts: dict[str, int] = {}

    tables_count = 0
    images_count = 0

    for r in records:
        doc_type_counts[r.document_type.value] = doc_type_counts.get(r.document_type.value, 0) + 1
        page_size_counts[r.page_size.value] = page_size_counts.get(r.page_size.value, 0) + 1
        layout_counts[r.layout.value] = layout_counts.get(r.layout.value, 0) + 1
        word_bucket_counts[r.approximate_word_count_bucket.value] = (
            word_bucket_counts.get(r.approximate_word_count_bucket.value, 0) + 1
        )
        density_counts[r.text_density.value] = density_counts.get(r.text_density.value, 0) + 1
        scan_counts[r.scanned_likelihood.value] = scan_counts.get(r.scanned_likelihood.value, 0) + 1
        lang_counts[r.language] = lang_counts.get(r.language, 0) + 1
        if r.has_tables:
            tables_count += 1
        if r.has_images:
            images_count += 1

    agg.document_types = _apply_threshold(doc_type_counts, min_group_size)
    agg.page_sizes = _apply_threshold(page_size_counts, min_group_size)
    agg.layouts = _apply_threshold(layout_counts, min_group_size)
    agg.word_count_buckets = _apply_threshold(word_bucket_counts, min_group_size)
    agg.text_densities = _apply_threshold(density_counts, min_group_size)
    agg.scanned_likelihoods = _apply_threshold(scan_counts, min_group_size)
    agg.languages = _apply_threshold(lang_counts, min_group_size)

    # Numeric distribution for page counts
    page_counts = [r.page_count for r in records]
    agg.page_count_distribution = NumericDistribution(
        min=min(page_counts),
        max=max(page_counts),
        mean=sum(page_counts) / len(page_counts),
        buckets=_bucket_page_counts(page_counts, min_group_size),
    )

    agg.tables_fraction = tables_count / len(records) if records else 0.0
    agg.images_fraction = images_count / len(records) if records else 0.0

    return agg


def _apply_threshold(
    counts: dict[str, int], min_group_size: int
) -> CategoryDistribution:
    """Merge groups below threshold into 'other'."""
    result: dict[str, int] = {}
    other = 0
    for key, count in counts.items():
        if count >= min_group_size:
            result[key] = count
        else:
            other += count
    if other > 0:
        result["other"] = other
    return CategoryDistribution(counts=result)


def _bucket_page_counts(
    page_counts: list[int], min_group_size: int
) -> dict[str, int]:
    """Bucket page counts into ranges."""
    buckets: dict[str, int] = {
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
        "5+": 0,
    }
    for pc in page_counts:
        if pc == 1:
            buckets["1"] += 1
        elif pc == 2:
            buckets["2"] += 1
        elif pc == 3:
            buckets["3"] += 1
        elif pc == 4:
            buckets["4"] += 1
        else:
            buckets["5+"] += 1

    # Apply threshold
    result: dict[str, int] = {}
    other = 0
    for key, count in buckets.items():
        if count >= min_group_size:
            result[key] = count
        else:
            other += count
    if other > 0:
        result["other"] = other
    return result
