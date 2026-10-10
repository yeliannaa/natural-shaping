#!/usr/bin/env python3
"""Build offline, unverified pose references without changing an input image.

Third-party imports are deliberately lazy so --help works without the optional
environment. No model is downloaded, no photo is retouched, and no mesh is made.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
REVIEW_STATUS = "needs_visual_review"
LANDMARK_NAMES = (
    "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
    "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER", "LEFT_EAR",
    "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT", "LEFT_SHOULDER",
    "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST",
    "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY", "LEFT_INDEX",
    "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB", "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL",
    "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
)
BODY_EDGES = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
    (24, 26), (26, 28), (27, 29), (29, 31), (27, 31),
    (28, 30), (30, 32), (28, 32),
)
DRAW_IDS = frozenset(range(11, 33))


class ReferenceError(Exception):
    """A useful stderr detail paired with a path-free artifact message."""

    def __init__(self, code, category, portable_message, detail=None):
        super().__init__(detail or portable_message)
        self.code = code
        self.category = category
        self.portable_message = portable_message


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def parser_for_cli():
    parser = argparse.ArgumentParser(
        description=(
            "Make optional offline MediaPipe body references. Requires a local "
            "model and a NEW output directory. Every result needs visual review."
        ),
        epilog=(
            "Coordinate basis: full image AFTER EXIF orientation is applied. "
            "Crop uses integer L T R B (right/bottom exclusive); anchor uses "
            "pixels in that full image. Pose indices start at 0 and are local "
            "to one run, not persistent identities. Exit codes: 0 success; "
            "2 arguments; 3 dependencies; 4 model; 5 source; 6 inference; "
            "7 output; 8 selection; 9 source changed."
        ),
    )
    parser.add_argument("--input", required=True, help="Read-only local source image.")
    parser.add_argument("--output-dir", required=True, help="New separate directory; existing directories are refused.")
    parser.add_argument("--model-path", required=True, help="Explicit local .task model; never downloaded automatically.")
    parser.add_argument("--crop", nargs=4, type=int, metavar=("L", "T", "R", "B"), help="Optional crop in EXIF-oriented full-source pixels.")
    parser.add_argument("--max-edge", type=int, default=1280, help="Inference and preview longest edge, 64..4096 (default 1280); never upsample.")
    parser.add_argument("--num-poses", type=int, default=4, help="Maximum poses requested, 1..32 (default 4); does not select a subject.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--pose-index", type=int, help="Explicit zero-based detected pose index; still unverified.")
    selection.add_argument("--subject-anchor", nargs=2, type=float, metavar=("X", "Y"), help="Full-source pixel click; match nearest reported skeleton, then review visually.")
    parser.add_argument("--segmentation", action="store_true", help="Also save unverified model probability references; these are not precise body masks.")
    parser.add_argument("--display-score-split", type=float, default=0.8, help="Display-only visibility/presence score split, 0..1 (default 0.8); never verifies a point.")
    return parser


def validate_arguments(parser, args):
    if not 64 <= args.max_edge <= 4096:
        parser.error("--max-edge must be between 64 and 4096")
    if not 1 <= args.num_poses <= 32:
        parser.error("--num-poses must be between 1 and 32")
    if args.pose_index is not None and args.pose_index < 0:
        parser.error("--pose-index must be zero or greater")
    if not math.isfinite(args.display_score_split) or not 0 <= args.display_score_split <= 1:
        parser.error("--display-score-split must be a finite number between 0 and 1")
    if args.subject_anchor and not all(math.isfinite(value) for value in args.subject_anchor):
        parser.error("--subject-anchor coordinates must be finite")
    for argument in ("input", "model_path", "output_dir"):
        if "://" in getattr(args, argument):
            parser.error("--" + argument.replace("_", "-") + " must be a filesystem path, not a URL")


def reserve_output(args):
    output = Path(args.output_dir).expanduser().resolve()
    skill_root = Path(__file__).resolve().parent.parent
    if output == skill_root or skill_root in output.parents:
        raise ReferenceError(2, "arguments", "Output must be separate from the skill directory.")
    try:
        # exist_ok=False also refuses an empty directory and a concurrent run.
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ReferenceError(7, "output", "Output directory is unavailable or already exists; nothing was overwritten.", str(exc)) from exc
    return output


def write_json(path, value, update=False):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if update:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
        temporary.replace(path)
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)


def save_image(image, path, file_format, **options):
    with path.open("xb") as stream:
        image.save(stream, format=file_format, **options)


def dependencies():
    modules = {}
    missing = []
    for name in ("mediapipe", "numpy", "PIL.Image", "PIL.ImageDraw", "PIL.ImageOps"):
        try:
            modules[name] = importlib.import_module(name)
        except Exception as exc:
            missing.append(f"{name}: {type(exc).__name__}: {exc}")
    if missing:
        raise ReferenceError(
            3, "dependencies", "Optional body-reference dependencies are missing or cannot load; no packages were installed.",
            "Optional dependencies could not load. Use a separate environment with requirements-body-reference.txt.\n" + "\n".join(missing),
        )
    return modules


def read_model(path):
    try:
        if not path.is_file():
            raise OSError("Not a regular model file: " + str(path))
        data = path.read_bytes()
        if not data:
            raise OSError("Model file is empty: " + str(path))
        return data
    except OSError as exc:
        raise ReferenceError(4, "model", "Explicit local model is missing, empty, or unreadable; no model was downloaded.", str(exc)) from exc


def read_source(path, Image, ImageOps):
    try:
        if not path.is_file():
            raise OSError("Not a regular input file: " + str(path))
        data = path.read_bytes()
        with Image.open(io.BytesIO(data)) as encoded:
            if getattr(encoded, "n_frames", 1) != 1:
                raise ValueError("Use a single-frame source image.")
            encoded_size = list(encoded.size)
            exif_orientation = encoded.getexif().get(274)
            source_format = encoded.format
            oriented = ImageOps.exif_transpose(encoded)
            oriented.load()
            source = oriented.convert("RGB")
        return source, {
            "file_name": path.name,
            "sha256_before": sha256_bytes(data),
            "encoded_size": encoded_size,
            "exif_orientation": exif_orientation,
            "format": source_format,
            "source_size": list(source.size),
            "coordinate_basis": "full_source_after_exif_transpose",
            "coordinate_convention": "top_left_origin_xy_pixels; model normalized coordinates map to image edges [0,width] and [0,height]",
            "read_only": True,
        }
    except Exception as exc:
        raise ReferenceError(5, "source", "Source image cannot be read as a single-frame image; see stderr for local detail.", str(exc)) from exc


def image_mapping(source, args, Image):
    width, height = source.size
    crop = list(args.crop) if args.crop else [0, 0, width, height]
    left, top, right, bottom = crop
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ReferenceError(2, "arguments", "Crop must be nonempty and inside the EXIF-oriented full source.", f"Invalid crop {crop} for oriented source {width} x {height}")
    if args.subject_anchor is not None:
        x, y = args.subject_anchor
        if not (0 <= x < width and 0 <= y < height):
            raise ReferenceError(2, "arguments", "Subject anchor must be inside the EXIF-oriented full source.")
    crop_image = source.crop(tuple(crop))
    crop_size = list(crop_image.size)
    crop_image.thumbnail((args.max_edge, args.max_edge), Image.Resampling.LANCZOS)
    preview = source.copy()
    preview.thumbnail((args.max_edge, args.max_edge), Image.Resampling.LANCZOS)
    input_width, input_height = crop_image.size
    mapping = {
        "coordinate_basis": "full_source_after_exif_transpose",
        "crop_pixels_ltrb": crop,
        "crop_right_bottom_exclusive": True,
        "crop_size": crop_size,
        "inference_size": list(crop_image.size),
        "preview_size": list(preview.size),
        "source_pixels_per_inference_pixel_xy": [crop_size[0] / input_width, crop_size[1] / input_height],
        "preview_pixels_per_source_pixel_xy": [preview.width / width, preview.height / height],
        "formula_source_xy": "[L + model_x_normalized * crop_width, T + model_y_normalized * crop_height]",
        "formula_from_inference_pixels": "[L + inference_x * crop_width/inference_width, T + inference_y * crop_height/inference_height]",
        "landmark_coordinates_are_not_clamped": True,
        "z_note": "z is the model's crop-width-normalized relative depth, not measured source-pixel or metric depth",
    }
    return crop_image, preview, mapping


def finite_float(value, label):
    number = float(value)
    if not math.isfinite(number):
        raise ReferenceError(6, "inference", "Model returned nonfinite landmark values.", "Nonfinite model value: " + label)
    return number


def map_poses(result, mapping, source_size):
    left, top, right, bottom = mapping["crop_pixels_ltrb"]
    crop_width, crop_height = right - left, bottom - top
    input_width, input_height = mapping["inference_size"]
    source_width, source_height = source_size
    poses = []
    for pose_index, landmarks in enumerate(result.pose_landmarks):
        if len(landmarks) != len(LANDMARK_NAMES):
            raise ReferenceError(6, "inference", "Expected 33 pose landmarks per detected pose.")
        points = []
        for index, landmark in enumerate(landmarks):
            x = finite_float(landmark.x, "x")
            y = finite_float(landmark.y, "y")
            sx, sy = left + x * crop_width, top + y * crop_height
            points.append({
                "id": index,
                "name": LANDMARK_NAMES[index],
                "model_normalized_xy": [x, y],
                "model_normalized_z": finite_float(landmark.z, "z"),
                "inference_xy_px": [x * input_width, y * input_height],
                "source_xy_px": [sx, sy],
                "source_normalized_xy": [sx / source_width, sy / source_height],
                "visibility": finite_float(landmark.visibility, "visibility"),
                "presence": finite_float(landmark.presence, "presence"),
                "outside_source_canvas": not (0 <= sx < source_width and 0 <= sy < source_height),
                "outside_inference_canvas": not (0 <= x < 1 and 0 <= y < 1),
                "review_status": REVIEW_STATUS,
            })
        poses.append({
            "pose_index": pose_index,
            "review_status": REVIEW_STATUS,
            "landmarks": points,
            "outside_source_canvas_ids": [p["id"] for p in points if p["outside_source_canvas"]],
        })
    return poses


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return math.dist(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator
    t = max(0.0, min(1.0, t))
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def choose_pose(poses, args, mapping):
    selection = {"method": "none", "selected_pose": None, "review_status": REVIEW_STATUS}
    if args.pose_index is not None:
        if args.pose_index >= len(poses):
            raise ReferenceError(8, "selection", "Requested pose index does not exist in this run.", f"Requested pose index {args.pose_index}; detected {len(poses)} pose(s).")
        selection.update(method="explicit_pose_index", selected_pose=args.pose_index)
    elif args.subject_anchor is not None:
        anchor = list(args.subject_anchor)
        left, top, right, bottom = mapping["crop_pixels_ltrb"]
        selection.update(method="explicit_subject_anchor", anchor_source_xy_px=anchor)
        selection["matching_rule"] = "minimum source-pixel distance to reported in-source body skeleton segments or any in-source landmark; model scores do not verify the match"
        distances = []
        for pose in poses:
            points = pose["landmarks"]
            candidates = [math.dist(anchor, p["source_xy_px"]) for p in points if not p["outside_source_canvas"]]
            for a, b in BODY_EDGES:
                if not points[a]["outside_source_canvas"] and not points[b]["outside_source_canvas"]:
                    candidates.append(point_segment_distance(anchor, points[a]["source_xy_px"], points[b]["source_xy_px"]))
            distances.append(min(candidates) if candidates else None)
        selection["anchor_distance_px_by_pose"] = distances
        # An anchor outside the requested crop cannot identify a crop subject.
        if not (left <= anchor[0] < right and top <= anchor[1] < bottom):
            selection["unresolved_reason"] = "anchor_outside_inference_crop"
        else:
            ranked = sorted((distance, index) for index, distance in enumerate(distances) if distance is not None)
            if not ranked:
                selection["unresolved_reason"] = "no_in_source_landmarks"
            elif len(ranked) > 1 and math.isclose(ranked[0][0], ranked[1][0], rel_tol=1e-9, abs_tol=1e-6):
                selection["unresolved_reason"] = "ambiguous_equal_anchor_distance"
            else:
                selection["selected_pose"] = ranked[0][1]
                selection["matching_warning"] = "Nearest reported skeleton may be the wrong person; compare source and all pose previews."
    elif len(poses) == 1:
        selection.update(method="unique_detection_unverified", selected_pose=0)
    elif not poses:
        selection["unresolved_reason"] = "no_poses_detected"
    else:
        selection["unresolved_reason"] = "multiple_poses_without_explicit_selection"
    return selection


def display_upper_band(point, threshold):
    return min(point["visibility"], point["presence"]) >= threshold


def dashed(draw, a, b, color, width):
    length = math.dist(a, b)
    if length < 0.1:
        return
    for start in range(0, math.ceil(length), 16):
        end = min(start + 9, length)
        p = tuple(a[i] + (b[i] - a[i]) * start / length for i in range(2))
        q = tuple(a[i] + (b[i] - a[i]) * end / length for i in range(2))
        draw.line((p, q), fill=color, width=width)


def draw_landmarks(poses, preview_size, source_size, threshold, Image, ImageDraw):
    canvas = Image.new("RGBA", preview_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    scale_x, scale_y = preview_size[0] / source_size[0], preview_size[1] / source_size[1]
    upper, lower = (57, 255, 160, 240), (255, 183, 50, 240)
    for pose in poses:
        points = pose["landmarks"]
        positions = [(p["source_xy_px"][0] * scale_x, p["source_xy_px"][1] * scale_y) for p in points]
        for a, b in BODY_EDGES:
            if points[a]["outside_source_canvas"] or points[b]["outside_source_canvas"]:
                continue
            if display_upper_band(points[a], threshold) and display_upper_band(points[b], threshold):
                draw.line((positions[a], positions[b]), fill=(0, 0, 0, 180), width=7)
                draw.line((positions[a], positions[b]), fill=upper, width=3)
            else:
                dashed(draw, positions[a], positions[b], lower, 3)
        in_source_body = []
        for p, (x, y) in zip(points, positions):
            if p["id"] not in DRAW_IDS or p["outside_source_canvas"]:
                continue
            in_source_body.append((x, y))
            color = upper if display_upper_band(p, threshold) else lower
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color, outline=(0, 0, 0, 230), width=2)
            label = str(p["id"])
            box = draw.textbbox((x + 7, y - 7), label)
            draw.rectangle((box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1), fill=(15, 20, 25, 220))
            draw.text((x + 7, y - 7), label, fill=(255, 255, 255, 255))
        if in_source_body:
            x = max(2, min(p[0] for p in in_source_body))
            y = max(2, min(p[1] for p in in_source_body) - 19)
            label = f"P{pose['pose_index']} | needs visual review"
            box = draw.textbbox((x, y), label)
            draw.rectangle((box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2), fill=(15, 20, 25, 230))
            draw.text((x, y), label, fill=(255, 255, 255, 255))
    return canvas


def composite_preview(preview, overlay, Image):
    return Image.alpha_composite(preview.convert("RGBA"), overlay).convert("RGB")


def legend_text(threshold):
    return (
        "OFFLINE BODY REFERENCE — NEEDS VISUAL REVIEW\n"
        "Pose index P0, P1, ... is zero-based and specific to this run.\n"
        "Body points 11..32 are drawn; all 33 landmarks are retained in JSON.\n"
        f"Green solid: both model visibility and presence >= {threshold:g}.\n"
        f"Amber/dashed: at least one model score < {threshold:g}.\n"
        "These bands only control display. Neither band verifies a landmark.\n"
        "Visibility and presence are model scores, not observed visibility,\n"
        "anatomical correctness, or measured edit safety.\n"
        "Out-of-source landmarks are retained in JSON and omitted from drawing.\n"
        "Every pose and landmark remains needs_visual_review.\n"
        "Coordinates refer to the full source AFTER EXIF orientation is applied.\n"
        "Crop/resize mappings use actual dimensions; coordinates are not clamped.\n"
        "A sole detection is selected provisionally, not identity-verified.\n"
        "Multiple detections require an explicit index or subject anchor.\n"
        "An anchor chooses a nearest reported skeleton and may choose the wrong person.\n"
        "Optional segmentation files are unverified probability references.\n"
        "They do not define a precise body, costume, or subject selection mask.\n"
        "Outside-crop zero padding was not evaluated by the model.\n"
        "Segmentation preview outlines use 0.5 only for visualization.\n"
        "No source pixels are changed; no mesh or retouch is generated.\n"
    )


def save_segmentation(mask, pose, output, preview, mapping, np, Image, artifacts):
    probability = np.squeeze(mask.numpy_view().copy())
    if probability.ndim != 2 or not np.isfinite(probability).all():
        raise ReferenceError(6, "inference", "Expected a finite 2D model segmentation probability reference.")
    stem = f"pose-{pose['pose_index']:03d}-segmentation-reference"
    raw_name = stem + ".npz"
    with (output / raw_name).open("xb") as stream:
        np.savez_compressed(stream, probability=probability)
    artifacts.append(raw_name)
    crop = mapping["crop_pixels_ltrb"]
    sx, sy = mapping["preview_pixels_per_source_pixel_xy"]
    destination = [round(crop[0] * sx), round(crop[1] * sy), round(crop[2] * sx), round(crop[3] * sy)]
    dest_width, dest_height = destination[2] - destination[0], destination[3] - destination[1]
    probability_image = Image.fromarray((np.clip(probability, 0, 1) * 255).astype(np.uint8))
    reference = Image.new("L", preview.size, 0)
    # Tiny crops can round to less than one preview pixel; raw inference data
    # remains available, and there is no fictitious enlarged source footprint.
    if dest_width > 0 and dest_height > 0:
        resized = probability_image.resize((dest_width, dest_height), Image.Resampling.BILINEAR)
        reference.paste(resized, tuple(destination[:2]))
    png_name = stem + ".png"
    save_image(reference, output / png_name, "PNG")
    artifacts.append(png_name)
    view = np.asarray(reference, dtype=np.float32) / 255.0
    rgba = np.zeros((preview.height, preview.width, 4), dtype=np.uint8)
    rgba[:, :, :3] = (45, 200, 190)
    rgba[:, :, 3] = (view * 68).astype(np.uint8)
    region = view >= 0.5
    edge = np.zeros_like(region)
    edge[1:, :] |= region[1:, :] != region[:-1, :]
    edge[:, 1:] |= region[:, 1:] != region[:, :-1]
    rgba[edge] = (80, 255, 225, 235)
    overlay = Image.fromarray(rgba)
    jpg_name = stem + "-preview.jpg"
    save_image(composite_preview(preview, overlay, Image), output / jpg_name, "JPEG", quality=95, subsampling=0)
    artifacts.append(jpg_name)
    pose["segmentation_reference"] = {
        "review_status": REVIEW_STATUS,
        "raw_probability_file": raw_name,
        "raw_probability_size_wh": [int(probability.shape[1]), int(probability.shape[0])],
        "probability_preview_file": png_name,
        "composite_preview_file": jpg_name,
        "preview_destination_ltrb": destination,
        "raw_coordinate_basis": "model_inference_image",
        "probability_preview_encoding": "8_bit_clipped_probability; zero padding outside requested crop",
        "not_a_precise_body_mask": True,
        "outline_threshold_display_only": 0.5,
    }


def run_reference(args, output, manifest, artifacts):
    started = time.perf_counter()
    model_path = Path(args.model_path).expanduser().resolve()
    source_path = Path(args.input).expanduser().resolve()
    model_bytes = read_model(model_path)
    modules = dependencies()
    mp, np = modules["mediapipe"], modules["numpy"]
    Image, ImageDraw, ImageOps = modules["PIL.Image"], modules["PIL.ImageDraw"], modules["PIL.ImageOps"]
    source, source_record = read_source(source_path, Image, ImageOps)
    manifest["source"] = dict(source_record)
    crop_image, preview, mapping = image_mapping(source, args, Image)
    model_record = {"file_name": model_path.name, "sha256": sha256_bytes(model_bytes), "loading": "explicit_local_file_bytes", "delegate": "CPU"}
    settings = {
        "max_edge": args.max_edge,
        "num_poses_requested": args.num_poses,
        "min_pose_detection_confidence": 0.5,
        "min_pose_presence_confidence": 0.5,
        "display_score_split": args.display_score_split,
        "display_score_split_does_not_verify_points": True,
        "segmentation_requested": args.segmentation,
    }
    try:
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=model_bytes, delegate=mp.tasks.BaseOptions.Delegate.CPU),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_poses=args.num_poses,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            output_segmentation_masks=args.segmentation,
        )
        creation_started = time.perf_counter()
        detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        creation_seconds = time.perf_counter() - creation_started
    except Exception as exc:
        raise ReferenceError(4, "model", "Local model could not initialize the CPU pose landmarker; see stderr for detail.", str(exc)) from exc
    try:
        with detector:
            inference_started = time.perf_counter()
            result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(crop_image).copy()))
            inference_seconds = time.perf_counter() - inference_started
        poses = map_poses(result, mapping, source.size)
    except ReferenceError:
        raise
    except Exception as exc:
        raise ReferenceError(6, "inference", "Pose inference failed; no edit was performed.", str(exc)) from exc
    selection = choose_pose(poses, args, mapping)
    report = {
        "schema_version": SCHEMA_VERSION,
        "review_status": REVIEW_STATUS,
        "created_utc": utc_now(),
        "source": source_record,
        "mapping": mapping,
        "model": model_record,
        "runtime": {"python": platform.python_version(), "mediapipe": mp.__version__, "numpy": np.__version__, "pillow": Image.__version__},
        "settings": settings,
        "inference_rgb_bytes_sha256": sha256_bytes(crop_image.tobytes()),
        "detected_poses": len(poses),
        "selected_pose": selection["selected_pose"],
        "selection": selection,
        "all_poses": poses,
        "score_interpretation": "visibility/presence are model scores, not observed visibility, anatomical verification, or permission to edit",
        "pose_index_scope": "zero_based_and_local_to_this_run; model output order is not persistent identity",
        "visualization": {
            "drawn_landmark_ids": sorted(DRAW_IDS),
            "solid_green": "both visibility and presence >= display_score_split",
            "dashed_amber": "at least one score below display_score_split",
            "outside_source_points": "retained in JSON, omitted from drawings",
            "all_bands_review_status": REVIEW_STATUS,
        },
        "warnings": [
            "Every pose and landmark needs comparison against the source image.",
            "Model may miss people, assign clothing/background points, or place occluded joints incorrectly.",
            "A unique detection or anchor/index selection is not identity verification.",
            "No mesh, anatomy correction, precise body mask, or retouch is produced.",
        ],
        "timing_seconds": {"model_creation": round(creation_seconds, 3), "inference": round(inference_seconds, 3)},
    }
    save_image(preview, output / "source_preview.jpg", "JPEG", quality=94, subsampling=0)
    artifacts.append("source_preview.jpg")
    with (output / "legend.txt").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(legend_text(args.display_score_split))
    artifacts.append("legend.txt")
    for pose in poses:
        stem = f"pose-{pose['pose_index']:03d}"
        overlay = draw_landmarks([pose], preview.size, source.size, args.display_score_split, Image, ImageDraw)
        png_name, jpg_name = stem + "-landmarks.png", stem + "-preview.jpg"
        save_image(overlay, output / png_name, "PNG")
        artifacts.append(png_name)
        save_image(composite_preview(preview, overlay, Image), output / jpg_name, "JPEG", quality=95, subsampling=0)
        artifacts.append(jpg_name)
        pose["landmark_overlay_file"] = png_name
        pose["composite_preview_file"] = jpg_name
    combined = draw_landmarks(poses, preview.size, source.size, args.display_score_split, Image, ImageDraw)
    save_image(combined, output / "all-poses-landmarks.png", "PNG")
    artifacts.append("all-poses-landmarks.png")
    save_image(composite_preview(preview, combined, Image), output / "all-poses-preview.jpg", "JPEG", quality=95, subsampling=0)
    artifacts.append("all-poses-preview.jpg")
    if args.segmentation:
        masks = result.segmentation_masks or []
        if len(masks) != len(poses):
            raise ReferenceError(6, "inference", "Segmentation reference count does not match detected pose count.")
        for mask, pose in zip(masks, poses):
            save_segmentation(mask, pose, output, preview, mapping, np, Image, artifacts)
    try:
        after = sha256_file(source_path)
    except OSError as exc:
        raise ReferenceError(9, "source_changed", "Source could not be rechecked after inference.", str(exc)) from exc
    source_record["sha256_after"] = after
    source_record["source_unchanged"] = source_record["sha256_before"] == after
    manifest["source"] = dict(source_record)
    if not source_record["source_unchanged"]:
        raise ReferenceError(9, "source_changed", "Source changed during this run; outputs must not be used as a verified source reference.")
    report["timing_seconds"]["total_with_outputs"] = round(time.perf_counter() - started, 3)
    write_json(output / "body_reference.json", report)
    artifacts.append("body_reference.json")
    return report


def main(argv=None):
    parser = parser_for_cli()
    args = parser.parse_args(argv)
    validate_arguments(parser, args)
    output = None
    manifest = None
    artifacts = []
    try:
        output = reserve_output(args)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "running",
            "review_status": REVIEW_STATUS,
            "started_utc": utc_now(),
            "artifacts": artifacts,
            "portable_evidence": "No absolute input, model, output, or interpreter paths are stored.",
        }
        write_json(output / "manifest.json", manifest)
        report = run_reference(args, output, manifest, artifacts)
        manifest.update(status="success", completed_utc=utc_now(), report_file="body_reference.json", detected_poses=report["detected_poses"], selected_pose=report["selected_pose"])
        write_json(output / "manifest.json", manifest, update=True)
        print(json.dumps({"status": "success", "output_dir": str(output), "detected_poses": report["detected_poses"], "selected_pose": report["selected_pose"], "review_status": REVIEW_STATUS, "source_unchanged": report["source"]["source_unchanged"]}, ensure_ascii=True))
        return 0
    except Exception as exc:
        error = exc if isinstance(exc, ReferenceError) else ReferenceError(7, "output", "Output generation failed; any partial artifacts are not a completed reference.", f"{type(exc).__name__}: {exc}")
        if manifest is not None:
            manifest.update(status="failed", completed_utc=utc_now(), exit_code=error.code, error={"category": error.category, "message": error.portable_message})
            try:
                write_json(output / "manifest.json", manifest, update=True)
            except Exception as manifest_error:
                print(f"Could not mark failure manifest: {manifest_error}", file=sys.stderr)
        print(f"body-reference error [{error.category}, exit {error.code}]: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
