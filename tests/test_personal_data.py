"""Training eligibility regressions using synthetic images and fictional feedback."""
import copy
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


SCRIPT = Path(__file__).resolve().parents[1] / "natural-shaping" / "scripts" / "personal_data.py"
SPEC = importlib.util.spec_from_file_location("personal_data_under_test", SCRIPT)
personal_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(personal_data)


def write_png(path, size, value):
    """Write a complete RGB8 PNG with only standard-library dependencies."""
    width, height = size

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    pixels = (b"\0" + bytes((value, value, value)) * width) * height
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class PersonalDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="natural-shaping-training-test-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.fixture_count = 0

    def fixture(self, size=(10, 10), input_crop=None, target_crop=None):
        self.fixture_count += 1
        root = self.workspace / str(self.fixture_count)
        media = root / "synthetic-media"
        media.mkdir(parents=True)
        assets = {}
        for index, (name, dimensions) in enumerate([
                ("original", (100, 100)), ("stage", (100, 100)),
                ("accepted", (100, 100)), ("input-crop", size), ("target-crop", size)]):
            path = media / (name + ".png")
            write_png(path, dimensions, index * 40)
            assets[name] = {"root": "synthetic", "path": path.name, "size": list(dimensions),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        input_crop = input_crop if input_crop is not None else [0, 0, 20, 20]
        target_crop = target_crop if target_crop is not None else [0, 0, 20, 20]
        for name, parent, crop in [("input-crop", "stage", input_crop),
                                   ("target-crop", "accepted", target_crop)]:
            assets[name]["derived_from"] = {
                "asset_id": parent, "operations": ["crop", "resize"],
                "mapping": {"crop_xyxy": list(crop), "output_size": list(size)},
                "verified": True, "evidence": "SYNTHETIC TEST ONLY: preparation"}
        scope = {"kind": "local", "region_id": "synthetic", "bbox_xyxy": list(target_crop)}
        pair = {
            "id": "synthetic-pair", "status": "ready", "scope": copy.deepcopy(scope),
            "input_asset": "input-crop", "input_parent_asset": "stage",
            "target_asset": "target-crop", "accepted_variant": "synthetic-variant",
            "alignment": {"method": "prepared_pair", "status": "verified",
                          "evidence": "SYNTHETIC TEST ONLY: alignment",
                          "mapping": {"input_crop_xyxy": list(input_crop),
                                      "target_crop_xyxy": list(target_crop), "output_size": list(size)}},
            "color_review": {"status": "verified", "evidence": "SYNTHETIC TEST ONLY: color"},
            "task": "synthetic-test", "instruction": "Synthetic fixture, not a real training sample",
            "review_evidence": "SYNTHETIC TEST ONLY: eligibility"}
        case = {
            "id": "synthetic-case", "source_group_id": "synthetic-group", "source_asset": "original",
            "assets": assets, "split": "train", "tags": [], "training_pairs": [pair],
            "variants": {"synthetic-variant": {"asset_id": "accepted", "acceptance": {
                "status": "accepted", "scope": copy.deepcopy(scope), "feedback_ids": ["synthetic-accept"]}}}}
        feedback = [{
            "id": "synthetic-accept", "case_id": case["id"], "variant_id": "synthetic-variant",
            "actor": "user", "decision": "accept", "scope": copy.deepcopy(scope),
            "asset_sha256": assets["accepted"]["sha256"],
            "quote": "Fictional acceptance for a synthetic test; not a real user statement",
            "source": "synthetic-unit-test"}]
        (root / "store-config.json").write_text(json.dumps({
            "schema_version": 1, "media_roots": {"synthetic": str(media)}}), encoding="utf-8")
        (root / "preferences.md").write_text("Synthetic test preferences only.\n", encoding="utf-8")
        return root, case, feedback

    def save(self, fixture):
        root, case, feedback = fixture
        (root / "cases-index.json").write_text(json.dumps({"schema_version": 1, "cases": [case]}), encoding="utf-8")
        (root / "feedback.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in feedback), encoding="utf-8")

    def collect(self, fixture):
        self.save(fixture)
        return personal_data.Store(fixture[0]).collect()

    def assert_eligible(self, fixture):
        rows, excluded, errors = self.collect(fixture)
        self.assertEqual([], errors)
        self.assertEqual([], excluded)
        self.assertEqual(1, len(rows))
        return rows[0]

    def assert_rejected(self, fixture, message=None):
        rows, _, errors = self.collect(fixture)
        self.assertEqual([], rows)
        self.assertTrue(errors)
        if message:
            self.assertIn(message, errors[0]["error"])

    def test_proportional_resize_and_integer_rounding(self):
        for crop, size in [([0, 0, 20, 20], (10, 10)), ([0, 0, 20, 40], (10, 20)),
                           ([0, 0, 21, 20], (10, 10)), ([0, 0, 20, 21], (10, 10)),
                           ([0, 0, 2, 1], (5, 2)), ([0, 0, 21, 20], (42, 40))]:
            with self.subTest(crop=crop, size=size):
                self.assert_eligible(self.fixture(size, crop, crop))

    def test_nonuniform_resize_rejected(self):
        for size in [(10, 20), (20, 10), (10, 11)]:
            with self.subTest(size=size):
                self.assert_rejected(self.fixture(size), "one scale")

    def test_without_resize_requires_exact_crop_dimensions(self):
        fixture = self.fixture((20, 20))
        for name in ("input-crop", "target-crop"):
            fixture[1]["assets"][name]["derived_from"]["operations"] = ["crop"]
        self.assert_eligible(fixture)
        bad = self.fixture()
        bad[1]["assets"]["input-crop"]["derived_from"]["operations"] = ["crop"]
        self.assert_rejected(bad, "without resize")

    def test_different_parent_coordinates_and_stage_input_remain_valid(self):
        fixture = self.fixture(input_crop=[40, 40, 60, 60])
        row = self.assert_eligible(fixture)
        self.assertNotEqual(fixture[1]["source_asset"], fixture[1]["training_pairs"][0]["input_parent_asset"])
        self.assertEqual([40, 40, 60, 60], row["alignment"]["mapping"]["input_crop_xyxy"])
        self.assertEqual([0, 0, 20, 20], row["alignment"]["mapping"]["target_crop_xyxy"])

    def test_pair_crop_and_output_conflicts_rejected(self):
        for field, value in [("input_crop_xyxy", [80, 80, 100, 100]),
                             ("target_crop_xyxy", [80, 80, 100, 100]),
                             ("output_size", [9999, 9999])]:
            with self.subTest(field=field):
                fixture = self.fixture()
                fixture[1]["training_pairs"][0]["alignment"]["mapping"][field] = value
                self.assert_rejected(fixture, "conflicts")

    def test_swapped_pair_crops_rejected(self):
        fixture = self.fixture(input_crop=[40, 40, 60, 60])
        mapping = fixture[1]["training_pairs"][0]["alignment"]["mapping"]
        mapping["input_crop_xyxy"], mapping["target_crop_xyxy"] = mapping["target_crop_xyxy"], mapping["input_crop_xyxy"]
        self.assert_rejected(fixture, "conflicts")

    def test_wrong_parent_rejected_on_each_side(self):
        for side in ("input-crop", "target-crop"):
            with self.subTest(side=side):
                fixture = self.fixture()
                fixture[1]["assets"][side]["derived_from"]["asset_id"] = "original"
                self.assert_rejected(fixture)
        fixture = self.fixture()
        fixture[1]["training_pairs"][0]["input_parent_asset"] = "original"
        self.assert_rejected(fixture, "parent canvas")

    def test_crop_and_pair_mapping_types_and_fields_rejected(self):
        for location in ("derived", "pair"):
            for invalid in (None, [], "mapping", {}, {"output_size": [10, 10]}):
                with self.subTest(location=location, invalid=invalid):
                    fixture = self.fixture()
                    if location == "derived":
                        fixture[1]["assets"]["input-crop"]["derived_from"]["mapping"] = invalid
                    else:
                        fixture[1]["training_pairs"][0]["alignment"]["mapping"] = invalid
                    self.assert_rejected(fixture)

    def test_invalid_crop_values_rejected_in_both_mappings(self):
        for crop in (None, "0,0,20,20", [], [0, 0, 0, 20], [20, 0, 0, 20], [-1, 0, 20, 20],
                     [0, 0, 101, 20], [False, 0, 20, 20], [0.0, 0, 20, 20], [0, 0, "20", 20]):
            for location in ("derived", "pair"):
                with self.subTest(location=location, crop=crop):
                    fixture = self.fixture()
                    if location == "derived":
                        fixture[1]["assets"]["input-crop"]["derived_from"]["mapping"]["crop_xyxy"] = crop
                    else:
                        fixture[1]["training_pairs"][0]["alignment"]["mapping"]["input_crop_xyxy"] = crop
                    self.assert_rejected(fixture)

    def test_invalid_output_sizes_rejected_in_all_records(self):
        for size in (None, "10x10", [], [10], [0, 10], [-1, 10], [True, 10], [10.0, 10], ["10", 10]):
            for location in ("asset", "derived", "pair"):
                with self.subTest(location=location, size=size):
                    fixture = self.fixture()
                    if location == "asset":
                        fixture[1]["assets"]["input-crop"]["size"] = size
                    elif location == "derived":
                        fixture[1]["assets"]["input-crop"]["derived_from"]["mapping"]["output_size"] = size
                    else:
                        fixture[1]["training_pairs"][0]["alignment"]["mapping"]["output_size"] = size
                    self.assert_rejected(fixture)

    def test_actual_file_dimensions_and_hash_are_checked(self):
        fixture = self.fixture()
        fixture[1]["assets"]["input-crop"]["size"] = [11, 10]
        self.assert_rejected(fixture, "dimensions changed")
        fixture = self.fixture()
        fixture[1]["assets"]["input-crop"]["sha256"] = "0" * 64
        self.assert_rejected(fixture, "hash changed")

    def test_unrecorded_padding_and_unsupported_operations_rejected(self):
        fixture = self.fixture()
        fixture[1]["assets"]["input-crop"]["derived_from"]["mapping"]["padding"] = [0, 0, 0, 0]
        self.assert_rejected(fixture, "padding/rotation")
        for operations in (["crop", "pad"], "crop", ["crop", True], []):
            with self.subTest(operations=operations):
                fixture = self.fixture()
                fixture[1]["assets"]["input-crop"]["derived_from"]["operations"] = operations
                self.assert_rejected(fixture)

    def test_withdrawal_still_blocks_eligibility(self):
        fixture = self.fixture()
        event = copy.deepcopy(fixture[2][0])
        event.update(id="synthetic-withdraw", decision="withdraw")
        fixture[2].append(event)
        self.assert_rejected(fixture, "withdrawn")

    def test_comparison_summary_keeps_outcome_conditions_without_implied_rejection(self):
        for outcome in ("win", "tie", "both_unsatisfactory", "unclear"):
            with self.subTest(outcome=outcome):
                fixture = self.fixture()
                case, feedback = fixture[1], fixture[2]
                case["tags"] = ["synthetic"]
                case["variants"]["synthetic-variant"]["style"] = "highp"
                comparison = {"id": "synthetic-comparison", "outcome": outcome,
                              "other_variant": "synthetic-variant", "feedback_ids": ["synthetic-opinion"],
                              "conditions": {"lighting": "synthetic low light", "scope": "local material"},
                              "applicability": "Synthetic condition only", "interpretation": "Synthetic opinion only"}
                if outcome == "win":
                    comparison["preferred_variant"] = "synthetic-variant"
                case["context"] = {"preference_comparisons": [comparison]}
                opinion = copy.deepcopy(feedback[0])
                opinion.update(id="synthetic-opinion", decision="comparison",
                               quote="Fictional comparison fixture only")
                feedback.append(opinion)
                self.save(fixture)
                store = personal_data.Store(fixture[0])
                summary = personal_data.summary_query(store, ["synthetic"], style="highp")
                row = summary["variants"][0]
                item = row["comparisons"][0]
                self.assertEqual(outcome, item["outcome"])
                self.assertEqual(comparison["conditions"], item["conditions"])
                self.assertEqual(comparison["applicability"], item["applicability"])
                self.assertEqual(comparison["interpretation"], item["interpretation"])
                if outcome != "win":
                    self.assertNotIn("preferred_variant", item)
                self.assertEqual("accepted", row["acceptance"]["effective_status"])
                self.assertEqual([], row["revision_examples"])
                rows, _, errors = store.collect()
                self.assertEqual([], errors)
                self.assertEqual(1, len(rows))

    def test_tied_compared_variants_are_retrievable_from_either_version(self):
        fixture = self.fixture()
        case, feedback = fixture[1], fixture[2]
        primary = case["variants"]["synthetic-variant"]
        primary.update(style="highp", tags=["version-a"])
        alternate = copy.deepcopy(primary)
        alternate["tags"] = ["version-b"]
        alternate["acceptance"]["feedback_ids"] = ["synthetic-other-accept"]
        case["variants"]["synthetic-other"] = alternate
        event = copy.deepcopy(feedback[0])
        event.update(id="synthetic-other-accept", variant_id="synthetic-other")
        feedback.append(event)
        compared = ["synthetic-variant", "synthetic-other"]
        case["context"] = {"preference_comparisons": [{
            "id": "synthetic-tie", "outcome": "tie", "compared_variants": compared,
            "conditions": {"lighting": "synthetic", "scope": "local"},
            "feedback_ids": ["synthetic-tie-feedback"]}]}
        opinion = copy.deepcopy(feedback[0])
        opinion.update(id="synthetic-tie-feedback", decision="comparison", quote="Fictional tie fixture only")
        feedback.append(opinion)
        self.save(fixture)
        store = personal_data.Store(fixture[0])
        for tag, variant_id in [("version-a", "synthetic-variant"), ("version-b", "synthetic-other")]:
            with self.subTest(variant_id=variant_id):
                row = personal_data.summary_query(store, [tag], style="highp")["variants"][0]
                self.assertEqual(variant_id, row["variant_id"])
                self.assertEqual("accepted", row["acceptance"]["effective_status"])
                self.assertEqual([], row["revision_examples"])
                item = row["comparisons"][0]
                self.assertEqual("tie", item["outcome"])
                self.assertEqual(compared, item["compared_variants"])
                self.assertNotIn("preferred_variant", item)
                self.assertNotIn("other_variant", item)
        rows, _, errors = store.collect()
        self.assertEqual([], errors)
        self.assertEqual(1, len(rows))

    def test_same_canvas_full_pair_does_not_require_crop_mapping(self):
        fixture = self.fixture()
        case, feedback = fixture[1], fixture[2]
        pair = case["training_pairs"][0]
        pair.update(scope={"kind": "full"}, input_asset="stage", target_asset="accepted")
        pair["alignment"] = {"status": "verified", "method": "same_canvas", "evidence": "SYNTHETIC TEST ONLY"}
        case["variants"]["synthetic-variant"]["acceptance"]["scope"] = {"kind": "full"}
        feedback[0]["scope"] = {"kind": "full"}
        self.assert_eligible(fixture)

    def test_cli_validate_and_invalid_export(self):
        valid = self.fixture()
        self.save(valid)
        command = [sys.executable, "-B", str(SCRIPT), "--store", str(valid[0]), "validate"]
        checked = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertEqual(1, json.loads(checked.stdout)["eligible_pairs"])
        invalid = self.fixture((10, 20))
        self.save(invalid)
        output = self.workspace / "must-not-export"
        rejected = subprocess.run([sys.executable, "-B", str(SCRIPT), "--store", str(invalid[0]),
                                   "export", "--output", str(output)],
                                  capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(1, rejected.returncode, rejected.stderr)
        self.assertFalse(json.loads(rejected.stdout)["exported"])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
