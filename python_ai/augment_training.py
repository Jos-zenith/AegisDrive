from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np
import yaml


def resolve_path(dataset_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else dataset_root / path


def augment_image(image: np.ndarray, rng: random.Random) -> np.ndarray:
    brightness = rng.uniform(0.7, 1.3)
    image = cv2.convertScaleAbs(image, alpha=brightness, beta=rng.randint(-12, 12))
    if rng.random() < 0.35:
        image = cv2.GaussianBlur(image, (3, 3), sigmaX=rng.uniform(0.1, 0.8))
    quality = rng.randint(55, 95)
    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )
    if not success:
        raise RuntimeError("OpenCV failed to JPEG-encode augmented training image")
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("OpenCV failed to decode its augmented JPEG output")
    return decoded


def build_training_augmentations(
    data_yaml: Path,
    output_yaml: Path,
    seed: int,
) -> dict[str, object]:
    with data_yaml.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or "path" not in config or "train" not in config:
        raise ValueError("Dataset YAML must define path and a train image directory")

    dataset_root = Path(config["path"]).resolve()
    train_images = resolve_path(dataset_root, str(config["train"]))
    if not train_images.is_dir():
        raise NotADirectoryError(
            f"Training augmentation requires a train image directory: {train_images}"
        )
    train_labels = dataset_root / "labels" / "train"
    if not train_labels.is_dir():
        raise NotADirectoryError(f"Training labels directory is missing: {train_labels}")

    augmentation_root = dataset_root / "train_augmentations"
    image_output_dir = augmentation_root / "images"
    label_output_dir = augmentation_root / "labels"
    image_output_dir.mkdir(parents=True, exist_ok=True)
    label_output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    image_paths = sorted(
        path for path in train_images.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    )
    if not image_paths:
        raise ValueError(f"No training images found under {train_images}")

    training_list = augmentation_root / "train_images.txt"
    with training_list.open("w", encoding="utf-8", newline="\n") as train_list:
        for index, image_path in enumerate(image_paths):
            label_path = train_labels / f"{image_path.stem}.txt"
            if not label_path.is_file():
                raise FileNotFoundError(f"Missing YOLO training label: {label_path}")
            train_list.write(f"{image_path.resolve().as_posix()}\n")
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Could not decode training image: {image_path}")
            augmented = augment_image(image, rng)
            augmented_name = f"{index:06d}_{image_path.stem}.jpg"
            augmented_path = image_output_dir / augmented_name
            if not cv2.imwrite(str(augmented_path), augmented):
                raise RuntimeError(f"Failed to write augmented image: {augmented_path}")
            shutil.copy2(
                label_path,
                label_output_dir / f"{Path(augmented_name).stem}.txt",
            )
            train_list.write(f"{augmented_path.resolve().as_posix()}\n")

    config["train"] = training_list.relative_to(dataset_root).as_posix()
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    with output_yaml.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)

    report = {
        "seed": seed,
        "source_training_images": len(image_paths),
        "generated_training_images": len(image_paths),
        "training_list": str(training_list),
        "dataset_yaml": str(output_yaml),
        "transformations": {
            "brightness_multiplier": [0.7, 1.3],
            "brightness_offset": [-12, 12],
            "gaussian_blur_probability": 0.35,
            "gaussian_blur_kernel": [3, 3],
            "jpeg_quality": [55, 95],
            "geometry": "YOLO trainer applies small rotation/scale after splitting",
            "validation_test_augmented": False,
        },
        "note": "Augmentations are generated only from already-split training images.",
    }
    (augmentation_root / "augmentation_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create deterministic brightness/blur/JPEG variants of train data only."
    )
    parser.add_argument("--data", type=Path, default=Path("data_signs.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data_signs_augmented.yaml"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(build_training_augmentations(args.data, args.output, args.seed), indent=2))


if __name__ == "__main__":
    main()
