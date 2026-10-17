"""Read-only binding checks for an actual retouch delivery; no aesthetic scoring.

Python standard library + Pillow. Paths in the JSON are relative to that JSON.
Run with --print-binding before recording the actual visual review, then validate.
"""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path, PureWindowsPath

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    Image = ImageChops = ImageDraw = None


class ContractError(Exception):
    def __init__(self, code, field, detail):
        super().__init__(detail)
        self.error = {"code": code, "field": field, "detail": detail}


def need(condition, code, field, detail):
    if not condition:
        raise ContractError(code, field, detail)


def integers(value, length, field):
    need(isinstance(value, list) and len(value) == length and
         all(type(v) is int for v in value), "invalid_coordinates", field,
         "Use an integer array of length %s; booleans are not coordinates." % length)
    return value


def rectangle(value, canvas, field):
    x0, y0, x1, y1 = integers(value, 4, field)
    need(0 <= x0 < x1 <= canvas[0] and 0 <= y0 < y1 <= canvas[1],
         "rectangle_out_of_bounds", field, "Use a nonempty half-open rectangle within the working canvas.")
    return value


def intersection(a, b):
    r = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return r if r[0] < r[2] and r[1] < r[3] else None


def valid_sha(value, field):
    need(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
         "invalid_sha256", field, "Use a lowercase SHA256 hex digest.")
    return value


def local_path(value, base, field):
    need(isinstance(value, str) and bool(value.strip()) and "\x00" not in value,
         "invalid_path", field, "Use a nonempty relative local file path.")
    win = PureWindowsPath(value)
    need(not win.drive and not win.root and not value.startswith(("/", "\\")) and
         re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) is None,
         "nonlocal_path", field, "Absolute paths, URI schemes and network paths are not accepted.")
    target = (base / value.replace("\\", "/")).resolve()
    need(not str(target).startswith(("\\\\", "//")), "nonlocal_path", field,
         "The resolved file must be local.")
    return target


def inspect_files(files, base):
    need(isinstance(files, dict) and {"source", "composite", "export"} <= set(files) and
         set(files) <= {"source", "composite", "candidate", "export"},
         "invalid_files", "files", "Require source, composite and export; candidate is optional.")
    need(Image is not None, "dependency_missing", "Pillow", "Install Pillow to inspect image dimensions and pixels.")
    found = {}
    for name, entry in files.items():
        field = "files." + name
        need(isinstance(entry, dict), "invalid_file", field, "A file entry must be an object.")
        expected_sha = valid_sha(entry.get("sha256"), field + ".sha256")
        size = integers(entry.get("size"), 2, field + ".size")
        need(min(size) > 0, "invalid_size", field + ".size", "Image dimensions must be positive.")
        target = local_path(entry.get("path"), base, field + ".path")
        try:
            raw = target.read_bytes()
        except OSError as exc:
            raise ContractError("file_unreadable", field, "Local file cannot be read (%s)." % type(exc).__name__)
        digest = hashlib.sha256(raw).hexdigest()
        need(digest == expected_sha, "file_sha_mismatch", field, "Actual file bytes differ from the bound SHA256.")
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                need(getattr(opened, "n_frames", 1) == 1, "multiple_frames", field, "Bind a single-frame image.")
                opened.load()
                image = opened.copy()
                image.info = dict(opened.info)
                image_format = opened.format
                orientation = opened.getexif().get(274, 1)
        except ContractError:
            raise
        except Exception as exc:
            raise ContractError("image_unreadable", field, "Image cannot be decoded (%s)." % type(exc).__name__)
        need(list(image.size) == size, "file_size_mismatch", field,
             "Actual image dimensions differ from the bound size.")
        png_depth = None
        if image_format == "PNG":
            # Pillow may decode 16-bit RGB/RGBA to an 8-bit RGB/RGBA mode.
            # Native depth must come from the bound file, never from image.mode.
            need(len(raw) >= 33 and raw[:8] == b"\x89PNG\r\n\x1a\n" and
                 raw[8:12] == b"\x00\x00\x00\x0d" and raw[12:16] == b"IHDR",
                 "invalid_png_header", field, "PNG must start with a complete IHDR.")
            png_depth = raw[24]
        found[name] = {"sha256": digest, "size": size, "format": image_format,
                       "image": image, "orientation": orientation,
                       "png_depth_bits": png_depth}
    return found


