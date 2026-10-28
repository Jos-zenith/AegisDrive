from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from augment_training import build_training_augmentations


class TrainingAugmentationTests(unittest.TestCase):
    def test_only_training_split_is_augmented_reproducibly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "images" / "train").mkdir(parents=True)
            (root / "images" / "val").mkdir(parents=True)
            (root / "images" / "test").mkdir(parents=True)
            (root / "labels" / "train").mkdir(parents=True)
            image = root / "images" / "train" / "sample.jpg"
            self.assertTrue(cv2.imwrite(str(image), np.full((24, 32, 3), 127, dtype=np.uint8)))
            label_text = "2 0.5 0.5 0.4 0.4\n"
            (root / "labels" / "train" / "sample.txt").write_text(
                label_text,
                encoding="utf-8",
            )
            data_yaml = root / "data.yaml"
            data_yaml.write_text(
                yaml.safe_dump(
                    {
                        "path": str(root),
                        "train": "images/train",
                        "val": "images/val",
                        "test": "images/test",
                        "names": ["school_zone", "hospital_zone", "speed_30", "speed_50", "speed_80"],
                    }
                ),
                encoding="utf-8",
            )

            output_yaml = root / "augmented.yaml"
            report = build_training_augmentations(data_yaml, output_yaml, seed=42)
            generated_image = root / "train_augmentations" / "images" / "000000_sample.jpg"
            generated_label = root / "train_augmentations" / "labels" / "000000_sample.txt"
            output_config = yaml.safe_load(output_yaml.read_text(encoding="utf-8"))
            self.assertEqual(report["generated_training_images"], 1)
            self.assertTrue(generated_image.is_file())
            self.assertEqual(generated_label.read_text(encoding="utf-8"), label_text)
            self.assertEqual(output_config["val"], "images/val")
            self.assertEqual(output_config["test"], "images/test")
            self.assertIn("train_augmentations/train_images.txt", output_config["train"])


if __name__ == "__main__":
    unittest.main()
