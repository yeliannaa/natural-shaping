"""Synthetic regressions: mechanics and recorded review binding, not aesthetic quality."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / "natural-shaping" / "scripts" / "verify_retouch_delivery.py"
SPEC = importlib.util.spec_from_file_location("retouch_delivery", SCRIPT)
DELIVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DELIVERY)


def synthetic_png16(color_type=2, delta=0):
    """2x2 native 16-bit PNG, constructed without a lossy Pillow save path."""
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    pixel = {0: [32768], 2: [32768, 16384, 8192],
             4: [32768, 65535], 6: [32768, 16384, 8192, 65535]}[color_type]
    samples = pixel * 4
    samples[0] += delta
    rows = []
    for y in range(2):
        row = samples[y * 2 * channels:(y + 1) * 2 * channels]
        rows.append(b"\0" + struct.pack(">" + "H" * len(row), *row))
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 16, color_type, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


class SyntheticDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="retouch-delivery-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Image.new("RGB", (16, 12), (80, 90, 100))
        ImageDraw.Draw(source).rectangle((2, 2, 5, 5), fill=(90, 110, 130))
        source.save(self.root / "source.png")
        composite = Image.new("RGB", (20, 16), (40, 50, 60))
        composite.paste(source, (2, 3))
        ImageDraw.Draw(composite).rectangle((8, 6, 10, 8), fill=(130, 120, 110))
        composite.save(self.root / "composite.png")
        composite.crop((1, 2, 19, 15)).save(self.root / "export.png")
        self.data = {
            "schema_version": 1,
            "files": {key: self.file_entry(key + ".png") for key in ("source", "composite", "export")},
            "mapping": {"canvas_size": [20, 16], "source_origin": [2, 3],
                        "delivery_crop": [1, 2, 19, 15], "export_crop_check": "exact_png"},
            "responsibilities": [{"id": "repair", "rect": [8, 6, 11, 9]}],
            "protections": [{"id": "outside", "type": "exact_pixels", "scope": "outside_responsibilities"},
                            {"id": "face", "type": "semantic", "rect": [4, 5, 8, 8]}],
        }
        self.review()

    def file_entry(self, name):
        path = self.root / name
        with Image.open(path) as image:
            size = list(image.size)
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": size}

    def review(self):
        self.data["visual_review"] = {
            "kind": "manual_visual", "export_sha256": self.data["files"]["export"]["sha256"],
            "binding_sha256": DELIVERY.binding_sha256(self.data),
            "views": ["fit", "native", "context"],
            "gates": {"goal": "pass", "structure": "pass", "finish": "pass"},
            "protection_results": {item["id"]: {"status": "pass", "note": "Synthetic review record for validator testing."}
                                   for item in self.data["protections"] if item["type"] != "exact_pixels"},
        }

    def run_record(self, embedded=False, require_review=True):
        path = self.root / "task.json"
        payload = {"synthetic": True, "delivery": self.data} if embedded else self.data
        path.write_text(json.dumps(payload), encoding="utf-8")
        return DELIVERY.verify_record(path, require_review=require_review)

    def assert_error(self, code):
        result = self.run_record()
        self.assertEqual("mechanical_checks_failed", result["status"], result)
        self.assertEqual(code, result["errors"][0]["code"], result)

    def save_composite_and_export(self, composite):
        composite.save(self.root / "composite.png")
        composite.crop(tuple(self.data["mapping"]["delivery_crop"])).save(self.root / "export.png")
        for key in ("composite", "export"):
            self.data["files"][key] = self.file_entry(key + ".png")

    def test_synthetic_stable_local_repair_with_expansion_and_native_crop(self):
        result = self.run_record(embedded=True)
        self.assertEqual("mechanical_checks_passed", result["status"], result)
        self.assertEqual("verified_exact_pixels", result["checks"]["export_crop"])
        self.assertEqual(183, result["checks"]["protections"][0]["compared_pixels"])

    def test_synthetic_wrong_declared_file_size(self):
        self.data["files"]["export"]["size"][0] += 1
        self.assert_error("file_size_mismatch")

    def test_synthetic_crop_size_does_not_match_export(self):
        self.data["mapping"]["delivery_crop"][2] -= 1
        self.assert_error("export_crop_size_mismatch")

    def test_synthetic_equal_size_shifted_crop_is_not_actual_export(self):
        self.data["mapping"]["delivery_crop"] = [0, 2, 18, 15]
        self.assert_error("export_crop_pixels_mismatch")

    def test_synthetic_different_composite_cannot_reuse_an_older_export(self):
        with Image.open(self.root / "composite.png") as opened:
            changed = opened.copy()
        changed.putpixel((9, 7), (210, 180, 150))
        changed.save(self.root / "composite.png")
        self.data["files"]["composite"] = self.file_entry("composite.png")
        self.review()
        self.assert_error("export_crop_pixels_mismatch")

    def test_synthetic_out_of_canvas_crop(self):
        self.data["mapping"]["delivery_crop"] = [1, 2, 21, 15]
        self.assert_error("rectangle_out_of_bounds")

    def test_synthetic_source_placement_must_fit_work_canvas(self):
        self.data["mapping"]["source_origin"] = [5, 3]
        self.assert_error("rectangle_out_of_bounds")

    def test_synthetic_boolean_is_not_a_coordinate(self):
        self.data["mapping"]["source_origin"] = [True, 3]
        self.assert_error("invalid_coordinates")

    def test_synthetic_float_is_not_a_coordinate(self):
        self.data["responsibilities"][0]["rect"][0] = 8.0
        self.assert_error("invalid_coordinates")

    def test_synthetic_responsibility_cannot_extend_outside_canvas(self):
        self.data["responsibilities"][0]["rect"][3] = 17
        self.assert_error("rectangle_out_of_bounds")

    def test_synthetic_complement_detects_damage_outside_small_protected_roi(self):
        with Image.open(self.root / "composite.png") as opened:
            changed = opened.copy()
        changed.putpixel((4, 5), (200, 0, 0))
        self.save_composite_and_export(changed)
        self.review()
        self.assert_error("protected_pixels_changed")

    def test_synthetic_strict_roi_can_protect_inside_allowed_change_rectangle(self):
        self.data["protections"].append({"id": "strict", "type": "exact_pixels", "scope": "roi", "rect": [8, 6, 9, 7]})
        self.review()
        self.assert_error("protected_pixels_changed")

    def test_synthetic_roi_not_present_in_source_is_rejected(self):
        self.data["protections"] = [{"id": "strict", "type": "exact_pixels", "scope": "roi", "rect": [1, 2, 2, 3]}]
        self.review()
        self.assert_error("exact_roi_outside_overlap")

    def test_synthetic_empty_complement_does_not_claim_protection(self):
        self.data["responsibilities"] = [{"id": "all", "rect": [0, 0, 20, 16]}]
        self.review()
        self.assert_error("empty_exact_scope")

    def test_synthetic_stale_file_hash_is_rejected(self):
        with Image.open(self.root / "source.png") as opened:
            changed = opened.copy()
        changed.putpixel((0, 0), (0, 0, 0))
        changed.save(self.root / "source.png")
        self.assert_error("file_sha_mismatch")

    def test_synthetic_new_export_bytes_need_new_visual_review(self):
        with Image.open(self.root / "composite.png") as opened:
            changed = opened.copy()
        changed.putpixel((9, 7), (210, 180, 150))
        self.save_composite_and_export(changed)
        self.assert_error("stale_review_export")

    def test_synthetic_updated_export_sha_alone_does_not_refresh_old_evidence(self):
        self.data["responsibilities"][0]["rect"] = [7, 6, 11, 9]
        self.assert_error("stale_review_binding")

    def test_synthetic_raw_candidate_is_optional_but_bound_if_present(self):
        Image.new("RGB", (3, 4), (1, 2, 3)).save(self.root / "donor.png")
        self.data["files"]["candidate"] = self.file_entry("donor.png")
        self.review()
        self.assertEqual("mechanical_checks_passed", self.run_record()["status"])
        Image.new("RGB", (3, 4), (4, 5, 6)).save(self.root / "donor.png")
        self.data["files"]["candidate"] = self.file_entry("donor.png")
        self.assert_error("stale_review_binding")

    def test_synthetic_missing_connection_context_view(self):
        self.data["visual_review"]["views"].remove("context")
        self.assert_error("missing_review_view")

    def test_synthetic_nonpassed_gate_is_not_completed_delivery(self):
        self.data["visual_review"]["gates"]["structure"] = "pending"
        self.assert_error("review_gate_not_passed")

    def test_synthetic_semantic_protection_needs_actual_recorded_conclusion(self):
        self.data["visual_review"]["protection_results"] = {}
        self.assert_error("missing_protection_review")

    def test_synthetic_authorized_global_light_and_geometry_semantics_are_legal(self):
        with Image.open(self.root / "source.png") as opened:
            changed = opened.point(lambda value: min(value + 30, 255))
        changed.save(self.root / "composite.png")
        changed.save(self.root / "export.png")
        self.data["files"]["composite"] = self.file_entry("composite.png")
        self.data["files"]["export"] = self.file_entry("export.png")
        self.data["mapping"] = {"canvas_size": [16, 12], "source_origin": [0, 0],
                                "delivery_crop": [0, 0, 16, 12], "export_crop_check": "exact_png"}
        self.data["responsibilities"] = [{"id": "light", "rect": [0, 0, 16, 12]}]
        self.data["protections"] = [{"id": "pose", "type": "geometry", "rect": [0, 0, 16, 12]},
                                    {"id": "makeup", "type": "semantic", "rect": [0, 0, 16, 12]}]
        self.review()
        self.assertEqual("mechanical_checks_passed", self.run_record()["status"])

    def test_synthetic_jpeg_delivery_is_bound_without_false_lossless_claim(self):
        with Image.open(self.root / "export.png") as opened:
            opened.save(self.root / "export.jpg", quality=90)
        self.data["files"]["export"] = self.file_entry("export.jpg")
        self.data["mapping"]["export_crop_check"] = "binding_only"
        self.data["protections"] = [item for item in self.data["protections"] if item["type"] != "exact_pixels"]
        self.review()
        result = self.run_record()
        self.assertEqual("mechanical_checks_passed", result["status"], result)
        self.assertEqual("bound_dimensions_only", result["checks"]["export_crop"])

    def test_synthetic_jpeg_cannot_be_exact_protected(self):
        with Image.open(self.root / "export.png") as opened:
            opened.save(self.root / "export.jpg", quality=90)
        self.data["files"]["export"] = self.file_entry("export.jpg")
        self.data["mapping"]["export_crop_check"] = "binding_only"
        self.review()
        self.assert_error("exact_requires_png")

    def test_synthetic_hidden_rgba_rgb_changes_are_not_ignored(self):
        for name in ("source", "composite", "export"):
            Image.new("RGBA", (8, 8), (80, 90, 100, 0)).save(self.root / (name + ".png"))
            self.data["files"][name] = self.file_entry(name + ".png")
        with Image.open(self.root / "composite.png") as opened:
            changed = opened.copy()
        changed.putpixel((1, 1), (99, 90, 100, 0))
        self.data["mapping"] = {"canvas_size": [8, 8], "source_origin": [0, 0],
                                "delivery_crop": [0, 0, 8, 8], "export_crop_check": "exact_png"}
        self.data["responsibilities"] = [{"id": "small", "rect": [4, 4, 6, 6]}]
        self.data["protections"] = [self.data["protections"][0]]
        self.save_composite_and_export(changed)
        self.review()
        self.assert_error("protected_pixels_changed")

    def test_synthetic_rgb_transparency_declarations_must_match(self):
        with Image.open(self.root / "export.png") as opened:
            opened.save(self.root / "export.png", transparency=(80, 90, 100))
        self.data["files"]["export"] = self.file_entry("export.png")
        self.review()
        self.assert_error("exact_representation_mismatch")

    def use_native16(self, color_type=2, composite_delta=0, export_delta=0):
        for name, delta in (("source", 0), ("composite", composite_delta), ("export", export_delta)):
            (self.root / (name + ".png")).write_bytes(synthetic_png16(color_type, delta))
            self.data["files"][name] = self.file_entry(name + ".png")
        self.data["mapping"] = {"canvas_size": [2, 2], "source_origin": [0, 0],
                                "delivery_crop": [0, 0, 2, 2], "export_crop_check": "exact_png"}
        self.data["responsibilities"] = [{"id": "repair", "rect": [1, 1, 2, 2]}]
        self.data["protections"] = [{"id": "outside", "type": "exact_pixels", "scope": "outside_responsibilities"}]
        self.review()

    def test_synthetic_native16_rgb_low_bit_export_change_is_not_called_exact(self):
        self.use_native16(composite_delta=1, export_delta=0)
        before = {p.name: p.read_bytes() for p in self.root.glob("*.png")}
        self.assert_error("exact_png_depth_unsupported")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.glob("*.png")})

    def test_synthetic_native16_rgb_low_bit_protection_change_is_not_ignored(self):
        self.use_native16(composite_delta=1, export_delta=1)
        self.data["mapping"]["export_crop_check"] = "binding_only"
        self.review()
        self.assert_error("exact_png_depth_unsupported")

    def test_synthetic_native16_all_color_types_are_rejected_for_exact_checks(self):
        for color_type in (0, 2, 4, 6):
            with self.subTest(color_type=color_type):
                self.use_native16(color_type)
                self.assert_error("exact_png_depth_unsupported")

    def test_synthetic_native16_binding_only_keeps_actual_bytes_and_review_binding(self):
        for color_type in (0, 2, 4, 6):
            with self.subTest(color_type=color_type):
                self.use_native16(color_type)
                self.data["mapping"]["export_crop_check"] = "binding_only"
                self.data["protections"] = [{"id": "pose", "type": "geometry", "rect": [0, 0, 2, 2]}]
                self.review()
                before = {p.name: p.read_bytes() for p in self.root.glob("*.png")}
                result = self.run_record()
                self.assertEqual("mechanical_checks_passed", result["status"], result)
                self.assertEqual("bound_dimensions_only", result["checks"]["export_crop"])
                self.assertEqual([], result["checks"]["protections"])
                self.assertTrue(all(item["png_depth_bits"] == 16 for item in result["checks"]["files"].values()))
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.glob("*.png")})
                (self.root / "export.png").write_bytes(synthetic_png16(color_type, delta=1))
                self.data["files"]["export"] = self.file_entry("export.png")
                self.assert_error("stale_review_export")

    def test_synthetic_native8_l_la_rgb_rgba_still_support_exact_pixels(self):
        for mode, color in (("L", 80), ("LA", (80, 128)),
                            ("RGB", (80, 90, 100)), ("RGBA", (80, 90, 100, 128))):
            with self.subTest(mode=mode):
                for name in ("source", "composite", "export"):
                    Image.new(mode, (2, 2), color).save(self.root / (name + ".png"))
                    self.data["files"][name] = self.file_entry(name + ".png")
                self.data["mapping"] = {"canvas_size": [2, 2], "source_origin": [0, 0],
                                        "delivery_crop": [0, 0, 2, 2], "export_crop_check": "exact_png"}
                self.data["responsibilities"] = [{"id": "repair", "rect": [1, 1, 2, 2]}]
                self.data["protections"] = [{"id": "outside", "type": "exact_pixels", "scope": "outside_responsibilities"}]
                self.review()
                result = self.run_record()
                self.assertEqual("mechanical_checks_passed", result["status"], result)
                self.assertEqual("verified_exact_pixels", result["checks"]["export_crop"])

    def test_synthetic_network_or_uri_inputs_are_rejected(self):
        self.data["files"]["source"]["path"] = "https://example.invalid/source.png"
        self.assert_error("nonlocal_path")

    def test_synthetic_print_binding_is_read_only_and_does_not_fabricate_review(self):
        del self.data["visual_review"]
        result = self.run_record(require_review=False)
        self.assertEqual("binding_ready", result["status"], result)
        self.assertEqual("not_checked", result["visual_review"])
        record = self.root / "task.json"
        snapshot = {p.name: p.read_bytes() for p in self.root.iterdir()}
        process = subprocess.run([sys.executable, "-B", str(SCRIPT), str(record), "--print-binding"],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertEqual("binding_ready", json.loads(process.stdout)["status"])
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assert_error("missing_visual_review")


if __name__ == "__main__":
    unittest.main()
