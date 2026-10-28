from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import cv2
import serial
from ultralytics import YOLO

from serial_protocol import (
    VALID_SPEED_LIMITS,
    encode_command,
    parse_telemetry,
    telemetry_to_dict,
    write_jsonl_record,
)

# -------- EDIT THESE SETTINGS --------
CAMERA_STREAM_URL = "http://192.168.1.50/stream"
SERIAL_PORT = "COM11"
SERIAL_BAUD = 115200
SIGN_MODEL_PATH = Path(__file__).with_name("best_signs.pt")
OBJECT_MODEL_PATH = Path(__file__).with_name("yolo11n.pt")
RUNTIME_LOG_PATH = Path(__file__).with_name("artifacts") / "runtime_metrics.jsonl"
EVALUATION_FRAME_DIR = Path(__file__).with_name("artifacts") / "evaluation_frames"

HAZARD_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
SIGN_SPEED_LIMITS = {"speed_30": 30, "speed_50": 50, "speed_80": 80}
SIGN_ZONE_CLASSES = {"school_zone", "hospital_zone"}
SUPPORTED_SIGN_CLASSES = set(SIGN_SPEED_LIMITS) | SIGN_ZONE_CLASSES
CONFIDENCE = 0.45
SIGN_MEMORY_SECONDS = 3.0
SERIAL_READ_TIMEOUT_SECONDS = 0.05
EVALUATION_FRAME_INTERVAL_SECONDS = 1.0
# -------------------------------------


def connect_serial() -> serial.Serial:
    controller = serial.Serial(
        SERIAL_PORT,
        SERIAL_BAUD,
        timeout=SERIAL_READ_TIMEOUT_SECONDS,
        write_timeout=0.5,
    )
    time.sleep(2.0)
    controller.reset_input_buffer()
    print(f"Connected to ESP32 controller on {SERIAL_PORT}")
    return controller


def normalize_name(name: object) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def model_names(model: YOLO) -> set[str]:
    names = model.names
    values = names.values() if isinstance(names, dict) else names
    return {normalize_name(name) for name in values}


def drain_telemetry(
    controller: serial.Serial,
) -> tuple[list[dict[str, object]], int]:
    readings: list[dict[str, object]] = []
    invalid_count = 0
    while controller.in_waiting:
        line = controller.readline()
        if not line:
            break
        try:
            telemetry = parse_telemetry(line)
        except ValueError as exc:
            print(f"Rejected invalid controller telemetry: {exc}")
            invalid_count += 1
            continue
        readings.append(telemetry_to_dict(telemetry))
    return readings, invalid_count


def detect(model: YOLO, frame: object) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    results = model.predict(source=frame, conf=CONFIDENCE, verbose=False)
    elapsed_ms = (time.perf_counter() - started) * 1000
    detections: list[dict[str, object]] = []
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0])
            name = normalize_name(model.names[class_id])
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            detections.append(
                {
                    "class": name,
                    "confidence": confidence,
                    "box_xyxy": [x1, y1, x2, y2],
                    "area": max(0, x2 - x1) * max(0, y2 - y1),
                }
            )
    return detections, elapsed_ms


