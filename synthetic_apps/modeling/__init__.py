"""Generative model package — fit from real samples, sample for generation."""
from .structural_model import StructuralModel, fit_model, load_model, save_model
from .dossier_model import DossierModel, fit_dossier_model, load_dossier_model, save_dossier_model
from .output_plan import (
    DossierOutputPlan, OutputDocumentPlan, SubDocumentPlan,
    sample_output_plans, save_output_plans, load_output_plans,
)
from .tabular_model import (
    StructuralTableModel, fit_structural_table_model,
    load_structural_table_model, save_structural_table_model,
)

__all__ = [
    "StructuralModel", "fit_model", "load_model", "save_model",
    "DossierModel", "fit_dossier_model", "load_dossier_model", "save_dossier_model",
    "DossierOutputPlan", "OutputDocumentPlan", "SubDocumentPlan",
    "sample_output_plans", "save_output_plans", "load_output_plans",
    "StructuralTableModel", "fit_structural_table_model",
    "load_structural_table_model", "save_structural_table_model",
]
