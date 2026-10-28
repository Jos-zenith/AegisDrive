from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CLASS_NAMES = (
    "school_zone",
    "hospital_zone",
    "speed_30",
    "speed_50",
    "speed_80",
)
SPLIT_BUCKETS = {
    "train": set(range(8)),
    "val": {8},
    "test": {9},
}


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "image_path",
        "label_path",
        "group_id",
        "class_labels",
        "reviewed",
    }
    if not rows:
        raise ValueError(f"No reviewed image rows in manifest: {path}")
    missing_columns = required - set(rows[0])
    if missing_columns:
        raise ValueError(f"Manifest is missing columns: {sorted(missing_columns)}")
    return rows


def image_group_split(group_id: str, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}:{group_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10
    for split_name, buckets in SPLIT_BUCKETS.items():
        if bucket in buckets:
            return split_name
    raise AssertionError("all split buckets must be assigned")


def validate_yolo_label(path: Path, image_path: Path, allowed_class_ids: set[int]) -> set[int]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing YOLO label file for {image_path}: {path}")
    found_ids: set[int] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_number}: expected class,x,y,width,height")
        try:
            class_id = int(fields[0])
            x_center, y_center, width, height = (float(value) for value in fields[1:])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: invalid numeric YOLO label") from exc
        if class_id not in allowed_class_ids:
            raise ValueError(f"{path}:{line_number}: class id {class_id} is not configured")
        found_ids.add(class_id)
        if not all(0 <= value <= 1 for value in (x_center, y_center, width, height)):
            raise ValueError(f"{path}:{line_number}: normalized box values must be in [0,1]")
        if width <= 0 or height <= 0 or x_center - width / 2 < 0 or x_center + width / 2 > 1:
            raise ValueError(f"{path}:{line_number}: invalid box width or horizontal bounds")
        if y_center - height / 2 < 0 or y_center + height / 2 > 1:
            raise ValueError(f"{path}:{line_number}: invalid vertical bounds")
    return found_ids