def main() -> None:
    if not OBJECT_MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Local object model not found: {OBJECT_MODEL_PATH}. "
            "Place a compatible checkpoint here; the app does not download one."
        )
    print(f"Loading object detector: {OBJECT_MODEL_PATH}")
    object_model = YOLO(str(OBJECT_MODEL_PATH))

    sign_model = None
    if not SIGN_MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Sign model not found: {SIGN_MODEL_PATH}. Collect and label the target "
            "classes before running the integrated detector."
        )
    sign_model = YOLO(str(SIGN_MODEL_PATH))
    unsupported = model_names(sign_model) - SUPPORTED_SIGN_CLASSES
    missing = SUPPORTED_SIGN_CLASSES - model_names(sign_model)
    if unsupported or missing:
        raise ValueError(
            "Sign model labels must match exactly the configured target classes. "
            f"Unsupported={sorted(unsupported)}, missing={sorted(missing)}"
        )

    cap = cv2.VideoCapture(CAMERA_STREAM_URL)
    if not cap.isOpened():
        raise RuntimeError(
            "Cannot open camera stream. Check the URL and confirm the stream is reachable."
        )

    controller = None
    log_stream = None
    try:
        controller = connect_serial()
        RUNTIME_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_stream = RUNTIME_LOG_PATH.open("a", encoding="utf-8")
        print(f"Runtime telemetry log: {RUNTIME_LOG_PATH}")

        sequence = 0
        run_id = uuid.uuid4().hex
        current_sign_limit = None
        last_sign_seen = 0.0
        last_evaluation_frame = 0.0
        last_telemetry: dict[str, object] | None = None
        pending_commands: dict[int, float] = {}

        while True:
            frame_started = time.perf_counter()
            captured_at = time.time()
            ok, frame = cap.read()
            if not ok or frame is None:
                write_jsonl_record(
                    log_stream,
                    {
                        "timestamp_unix": captured_at,
                        "event": "camera_frame_failure",
                        "elapsed_ms": (time.perf_counter() - frame_started) * 1000,
                        "ground_truth": None,
                    },
                )
                raise RuntimeError(
                    "Camera frame read failed; exiting so the controller watchdog "
                    "can stop the motor."
                )

            object_detections, object_inference_ms = detect(object_model, frame)
            sign_detections, sign_inference_ms = detect(sign_model, frame)
            now = time.monotonic()

            object_hazard = any(
                detection["class"] in HAZARD_CLASSES
                for detection in object_detections
            )
            target_signs = [
                detection
                for detection in sign_detections
                if detection["class"] in SUPPORTED_SIGN_CLASSES
            ]
            observed_speed_signs = [
                detection
                for detection in target_signs
                if detection["class"] in SIGN_SPEED_LIMITS
            ]
            if observed_speed_signs:
                selected_sign = max(observed_speed_signs, key=lambda item: int(item["area"]))
                current_sign_limit = SIGN_SPEED_LIMITS[str(selected_sign["class"])]
                last_sign_seen = now
            elif now - last_sign_seen > SIGN_MEMORY_SECONDS:
                current_sign_limit = None

            sequence += 1
            command = encode_command(sequence, bool(object_hazard), current_sign_limit)
            command_sent_at = time.monotonic()
            try:
                controller.write(command)
                controller.flush()
            except serial.SerialException as exc:
                write_jsonl_record(
                    log_stream,
                    {
                        "timestamp_unix": captured_at,
                        "sequence": sequence,
                        "event": "serial_write_failure",
                        "error": str(exc),
                        "object_hazard_input": bool(object_hazard),
                        "sign_limit_input": current_sign_limit,
                        "ground_truth": None,
                    },
                )
                raise
            pending_commands[sequence] = command_sent_at

            new_readings, invalid_telemetry_count = drain_telemetry(controller)
            for reading in new_readings:
                ack_sequence = int(reading["sequence"])
                acknowledged = [
                    pending_sequence
                    for pending_sequence in pending_commands
                    if pending_sequence <= ack_sequence
                ]
                acknowledged_sent_at = (
                    pending_commands[max(acknowledged)] if acknowledged else None
                )
                for pending_sequence in acknowledged:
                    pending_commands.pop(pending_sequence)
                if acknowledged_sent_at is not None:
                    reading["command_response_ms"] = (
                        float(reading["received_monotonic"]) - acknowledged_sent_at
                    ) * 1000
                last_telemetry = reading
            while len(pending_commands) > 256:
                pending_commands.pop(next(iter(pending_commands)))

            object_labels = [
                f"{item['class']} {float(item['confidence']):.2f}"
                for item in object_detections
            ]
            sign_labels = [
                f"{item['class']} {float(item['confidence']):.2f}"
                for item in target_signs
            ]
            end_to_end_ms = (time.perf_counter() - frame_started) * 1000
            evaluation_image = None
            if now - last_evaluation_frame >= EVALUATION_FRAME_INTERVAL_SECONDS:
                frame_directory = EVALUATION_FRAME_DIR / run_id
                frame_directory.mkdir(parents=True, exist_ok=True)
                frame_path = frame_directory / f"frame_{sequence:08d}.jpg"
                if not cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                    write_jsonl_record(
                        log_stream,
                        {
                            "run_id": run_id,
                            "timestamp_unix": captured_at,
                            "sequence": sequence,
                            "event": "evaluation_frame_write_failure",
                            "path": str(frame_path),
                        },
                    )
                    raise RuntimeError(f"Could not save evaluation frame: {frame_path}")
                evaluation_image = str(frame_path)
                last_evaluation_frame = now
            write_jsonl_record(
                log_stream,
                {
                    "run_id": run_id,
                    "timestamp_unix": captured_at,
                    "sequence": sequence,
                    "evaluation_image": evaluation_image,
                    "object_detections": object_detections,
                    "sign_detections": sign_detections,
                    "object_hazard_input": bool(object_hazard),
                    "sign_limit_input": current_sign_limit,
                    "rpm": last_telemetry["rpm"] if last_telemetry else None,
                    "mq3_adc": last_telemetry["mq3_adc"] if last_telemetry else None,
                    "alcohol_alert": (
                        last_telemetry["alcohol_alert"] if last_telemetry else None
                    ),
                    "overspeed_alert": (
                        last_telemetry["overspeed_alert"] if last_telemetry else None
                    ),
                    "controller_command_stale": (
                        last_telemetry["command_stale"] if last_telemetry else None
                    ),
                    "controller_sensor_fault": (
                        last_telemetry["sensor_fault"] if last_telemetry else None
                    ),
                    "controller_hazard": (
                        last_telemetry["controller_hazard"] if last_telemetry else None
                    ),
                    "controller_estop_active": (
                        last_telemetry["estop_active"] if last_telemetry else None
                    ),
                    "controller_warmup_active": (
                        last_telemetry["warmup_active"] if last_telemetry else None
                    ),
                    "motor_pwm": (
                        last_telemetry["motor_pwm"] if last_telemetry else None
                    ),
                    "object_inference_ms": object_inference_ms,
                    "sign_inference_ms": sign_inference_ms,
                    "end_to_end_ms": end_to_end_ms,
                    "controller_telemetry": new_readings,
                    "invalid_telemetry_count": invalid_telemetry_count,
                    "ground_truth": None,
                },
            )

            cv2.putText(
                frame,
                f"object_hazard={int(object_hazard)} sign_limit={current_sign_limit}",
                (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 255) if object_hazard else (255, 255, 0),
                1,
            )
            cv2.putText(
                frame,
                f"objects: {', '.join(object_labels)[:90]}",
                (8, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            cv2.putText(
                frame,
                f"signs: {', '.join(sign_labels)[:90]}",
                (8, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            cv2.imshow("AegisDrive - bench prototype", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        if log_stream is not None:
            log_stream.close()
        if controller is not None:
            controller.close()


if __name__ == "__main__":
    main()
