import time
from pathlib import Path

import cv2
import serial
from ultralytics import YOLO

# -------- EDIT THESE SETTINGS --------
CAMERA_STREAM_URL = "http://192.168.1.50/stream"  # replace with ESP32-CAM IP
SERIAL_PORT = "COM11"                             # replace with ESP32 DevKit COM port
SERIAL_BAUD = 115200
SIGN_MODEL_PATH = Path(__file__).with_name("best_signs.pt")
COCO_MODEL_PATH = "yolo11n.pt"

# This must match the class names in your trained sign model.
# The model's class names may be strings or a dict of class IDs to names.
SPEED_SIGN_LIMITS = {
    "speed_limit_20": 20,
    "speed_limit_30": 30,
    "speed_limit_40": 40,
    "speed_limit_50": 50,
    "speed_limit_60": 60,
    "speed_limit_80": 80,
}

# Objects from COCO model that we treat as potential hazards for a tabletop demo.
HAZARD_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
CONFIDENCE = 0.45
SEND_INTERVAL_SECONDS = 0.5
# -------------------------------------

def connect_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.1)
        time.sleep(2)  # ESP32 often resets when serial opens
        print(f"Connected to ESP32 on {SERIAL_PORT}")
        return ser
    except serial.SerialException as exc:
        print(f"Serial unavailable ({exc}). Running AI without hardware commands.")
        return None

def send_line(ser, line):
    if ser is None:
        return
    try:
        ser.write((line + "\n").encode("utf-8"))
    except serial.SerialException as exc:
        print("Serial write error:", exc)

def normalize_name(name):
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")

def main():
    print("Loading COCO object detector...")
    object_model = YOLO(COCO_MODEL_PATH)

    sign_model = None
    if SIGN_MODEL_PATH.exists():
        print(f"Loading custom sign model: {SIGN_MODEL_PATH}")
        sign_model = YOLO(str(SIGN_MODEL_PATH))
    else:
        print("WARNING: best_signs.pt not found. Speed-sign recognition is DISABLED.")
        print("Train a model using train_signs.py and install the resulting weights.")

    print("Opening camera stream:", CAMERA_STREAM_URL)
    cap = cv2.VideoCapture(CAMERA_STREAM_URL)
    if not cap.isOpened():
        raise RuntimeError(
            "Cannot open camera stream. Confirm the ESP32-CAM stream URL works in a browser."
        )

    ser = connect_serial()
    last_send = 0.0
    last_limit = None
    last_hazard = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame unavailable; retrying...")
                time.sleep(0.25)
                continue

            hazard_found = False
            detected_sign_limit = None
            labels_to_draw = []

            # General road objects: COCO model
            object_results = object_model.predict(
                source=frame, conf=CONFIDENCE, imgsz=640, verbose=False
            )
            for result in object_results:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    name = normalize_name(object_model.names[cls_id])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    if name in HAZARD_CLASSES:
                        hazard_found = True
                    label = f"{name} {conf:.2f}"
                    labels_to_draw.append((x1, y1, x2, y2, label))

            # Speed signs: custom trained detector only
            if sign_model is not None:
                sign_results = sign_model.predict(
                    source=frame, conf=CONFIDENCE, imgsz=640, verbose=False
                )
                for result in sign_results:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        name = normalize_name(sign_model.names[cls_id])
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        if name in SPEED_SIGN_LIMITS:
                            detected_sign_limit = SPEED_SIGN_LIMITS[name]
                        label = f"SIGN:{name} {conf:.2f}"
                        labels_to_draw.append((x1, y1, x2, y2, label))

            # Send hardware commands periodically; repeat state to avoid stale flags.
            now = time.time()
            if now - last_send >= SEND_INTERVAL_SECONDS:
                if detected_sign_limit is not None:
                    last_limit = detected_sign_limit
                if last_limit is not None:
                    send_line(ser, f"LIMIT:{last_limit}")

                # A car/person in a frame is a potential hazard in this basic demo,
                # not proof of imminent collision. Tune this logic for your test scene.
                last_hazard = hazard_found
                send_line(ser, f"HAZARD:{1 if hazard_found else 0}")
                last_send = now

            for x1, y1, x2, y2, label in labels_to_draw:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    frame, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2
                )

            status = (
                f"hazard={hazard_found} | "
                f"speed sign={detected_sign_limit if detected_sign_limit is not None else 'not detected'}"
            )
            cv2.putText(frame, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (0, 0, 255) if hazard_found else (255, 255, 0), 2)

            cv2.imshow("AI Accident Prevention - Prototype", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        if ser is not None:
            ser.close()

if __name__ == "__main__":
    main()