def prepare_split(
    manifest_path: Path,
    output_dir: Path,
    seed: int = 42,
) -> dict[str, Any]:
    rows = load_manifest(manifest_path)
    class_to_id = {name: index for index, name in enumerate(CLASS_NAMES)}
    split_rows: dict[str, list[dict[str, Any]]] = {
        split_name: [] for split_name in SPLIT_BUCKETS
    }
    class_split_groups: dict[str, set[str]] = defaultdict(set)
    group_splits: dict[str, str] = {}
    seen_sources: set[Path] = set()
    seen_content_hashes: dict[str, Path] = {}

    for row in rows:
        if row["reviewed"].strip().lower() not in {"true", "1", "yes"}:
            raise ValueError(f"Image labels are not reviewed: {row['image_path']}")
        group_id = row["group_id"].strip()
        if not group_id:
            raise ValueError(f"Missing group_id for {row['image_path']}")
        image_path = Path(row["image_path"]).resolve()
        label_path = Path(row["label_path"]).resolve()
        if image_path in seen_sources:
            raise ValueError(f"Duplicate image in manifest: {image_path}")
        seen_sources.add(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if image_hash in seen_content_hashes:
            raise ValueError(
                f"Exact duplicate images detected: {seen_content_hashes[image_hash]} "
                f"and {image_path}. Deduplicate before splitting."
            )
        seen_content_hashes[image_hash] = image_path
        labels = {
            label.strip()
            for label in row["class_labels"].split("|")
            if label.strip()
        }
        if not labels:
            raise ValueError(f"Every image must be labeled as a sign class or no_sign: {image_path}")
        unknown = labels - set(CLASS_NAMES) - {"no_sign"}
        if unknown:
            raise ValueError(f"Unsupported labels for {image_path}: {sorted(unknown)}")
        if "no_sign" in labels and len(labels) != 1:
            raise ValueError(f"no_sign cannot be combined with object classes: {image_path}")

        found_class_ids = validate_yolo_label(
            label_path,
            image_path,
            set(class_to_id.values()),
        )
        label_lines = [
            line for line in label_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if "no_sign" in labels and label_lines:
            raise ValueError(f"no_sign image must have an empty label file: {image_path}")
        if labels and "no_sign" not in labels and not label_lines:
            raise ValueError(f"Positive image has no boxes: {image_path}")
        expected_class_ids = {class_to_id[label] for label in labels if label in class_to_id}
        if found_class_ids != expected_class_ids:
            raise ValueError(
                f"YOLO class ids {sorted(found_class_ids)} do not match manifest "
                f"labels {sorted(expected_class_ids)} for {image_path}"
            )

        split_name = group_splits.setdefault(
            group_id,
            image_group_split(group_id, seed),
        )
        for class_name in labels - {"no_sign"}:
            class_split_groups[class_name].add(split_name)
        split_rows[split_name].append(
            {
                "source_image": image_path,
                "source_label": label_path,
                "group_id": group_id,
                "labels": sorted(labels),
            }
        )

    missing = {
        class_name: sorted({"train", "val", "test"} - class_split_groups[class_name])
        for class_name in CLASS_NAMES
        if {"train", "val", "test"} - class_split_groups[class_name]
    }
    if missing:
        raise ValueError(
            "Each sign class must have reviewed examples in independent groups "
            f"assigned to train/val/test; missing splits: {missing}. Collect more "
            "sessions or review the source manifest; do not move individual frames."
        )

    image_counts: Counter[str] = Counter()
    class_counts: dict[str, Counter[str]] = {
        split_name: Counter() for split_name in SPLIT_BUCKETS
    }
    for split_name, split_images in split_rows.items():
        for index, item in enumerate(split_images):
            image_name = f"{index:06d}_{item['source_image'].name}"
            image_output = output_dir / "images" / split_name / image_name
            label_output = output_dir / "labels" / split_name / f"{Path(image_name).stem}.txt"
            image_output.parent.mkdir(parents=True, exist_ok=True)
            label_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["source_image"], image_output)
            shutil.copy2(item["source_label"], label_output)
            image_counts[split_name] += 1
            for label in item["labels"]:
                class_counts[split_name][label] += 1

    manifest_output = output_dir / "split_manifest.csv"
    with manifest_output.open("w", encoding="utf-8", newline="") as stream:
        fields = ["image_path", "label_path", "group_id", "class_labels", "split", "seed"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for split_name, split_images in split_rows.items():
            for item in split_images:
                writer.writerow(
                    {
                        "image_path": str(item["source_image"]),
                        "label_path": str(item["source_label"]),
                        "group_id": item["group_id"],
                        "class_labels": "|".join(item["labels"]),
                        "split": split_name,
                        "seed": seed,
                    }
                )

    data_yaml = output_dir / "data.yaml"
    yaml_lines = [
        f"path: {output_dir.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    data_yaml.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    report = {
        "status": "prepared",
        "seed": seed,
        "group_split": "sha256(seed:group_id) mod 10; 0-7 train, 8 val, 9 test",
        "image_counts": dict(image_counts),
        "class_image_presence_counts": {
            split_name: dict(class_counts[split_name])
            for split_name in SPLIT_BUCKETS
        },
        "group_count": len(group_splits),
        "group_assignments": dict(sorted(group_splits.items())),
        "class_names": list(CLASS_NAMES),
        "data_yaml": str(data_yaml),
        "manifest": str(manifest_output),
    }
    (output_dir / "split_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create reproducible YOLO splits from manually reviewed labels."
    )
    parser.add_argument("manifest", type=Path, help="Reviewed CSV with group_id and YOLO labels")
    parser.add_argument("--output-dir", type=Path, default=Path("data_signs_split"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    report = prepare_split(args.manifest, args.output_dir, args.seed)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
