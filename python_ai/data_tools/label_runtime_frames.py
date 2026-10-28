from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2


SIGN_CLASSES = (
    "school_zone",
    "hospital_zone",
    "speed_30",
    "speed_50",
    "speed_80",
)


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually label sampled runtime frames for frame-level evaluation."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_name(f"{args.input.stem}_labeled.jsonl")
    records = load_records(args.input)

    try:
        for index, record in enumerate(records):
            image_path = record.get("evaluation_image")
            if not image_path or record.get("ground_truth") is not None:
                continue
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(f"Could not read sampled evaluation frame: {image_path}")
            cv2.imshow("Manual frame review (close window or press q to stop)", image)
            cv2.waitKey(1)
            print(
                f"\nFrame {record.get('sequence')} from run {record.get('run_id')}: {image_path}"
            )
            object_answer = input("Ground-truth object hazard? [y/n/q]: ").strip().lower()
            if object_answer == "q":
                break
            if object_answer not in {"y", "n"}:
                raise ValueError("Answer object hazard with y, n, or q")
            sign_answer = input(
                "Visible target sign classes, comma-separated "
                f"({', '.join(SIGN_CLASSES)}), or blank for none: "
            ).strip()
            labels = sorted(
                {
                    label.strip()
                    for label in sign_answer.split(",")
                    if label.strip()
                }
            )
            unsupported = set(labels) - set(SIGN_CLASSES)
            if unsupported:
                raise ValueError(f"Unsupported sign classes: {sorted(unsupported)}")
            record["ground_truth"] = {
                "object_hazard": object_answer == "y",
                "sign_classes": labels,
            }
            write_records(output, records)
            print(f"Saved reviewed labels to {output}")
    finally:
        cv2.destroyAllWindows()

    write_records(output, records)
    pending = sum(
        1
        for record in records
        if record.get("evaluation_image") and record.get("ground_truth") is None
    )
    print(f"Output: {output}; sampled frames still awaiting labels: {pending}")


if __name__ == "__main__":
    main()
