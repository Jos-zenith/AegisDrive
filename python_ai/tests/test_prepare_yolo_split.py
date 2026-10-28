import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_yolo_split import CLASS_NAMES, image_group_split, prepare_split


class PrepareYoloSplitTests(unittest.TestCase):
    def test_group_assignment_is_fixed_and_reproducible(self) -> None:
        assignments = {
            image_group_split(f"site-session-{index}", 42)
            for index in range(100)
        }
        self.assertEqual(assignments, {"train", "val", "test"})
        self.assertEqual(
            image_group_split("site-session-17", 42),
            image_group_split("site-session-17", 42),
        )

    def test_builds_splits_without_splitting_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = []
            group_ids_by_split = {
                split: [
                    group_id
                    for index in range(500)
                    if (group_id := f"{split}-group-{index}")
                    and image_group_split(group_id, 42) == split
                ][:2]
                for split in ("train", "val", "test")
            }
            self.assertTrue(all(len(group_ids) == 2 for group_ids in group_ids_by_split.values()))
            labels_text = "\n".join(
                f"{class_id} 0.5 0.5 0.2 0.2"
                for class_id, _ in enumerate(CLASS_NAMES)
            )
            for split, group_ids in group_ids_by_split.items():
                for index, group_id in enumerate(group_ids):
                    image = root / f"{group_id}-{index}.jpg"
                    label = root / f"{group_id}-{index}.txt"
                    image.write_bytes(f"test image content {group_id}".encode("utf-8"))
                    label.write_text(labels_text, encoding="utf-8")
                    rows.append(
                        {
                            "image_path": str(image),
                            "label_path": str(label),
                            "group_id": group_id,
                            "class_labels": "|".join(CLASS_NAMES),
                            "reviewed": "true",
                        }
                    )

            manifest = root / "reviewed.csv"
            with manifest.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            report = prepare_split(manifest, root / "prepared", seed=42)
            self.assertEqual(report["image_counts"], {"train": 2, "val": 2, "test": 2})
            with (root / "prepared" / "split_manifest.csv").open(encoding="utf-8") as stream:
                split_manifest = list(csv.DictReader(stream))
            for row in split_manifest:
                self.assertEqual(image_group_split(row["group_id"], 42), row["split"])

    def test_rejects_unreviewed_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "one.jpg"
            label = root / "one.txt"
            image.write_bytes(b"image")
            label.write_text("", encoding="utf-8")
            manifest = root / "reviewed.csv"
            manifest.write_text(
                "image_path,label_path,group_id,class_labels,reviewed\n"
                f"{image},{label},session-1,no_sign,false\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not reviewed"):
                prepare_split(manifest, root / "out")


if __name__ == "__main__":
    unittest.main()
