from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


TARGET_CLASSES = (
    "school_zone",
    "hospital_zone",
    "speed_30",
    "speed_50",
    "speed_80",
)
BACKGROUND_CLASS = "no_sign"
CLASS_MAP = {
    "school_zone": [],
    "hospital_zone": [],
    "speed_30": [],
    "speed_50": [],
    "speed_80": [],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit_signs(dataset: Path) -> dict[str, Any]:
    image_root = dataset / "Images"
    class_csv = dataset / "traffic_sign.csv"
    if not image_root.is_dir() or not class_csv.is_file():
        raise FileNotFoundError(
            f"Expected Images/ and traffic_sign.csv under {dataset}"
        )

    source_names = {
        int(row["ClassId"]): row["Name"]
        for row in read_csv(class_csv)
    }
    image_paths = sorted(
        (path for path in image_root.rglob("*") if path.is_file()),
        key=lambda path: str(path).casefold(),
    )
    counts: Counter[int] = Counter()
    dimensions: Counter[str] = Counter()
    exact_hashes: dict[str, list[str]] = defaultdict(list)
    corrupt_files: list[str] = []
    non_png_files: list[str] = []

    for path in image_paths:
        if path.suffix.lower() != ".png":
            non_png_files.append(path.relative_to(dataset).as_posix())
            continue
        try:
            encoded = path.read_bytes()
            image = cv2.imdecode(
                np.frombuffer(encoded, dtype=np.uint8),
                cv2.IMREAD_UNCHANGED,
            )
            if image is None:
                raise ValueError("OpenCV could not decode image")
            class_id = int(path.parent.name)
            counts[class_id] += 1
            height, width = image.shape[:2]
            dimensions[f"{width}x{height}"] += 1
            exact_hashes[hashlib.sha256(encoded).hexdigest()].append(
                path.relative_to(dataset).as_posix()
            )
        except (ValueError, OSError):
            corrupt_files.append(path.relative_to(dataset).as_posix())

    ids_from_csv = set(source_names)
    ids_from_dirs = set(counts)
    missing_ids = sorted(ids_from_csv - ids_from_dirs)
    ids_without_names = sorted(ids_from_dirs - ids_from_csv)
    duplicate_groups = [
        paths for paths in exact_hashes.values() if len(paths) > 1
    ]

    source_to_target: dict[str, list[str]] = defaultdict(list)
    for target, source_ids in CLASS_MAP.items():
        for source_id in source_ids:
            source_to_target[str(source_id)].append(target)

    class_rows = []
    for class_id in sorted(ids_from_csv | ids_from_dirs):
        source_name = source_names.get(class_id, "NAME_MISSING")
        mapped = source_to_target.get(str(class_id), [])
        class_rows.append(
            {
                "source_class_id": class_id,
                "source_class_name": source_name,
                "image_count": counts.get(class_id, 0),
                "mapped_target_classes": mapped,
                "mapping_status": (
                    "mapped" if mapped else "no_semantic_match_to_target"
                ),
            }
        )

    target_rows = [
        {
            "target_class": target,
            "source_class_ids": CLASS_MAP[target],
            "image_count": sum(counts.get(class_id, 0) for class_id in CLASS_MAP[target]),
            "minimum_images": 150,
            "below_minimum": True,
            "additional_esp32cam_photos_to_capture": 500,
            "capture_note": (
                "Capture full 320x240 scenes with the target sign visible; "
                "collect distinct physical signs across scenes, distances, "
                "angles, lighting, and weather."
            ),
        }
        for target in TARGET_CLASSES
    ]
    target_rows.append(
        {
            "target_class": BACKGROUND_CLASS,
            "source_class_ids": [],
            "image_count": 0,
            "minimum_images": 150,
            "below_minimum": True,
            "additional_esp32cam_photos_to_capture": 500,
            "capture_note": (
                "Capture full 320x240 road scenes with none of the target signs; "
                "use empty detection-label files because no_sign is background, "
                "not a bounding-box class."
            ),
        }
    )

    return {
        "dataset_path": str(dataset),
        "format": "PNG images arranged in class folders; classification labels only",
        "image_count": sum(counts.values()),
        "class_directory_count": len(ids_from_dirs),
        "class_csv_row_count": len(ids_from_csv),
        "class_counts": class_rows,
        "target_class_counts": target_rows,
        "missing_class_ids": missing_ids,
        "directory_ids_without_class_names": ids_without_names,
        "resolution_counts": dict(sorted(dimensions.items())),
        "corrupt_png_count": len(corrupt_files),
        "corrupt_png_files": corrupt_files,
        "non_png_file_count": len(non_png_files),
        "exact_duplicate_group_count": len(duplicate_groups),
        "exact_duplicate_extra_copy_count": sum(
            len(group) - 1 for group in duplicate_groups
        ),
        "exact_duplicate_groups": duplicate_groups,
        "near_duplicate_analysis": "not_performed",
        "annotation_status": {
            "bounding_boxes_present": False,
            "pseudo_labels_generated": 0,
            "pseudo_labels_manually_reviewed": 0,
            "reviewed_fraction": None,
            "reviewed_fraction_note": (
                "Not applicable: there are no bounding boxes and no "
                "pseudo-labels have been generated or reviewed."
            ),
            "existing_images_usable_for_requested_detection_classes": 0,
        },
        "class_mapping": CLASS_MAP,
        "class_mapping_note": (
            "No exact requested class is present in the source taxonomy. "
            "The source has speed limits 90 and 110 km/h (IDs 18 and 19), "
            "not 30, 50, or 80; it has no school-zone or hospital-zone class. "
            "It also has no negative road-scene images for the no_sign background."
        ),
        "split_status": "blocked_until_scene_images_are_box_annotated",
        "split_plan": {
            "method": "group by source scene and near-duplicate cluster before splitting",
            "train_percent": 80,
            "validation_percent": 10,
            "test_percent": 10,
            "esp32cam_real_device_test": "keep separate from the public/source-image split",
            "split_created": False,
        },
    }


def percentile_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = ((start + 1) + end) / 2
        percentile = (average_rank - 1) / (len(values) - 1) * 100 if len(values) > 1 else 0
        for position in range(start, end):
            ranks[order[position]] = percentile
        start = end
    return ranks


def build_district_index(summary_path: Path, monthly_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = read_csv(summary_path)
    monthly = read_csv(monthly_path)
    summary_by_district = {row["district"]: row for row in summary}
    monthly_sums: dict[str, dict[str, int]] = defaultdict(
        lambda: {"accidents": 0, "deaths": 0, "helmet_non_wearing_deaths": 0, "months": 0}
    )
    for row in monthly:
        district = row["district"]
        totals = monthly_sums[district]
        for column in ("accidents", "deaths", "helmet_non_wearing_deaths"):
            totals[column] += int(row[column])
        totals["months"] += 1

    if set(summary_by_district) != set(monthly_sums):
        raise ValueError("District names do not match between summary and monthly files")

    for district, row in summary_by_district.items():
        monthly_total = monthly_sums[district]
        if monthly_total["months"] != 12:
            raise ValueError(f"{district} has {monthly_total['months']} monthly rows, expected 12")
        if monthly_total["accidents"] != int(row["total_accidents"]):
            raise ValueError(f"Monthly accident total mismatch for {district}")
        if monthly_total["deaths"] != int(row["total_deaths"]):
            raise ValueError(f"Monthly death total mismatch for {district}")

    districts = sorted(summary_by_district)
    fatality_rates = [
        float(summary_by_district[district]["fatality_per_100_accidents"])
        for district in districts
    ]
    hotspot_counts = [
        float(summary_by_district[district]["hotspots_identified"])
        for district in districts
    ]
    fatality_percentiles = percentile_ranks(fatality_rates)
    hotspot_percentiles = percentile_ranks(hotspot_counts)

    results: list[dict[str, Any]] = []
    for index, district in enumerate(districts):
        source = summary_by_district[district]
        monthly_totals = monthly_sums[district]
        score = 0.70 * fatality_percentiles[index] + 0.30 * hotspot_percentiles[index]
        results.append(
            {
                "district": district,
                "statistical_risk_index": round(score, 2),
                "risk_rank": 0,
                "fatality_per_100_accidents": float(source["fatality_per_100_accidents"]),
                "fatality_rate_percentile": round(fatality_percentiles[index], 2),
                "hotspots_identified": int(source["hotspots_identified"]),
                "hotspot_count_percentile": round(hotspot_percentiles[index], 2),
                "accidents_2023": int(source["total_accidents"]),
                "deaths_2023": int(source["total_deaths"]),
                "helmet_non_wearing_deaths_2023": monthly_totals["helmet_non_wearing_deaths"],
                "index_method": "70% fatality-rate percentile + 30% hotspot-count percentile",
            }
        )
    results.sort(key=lambda row: (-row["statistical_risk_index"], row["district"]))
    for rank, row in enumerate(results, start=1):
        row["risk_rank"] = rank

    audit = {
        "summary_csv": str(summary_path),
        "monthly_csv": str(monthly_path),
        "district_count": len(results),
        "monthly_rows": len(monthly),
        "months_per_district": 12,
        "monthly_totals_match_summary": True,
        "statewide_accidents_2023": sum(row["accidents_2023"] for row in results),
        "statewide_deaths_2023": sum(row["deaths_2023"] for row in results),
        "statewide_helmet_non_wearing_deaths_2023": sum(
            row["helmet_non_wearing_deaths_2023"] for row in results
        ),
        "index_name": "statistical risk index",
        "formula": (
            "0.70 * percentile_rank(fatalities per 100 accidents) + "
            "0.30 * percentile_rank(identified hotspot count)"
        ),
        "percentile_definition": (
            "Ascending average rank for ties, scaled to [0,100] using "
            "(average_rank - 1) / (district_count - 1) * 100."
        ),
        "limitations": [
            "Descriptive district-level prioritization only; it is not a trained or predictive model.",
            "Hotspot counts are not normalized by population, road length, or traffic volume.",
            "The 2023 aggregate data has no per-trip speed, alcohol, sign, or vehicle-level features.",
            "Weights are transparent analyst choices, not statistically fitted parameters.",
            "Monthly data is used for consistency checks and district helmet-death totals, not forecasting.",
        ],
    }
    return results, audit


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_audit_report(path: Path, audit: dict[str, Any]) -> None:
    lines = [
        "# Traffic-sign dataset audit",
        "",
        f"- **Dataset:** `{audit['dataset_path']}`",
        f"- **Images audited:** {audit['image_count']:,}",
        f"- **Format:** {audit['format']}",
        f"- **Resolution counts:** {audit['resolution_counts']}",
        f"- **Corrupt PNG files:** {audit['corrupt_png_count']}",
        f"- **Missing class IDs:** {audit['missing_class_ids']}",
        (
            "- **Exact duplicates:** "
            f"{audit['exact_duplicate_group_count']} groups, "
            f"{audit['exact_duplicate_extra_copy_count']} extra copies"
        ),
        "- **Near duplicates:** not analyzed",
        "",
        "## Source class counts",
        "",
        "| ID | Source label | Images | Requested detector mapping |",
        "|---:|---|---:|---|",
    ]
    for row in audit["class_counts"]:
        mapping = ", ".join(row["mapped_target_classes"]) or "none"
        lines.append(
            f"| {row['source_class_id']} | {row['source_class_name']} | "
            f"{row['image_count']} | {mapping} |"
        )
    lines.extend(
        [
            "",
            "## Requested class gaps",
            "",
            "| Target class | Mapped source images | Below 150? | Additional ESP32-CAM captures planned |",
            "|---|---:|---|---:|",
        ]
    )
    for row in audit["target_class_counts"]:
        lines.append(
            f"| `{row['target_class']}` | {row['image_count']} | "
            f"{row['below_minimum']} | {row['additional_esp32cam_photos_to_capture']} |"
        )
    lines.extend(
        [
            "",
            "## Annotation and split readiness",
            "",
            f"- Bounding boxes present: {audit['annotation_status']['bounding_boxes_present']}.",
            f"- Pseudo-labels generated/reviewed: {audit['annotation_status']['pseudo_labels_generated']}/"
            f"{audit['annotation_status']['pseudo_labels_manually_reviewed']}; "
            f"review fraction: not applicable.",
            f"- Split: not created ({audit['split_status']}).",
            "- Future split: group by source scene and near-duplicate cluster before an 80/10/10 "
            "train/validation/test split. Keep ESP32-CAM captures as a separate real-device test set.",
            "",
            "No object boxes were inferred from classification labels. The requested target classes "
            "have no matching source classes in this dataset, and it has no no_sign background images. "
            "Capture full 320x240 scenes containing each requested sign class and negative road scenes; "
            "the suggested 500 captures per class are collection targets, "
            "not a guarantee of coverage or model performance.",
            "",
            "Licensing was not established from the inspected dataset files.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    default_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Audit sign data and build the TN statistical risk index.")
    parser.add_argument(
        "--sign-dataset",
        type=Path,
        default=default_root.parent / "archive (1)" / "Indian-Traffic Sign-Dataset",
    )
    parser.add_argument("--csv-dir", type=Path, default=default_root / "files (2)")
    parser.add_argument("--output-dir", type=Path, default=default_root / "artifacts")
    args = parser.parse_args()

    sign_audit = audit_signs(args.sign_dataset)
    risk_rows, risk_audit = build_district_index(
        args.csv_dir / "02_district_summary_2023.csv",
        args.csv_dir / "01_district_monthly_2023.csv",
    )
    write_json(args.output_dir / "data_audit.json", sign_audit)
    write_audit_report(args.output_dir / "data_audit_report.md", sign_audit)
    write_csv(
        args.output_dir / "sign_class_counts.csv",
        sign_audit["class_counts"],
        [
            "source_class_id",
            "source_class_name",
            "image_count",
            "mapped_target_classes",
            "mapping_status",
        ],
    )
    write_csv(
        args.output_dir / "target_class_gaps.csv",
        sign_audit["target_class_counts"],
        [
            "target_class",
            "source_class_ids",
            "image_count",
            "minimum_images",
            "below_minimum",
            "additional_esp32cam_photos_to_capture",
            "capture_note",
        ],
    )
    write_csv(
        args.output_dir / "annotation_review_queue.csv",
        [],
        [
            "image_path",
            "source_scene_id",
            "near_duplicate_group",
            "proposed_class",
            "confidence",
            "proposed_x_min_px",
            "proposed_y_min_px",
            "proposed_x_max_px",
            "proposed_y_max_px",
            "reviewer",
            "decision",
            "final_class",
            "final_x_min_px",
            "final_y_min_px",
            "final_x_max_px",
            "final_y_max_px",
            "review_notes",
        ],
    )
    write_csv(
        args.output_dir / "district_risk_index_2023.csv",
        risk_rows,
        list(risk_rows[0]),
    )
    write_json(args.output_dir / "district_index_audit.json", risk_audit)
    write_json(
        args.output_dir / "metrics.json",
        {
            "status": "not_trained_or_evaluated",
            "reason": (
                "The uploaded classification dataset has no target-class examples "
                "and no bounding boxes; no ESP32-CAM held-out test set was supplied."
            ),
            "class_names": list(TARGET_CLASSES),
            "test_metrics": None,
            "real_device_metrics": None,
            "domain_gap": None,
            "model_size_bytes": None,
            "ram_estimate_bytes": None,
            "inference_time_ms": None,
            "note": "Null means not measured; no metric or deployment estimate is asserted.",
        },
    )
    write_json(
        args.output_dir / "confusion_matrix.json",
        {
            "status": "not_measured",
            "class_names": list(TARGET_CLASSES) + [BACKGROUND_CLASS],
            "matrix": None,
            "reason": "No detector has been trained and no held-out labeled images are available.",
        },
    )
    print(
        json.dumps(
            {
                "sign_images": sign_audit["image_count"],
                "target_classes_below_150": [
                    row["target_class"]
                    for row in sign_audit["target_class_counts"]
                    if row["image_count"] < 150
                ],
                "exact_duplicate_groups": sign_audit["exact_duplicate_group_count"],
                "corrupt_pngs": sign_audit["corrupt_png_count"],
                "districts": risk_audit["district_count"],
                "accidents_2023": risk_audit["statewide_accidents_2023"],
                "deaths_2023": risk_audit["statewide_deaths_2023"],
                "helmet_non_wearing_deaths_2023": risk_audit[
                    "statewide_helmet_non_wearing_deaths_2023"
                ],
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
