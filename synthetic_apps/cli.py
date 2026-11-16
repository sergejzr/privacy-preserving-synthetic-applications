from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from . import __version__
from .applicant_generator import generate_applicants
from .config import RunConfig, config_from_file
from .document_generator import generate_document_texts
from .genconfig import Config as GenConfig
from .ground_truth import generate_document_evidence
from .ingestion import discover_dossiers, extract_dossier
from .ingestion.extract import stable_private_id
from .job_generator import generate_job_description
from .local_llm import LocalLLMClient
from .modeling import (
    DossierOutputPlan, OutputDocumentPlan,
    StructuralModel, fit_dossier_model, fit_model,
    load_dossier_model, load_model,
    sample_output_plans, save_dossier_model, save_model, save_output_plans,
)
from .modeling.audit import audit_pdf_plan, print_audit_report
from .paths import ensure_safe_output, prepare_output, prepare_private_cache
from .pdf_renderer import PDFRenderer
from .release import create_release_archive
from .struct_schemas import StructuralRecord
from .structural_aggregation import aggregate
from .structure_analysis import analyze_pdf
from .validator import validate_dataset
from . import __version__


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    import io
    try:
        import pymupdf as fitz
        merged = fitz.open()
        for pdf_bytes in pdf_bytes_list:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            merged.insert_pdf(doc)
            doc.close()
        buf = io.BytesIO()
        merged.save(buf)
        merged.close()
        return buf.getvalue()
    except ImportError:
        return pdf_bytes_list[0] if pdf_bytes_list else b""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synthetic-apps",
        description="Local privacy-preserving synthetic application generator",
    )
    p.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # --- Codex run command (unchanged) ---
    run = sub.add_parser("run", help="Ingest real dossiers and extract features")
    run.add_argument("--input", type=Path)
    run.add_argument("--track", choices=["safe", "private"], default=None)
    run.add_argument("--ocr-dir", type=Path)
    run.add_argument("--output", type=Path, default=Path("synthetic_dataset"))
    run.add_argument("--count", type=int, default=None)
    run.add_argument("--config", type=Path)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--stage", choices=["all", "structured", "pdf"], default=None)
    run.add_argument("--force", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--offline", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--report", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--private-cache-dir", type=Path, default=None)
    run.add_argument("--local-model-endpoint", default=None)

    # --- analyze ---
    analyze = sub.add_parser("analyze", help="Analyze PDFs and extract structural profiles")
    analyze.add_argument("input", type=Path, help="Directory with applicant PDF subdirectories")
    analyze.add_argument("output", type=Path, help="Output directory for profile JSON files")

    # --- summarize ---
    summarize = sub.add_parser("summarize", help="Aggregate structural profiles into distributions")
    summarize.add_argument("profiles", type=Path, help="Directory with profile JSON files")
    summarize.add_argument("--min-group", "-m", type=int, default=5, help="Minimum group size")

    fit = sub.add_parser("fit", help="Fit a private structural population model")
    fit.add_argument("profiles", type=Path, help="Directory with profile JSON files")
    fit.add_argument("output", type=Path, help="Private model JSON path")
    fit.add_argument("--min-support", type=int, default=5)
    fit.add_argument("--seed", type=int, default=20261008)

    fit_dossier = sub.add_parser("fit-dossier", help="Fit document composition and semantic-code model")
    fit_dossier.add_argument("profiles", type=Path)
    fit_dossier.add_argument("output", type=Path)
    fit_dossier.add_argument("--min-support", type=int, default=3)
    fit_dossier.add_argument("--cleaned-md", type=Path, default=None,
                             help="Path to md_raw dir with Bewerbung.cleaned.md for subdocument learning")

    sample_dossier = sub.add_parser("sample-dossier", help="Sample dossier manifests from a composition model")
    sample_dossier.add_argument("model", type=Path)
    sample_dossier.add_argument("--count", "-n", type=int, default=5)
    sample_dossier.add_argument("--seed", type=int, default=42)
    sample_dossier.add_argument("--output", type=Path, default="dossier_plans.json")

    fit_table = sub.add_parser("fit-table", help="Fit a license-independent structural table model")
    fit_table.add_argument("profiles", type=Path, help="Coarsened structural profile directory")
    fit_table.add_argument("output", type=Path, help="Private table model JSON path")

    sample_table = sub.add_parser("sample-table", help="Sample rows from a structural table model")
    sample_table.add_argument("model", type=Path)
    sample_table.add_argument("--count", "-n", type=int, default=5)
    sample_table.add_argument("--seed", type=int, default=42)
    sample_table.add_argument("--output", type=Path, default="structural_samples.json")

    sample = sub.add_parser("sample-plan", help="Sample fictional document plans from a fitted model")
    sample.add_argument("model", type=Path, help="Private fitted model JSON")
    sample.add_argument("--count", "-n", type=int, default=5)
    sample.add_argument("--seed", type=int, default=42)
    sample.add_argument("--output", type=Path, help="Output JSON path", default="document_plans.json")

    # --- generate ---
    gen = sub.add_parser("generate", help="Generate fictional job posting, applicants, and PDFs")
    gen.add_argument("--config", "-c", type=Path, default=None, help="Config YAML path")
    gen.add_argument("--count", "-n", type=int, default=5, help="Number of applicants")
    gen.add_argument("--force", "-f", action="store_true", help="Overwrite existing outputs")
    gen.add_argument("--job-only", action="store_true", help="Only generate job description")
    gen.add_argument("--structural-model", type=Path, default=None, help="Private fitted population model JSON")
    gen.add_argument("--dossier-model", type=Path, default=None, help="Private fitted dossier/semantic model JSON")
    gen.add_argument("--title", default=None, help="Override the fictional job title/topic")
    gen.add_argument("--organization", default=None, help="Override the fictional organization")
    gen.add_argument("--fictional-universe", default=None, help="Override the fictional setting")

    # --- validate ---
    validate = sub.add_parser("validate", help="Validate generated dataset for privacy & quality")
    validate.add_argument("dataset", type=Path, help="Path to dataset directory")
    validate.add_argument("--private-ref", type=Path, default=None, help="Reference PDFs for similarity check")

    # --- release ---
    release = sub.add_parser("release", help="Create allowlist-based release archive")
    release.add_argument("dataset", type=Path, help="Path to dataset directory")
    release.add_argument("output", type=Path, help="Output .zip path")
    release.add_argument("--dry-run", "-n", action="store_true", help="List files without creating archive")

    return p


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    overrides = {k: getattr(args, k.replace("-", "_"), None)
                 for k in ("input", "ocr_dir", "count", "seed", "stage", "output",
                           "resume", "force", "offline", "report", "track",
                           "private_cache_dir", "local_model_endpoint")}
    overrides["input_dir"] = overrides.pop("input")
    overrides["output_dir"] = overrides.pop("output")
    if args.config:
        cfg = config_from_file(args.config, **overrides)
    else:
        cfg = RunConfig(**{k: v for k, v in overrides.items() if v is not None})
    cfg.validate(require_input=cfg.stage != "pdf")
    ensure_safe_output(cfg.output_dir, cfg.input_dir)
    paths = prepare_output(cfg.output_dir)
    private_paths = prepare_private_cache(cfg.private_cache_dir) if cfg.private_cache_dir else None
    if cfg.stage == "pdf":
        raise NotImplementedError("PDF stage is reserved for Phase 6")
    dossiers = discover_dossiers(cfg.input_dir, cfg.ocr_dir)
    if not dossiers:
        raise ValueError("no PDF dossiers found under --input")
    feature_file = (private_paths["features"] if private_paths else paths["features"]) / "dossier_features.jsonl"
    with feature_file.open("w", encoding="utf-8") as out:
        for item in dossiers:
            feature = extract_dossier(
                cfg.input_dir / item.relative_path, cfg.input_dir,
                stable_private_id(cfg.input_dir / item.relative_path), cfg.ocr_dir,
            )
            out.write(json.dumps(feature.public_dict(), ensure_ascii=False) + "\n")
    report = {
        "schema_version": "report-0.1", "track": cfg.track,
        "n_real_dossiers": len(dossiers), "count_requested": cfg.count,
        "stage": cfg.stage, "offline": cfg.offline,
        "source_text_exported": False,
        "private_features_written": cfg.track == "private",
    }
    (paths["reports"] / "extraction_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    print(f"discovered={len(dossiers)} extracted={feature_file}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    input_path = args.input
    output_path = args.output
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists() or not input_path.is_dir():
        print(f"Error: input directory not found: {input_path}", file=sys.stderr)
        return 1

    applicant_dirs = sorted(d for d in input_path.iterdir() if d.is_dir())
    total_pdfs = 0
    for applicant_dir in applicant_dirs:
        pdf_files = sorted(applicant_dir.glob("*.pdf"))
        if not pdf_files:
            continue
        records = []
        for pdf_path in pdf_files:
            record = analyze_pdf(pdf_path)
            if record is not None:
                records.append(record)
                total_pdfs += 1
                print(f"  {applicant_dir.name}/{pdf_path.name}: {record.document_type.value}, "
                      f"{record.page_count}p, {record.layout.value}")
        if records:
            out_file = output_path / f"{applicant_dir.name}.json"
            data = []
            for r in records:
                item = r.model_dump(mode="json")
                # Geometry-only portrait signal is kept separate from the
                # public StructuralRecord schema for backwards compatibility.
                item["has_photo"] = r.has_photo
                data.append(item)
            out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  -> wrote {out_file.name}")

    print(f"\nAnalyzed {total_pdfs} PDFs across {len(applicant_dirs)} applicants")
    print(f"Profiles saved to {output_path.resolve()}")
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    profiles_path = args.profiles
    if not profiles_path.exists() or not profiles_path.is_dir():
        print(f"Error: profiles directory not found: {profiles_path}", file=sys.stderr)
        return 1

    all_records = []
    for json_file in sorted(profiles_path.glob("*.json")):
        data = json.loads(json_file.read_text())
        for item in data:
            all_records.append(StructuralRecord(**item))

    agg = aggregate(all_records, min_group_size=args.min_group)
    print(f"Structural Summary ({agg.total_documents} documents, {agg.total_pages} pages)")
    print(f"  Document types: {dict(agg.document_types.counts)}")
    print(f"  Page sizes: {dict(agg.page_sizes.counts)}")
    print(f"  Layouts: {dict(agg.layouts.counts)}")
    print(f"  Word count buckets: {dict(agg.word_count_buckets.counts)}")
    print(f"  Text densities: {dict(agg.text_densities.counts)}")
    print(f"  Scanned likelihoods: {dict(agg.scanned_likelihoods.counts)}")
    print(f"  Languages: {dict(agg.languages.counts)}")
    print(f"  Page count distribution: {dict(agg.page_count_distribution.buckets)}")
    print(f"  Tables: {agg.tables_fraction:.1%}, Images: {agg.images_fraction:.1%}")
    return 0


def cmd_fit(args: argparse.Namespace) -> int:
    """Fit a structural population model from private profiles."""
    profiles_dir = args.profiles
    if not profiles_dir.exists():
        print(f"Error: profiles directory not found: {profiles_dir}", file=sys.stderr)
        return 1

    print(f"Fitting model from {profiles_dir}...")
    model = fit_model(profiles_dir, seed=args.seed if hasattr(args, 'seed') else 20261008)

    save_model(model, args.output)
    print(f"Model saved to {args.output}")
    print(f"  {model.n_applicants} applicants, {model.total_pages_real} pages")
    print(f"  Page count: {len(model.bewerbung_page_count.values)} values")
    print(f"  Image ratio: {len(model.image_ratio.values)} buckets")
    print(f"  Layouts: {model.bewerbung_layout.values}")
    return 0


def cmd_sample_plan(args: argparse.Namespace) -> int:
    """Sample fictional document plans from a fitted model."""
    if not args.model.exists():
        print(f"Error: model file not found: {args.model}", file=sys.stderr)
        return 1

    model = load_model(args.model)
    rng = random.Random(args.seed)

    plans = []
    for i in range(args.count):
        config = model.sample_applicant(rng)
        plan = model.document_plan(config, rng)
        plans.append({
            "applicant_id": f"SG{i+1:03d}",
            "total_pages": config["total_pages"],
            "ausdruck": config["ausdruck"],
            "bewerbung": config["bewerbung"],
            "documents": plan,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plans, indent=2, ensure_ascii=False))
    print(f"Sampled {args.count} document plans to {args.output}")
    return 0


def cmd_fit_dossier(args: argparse.Namespace) -> int:
    model = fit_dossier_model(
        args.profiles,
        cleaned_md_dir=args.cleaned_md,
        min_support=args.min_support,
    )
    save_dossier_model(model, args.output)
    print(f"Fitted dossier model from {model.n_dossiers} dossiers: {args.output}")
    print(f"  document presence: {model.document_presence}")
    print(f"  subdocument types: {len(model.subdocuments.subdoc_presence)}")
    print(f"  sequence patterns: {len(model.subdocuments.sequence_patterns)}")
    print(f"  calibrated: {model.calibrated}")
    return 0


def cmd_sample_dossier(args: argparse.Namespace) -> int:
    model = load_dossier_model(args.model)
    plans = model.sample(args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plans, indent=2, ensure_ascii=False))
    print(f"Sampled {len(plans)} dossier plans to {args.output}")
    return 0


def cmd_fit_table(args: argparse.Namespace) -> int:
    from .modeling import fit_structural_table_model, save_structural_table_model
    model = fit_structural_table_model(args.profiles)
    save_structural_table_model(model, args.output)
    print(f"Fitted structural table model from {model.n_applicants} applicants: {args.output}")
    print(f"  page buckets: {model.page_bucket_counts}")
    return 0


def cmd_sample_table(args: argparse.Namespace) -> int:
    from .modeling import load_structural_table_model
    model = load_structural_table_model(args.model)
    rows = model.sample(args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Sampled {len(rows)} structural rows to {args.output}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    if args.config:
        cfg = GenConfig.from_yaml(args.config)
    else:
        cfg = GenConfig.from_env_defaults()

    # Keep the scenario configurable both through YAML and per-run CLI
    # overrides, so one fitted population model can support many topics.
    if args.title is not None:
        cfg.scenario.title = args.title
    if args.organization is not None:
        cfg.scenario.organization = args.organization
    if args.fictional_universe is not None:
        cfg.scenario.fictional_universe = args.fictional_universe

    print(f"Scenario: {cfg.scenario.title}")
    print(f"Organization: {cfg.scenario.organization}")

    output_dir = Path(cfg.paths.output)
    stellen_dir = output_dir / "stellenbeschreibungen"
    stellen_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "applications_pdf"
    gt_dir = output_dir / "ground_truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    stellen_md = stellen_dir / "stellenbeschreibung.md"
    extra_txt = output_dir / "extra_attributes.txt"

    # Initialize the manifest before sampling plans so model metadata can be
    # recorded even when generation is run with an existing output directory.
    manifest_path = output_dir / "generation_manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    # Resolve LLM settings
    llm_settings = cfg.resolve_llm_settings()
    client = LocalLLMClient(
        base_url=llm_settings["base_url"],
        model=llm_settings["model"],
        api_key=llm_settings["api_key"],
        timeout_seconds=llm_settings["timeout_seconds"],
        max_retries=llm_settings["max_retries"],
        temperature=llm_settings["temperature"],
        allow_non_loopback=False,
        trusted_hosts=llm_settings["trusted_hosts"],
    )

    # Load structural + dossier models and sample output plans
    output_plans: list[DossierOutputPlan] | None = None
    struct_path = args.structural_model or (Path(cfg.paths.structural_model) if cfg.paths.structural_model else None)
    dossier_path = args.dossier_model
    if struct_path and struct_path.exists() and dossier_path and dossier_path.exists():
        sm = load_model(struct_path)
        dm = load_dossier_model(dossier_path)
        output_plans = sample_output_plans(sm, dm, args.count, cfg.generation.seed)
        # Save plans for audit
        plans_path = output_dir / "output_plans.json"
        save_output_plans(output_plans, plans_path)
        manifest["output_plans_sampled"] = len(output_plans)
        manifest["output_plans_path"] = str(plans_path)
        print(f"  Loaded structural model ({sm.n_applicants} apps) + dossier model ({dm.n_dossiers} dossiers)")
        print(f"  Sampled {len(output_plans)} output plans")
    elif struct_path and struct_path.exists():
        # Fallback: structural model only
        sm = load_model(struct_path)
        output_plans = []
        for i in range(args.count):
            config = sm.sample_applicant()
            doc_plan = sm.document_plan(config)
            from .modeling.dossier_model import DossierModel
            dummy_dm = DossierModel("dummy", 0, {"2": 1},
                                     {"cv": 1.0, "cover_letter": 1.0},
                                     {"cv": {"2": 1}, "cover_letter": {"16": 1}},
                                     {"skill_family": {"project_management": 1.0}},
                                     {})
            dp = dummy_dm.sample(1, seed=cfg.generation.seed + i)[0]
            from .modeling.output_plan import DossierOutputPlan as DOP
            output_plans.append(DOP.from_samples(config, dp, i))
        print(f"  Loaded structural model ({sm.n_applicants} apps), sampled {len(output_plans)} plans")
    else:
        print("  No structural model loaded — generation will use LLM defaults")

    try:
        # Phase B: Job description
        job_text, attr_text, m = generate_job_description(cfg, output_dir=stellen_dir, client=client)
        manifest.update(m)

        if args.job_only:
            print("\nJob description generation complete.")
            return 0

        # Phase C: Applicant profiles
        profiles = generate_applicants(
            cfg, output_dir=gt_dir, count=args.count,
            client=client, job_description=job_text, extra_attributes=attr_text,
            structural_plans=[p.to_dict() for p in output_plans] if output_plans else None,
            dossier_plans=[p.to_dict() for p in output_plans] if output_plans else None,
        )
        manifest["applicant_profile_ids"] = [p.get("applicant_id") for p in profiles]

        # Phase D: Document texts + PDFs (merged — Ausdruck.pdf + Bewerbung.pdf)
        renderer = PDFRenderer(template_dir="templates")
        for idx, profile in enumerate(profiles):
            aid = profile.get("applicant_id", "?")
            name = profile.get("fictional_name", "?")
            if profile.get("_parse_error", False):
                print(f"  Skipping {aid} (parse error)")
                continue
            print(f"  Rendering {aid}: {name}...", flush=True)

            doc_texts = generate_document_texts(
                cfg, profile, client, job_description=job_text,
                output_plan=(output_plans[idx] if output_plans and idx < len(output_plans) else None),
            )
            app_pdf_dir = pdf_dir / aid
            app_pdf_dir.mkdir(exist_ok=True)
            if args.force:
                for old_pdf in app_pdf_dir.glob("*.pdf"):
                    old_pdf.unlink()

            plan = output_plans[idx] if output_plans and idx < len(output_plans) else None
            if plan:
                # Render Ausdruck.pdf (cover sheet)
                try:
                    ausdruck_pdf = renderer.render_ausdruck(plan, profile)
                    (app_pdf_dir / "Ausdruck.pdf").write_bytes(ausdruck_pdf)
                except Exception as exc:
                    print(f"    Warning: Ausdruck.pdf failed: {exc}")

                # Render merged Bewerbung.pdf (all sub-documents merged)
                try:
                    bewerbung_pdf = renderer.render_merged_dossier(plan, profile, doc_texts)
                    (app_pdf_dir / "Bewerbung.pdf").write_bytes(bewerbung_pdf)
                except Exception as exc:
                    print(f"    Warning: Bewerbung.pdf failed: {exc}")

                print(f"    -> {aid} Ausdruck.pdf + Bewerbung.pdf done")
            else:
                # Fallback: one merged PDF with basic content
                try:
                    fallback_html = f"<h1>{name}</h1><p>{profile.get('fictional_email','')}</p>"
                    fallback_pdf = renderer._html_to_pdf(fallback_html, apply_scan=True)
                    (app_pdf_dir / "Bewerbung.pdf").write_bytes(fallback_pdf)
                except Exception as exc:
                    print(f"    Warning: fallback failed: {exc}")
                print(f"    -> {aid} fallback Bewerbung.pdf done")

        # Phase E: Document evidence
        evidence = generate_document_evidence(
            applicants_path=gt_dir / "applicants.json",
            pdf_base_dir=pdf_dir, output_dir=gt_dir,
        )
        manifest["document_evidence_generated"] = True
        manifest["document_evidence_count"] = sum(
            len(e["document_observable_facts"]) for e in evidence.values()
        )
        audit = audit_pdf_plan(gt_dir / "applicants.json", pdf_dir)
        (output_dir / "render_audit.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=False)
        )
        manifest["render_audit_count"] = len(audit)
        manifest["render_audit_deviations"] = sum(
            1 for item in audit if item["status"] != "ok"
        )
        print(print_audit_report(audit))

    finally:
        client.close()

    # Save manifest
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    tmp.rename(manifest_path)

    print(f"\nGeneration complete. Dataset at {output_dir.resolve()}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    if not args.dataset.exists():
        print(f"Error: dataset directory not found: {args.dataset}", file=sys.stderr)
        return 1

    results = validate_dataset(args.dataset, private_ref_dir=args.private_ref)
    print(f"\nStatus: {results['status']}")
    print(f"  Passed: {len(results['passed'])}")
    print(f"  Warnings: {len(results['warnings'])}")
    print(f"  Errors: {len(results['errors'])}")
    for msg in results.get("warnings", []):
        print(f"  ⚠ {msg}")
    for msg in results.get("errors", []):
        print(f"  ✗ {msg}")

    return 1 if results["errors"] else 0


def cmd_release(args: argparse.Namespace) -> int:
    if not args.dataset.exists():
        print(f"Error: dataset directory not found: {args.dataset}", file=sys.stderr)
        return 1

    try:
        result = create_release_archive(args.dataset, args.output, dry_run=args.dry_run)
        if args.dry_run:
            print(result)
        else:
            print(f"Release archive created: {result}")
            results = validate_dataset(args.dataset)
            print(f"Validation: {results['status']} ({len(results['passed'])} checks)")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    handlers = {
        "run": cmd_run,
        "analyze": cmd_analyze,
        "summarize": cmd_summarize,
        "fit": cmd_fit,
        "sample-plan": cmd_sample_plan,
        "fit-dossier": cmd_fit_dossier,
        "sample-dossier": cmd_sample_dossier,
        "fit-table": cmd_fit_table,
        "sample-table": cmd_sample_table,
        "generate": cmd_generate,
        "validate": cmd_validate,
        "release": cmd_release,
    }
    handler = handlers.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1
    return handler(args)


def main() -> None:
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except (ValueError, NotImplementedError) as exc:
        raise SystemExit(f"error: {exc}")
    except Exception as exc:
        raise SystemExit(f"error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
