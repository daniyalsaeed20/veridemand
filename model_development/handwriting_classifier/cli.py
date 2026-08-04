"""CLI entrypoints for Phase 5 Task B3 dual-risk train / evaluate / export / ASAP prepare."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.paths import default_private_root
from backend.app.extraction.handwriting_router.manifest import ClassifierPackageStatus

from model_development.handwriting_classifier import MODEL_VERSION, THRESHOLD_SET_VERSION
from model_development.handwriting_classifier.config import (
    CANDIDATE_CONFIGS,
    ThresholdCandidate,
    TrainConfig,
)
from model_development.handwriting_classifier.cross_validate import run_losgo
from model_development.handwriting_classifier.dataset import (
    aggregate_is_expected,
    build_training_manifest,
    write_deferred_held_out_manifest,
    write_private_manifest,
)
from model_development.handwriting_classifier.evaluate import (
    opaque_error_categories,
    summarize_oof,
)
from model_development.handwriting_classifier.export_onnx import export_onnx, run_parity_suite
from model_development.handwriting_classifier.model import weights_provenance
from model_development.handwriting_classifier.package_model import write_package
from model_development.handwriting_classifier.public_data.download import LicenceBlockedError
from model_development.handwriting_classifier.public_data.prepare import prepare_asap
from model_development.handwriting_classifier.public_data.refs import (
    asap_provenance_summary,
    default_asap_data_root,
    load_asap_handwriting_refs,
)
from model_development.handwriting_classifier.reports import oof_without_ids, write_json
from model_development.handwriting_classifier.synthetic_nontext import generate_synthetic_nontext
from model_development.handwriting_classifier.thresholds import (
    challenge_routing_report,
    search_thresholds,
    thresholds_to_dict,
)
from model_development.handwriting_classifier.train import (
    ExampleRef,
    predict_logits,
    to_refs,
    train_model,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS = REPO_ROOT / "model_development" / ".artifacts"
DEFAULT_PACKAGE = REPO_ROOT / "models" / "handwriting_classifier"


def _repo_commit() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _load_public_for_config(cfg: TrainConfig, data_root: Path | None) -> list[ExampleRef]:
    if cfg.public_asap_variant == "none":
        return []
    variant = "light" if cfg.public_asap_variant == "light" else "medium"
    return load_asap_handwriting_refs(data_root, variant=variant)


def _candidate_sort_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Model selection order when multiple configs pass gates (Task §17)."""

    thr = entry.get("selected_thresholds") or {}
    return (
        0 if entry.get("passes_safety_gate") else 1,
        -(thr.get("printed_retention_recall") or 0.0),
        -(thr.get("direct_handwritten_rate") or 0.0),
        thr.get("handwriting_grey_zone_rate") or 1.0,
        0,
        -(thr.get("direct_nontext_rate") or 0.0),
        {"weighted_bce": 0, "asymmetric_bce": 1, "focal": 2}.get(
            entry.get("loss_name", "focal"), 3
        ),
    )


