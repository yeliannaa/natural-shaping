# -*- coding: utf-8 -*-
"""Private preference/case registry and model-neutral editing-pair export.

Python 3.8+, standard library only. No image editing, model invocation, training,
network, or image copying. Paths and personal data live outside the skill package.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import struct
import sys


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def canonical_hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("Expected a 64-character SHA256")
    return value.lower()


def private_path(path):
    path = Path(path).resolve()
    skill_root = Path(__file__).resolve().parents[1]
    if path == skill_root or skill_root in path.parents:
        raise ValueError("Keep private stores and exports outside the skill package")
    return path


def scope_overlaps(left, right):
    if left.get("kind") == "full" or right.get("kind") == "full":
        return True
    if left.get("region_id") == right.get("region_id"):
        return True
    a, b = left.get("bbox_xyxy", []), right.get("bbox_xyxy", [])
    if len(a) == len(b) == 4:
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    return False


def validate_size(size, label="Image size"):
    if (not isinstance(size, list) or len(size) != 2
            or not all(type(value) is int and value > 0 for value in size)):
        raise ValueError(label + " needs two positive integers")
    return size


def validate_crop(crop, size, label="Crop"):
    validate_size(size)
    if not isinstance(crop, list) or len(crop) != 4 or not all(type(value) is int for value in crop):
        raise ValueError(label + " needs four integer coordinates")
    left, top, right, bottom = crop
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError(label + " must be nonempty and inside its parent image")
    return crop


def is_proportional_resize(crop_size, output_size):
    """One positive scale must round both dimensions half-up to the output.

    Each output n admits n - 1/2 <= source * scale < n + 1/2.
    Intersect these half-open scale intervals exactly; no percentage tolerance.
    """
    lower = max(Fraction(2 * output - 1, 2 * source)
                for source, output in zip(crop_size, output_size))
    upper = min(Fraction(2 * output + 1, 2 * source)
                for source, output in zip(crop_size, output_size))
    return lower < upper


def validate_scope(scope, size):
    validate_size(size)
    if not isinstance(scope, dict) or scope.get("kind") not in ("full", "local"):
        raise ValueError("Result scope must be full or local")
    if scope["kind"] == "local":
        if not isinstance(scope.get("region_id"), str) or not scope["region_id"]:
            raise ValueError("Local result scope needs a region ID")
        validate_crop(scope.get("bbox_xyxy"), size, "Local result scope")


def image_size(path):
    """Read PNG/JPEG dimensions only; this is not a color or visual inspection."""
    with Path(path).open("rb") as stream:
        start = stream.read(24)
        if start[:8] == b"\x89PNG\r\n\x1a\n" and start[12:16] == b"IHDR":
            return list(struct.unpack(">II", start[16:24]))
        if start[:2] != b"\xff\xd8":
            raise ValueError("Training images must be PNG or JPEG")
        stream.seek(2)
        sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while True:
            byte = stream.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            marker = stream.read(1)
            while marker == b"\xff":
                marker = stream.read(1)
            if not marker or marker[0] in (0xDA, 0xD9):
                break
            if marker[0] in (0x01, 0xD8) or 0xD0 <= marker[0] <= 0xD7:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                break
            if marker[0] in sof:
                data = stream.read(5)
                if len(data) == 5:
                    height, width = struct.unpack(">HH", data[1:5])
                    return [width, height]
                break
            stream.seek(length - 2, 1)
    raise ValueError("Cannot read image dimensions")


class Store:
    def __init__(self, root):
        self.root = private_path(root)
        self.config = read_json(self.root / "store-config.json")
        self.index = read_json(self.root / "cases-index.json")
        if self.config.get("schema_version") != 1 or self.index.get("schema_version") != 1:
            raise ValueError("Unsupported private store schema")
        self.cases = self.index["cases"]
        self.feedback = []
        for line in (self.root / "feedback.jsonl").read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                self.feedback.append(json.loads(line))
        self.by_feedback = {event["id"]: event for event in self.feedback}
        if len(self.by_feedback) != len(self.feedback):
            raise ValueError("Duplicate feedback IDs")
        if len({case["id"] for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        by_case = {case["id"]: case for case in self.cases}
        for event in self.feedback:
            if event.get("decision") in ("accept", "reject", "withdraw", "revision"):
                case = by_case[event["case_id"]]
                variant = case["variants"][event["variant_id"]]
                asset = case["assets"][variant["asset_id"]]
                validate_scope(event["scope"], asset["size"])
                if not event.get("quote") or not event.get("source"):
                    raise ValueError("Result feedback needs actual quote and source")
                if canonical_hash(event["asset_sha256"]) != canonical_hash(asset["sha256"]):
                    raise ValueError("Feedback hash does not match its recorded variant")
        self.verified = {}

    def resolve(self, asset):
        relative = asset["path"]
        if PureWindowsPath(relative).drive or PurePosixPath(relative).is_absolute() or ":" in relative:
            raise ValueError("Asset path must be relative to a named media root")
        parts = PurePosixPath(relative.replace("\\", "/")).parts
        if ".." in parts:
            raise ValueError("Asset path cannot escape its media root")
        base = Path(self.config["media_roots"][asset["root"]])
        if not base.is_absolute():
            raise ValueError("Private media root must be an absolute local path")
        base = base.resolve()
        path = base.joinpath(*parts).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            raise ValueError("Asset resolves outside its media root")
        return path

    def verify_asset(self, asset):
        if not isinstance(asset, dict):
            raise ValueError("Asset must be an object")
        validate_size(asset.get("size"), "Asset size")
        path = self.resolve(asset)
        key = (str(path), canonical_hash(asset["sha256"]), tuple(asset["size"]))
        if key not in self.verified:
            if not path.is_file():
                raise ValueError("Missing asset: " + str(path))
            if digest(path) != key[1]:
                raise ValueError("Asset hash changed: " + str(path))
            if image_size(path) != asset["size"]:
                raise ValueError("Asset dimensions changed: " + str(path))
            self.verified[key] = path
        return self.verified[key]

    def verify_derived(self, case, child_id, parent_id):
        """Check recorded, non-retouch lineage; geometry still requires human review."""
        seen = set()
        while child_id != parent_id:
            if child_id in seen:
                raise ValueError("Cyclic asset lineage")
            seen.add(child_id)
            child = case["assets"][child_id]
            self.verify_asset(child)
            lineage = child.get("derived_from", {})
            if (not isinstance(lineage, dict) or lineage.get("verified") is not True
                    or not lineage.get("evidence") or not isinstance(lineage.get("mapping"), dict)
                    or not lineage["mapping"]):
                raise ValueError("Prepared target lacks verified mapping to accepted image")
            operations = lineage.get("operations", [])
            if (not isinstance(operations, list) or not operations
                    or any(not isinstance(item, str) or item not in {"crop", "resize", "color_convert"}
                           for item in operations)):
                raise ValueError("Derived target includes unaccepted image modifications")
            child_id = lineage["asset_id"]
        self.verify_asset(case["assets"][parent_id])

    def local_crop(self, case, child_id, parent_id):
        if not all(isinstance(value, str) and value for value in (child_id, parent_id)):
            raise ValueError("Prepared crop and parent IDs must be nonempty strings")
        if child_id == parent_id:
            raise ValueError("A prepared pair must use actual prepared crops, not the parent image")
        child, parent = case["assets"][child_id], case["assets"][parent_id]
        lineage = child.get("derived_from", {})
        if not isinstance(lineage, dict) or lineage.get("asset_id") != parent_id:
            raise ValueError("Prepared crops need direct mapping to their recorded parent canvas")
        self.verify_derived(case, child_id, parent_id)
        if "crop" not in lineage["operations"]:
            raise ValueError("Prepared crop operations must include crop")
        mapping = lineage["mapping"]
        if set(mapping) != {"crop_xyxy", "output_size"}:
            raise ValueError("Crop mapping needs only crop_xyxy and output_size; padding/rotation is unsupported")
        crop = validate_crop(mapping["crop_xyxy"], parent["size"], "Prepared crop")
        output_size = validate_size(mapping["output_size"], "Crop output size")
        if output_size != child["size"]:
            raise ValueError("Crop output size is not bound to the actual prepared image")
        crop_size = [crop[2] - crop[0], crop[3] - crop[1]]
        if "resize" not in lineage["operations"]:
            if output_size != crop_size:
                raise ValueError("Crop dimensions do not match its mapping without resize")
        elif not is_proportional_resize(crop_size, output_size):
            raise ValueError("Crop resize must use one scale with round-half-up integer dimensions")
        return crop

    def prepared_pair_mapping(self, case, pair, target_parent_id):
        mapping = pair["alignment"].get("mapping")
        if (not isinstance(mapping, dict)
                or set(mapping) != {"input_crop_xyxy", "target_crop_xyxy", "output_size"}):
            raise ValueError("Prepared pair mapping needs input_crop_xyxy, target_crop_xyxy and output_size")
        input_parent_id = pair["input_parent_asset"]
        input_crop = self.local_crop(case, pair["input_asset"], input_parent_id)
        target_crop = self.local_crop(case, pair["target_asset"], target_parent_id)
        validate_crop(mapping["input_crop_xyxy"], case["assets"][input_parent_id]["size"], "Pair input crop")
        validate_crop(mapping["target_crop_xyxy"], case["assets"][target_parent_id]["size"], "Pair target crop")
        output_size = validate_size(mapping["output_size"], "Pair output size")
        if mapping["input_crop_xyxy"] != input_crop or mapping["target_crop_xyxy"] != target_crop:
            raise ValueError("Pair crop mapping conflicts with its respective prepared asset")
        if (output_size != case["assets"][pair["input_asset"]]["size"]
                or output_size != case["assets"][pair["target_asset"]]["size"]):
            raise ValueError("Pair output size conflicts with the actual prepared images")
        return target_crop

    def pair_row(self, case, pair):
        if pair.get("status") != "ready":
            raise ValueError("Pair has not been marked ready after review")
        if case.get("split") not in ("train", "validation"):
            raise ValueError("Assign the source group to train or validation before export")
        if not case.get("source_group_id"):
            raise ValueError("Missing source group")
        scope = pair["scope"]
        if not isinstance(scope, dict) or scope.get("kind") not in ("full", "local"):
            raise ValueError("Unsupported pair scope")
        if scope["kind"] == "local" and not scope.get("region_id"):
            raise ValueError("Local pair needs a region ID")
        variant = case["variants"][pair["accepted_variant"]]
        acceptance = variant["acceptance"]
        if acceptance.get("status") != "accepted":
            raise ValueError("Target variant is not explicitly accepted")
        accepted_scope = acceptance["scope"]
        if accepted_scope.get("kind") != "full" and accepted_scope != scope:
            raise ValueError("Acceptance does not cover this pair scope")
        accepted_asset = case["assets"][variant["asset_id"]]
        validate_scope(scope, accepted_asset["size"])
        validate_scope(accepted_scope, accepted_asset["size"])
        evidence = [self.by_feedback.get(item, {}) for item in acceptance.get("feedback_ids", [])]
        valid_evidence = [event for event in evidence if event.get("decision") == "accept" and event.get("actor") == "user"
                   and event.get("case_id") == case["id"] and event.get("variant_id") == pair["accepted_variant"]
                   and event.get("asset_sha256", "").lower() == accepted_asset["sha256"].lower()
                   and event.get("scope") == accepted_scope and event.get("quote") and event.get("source")]
        if not valid_evidence:
            raise ValueError("Missing user acceptance bound to this version, hash and scope")
        accepted_positions = [i for i, event in enumerate(self.feedback)
                              if event in valid_evidence and event.get("decision") == "accept"
                              and event.get("scope") == accepted_scope]
        for event in self.feedback[max(accepted_positions) + 1:]:
            if (event.get("actor") == "user" and event.get("case_id") == case["id"]
                    and event.get("variant_id") == pair["accepted_variant"]
                    and event.get("asset_sha256", "").lower() == canonical_hash(accepted_asset["sha256"])
                    and event.get("decision") in ("reject", "withdraw", "revision")
                    and scope_overlaps(event.get("scope", {}), scope)):
                raise ValueError("Acceptance was withdrawn, rejected or marked for revision")
        self.verify_derived(case, pair["target_asset"], variant["asset_id"])
        input_asset = case["assets"][pair["input_asset"]]
        target_asset = case["assets"][pair["target_asset"]]
        source = self.verify_asset(case["assets"][case["source_asset"]])
        input_path = self.verify_asset(input_asset)
        target_path = self.verify_asset(target_asset)
        alignment = pair.get("alignment", {})
        if not isinstance(alignment, dict) or alignment.get("status") != "verified" or not alignment.get("evidence"):
            raise ValueError("Pair alignment has not been reviewed")
        if alignment.get("method") not in ("same_canvas", "prepared_pair"):
            raise ValueError("Unsupported alignment method")
        if input_asset["size"] != target_asset["size"]:
            raise ValueError("Prepare mapped, equal-canvas input and target before export")
        target_crop = None
        if alignment["method"] == "prepared_pair":
            target_crop = self.prepared_pair_mapping(case, pair, variant["asset_id"])
        if scope["kind"] == "local":
            if alignment["method"] != "prepared_pair":
                raise ValueError("Local pairs must be prepared mapped crops")
            if scope.get("bbox_xyxy") != target_crop:
                raise ValueError("Local target crop must match the recorded acceptance region")
        colors = pair.get("color_review", {})
        if colors.get("status") != "verified" or not colors.get("evidence"):
            raise ValueError("Missing reviewed orientation, color and image-quality record")
        if not pair.get("instruction") or not pair.get("task") or not pair.get("review_evidence"):
            raise ValueError("Missing task, instruction or pair eligibility review")
        return {
            "case_id": case["id"], "pair_id": pair["id"], "source_group_id": case["source_group_id"],
            "split": case["split"], "task": pair["task"], "instruction": pair["instruction"],
            "input_image": str(input_path), "target_image": str(target_path),
            "input_sha256": canonical_hash(input_asset["sha256"]), "target_sha256": canonical_hash(target_asset["sha256"]),
            "source_sha256": canonical_hash(case["assets"][case["source_asset"]]["sha256"]),
            "size": input_asset["size"], "scope": scope, "alignment": alignment,
            "preserve": pair.get("preserve", []), "accepted_variant": pair["accepted_variant"],
            "acceptance_feedback_ids": acceptance["feedback_ids"], "source_image": str(source),
            "review_evidence": pair["review_evidence"], "color_review": colors,
        }

    def collect(self):
        rows, excluded, errors = [], [], []
        groups, asset_hashes = {}, {}
        for case in self.cases:
            if case.get("split") not in ("train", "validation"):
                continue
            source_hash = canonical_hash(case["assets"][case["source_asset"]]["sha256"])
            for registry, value, name in ((groups, case["source_group_id"], "source group"),
                                          (asset_hashes, source_hash, "original photo")):
                if registry.get(value, case["split"]) != case["split"]:
                    errors.append({"case_id": case["id"], "error": name + " crosses train/validation split"})
                registry[value] = case["split"]
        for case in self.cases:
            pairs = case.get("training_pairs", [])
            if not pairs:
                excluded.append({"case_id": case["id"], "reason": "No reviewed task-specific training pairs"})
            for pair in pairs:
                label = {"case_id": case["id"], "pair_id": pair["id"]}
                if pair.get("status") != "ready":
                    excluded.append(dict(label, reason=pair.get("exclusion_reason") or "Pair pending or excluded"))
                    continue
                try:
                    row = self.pair_row(case, pair)
                except (KeyError, ValueError, OSError, TypeError) as exc:
                    errors.append(dict(label, error=str(exc)))
                    continue
                for registry, value, name in (
                    (groups, row["source_group_id"], "source group"),
                    (asset_hashes, row["source_sha256"], "original photo"),
                    (asset_hashes, row["input_sha256"], "input image"),
                    (asset_hashes, row["target_sha256"], "target image"),
                ):
                    if registry.get(value, row["split"]) != row["split"]:
                        errors.append(dict(label, error=name + " crosses train/validation split"))
                    registry[value] = row["split"]
                rows.append(row)
        return rows, excluded, errors


def retrieval_style(case, variant_id, variant):
    """Use explicit variant/mapping metadata, never infer style from a name."""
    evidence = []
    declared = variant.get("style")
    if declared in ("natural", "highp"):
        evidence.append({"field": "variant.style", "style": declared})
    context = case.get("context", {})
    finals = context.get("current_finals_by_style", {})
    if not isinstance(finals, dict):
        finals = {}
    for style in ("natural", "highp"):
        entry = finals.get(style, {})
        mapped = entry.get("variant") if isinstance(entry, dict) else entry
        if mapped == variant_id:
            evidence.append({"field": "context.current_finals_by_style." + style, "style": style})
    styles = {item["style"] for item in evidence}
    if len(styles) != 1:
        return None, False, evidence
    style = next(iter(styles))
    current = any(item["field"].startswith("context.") for item in evidence)
    return style, current, evidence


def feedback_summary(event):
    fields = ("id", "actor", "decision", "variant_id", "asset_sha256", "scope",
              "quote", "source", "recorded_at", "interpretation")
    return {key: event[key] for key in fields if key in event}


def retrieval_acceptance(store, case, variant_id, variant):
    """Report effective recorded acceptance without opening or hashing media."""
    acceptance = variant.get("acceptance", {})
    scope = acceptance.get("scope")
    result = {"recorded_status": acceptance.get("status", "pending"),
              "effective_status": "pending", "scope": scope,
              "feedback": [], "blocking_feedback": []}
    if acceptance.get("status") != "accepted":
        result["effective_status"] = acceptance.get("status", "pending")
        return result
    asset = case["assets"][variant["asset_id"]]
    try:
        validate_scope(scope, asset["size"])
        asset_hash = canonical_hash(asset["sha256"])
    except (ValueError, TypeError, KeyError, AttributeError):
        result["effective_status"] = "unverified"
        return result
    linked = set(acceptance.get("feedback_ids", []))
    valid = [(position, event) for position, event in enumerate(store.feedback)
             if event.get("id") in linked and event.get("actor") == "user"
             and event.get("decision") == "accept" and event.get("case_id") == case["id"]
             and event.get("variant_id") == variant_id
             and event.get("asset_sha256", "").lower() == asset_hash
             and event.get("scope") == scope and event.get("quote") and event.get("source")]
    result["feedback"] = [feedback_summary(event) for _, event in valid]
    if not valid:
        result["effective_status"] = "unverified"
        return result
    last_accept = max(position for position, _ in valid)
    blockers = [event for event in store.feedback[last_accept + 1:]
                if event.get("actor") == "user" and event.get("case_id") == case["id"]
                and event.get("variant_id") == variant_id
                and event.get("asset_sha256", "").lower() == asset_hash
                and event.get("decision") in ("reject", "withdraw", "revision")
                and event.get("quote") and event.get("source")
                and scope_overlaps(event.get("scope", {}), scope)]
    result["blocking_feedback"] = [feedback_summary(event) for event in blockers]
    result["effective_status"] = blockers[-1]["decision"] if blockers else "accepted"
    return result


def retrieval_comparisons(store, case, variant_id):
    records = case.get("context", {}).get("preference_comparisons", [])
    if isinstance(records, dict):
        records = records.get("records", [])
    summaries = []
    for record in records:
        if not isinstance(record, dict):
            continue
        preferred = record.get("preferred_variant")
        other = record.get("other_variant", record.get("compared_variant"))
        compared = record.get("compared_variants", [])
        if not isinstance(compared, list):
            compared = []
        if variant_id not in (preferred, other) and variant_id not in compared:
            continue
        fields = ("id", "actor", "statement_type", "status", "tentative", "note", "tags",
                  "scope", "summary", "interpretation", "applicability", "outcome", "conditions",
                  "compared_variants")
        item = {key: record[key] for key in fields if key in record}
        if preferred is not None:
            item["preferred_variant"] = preferred
        if other is not None:
            item["other_variant"] = other
        item["feedback"] = [feedback_summary(store.by_feedback[feedback_id])
                            for feedback_id in record.get("feedback_ids", [])
                            if feedback_id in store.by_feedback
                            and store.by_feedback[feedback_id].get("case_id") == case["id"]]
        summaries.append(item)
    return summaries[-3:]


def retrieval_revisions(store, case, variant_id, terms):
    """Surface recorded lessons with their original decisions, not inferred rejects."""
    ranked = []
    for position, record in enumerate(case.get("context", {}).get("revision_examples", [])):
        if not isinstance(record, dict):
            continue
        other = record.get("variant")
        if other not in case.get("variants", {}):
            continue
        tags = {tag for tag in record.get("tags", []) if isinstance(tag, str)}
        matched = terms.intersection(tags)
        if other != variant_id and not matched:
            continue
        feedback = [feedback_summary(store.by_feedback[feedback_id])
                    for feedback_id in record.get("feedback_ids", [])
                    if feedback_id in store.by_feedback
                    and store.by_feedback[feedback_id].get("case_id") == case["id"]
                    and store.by_feedback[feedback_id].get("variant_id") == other]
        if not feedback:
            continue
        item = {key: record[key] for key in ("variant", "tags", "note", "status") if key in record}
        item.update(matched_tags=sorted(matched), feedback=feedback)
        ranked.append((other != variant_id, -len(matched), -position, item))
    ranked.sort(key=lambda item: item[:3])
    return [item[-1] for item in ranked[:2]]


def summary_query(store, tags, limit=3, style=None, status="accepted"):
    if not 1 <= limit <= 3:
        raise ValueError("Summary retrieval limit must be between 1 and 3")
    terms = set(tags)
    ranked = []
    for case in store.cases:
        case_tags = {tag for tag in case.get("tags", []) if isinstance(tag, str)}
        for variant_id, variant in case.get("variants", {}).items():
            explicit_style, current, style_evidence = retrieval_style(case, variant_id, variant)
            if explicit_style is None or (style and explicit_style != style):
                continue
            variant_tags = {tag for tag in variant.get("tags", []) if isinstance(tag, str)}
            matched = terms.intersection(case_tags | variant_tags)
            if not matched:
                continue
            acceptance = retrieval_acceptance(store, case, variant_id, variant)
            if status == "accepted" and acceptance["effective_status"] != "accepted":
                continue
            def asset_info(asset_id):
                asset = case["assets"][asset_id]
                return dict(asset_id=asset_id, **{key: asset[key] for key in ("root", "path", "sha256", "size") if key in asset})
            row = {"case_id": case["id"], "variant_id": variant_id, "style": explicit_style,
                   "current_for_style": current, "style_evidence": style_evidence,
                   "matched_tags": sorted(matched),
                   "source_group_id": case.get("source_group_id"),
                   "subject_group_id": case.get("context", {}).get("subject_group_id"),
                   "source_asset": asset_info(case["source_asset"]),
                   "target_asset": asset_info(variant["asset_id"]), "scope": acceptance["scope"],
                   "acceptance": acceptance, "comparisons": retrieval_comparisons(store, case, variant_id),
                   "revision_examples": retrieval_revisions(store, case, variant_id, terms),
                   "training_pair_statuses": [{"id": pair.get("id"), "status": pair.get("status")}
                                              for pair in case.get("training_pairs", [])
                                              if pair.get("accepted_variant") == variant_id],
                   "training_eligibility": "not_evaluated"}
            accepted = acceptance["effective_status"] == "accepted"
            ranked.append((-len(matched), not (current and accepted), not accepted, case["id"], variant_id, row))
    ranked.sort(key=lambda item: item[:5])
    selected, groups = [], set()
    for item in ranked:
        row = item[-1]
        group = (row["source_group_id"] or row["case_id"], row["style"])
        if group not in groups:
            selected.append(row)
            groups.add(group)
        if len(selected) == limit:
            break
    return {"mode": "summary", "query": {"tags": sorted(terms), "style": style, "status": status, "limit": limit},
            "preferences": (store.root / "preferences.md").read_text(encoding="utf-8-sig"),
            "general_feedback": [feedback_summary(event) for event in store.feedback if not event.get("case_id")][-8:],
            "variants": selected, "metadata_only": True,
            "scope": "Recorded metadata only; no media hash/visual or training-eligibility review. Local acceptance remains local."}


def store_path(args):
    if args.store:
        return Path(args.store)
    config_path = Path(args.config) if args.config else Path.home() / ".codex" / "natural-shaping.local.json"
    return Path(read_json(config_path)["personal_store"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", help="Explicit private store; otherwise use local config")
    parser.add_argument("--config", help="Override the user's local config path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("validate")
    query = commands.add_parser("query")
    query.add_argument("--tags", nargs="+", required=True)
    query.add_argument("--limit", type=int, default=3)
    query.add_argument("--summary", action="store_true", help="Return 1-3 specific variants instead of legacy whole cases")
    query.add_argument("--style", choices=("natural", "highp"), help="Explicit variant style; requires --summary")
    query.add_argument("--status", choices=("accepted", "any"), help="Effective recorded acceptance; summary defaults to accepted")
    for command in ("record-case", "record-feedback"):
        record = commands.add_parser(command)
        record.add_argument("--file", required=True, help="Structured UTF-8 JSON record")
    export = commands.add_parser("export")
    export.add_argument("--output", required=True, help="New private directory; images are not copied")
    args = parser.parse_args()
    root = private_path(store_path(args))
    if args.command == "init":
        root.mkdir(parents=True, exist_ok=True)
        initial = {"store-config.json": {"schema_version": 1, "media_roots": {}},
                   "cases-index.json": {"schema_version": 1, "cases": []}}
        for name, value in initial.items():
            if not (root / name).exists():
                write_json(root / name, value)
        for name, text in (("feedback.jsonl", ""), ("preferences.md", "# 私人审美偏好\n\n仅记录有用户证据及适用条件的偏好。\n")):
            if not (root / name).exists():
                (root / name).write_text(text, encoding="utf-8")
        print(json.dumps({"initialized": str(root)}, ensure_ascii=False))
        return 0
    store = Store(root)
    if args.command == "record-case":
        case = read_json(args.file)
        required = {"id", "source_group_id", "source_asset", "assets", "variants", "tags", "split", "training_pairs"}
        if not required.issubset(case) or case["source_asset"] not in case["assets"]:
            raise ValueError("Incomplete case record")
        if len({pair["id"] for pair in case["training_pairs"]}) != len(case["training_pairs"]):
            raise ValueError("Duplicate pair IDs in a case")
        if case["split"] not in ("train", "validation", "unassigned"):
            raise ValueError("Unsupported case split")
        for variant in case["variants"].values():
            if variant["asset_id"] not in case["assets"]:
                raise ValueError("Variant references an unknown asset")
        for asset in case["assets"].values():
            store.verify_asset(asset)
        existing = next((item for item in store.cases if item["id"] == case["id"]), None)
        if existing:
            if case["source_asset"] != existing["source_asset"] or case["source_group_id"] != existing["source_group_id"]:
                raise ValueError("Retain the case source identity and source group")
            for asset_id, old in existing["assets"].items():
                if asset_id not in case["assets"] or canonical_hash(case["assets"][asset_id]["sha256"]) != canonical_hash(old["sha256"]):
                    raise ValueError("Retain existing asset IDs and hashes; add a new version instead")
            if not set(existing["variants"]).issubset(case["variants"]):
                raise ValueError("Retain historical variant records")
            if any(case["variants"][key]["asset_id"] != value["asset_id"] for key, value in existing["variants"].items()):
                raise ValueError("A historical variant cannot be rebound to another asset")
            store.cases[store.cases.index(existing)] = case
        else:
            store.cases.append(case)
        write_json(root / "cases-index.json", store.index)
        print(json.dumps({"recorded_case": case["id"]}, ensure_ascii=False))
        return 0
    if args.command == "record-feedback":
        event = read_json(args.file)
        if not {"id", "actor", "decision", "quote", "source", "scope", "recorded_at"}.issubset(event):
            raise ValueError("Incomplete feedback record")
        case = next((item for item in store.cases if item["id"] == event.get("case_id")), None)
        if event.get("case_id") and case is None:
            raise ValueError("Feedback references an unknown case")
        if event["decision"] in ("accept", "reject", "withdraw", "revision"):
            if case is None or event.get("variant_id") not in case["variants"]:
                raise ValueError("A result decision must reference a known variant")
            asset = case["assets"][case["variants"][event["variant_id"]]["asset_id"]]
            store.verify_asset(asset)
            validate_scope(event["scope"], asset["size"])
            if not event.get("quote") or not event.get("source"):
                raise ValueError("Result feedback needs actual quote and source")
            if event.get("actor") != "user" or event.get("asset_sha256", "").lower() != asset["sha256"].lower():
                raise ValueError("A result decision must be bound to the actual user-reviewed version")
        if event["id"] in store.by_feedback:
            if store.by_feedback[event["id"]] != event:
                raise ValueError("Feedback ID already has different content")
        else:
            with (root / "feedback.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(json.dumps({"recorded_feedback": event["id"]}, ensure_ascii=False))
        return 0
    if args.command == "query":
        if args.summary:
            print(json.dumps(summary_query(store, args.tags, args.limit, args.style, args.status or "accepted"),
                             ensure_ascii=False, indent=2))
            return 0
        if args.style or args.status:
            raise ValueError("Style/status filters require --summary; omit them for legacy case output")
        terms = set(args.tags)
        if not 1 <= args.limit <= 10:
            raise ValueError("Retrieval limit must be between 1 and 10")
        scored = [(len(terms.intersection(case.get("tags", []))), case) for case in store.cases]
        scored.sort(key=lambda item: (-item[0], item[1]["id"]))
        selected = [dict(case, matched_tags=sorted(terms.intersection(case["tags"])),
                         feedback=[event for event in store.feedback if event.get("case_id") == case["id"]])
                    for score, case in scored if score][:args.limit]
        print(json.dumps({"preferences": (root / "preferences.md").read_text(encoding="utf-8-sig"),
                          "general_feedback": [event for event in store.feedback if not event.get("case_id")][-8:],
                          "cases": selected, "scope": "Metadata retrieval; inspect selected images before judging"},
                         ensure_ascii=False, indent=2))
        return 0
    rows, excluded, errors = store.collect()
    if args.command == "validate":
        for case in store.cases:
            for asset_id, asset in case["assets"].items():
                try:
                    store.verify_asset(asset)
                except (KeyError, ValueError, OSError, TypeError) as exc:
                    errors.append({"case_id": case["id"], "asset_id": asset_id, "error": str(exc)})
        print(json.dumps({"passed": not errors, "cases": len(store.cases), "feedback": len(store.feedback),
                          "eligible_pairs": len(rows), "excluded": excluded, "errors": errors,
                          "scope": "File identity and recorded eligibility only; not automatic visual acceptance"},
                         ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    if errors:
        print(json.dumps({"exported": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    output = private_path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new or empty export directory")
    if output == root:
        raise ValueError("Export cannot replace the private store")
    output.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        with (output / (split + "-pairs.jsonl")).open("w", encoding="utf-8") as stream:
            for row in rows:
                if row["split"] == split:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"format": "model-neutral-editing-pairs-v1", "cases_index_sha256": digest(root / "cases-index.json"),
              "feedback_sha256": digest(root / "feedback.jsonl"), "training_started": False,
              "images_copied": 0, "eligible_pairs": len(rows), "excluded": excluded,
              "train": sum(row["split"] == "train" for row in rows),
              "validation": sum(row["split"] == "validation" for row in rows),
              "scope": "Neutral manifest only; Qwen base, framework adapter and ncnn LoRA loading still require validation"}
    write_json(output / "export-report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, ValueError, OSError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
