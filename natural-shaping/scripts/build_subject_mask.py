#!/usr/bin/env python3
"""Build local soft subject masks. Never resave or alter the source photo.

Only the mask is production output. RGB cutouts/overlays are QA previews.
One ONNX session is reused for every input and repeated benchmark in a run.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time


ALLOWED_MODELS = ("birefnet-general-lite", "birefnet-portrait", "u2netp")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_roi(text: str) -> tuple[str, tuple[int, int, int, int]]:
    name, bounds = text.split(":", 1)
    values = tuple(int(x) for x in bounds.split(","))
    if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
        raise argparse.ArgumentTypeError("ROI must be name:left,top,right,bottom")
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise argparse.ArgumentTypeError("ROI name must use ASCII letters, numbers, - or _")
    return name, values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--model", choices=ALLOWED_MODELS, default="birefnet-general-lite")
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=1,
                        help="Same-session repeats for benchmarking; first mask is saved")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-mode", choices=("bounded", "default"), default="bounded",
                        help="bounded disables ONNX memory arena/pattern caching for coexistence with Photoshop")
    parser.add_argument("--preview-max-side", type=int, default=1600)
    parser.add_argument("--roi", action="append", type=parse_roi, default=[])
    args = parser.parse_args()
    if args.threads < 1 or args.preview_max_side < 64:
        parser.error("threads must be positive; preview-max-side must be >=64")
    args.output_dir = args.output_dir.resolve()
    args.cache_dir = args.cache_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["REMBG_HOME"] = str(args.cache_dir)
    os.environ["U2NET_HOME"] = str(args.cache_dir)
    os.environ["NUMBA_CACHE_DIR"] = str(args.cache_dir / "numba-cache")
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    import_started = time.perf_counter()
    from importlib.metadata import version
    import numpy as np
    from PIL import Image, ImageCms, ImageDraw, ImageOps
    from rembg import new_session, remove
    import onnxruntime as ort
    import_seconds = time.perf_counter() - import_started

    report = {
        "status": "running", "model": args.model, "network_for_inference": False,
        "cache_dir": str(args.cache_dir), "python": sys.version,
        "packages": {k: version(k) for k in ("rembg", "onnxruntime", "numpy", "pillow")},
        "threads": args.threads, "memory_mode": args.memory_mode, "import_seconds": import_seconds,
        "notes": ["Model weights may download on first use; source photos are never uploaded.",
                  "8-bit L PNG is a coverage mask only; it does not change the master photo bit depth.",
                  "Occluded anatomy, costume and hidden hair cannot be recovered by segmentation.",
                  "EXIF orientation is applied to in-memory inference and previews; source bytes stay unchanged."],
        "inputs": [],
    }
    report_path = args.output_dir / "mask-run.json"

    def write_report():
        pending_report = report_path.with_suffix(".pending.json")
        pending_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        pending_report.replace(report_path)

    def save_png(image, destination):
        pending = destination.with_suffix(".pending.png")
        image.save(pending, optimize=True)
        pending.replace(destination)

    try:
        session_started = time.perf_counter()
        options = ort.SessionOptions()
        options.intra_op_num_threads = args.threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        if args.memory_mode == "bounded":
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
        session = new_session(args.model, providers=["CPUExecutionProvider"], sess_opts=options)
        report["session_create_seconds"] = time.perf_counter() - session_started
        report["providers"] = session.inner_session.get_providers()
        report["session_reused_across_inputs_and_repeats"] = True
        report["model_files"] = [{"path": str(p), "bytes": p.stat().st_size, "sha256": file_sha256(p)}
                                 for p in args.cache_dir.rglob("*.onnx")]
        for input_index, source_path in enumerate(args.input):
            source_path = source_path.resolve(strict=True)
            before_sha = file_sha256(source_path)
            entry = {"source": str(source_path), "source_sha256_before": before_sha,
                     "inference_seconds": [], "first_inference_in_session": input_index == 0}
            report["inputs"].append(entry)
            with Image.open(source_path) as source:
                entry["source_mode"] = source.mode
                entry["source_stored_size"] = list(source.size)
                entry["source_exif_orientation"] = source.getexif().get(274, 1)
                entry["source_icc_sha256"] = hashlib.sha256(source.info.get("icc_profile", b"")).hexdigest()
                original_icc = source.info.get("icc_profile")
                rgb = ImageOps.exif_transpose(source).convert("RGB")
            entry["inference_size"] = list(rgb.size)
            inference_started = time.perf_counter()
            predicted = remove(rgb, session=session, only_mask=True,
                               alpha_matting=False, post_process_mask=False)
            entry["inference_seconds"].append(time.perf_counter() - inference_started)
            if predicted.size != rgb.size:
                raise RuntimeError(f"Mask dimensions {predicted.size} do not match source {rgb.size}")
            mask = predicted.convert("L")
            stem = f"{source_path.stem}-{before_sha[:8]}-{args.model}"
            mask_path = args.output_dir / f"{stem}-mask.png"
            if mask_path.resolve() == source_path:
                raise RuntimeError("Output would overwrite source")
            save_png(mask, mask_path)
            array = np.asarray(mask)
            entry.update({"mask": str(mask_path), "mask_mode": mask.mode, "mask_size": list(mask.size),
                          "mask_bit_depth": 8, "mask_sha256": file_sha256(mask_path),
                          "alpha_unique_values": int(np.unique(array).size),
                          "partial_alpha_pixels": int(np.count_nonzero((array > 0) & (array < 255))),
                          "foreground_pixels_at_128": int(np.count_nonzero(array >= 128)),
                          "foreground_fraction_at_128": float(np.mean(array >= 128))})
            entry["first_mask_saved_before_warm_test"] = True
            entry["warm_reuse_status"] = "not_tested"
            write_report()
            # Color-management affects QA previews only, never the source or mask.
            preview_rgb = rgb
            try:
                if original_icc:
                    preview_rgb = ImageCms.profileToProfile(rgb,
                        ImageCms.ImageCmsProfile(io.BytesIO(original_icc)),
                        ImageCms.createProfile("sRGB"), outputMode="RGB")
                    entry["preview_color_space"] = "converted from source ICC to sRGB"
                else:
                    entry["preview_color_space"] = "untagged RGB assumed sRGB for preview"
            except Exception as exc:
                entry["preview_color_space"] = f"ICC preview conversion unavailable: {exc}"
            def qa_views(photo, alpha):
                tint = Image.new("RGB", photo.size, (35, 230, 135))
                overlay = Image.composite(Image.blend(photo, tint, 0.38), photo, alpha)
                checker = Image.new("RGB", photo.size, (210,210,210))
                draw = ImageDraw.Draw(checker)
                for y in range(0, photo.height, 40):
                    for x in range(0, photo.width, 40):
                        if (x // 40 + y // 40) % 2:
                            draw.rectangle((x,y,x+39,y+39), fill=(150,150,150))
                return overlay, Image.composite(photo, checker, alpha)

            scaled_rgb = preview_rgb.copy()
            scaled_rgb.thumbnail((args.preview_max_side,args.preview_max_side), Image.Resampling.LANCZOS)
            scaled_mask = mask.resize(scaled_rgb.size, Image.Resampling.LANCZOS)
            overlay, cutout = qa_views(scaled_rgb, scaled_mask)
            preview_paths = {}
            for name, scaled in (("overlay", overlay), ("checker", cutout), ("original", scaled_rgb)):
                path = args.output_dir / f"{stem}-{name}-preview.png"
                save_png(scaled, path)
                preview_paths[name] = str(path)
            entry["previews"] = preview_paths
            entry["rois"] = []
            for roi_name, requested_bounds in args.roi:
                l, t, r, b = requested_bounds
                bounds = (max(0,l), max(0,t), min(rgb.width,r), min(rgb.height,b))
                if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                    raise ValueError(f"ROI {roi_name} is outside the image")
                roi_rgb = preview_rgb.crop(bounds)
                roi_overlay, roi_cutout = qa_views(roi_rgb, mask.crop(bounds))
                panels = [roi_rgb, roi_overlay, roi_cutout]
                board = Image.new("RGB", (panels[0].width * 3, panels[0].height))
                for panel_index, panel in enumerate(panels):
                    board.paste(panel, (panel.width * panel_index, 0))
                path = args.output_dir / f"{stem}-roi-{roi_name}.png"
                save_png(board, path)
                entry["rois"].append({"name":roi_name, "bounds":list(bounds), "path":str(path),
                                      "panel_order":["original", "foreground_overlay", "checker_cutout"]})
            after_sha = file_sha256(source_path)
            entry["source_sha256_after"] = after_sha
            entry["source_unchanged"] = before_sha == after_sha
            if not entry["source_unchanged"]:
                raise RuntimeError("Source file changed during analysis")
            # First result and QA previews survive a later warm-session allocation failure.
            write_report()
            for repetition in range(1, args.repeat):
                try:
                    inference_started = time.perf_counter()
                    repeated = remove(rgb, session=session, only_mask=True,
                                      alpha_matting=False, post_process_mask=False).convert("L")
                    entry["inference_seconds"].append(time.perf_counter() - inference_started)
                    if repeated.size != mask.size or not np.array_equal(array, np.asarray(repeated)):
                        raise RuntimeError("Same-session repeat mask changed unexpectedly")
                    entry["warm_reuse_status"] = "passed"
                except Exception as warm_exc:
                    entry["warm_reuse_status"] = "failed"
                    entry["warm_reuse_error"] = f"{type(warm_exc).__name__}: {warm_exc}"
                    write_report()
                    raise
                write_report()
        report["status"] = "passed"
        write_report()
        print(json.dumps({"status": report["status"], "report": str(report_path),
                          "session_create_seconds": report["session_create_seconds"],
                          "inputs": [{"mask":x["mask"], "inference_seconds":x["inference_seconds"]}
                                     for x in report["inputs"]]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_report()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