def cmd_prepare_asap(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root) if args.data_root else default_asap_data_root(REPO_ROOT)
    try:
        result = prepare_asap(
            data_root,
            verify_only=bool(args.verify_only),
            force_download=bool(args.force_download),
            seed=int(args.seed),
        )
    except LicenceBlockedError as exc:
        print(
            json.dumps(
                {
                    "decision": "PUBLIC HANDWRITING SUPPLEMENT BLOCKED BY LICENSING",
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 7
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_build_manifest(args: argparse.Namespace) -> int:
    private_root = Path(args.private_root) if args.private_root else default_private_root()
    fit, challenge, summary = build_training_manifest(private_root)
    ok, msg = aggregate_is_expected(summary)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_sha = write_private_manifest(fit, out_dir / "classifier-training-manifest.jsonl")
    challenge_sha = write_private_manifest(
        challenge, out_dir / "classifier-uncertain-challenge.jsonl"
    )
    held_sha = write_deferred_held_out_manifest(out_dir / "classifier-deferred-held-out.jsonl")
    summary_out = {
        **summary,
        "training_manifest_sha256": train_sha,
        "challenge_manifest_sha256": challenge_sha,
        "held_out_manifest_sha256": held_sha,
        "aggregates_match_expected": ok,
        "aggregates_message": msg,
    }
    write_json(out_dir / "manifest-summary.json", summary_out)
    print(json.dumps(summary_out, indent=2, sort_keys=True))
    if not ok and args.strict_aggregates:
        return 2
    return 0


def cmd_train_export(args: argparse.Namespace) -> int:
    private_root = Path(args.private_root) if args.private_root else default_private_root()
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    package_dir = Path(args.package_dir)
    asap_root = (
        Path(args.asap_data_root) if args.asap_data_root else default_asap_data_root(REPO_ROOT)
    )

    fit, challenge, summary = build_training_manifest(private_root)
    ok, msg = aggregate_is_expected(summary)
    if not ok:
        print(f"WARNING: aggregate mismatch: {msg}")
        if args.strict_aggregates:
            return 2

    model_dev = private_root / "model-dev"
    model_dev.mkdir(parents=True, exist_ok=True)
    train_sha = write_private_manifest(fit, model_dev / "classifier-training-manifest.jsonl")
    challenge_sha = write_private_manifest(
        challenge, model_dev / "classifier-uncertain-challenge.jsonl"
    )
    held_sha = write_deferred_held_out_manifest(model_dev / "classifier-deferred-held-out.jsonl")

    configs: list[TrainConfig] = list(CANDIDATE_CONFIGS)
    if args.config:
        configs = [c for c in CANDIDATE_CONFIGS if c.name == args.config]
        if not configs:
            raise SystemExit(f"Unknown config {args.config}")

    needs_asap = any(c.public_asap_variant != "none" for c in configs)
    if needs_asap and not (asap_root / "prepared" / "subset-manifest.json").is_file():
        print(
            "ASAP prepared subset missing. Run: pnpm phase5:model-data:asap:prepare",
            flush=True,
        )
        return 6

    public_prov = asap_provenance_summary(asap_root) if needs_asap else {}
    config_results: list[dict[str, Any]] = []
    passing_candidates: list[dict[str, Any]] = []

    for cfg in configs:
        print(f"=== LOSGO config={cfg.name} loss={cfg.loss} ===", flush=True)
        public_refs = _load_public_for_config(cfg, asap_root)
        t0 = time.perf_counter()
        result = run_losgo(
            fit,
            cfg,
            artifacts_dir=artifacts,
            challenge=challenge,
            device=args.device,
            public_refs=public_refs,
        )
        selected, top = search_thresholds(result["oof_predictions"])
        elapsed = time.perf_counter() - t0
        entry = {
            "config_name": cfg.name,
            "config_hash": cfg.config_hash(),
            "loss_name": cfg.loss,
            "elapsed_sec": elapsed,
            "oof_summary": result["oof_summary"],
            "fold_reports": result["fold_reports"],
            "synthetic_nontext_count": result["synthetic_nontext_count"],
            "public_handwriting_count": result.get("public_handwriting_count", len(public_refs)),
            "public_asap_variant": cfg.public_asap_variant,
            "handwriting_fn_multiplier": cfg.handwriting_fn_multiplier,
            "hard_example_emphasis": cfg.hard_example_emphasis,
            "selected_thresholds": thresholds_to_dict(selected) if selected else None,
            "top_threshold_candidates": [thresholds_to_dict(m) for m in top[:5]],
            "passes_safety_gate": bool(selected and selected.passes_safety_gate),
        }
        write_json(
            artifacts / "oof" / f"{cfg.name}_oof_summary.json",
            {
                "oof_summary": result["oof_summary"],
                "predictions": oof_without_ids(result["oof_predictions"]),
            },
        )
        config_results.append(entry)
        if selected is not None and selected.passes_safety_gate:
            passing_candidates.append(
                {
                    "config": cfg,
                    "result": result,
                    "thresholds": selected,
                    "entry": entry,
                    "public_refs": public_refs,
                }
            )

    decision_payload: dict[str, Any] = {
        "label_aggregates": {
            "printed": summary["printed"],
            "handwritten": summary["handwritten"],
            "non_text": summary["non_text"],
            "uncertain_challenge": summary["uncertain_challenge"],
            "source_group_count": summary["source_group_count"],
            "handwriting_source_group_count": summary["handwriting_source_group_count"],
        },
        "public_provenance": {
            k: public_prov.get(k)
            for k in (
                "title",
                "doi",
                "zenodo_record_id",
                "licence_id",
                "licence_name",
                "access_date",
                "archive_filename",
                "official_md5",
                "local_sha256",
                "attribution",
                "modification_notice",
            )
            if public_prov
        },
        "training_manifest_sha256": train_sha,
        "challenge_manifest_sha256": challenge_sha,
        "held_out_manifest_sha256": held_sha,
        "config_results": [
            {k: v for k, v in e.items() if k != "fold_reports"}
            | {"fold_reports": e["fold_reports"]}
            for e in config_results
        ],
        "threshold_set_version": THRESHOLD_SET_VERSION,
        "architecture": "dual_risk_independent_binary_logits",
        "three_class_baseline_status": ("prototype baseline — superseded for safety evaluation"),
    }

    if not passing_candidates:
        decision_payload["decision"] = "SAFETY-FIRST MODEL STILL NOT SAFE"
        decision_payload["package_status"] = None
        failing_slices: list[str] = []
        for e in config_results:
            tops = e.get("top_threshold_candidates") or []
            if tops:
                sg = (tops[0] or {}).get("slice_gates") or {}
                if sg.get("cursive_routed_printed"):
                    failing_slices.append("cursive_printed")
                if sg.get("signature_routed_printed"):
                    failing_slices.append("signature_printed")
                if sg.get("cursive_routed_non_text"):
                    failing_slices.append("cursive_non_text")
                if sg.get("signature_routed_non_text"):
                    failing_slices.append("signature_non_text")
                if (tops[0] or {}).get("handwritten_to_printed"):
                    failing_slices.append("handwritten_to_printed")
                if (tops[0] or {}).get("handwritten_to_nontext"):
                    failing_slices.append("handwritten_to_nontext")
        decision_payload["failing_slices"] = sorted(set(failing_slices))
        write_json(artifacts / "task_b3_decision.json", decision_payload)
        print(json.dumps({"decision": decision_payload["decision"]}, indent=2))
        return 3

    passing_candidates.sort(key=lambda c: _candidate_sort_key(c["entry"]))
    best_gate = passing_candidates[0]

    cfg = best_gate["config"]
    thr = best_gate["thresholds"]
    oof_preds = best_gate["result"]["oof_predictions"]
    public_refs = best_gate["public_refs"]

    for p in oof_preds:
        from model_development.handwriting_classifier.thresholds import route_probabilities

        probs = p.get("risk_probabilities") or p["probabilities"]
        p["routed_outcome"] = route_probabilities(probs, thr)

    print(f"=== Final fit config={cfg.name} ===")
    synth = generate_synthetic_nontext(
        artifacts / "synthetic_nontext" / f"{cfg.name}_final",
        count=cfg.synthetic_nontext_count,
        seed=cfg.random_seed,
    )
    final_refs = list(to_refs(fit, synth)) + list(public_refs)
    ckpt = artifacts / "checkpoints" / cfg.name / "final.pt"
    final = train_model(final_refs, cfg, device=args.device, checkpoint_path=ckpt)
    model = final["model"]

    challenge_refs = [
        ExampleRef(
            path=e.crop_path_private,
            label="uncertain",
            source_group_id=e.source_group_id,
            crop_id=e.crop_id,
        )
        for e in challenge
    ]
    challenge_preds = predict_logits(
        model, challenge_refs, device=final["device"], batch_size=cfg.batch_size
    )
    for p in challenge_preds:
        p.pop("path", None)
        p.pop("crop_id", None)
    challenge_counts = challenge_routing_report(challenge_preds, thr)

    onnx_path = artifacts / "export" / "model.onnx"
    export_onnx(model, onnx_path)

    from PIL import Image

    samples = []
    for lab in ("printed", "handwritten", "non_text"):
        ex = next((e for e in fit if e.label == lab), None)
        if ex is not None:
            samples.append(Image.open(ex.crop_path_private).convert("RGB"))

    thr_cand = ThresholdCandidate(
        handwriting_accept_threshold=thr.handwriting_accept_threshold,
        handwriting_safe_low_threshold=thr.handwriting_safe_low_threshold,
        non_text_accept_threshold=thr.non_text_accept_threshold,
        non_text_safe_low_threshold=thr.non_text_safe_low_threshold,
    )
    parity = run_parity_suite(model, onnx_path, sample_images=samples, thresholds=thr_cand)
    if not parity["passed"]:
        decision_payload["decision"] = "SAFETY-FIRST MODEL STILL NOT SAFE"
        decision_payload["parity"] = parity
        decision_payload["reason"] = "onnx_parity_failed"
        write_json(artifacts / "task_b3_decision.json", decision_payload)
        print("ONNX parity failed")
        return 4

    oof_index = [
        {
            "fold_index": p.get("held_out_fold_index"),
            "label": p.get("label"),
            "p_hw": p.get("p_hw"),
            "p_nt": p.get("p_nt"),
            "routed_outcome": p.get("routed_outcome"),
        }
        for p in oof_preds
    ]
    oof_bytes = (json.dumps(oof_index, sort_keys=True) + "\n").encode("utf-8")
    from hashlib import sha256

    val_sha = sha256(oof_bytes).hexdigest()
    (model_dev / "classifier-oof-eval-index.json").write_bytes(oof_bytes)

    import onnx
    import onnxruntime as ort
    import torch
    import torchvision

    prov = weights_provenance()
    package_status = ClassifierPackageStatus.PRODUCTION_CANDIDATE
    subset_meta: dict[str, Any] = {}
    subset_path = asap_root / "prepared" / "subset-manifest.json"
    if subset_path.is_file():
        subset_meta = json.loads(subset_path.read_text(encoding="utf-8"))
    public_package_prov = {
        **public_prov,
        "public_sample_count": len(public_refs),
        "subset_version": subset_meta.get("subset_version"),
        "subset_manifest_sha256": subset_meta.get("subset_manifest_sha256"),
        "transform_version": subset_meta.get("transform_version"),
        "prompt_group_count": subset_meta.get("prompt_group_count"),
        "doi": public_prov.get("doi") or "10.5281/zenodo.8088866",
    }
    pkg = write_package(
        package_dir,
        onnx_path,
        MODEL_VERSION,
        _repo_commit(),
        package_status,
        train_sha,
        val_sha,
        held_sha,
        thr,
        summarize_oof(oof_preds),
        {
            "printed": summary["printed"],
            "handwritten": summary["handwritten"],
            "non_text": summary["non_text"],
        },
        len(synth),
        cfg.config_hash(),
        json.dumps(prov, sort_keys=True)[:512],
        torch.__version__,
        torchvision.__version__,
        onnx.__version__,
        ort.__version__,
        (
            "Phase 5 Task B3 dual-risk safety-first production_candidate. "
            "Live OCR routing not integrated. "
            f"selected_config={cfg.name}."
        ),
        public_provenance=public_package_prov,
    )
    if not pkg["verification_ok"]:
        decision_payload["decision"] = "SAFETY-FIRST MODEL STILL NOT SAFE"
        decision_payload["package"] = pkg
        decision_payload["reason"] = "package_verification_failed"
        write_json(artifacts / "task_b3_decision.json", decision_payload)
        return 5

    from backend.app.extraction.handwriting_router.service import HandwritingClassifierService
    from backend.app.settings.config import Settings
    from PIL import Image as PILImage

    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_required=False,
        handwriting_classifier_path=package_dir,
        handwriting_accept_threshold=thr.handwriting_accept_threshold,
        handwriting_safe_low_threshold=thr.handwriting_safe_low_threshold,
        non_text_accept_threshold=thr.non_text_accept_threshold,
        non_text_safe_low_threshold=thr.non_text_safe_low_threshold,
    )
    svc = HandwritingClassifierService(settings)
    t_load0 = time.perf_counter()
    ready = svc.readiness_check(allow_test_fixture=False)
    t_load = time.perf_counter() - t_load0
    bench_img = PILImage.new("RGB", (120, 40), color=(255, 255, 255))
    t0 = time.perf_counter()
    _ = svc.classify_crop(bench_img, region_id="bench_first", allow_test_fixture=False)
    first_inf = time.perf_counter() - t0
    warm = []
    for _ in range(20):
        t0 = time.perf_counter()
        _ = svc.classify_crop(bench_img, region_id="bench_warm", allow_test_fixture=False)
        warm.append(time.perf_counter() - t0)
    batch_latency = {}
    for bs in (1, 4, 8, 16):
        imgs = [bench_img] * bs
        t0 = time.perf_counter()
        _ = svc.classify_crops(
            imgs, region_ids=[f"b{i}" for i in range(bs)], allow_test_fixture=False
        )
        batch_latency[str(bs)] = time.perf_counter() - t0

    model_size = (package_dir / "model.onnx").stat().st_size
    decision_payload.update(
        {
            "decision": "SAFETY-FIRST ONNX ROUTER READY FOR INTEGRATION",
            "package_status": package_status.value,
            "selected_config": cfg.name,
            "selected_config_hash": cfg.config_hash(),
            "selected_thresholds": thresholds_to_dict(thr),
            "oof_summary": summarize_oof(oof_preds),
            "fp_fn_categories": opaque_error_categories(oof_preds),
            "uncertain_challenge_routing": challenge_counts,
            "mixture": {
                "project_printed": summary["printed"],
                "project_handwritten": summary["handwritten"],
                "project_non_text": summary["non_text"],
                "uncertain_challenge": summary["uncertain_challenge"],
                "public_handwriting": len(public_refs),
                "synthetic_nontext": len(synth),
                "public_asap_variant": cfg.public_asap_variant,
                "loss": cfg.loss,
            },
            "parity": parity,
            "package": pkg,
            "performance": {
                "model_bytes": model_size,
                "session_or_readiness_sec": t_load,
                "readiness_ready": ready.ready if hasattr(ready, "ready") else bool(ready),
                "first_inference_sec": first_inf,
                "warm_single_mean_sec": float(sum(warm) / len(warm)),
                "batch_latency_sec": batch_latency,
            },
            "weights_provenance": prov,
            "final_parameter_counts": final["parameter_counts"],
            "final_pos_weight": final["pos_weight"],
            "device": final["device"],
        }
    )
    write_json(artifacts / "task_b3_decision.json", decision_payload)
    write_json(artifacts / "task_b3_public_summary.json", decision_payload)
    print(json.dumps({"decision": decision_payload["decision"], "package": pkg}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 5 Task B3 dual-risk classifier tooling")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("prepare-asap", help="Download/verify Handwritten ASAP and build subset")
    a.add_argument("--data-root", default=None)
    a.add_argument("--verify-only", action="store_true")
    a.add_argument("--force-download", action="store_true")
    a.add_argument("--seed", type=int, default=42)
    a.set_defaults(func=cmd_prepare_asap)

    m = sub.add_parser("build-manifest", help="Build private training manifests")
    m.add_argument("--private-root", default=None)
    m.add_argument(
        "--out-dir",
        default=str(default_private_root() / "model-dev"),
    )
    m.add_argument("--strict-aggregates", action="store_true")
    m.set_defaults(func=cmd_build_manifest)

    t = sub.add_parser("train-export", help="LOSGO, thresholds, final fit, ONNX package")
    t.add_argument("--private-root", default=None)
    t.add_argument("--artifacts", default=str(DEFAULT_ARTIFACTS))
    t.add_argument("--package-dir", default=str(DEFAULT_PACKAGE))
    t.add_argument("--asap-data-root", default=None)
    t.add_argument("--device", default=None)
    t.add_argument("--config", default=None, help="Run a single named config")
    t.add_argument("--strict-aggregates", action="store_true")
    t.set_defaults(func=cmd_train_export)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