def binding_sha256(data):
    """Bind relevant declarations; moving the record and relative files does not change the binding."""
    payload = {"schema_version": data["schema_version"],
               "files": {k: {"sha256": v["sha256"], "size": v["size"]}
                         for k, v in data["files"].items()},
               "mapping": data["mapping"], "responsibilities": data["responsibilities"],
               "protections": data["protections"]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def same_png_representation(a, b, field):
    need(a["format"] == b["format"] == "PNG", "exact_requires_png", field,
         "Exact pixel checks require lossless PNG files.")
    need(a["png_depth_bits"] == b["png_depth_bits"] == 8,
         "exact_png_depth_unsupported", field,
         "Exact delivery checks support native 8-bit PNG only. Use binding_only without "
         "exact_pixels protections, or verify_native_png.ps1 for a separate native-depth check.")
    ia, ib = a["image"], b["image"]
    need(ia.mode == ib.mode and ia.mode in {"L", "LA", "RGB", "RGBA"},
         "exact_representation_mismatch", field, "Exact checks support matching L, LA, RGB or RGBA modes.")
    keys = ("icc_profile", "gamma", "srgb", "chromaticity", "transparency")
    need(all(ia.info.get(k) == ib.info.get(k) for k in keys) and
         a["orientation"] == b["orientation"] == 1,
         "exact_representation_mismatch", field,
         "Exact checks require matching ICC, PNG color/transparency declarations and native orientation.")


def difference_mask(a, b):
    # RGBA conversion includes RGB+tRNS alpha. Check every channel, including hidden RGB.
    bands = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).split()
    maximum = bands[0]
    for band in bands[1:]:
        maximum = ImageChops.lighter(maximum, band)
    return maximum.point(lambda value: 255 if value else 0)


def relative_crop(image, rect, origin):
    return image.crop((rect[0] - origin[0], rect[1] - origin[1],
                       rect[2] - origin[0], rect[3] - origin[1]))


def check_pixels(data, files, canvas, crop, source_rect):
    mapping = data["mapping"]
    mode = mapping.get("export_crop_check")
    need(mode in {"exact_png", "binding_only"}, "invalid_export_crop_check",
         "mapping.export_crop_check", "Choose exact_png or binding_only explicitly.")
    results = {"export_crop": "bound_dimensions_only", "protections": []}
    if mode == "exact_png":
        same_png_representation(files["composite"], files["export"], "mapping.export_crop_check")
        delta = difference_mask(files["composite"]["image"].crop(tuple(crop)), files["export"]["image"])
        need(delta.getbbox() is None, "export_crop_pixels_mismatch", "files.export",
             "Actual export pixels differ from the declared composite crop.")
        results["export_crop"] = "verified_exact_pixels"
    overlap = intersection(source_rect, crop)
    for item in data["protections"]:
        if item["type"] != "exact_pixels":
            continue
        field = "protections." + item["id"]
        same_png_representation(files["source"], files["export"], field)
        need(overlap is not None, "empty_exact_scope", field, "Source and export have no common valid pixels.")
        region = overlap if item["scope"] == "outside_responsibilities" else item["rect"]
        need(intersection(region, overlap) == region, "exact_roi_outside_overlap", field,
             "An exact ROI must be entirely visible in both source and export.")
        mask = Image.new("L", (region[2] - region[0], region[3] - region[1]), 255)
        if item["scope"] == "outside_responsibilities":
            draw = ImageDraw.Draw(mask)
            for responsibility in data["responsibilities"]:
                cut = intersection(region, responsibility["rect"])
                if cut:
                    draw.rectangle((cut[0] - region[0], cut[1] - region[1],
                                    cut[2] - region[0] - 1, cut[3] - region[1] - 1), fill=0)
        compared = mask.histogram()[255]
        need(compared > 0, "empty_exact_scope", field, "Exact protection must inspect at least one pixel.")
        first = relative_crop(files["source"]["image"], region, data["mapping"]["source_origin"])
        second = relative_crop(files["export"]["image"], region, crop[:2])
        changed = ImageChops.multiply(difference_mask(first, second), mask).histogram()[255]
        need(changed == 0, "protected_pixels_changed", field,
             "%s protected pixels changed outside the declared allowed scope." % changed)
        results["protections"].append({"id": item["id"], "compared_pixels": compared, "changed_pixels": changed})
    return results


