from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from ultralytics import YOLO


EXPECTED_NAMES = [
    "school_zone",
    "hospital_zone",
    "speed_30",
    "speed_50",
    "speed_80",
]
DEFAULT_BASE_MODEL = Path(__file__).with_name("yolo11n.pt")
DEFAULT_RUNS_DIR = Path(__file__).with_name("runs") / "traffic_signs"
ARTIFACTS_DIR = Path(__file__).with_name("artifacts")


def class_names_from_yaml(config: dict[str, Any]) -> list[str]:
    names = config.get("names", {})
    if isinstance(names, dict):
        return [
            name
            for _, name in sorted(names.items(), key=lambda item: int(item[0]))
        ]
    if isinstance(names, list):
        return names
    raise ValueError("Dataset YAML names must be a class-index mapping or list")


def count_split_images(dataset_config: dict[str, Any], split_name: str) -> int:
    dataset_root = Path(dataset_config["path"])
    if not dataset_root.is_absolute():
        dataset_root = dataset_root.resolve()
    split_path = Path(str(dataset_config[split_name]))
    if not split_path.is_absolute():
        split_path = dataset_root / split_path
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    if split_path.is_dir():
        return sum(
            1
            for path in split_path.rglob("*")
            if path.is_file() and path.suffix.lower() in image_extensions
        )
    if not split_path.is_file():
        raise FileNotFoundError(f"{split_name} split not found: {split_path}")
    if split_path.suffix.lower() == ".txt":
        image_paths = [
            Path(line.strip())
            for line in split_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        missing = [path for path in image_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing test/train image listed in {split_path}: {missing[0]}")
        return len(image_paths)
    if split_path.suffix.lower() in image_extensions:
        return 1
    raise ValueError(f"Unsupported {split_name} split path: {split_path}")


def train_and_evaluate(
    data_yaml: Path,
    base_model_path: Path,
    runs_dir: Path,
    seed: int,
    image_size: int,
) -> dict[str, Any]:
    if not data_yaml.is_file():
        raise FileNotFoundError(
            "Create data_signs.yaml from data_signs.yaml.example and point it to "
            "the reviewed, grouped YOLO dataset produced by prepare_yolo_split.py."
        )
    if not base_model_path.is_file():
        raise FileNotFoundError(
            f"Local base checkpoint not found: {base_model_path}. "
            "Place a compatible checkpoint here yourself; this script does not download one."
        )

    with data_yaml.open(encoding="utf-8") as stream:
        dataset_config = yaml.safe_load(stream)
    if not isinstance(dataset_config, dict):
        raise ValueError("Dataset YAML must contain a mapping")
    configured_names = class_names_from_yaml(dataset_config)
    if configured_names != EXPECTED_NAMES:
        raise ValueError(
            f"Dataset class ordering must be {EXPECTED_NAMES}, got {configured_names}"
        )
    for split_name in ("train", "val", "test"):
        if split_name not in dataset_config:
            raise ValueError(f"Dataset YAML must define a separate {split_name!r} split")
    test_image_count = count_split_images(dataset_config, "test")
    if test_image_count == 0:
        raise ValueError("The held-out test split contains no images")

    model = YOLO(str(base_model_path))
    model.train(
        data=str(data_yaml),
        epochs=60,
        imgsz=image_size,
        batch=8,
        patience=15,
        seed=seed,
        deterministic=True,
        workers=0,
        degrees=8,
        scale=0.1,
        fliplr=0.0,
        flipud=0.0,
        hsv_v=0.2,
        mosaic=0.0,
        project=str(runs_dir),
        name="train",
    )

    best_weights = runs_dir / "train" / "weights" / "best.pt"
    if not best_weights.is_file():
        raise FileNotFoundError(f"Training completed without best weights: {best_weights}")
    best_model = YOLO(str(best_weights))
    evaluation = best_model.val(
        data=str(data_yaml),
        split="test",
        imgsz=image_size,
        plots=True,
        save_json=True,
        project=str(runs_dir),
        name="held_out_test",
    )

    box_metrics = evaluation.box
    per_class = {}
    for index, name in enumerate(EXPECTED_NAMES):
        per_class[name] = {
            "precision": float(box_metrics.p[index]),
            "recall": float(box_metrics.r[index]),
            "map50": float(box_metrics.ap50[index]),
            "map50_95": float(box_metrics.maps[index]),
        }

    confusion_matrix = None
    if hasattr(evaluation, "confusion_matrix"):
        matrix = getattr(evaluation.confusion_matrix, "matrix", None)
        if matrix is not None:
            confusion_matrix = matrix.tolist()
    confusion_plot = Path(evaluation.save_dir) / "confusion_matrix.png"

    return {
        "status": "evaluated",
        "test_split": "test",
        "test_image_count": test_image_count,
        "class_names": EXPECTED_NAMES,
        "seed": seed,
        "image_size": image_size,
        "metrics": {
            "precision": float(box_metrics.mp),
            "recall": float(box_metrics.mr),
            "map50": float(box_metrics.map50),
            "map50_95": float(box_metrics.map),
            "per_class": per_class,
            "confusion_matrix": {
                "matrix": confusion_matrix,
                "plot_path": str(confusion_plot) if confusion_plot.is_file() else None,
                "status": "available" if confusion_matrix is not None else "plot_only_or_unavailable",
            },
            "inference_ms_per_image": float(evaluation.speed["inference"]),
        },
        "model": str(best_weights),
        "host_checkpoint_size_bytes": best_weights.stat().st_size,
        "esp32_model_size_bytes": None,
        "esp32_ram_bytes": None,
        "esp32_inference_ms": None,
        "hardware_note": (
            "Latency is measured by Ultralytics validation on this host, not on the "
            "ESP32-CAM. This checkpoint is not an Edge Impulse deployment artifact."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the reviewed sign dataset and evaluate the held-out test split."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).with_name("data_signs.yaml"),
    )
    parser.add_argument("--base-model", type=Path, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--image-size", type=int, default=160)
    args = parser.parse_args()
    results = train_and_evaluate(
        args.data,
        args.base_model,
        args.runs_dir,
        args.seed,
        args.image_size,
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = ARTIFACTS_DIR / "detector_test_metrics.json"
    metrics_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Held-out test metrics written to {metrics_path}")


if __name__ == "__main__":
    main()
