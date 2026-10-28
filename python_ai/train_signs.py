from ultralytics import YOLO
from pathlib import Path

DATA_YAML = Path(__file__).with_name("data_signs.yaml")

if not DATA_YAML.exists():
    raise FileNotFoundError(
        "Create data_signs.yaml from data_signs.yaml.example and set the correct dataset paths."
    )

# Starts from a general pretrained detector; it is NOT a pretrained traffic-sign model.
model = YOLO("yolo11n.pt")
results = model.train(
    data=str(DATA_YAML),
    epochs=60,
    imgsz=640,
    batch=8,
    patience=15,
    project="runs/traffic_signs",
    name="train",
)
print("Training finished. Find best.pt under runs/traffic_signs/train/weights/")