def validate_declarations(data, files):
    mapping = data.get("mapping")
    need(isinstance(mapping, dict), "invalid_mapping", "mapping", "Require an explicit working-canvas mapping.")
    canvas = integers(mapping.get("canvas_size"), 2, "mapping.canvas_size")
    need(min(canvas) > 0 and files["composite"]["size"] == canvas, "canvas_size_mismatch",
         "mapping.canvas_size", "Working canvas must match the actual composite dimensions.")
    origin = integers(mapping.get("source_origin"), 2, "mapping.source_origin")
    size = files["source"]["size"]
    source_rect = [origin[0], origin[1], origin[0] + size[0], origin[1] + size[1]]
    rectangle(source_rect, canvas, "mapping.source_origin")
    crop = rectangle(mapping.get("delivery_crop"), canvas, "mapping.delivery_crop")
    need(files["export"]["size"] == [crop[2] - crop[0], crop[3] - crop[1]],
         "export_crop_size_mismatch", "mapping.delivery_crop", "Export size must equal the native crop size; implicit resizing is unsupported.")
    for key in ("responsibilities", "protections"):
        need(isinstance(data.get(key), list), "invalid_regions", key, "Use a list, including an empty list when appropriate.")
        ids = set()
        for item in data[key]:
            need(isinstance(item, dict) and isinstance(item.get("id"), str) and
                 re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]) is not None and item["id"] not in ids,
                 "invalid_region_id", key, "Use unique nonempty ASCII identifiers.")
            ids.add(item["id"])
            field = key + "." + item["id"]
            if key == "responsibilities":
                rectangle(item.get("rect"), canvas, field + ".rect")
                continue
            kind = item.get("type")
            need(kind in {"exact_pixels", "geometry", "semantic"}, "invalid_protection_type", field,
                 "Choose exact_pixels, geometry or semantic.")
            if kind == "exact_pixels":
                need(item.get("scope") in {"outside_responsibilities", "roi"}, "invalid_exact_scope", field,
                     "Choose outside_responsibilities or roi.")
                if item["scope"] == "outside_responsibilities":
                    need("rect" not in item, "ambiguous_exact_scope", field,
                         "outside_responsibilities uses the full source/export overlap, not an extra small rectangle.")
                    continue
            region = rectangle(item.get("rect"), canvas, field + ".rect")
            need(intersection(region, crop) == region, "protection_outside_export", field,
                 "A protected ROI must be present in the actual delivery crop.")
    return canvas, crop, source_rect


def validate_review(data, files, binding):
    review = data.get("visual_review")
    need(isinstance(review, dict), "missing_visual_review", "visual_review", "Record the actual visual review of this export.")
    need(review.get("kind") == "manual_visual", "invalid_review_kind", "visual_review.kind",
         "Use manual_visual for an assistant or human looking at the actual file.")
    need(review.get("export_sha256") == files["export"]["sha256"], "stale_review_export",
         "visual_review.export_sha256", "The review is not bound to the actual export bytes.")
    need(review.get("binding_sha256") == binding, "stale_review_binding", "visual_review.binding_sha256",
         "File identity, dimensions, mapping or protected scope changed after this review.")
    views = review.get("views")
    need(isinstance(views, list) and all(isinstance(v, str) for v in views) and
         {"fit", "native", "context"} <= set(views), "missing_review_view", "visual_review.views",
         "Record fit, native and complete affected-connection context views.")
    gates = review.get("gates")
    need(isinstance(gates, dict) and all(gates.get(k) == "pass" for k in ("goal", "structure", "finish")),
         "review_gate_not_passed", "visual_review.gates", "All three actual review conclusions must be pass for a completed delivery.")
    manual = review.get("protection_results", {})
    need(isinstance(manual, dict), "invalid_protection_review", "visual_review.protection_results", "Use an object keyed by protection id.")
    for item in data["protections"]:
        if item["type"] == "exact_pixels":
            continue
        result = manual.get(item["id"])
        need(isinstance(result, dict) and result.get("status") == "pass" and
             isinstance(result.get("note"), str) and bool(result["note"].strip()),
             "missing_protection_review", "visual_review.protection_results." + item["id"],
             "Geometry and semantic protection need a bound visual conclusion and a specific observation.")


def verify_record(record_path, require_review=True):
    report = {"status": "mechanical_checks_failed", "errors": [], "checks": {}}
    try:
        def unique_keys(pairs):
            obj = {}
            for key, value in pairs:
                need(key not in obj, "duplicate_json_key", key, "Duplicate JSON keys are ambiguous.")
                obj[key] = value
            return obj
        path = Path(record_path).resolve()
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
        need(isinstance(data, dict), "invalid_record", "record", "The record must be a JSON object.")
        data = data.get("delivery", data)
        need(isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == 1,
             "unsupported_schema", "schema_version", "Require delivery schema_version 1.")
        files = inspect_files(data.get("files"), path.parent)
        report["checks"]["files"] = {k: {f: v[f] for f in ("sha256", "size", "format", "png_depth_bits")} for k, v in files.items()}
        canvas, crop, source_rect = validate_declarations(data, files)
        report["checks"].update(check_pixels(data, files, canvas, crop, source_rect))
        binding = binding_sha256(data)
        report["review_binding_sha256"] = binding
        if require_review:
            validate_review(data, files, binding)
        report["status"] = "mechanical_checks_passed" if require_review else "binding_ready"
        report["visual_review"] = "bound_record_checked" if require_review else "not_checked"
    except ContractError as exc:
        report["errors"].append(exc.error)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report["errors"].append({"code": "record_unreadable", "field": "record", "detail": type(exc).__name__})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", help="Existing local task/runtime JSON or standalone delivery JSON")
    parser.add_argument("--print-binding", action="store_true", help="Check mechanical declarations and print the binding; do not approve a review")
    args = parser.parse_args()
    report = verify_record(args.record, require_review=not args.print_binding)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
