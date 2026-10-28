from __future__ import annotations

import argparse
from collections import Counter
import json
import statistics
from pathlib import Path
from typing import Any


SIGN_CLASSES = (
    "school_zone",
    "hospital_zone",
    "speed_30",
    "speed_50",
    "speed_80",
)


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def binary_metrics(truth: list[bool], predictions: list[bool]) -> dict[str, Any]:
    tp = sum(actual and predicted for actual, predicted in zip(truth, predictions))
    tn = sum(not actual and not predicted for actual, predicted in zip(truth, predictions))
    fp = sum(not actual and predicted for actual, predicted in zip(truth, predictions))
    fn = sum(actual and not predicted for actual, predicted in zip(truth, predictions))
    return {
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "specificity": tn / (tn + fp) if tn + fp else None,
        "frame_count": len(truth),
    }


def read_records(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if record.get("event") in {
                "camera_frame_failure",
                "serial_write_failure",
                "evaluation_frame_write_failure",
            }:
                records.append(record)
                continue
            truth = record.get("ground_truth")
            if truth is None:
                if record.get("evaluation_image"):
                    raise ValueError(
                        f"{path}:{line_number}: manually label each saved evaluation "
                        "frame before computing metrics"
                    )
                continue
            if not isinstance(truth, dict) or not isinstance(truth.get("object_hazard"), bool):
                raise ValueError(
                    f"{path}:{line_number}: add manually verified ground_truth "
                    "with boolean object_hazard and sign_classes list before evaluation"
                )
            sign_classes = truth.get("sign_classes")
            if not isinstance(sign_classes, list):
                raise ValueError(
                    f"{path}:{line_number}: ground_truth.sign_classes must be a list "
                    "(empty means no target sign)"
                )
            invalid_labels = set(sign_classes) - set(SIGN_CLASSES)
            if invalid_labels:
                raise ValueError(
                    f"{path}:{line_number}: unsupported ground-truth labels "
                    f"{sorted(invalid_labels)}"
                )
            records.append(record)
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    failure_events = Counter(
        record["event"]
        for record in records
        if record.get("event")
        in {
            "camera_frame_failure",
            "serial_write_failure",
            "evaluation_frame_write_failure",
        }
    )
    frame_records = [record for record in records if "event" not in record]
    if not frame_records:
        raise ValueError("No annotated inference frames are available for model metrics")

    object_truth = []
    object_predictions = []
    class_truth = {name: [] for name in SIGN_CLASSES}
    class_predictions = {name: [] for name in SIGN_CLASSES}
    inference = {"object_inference_ms": [], "sign_inference_ms": [], "end_to_end_ms": []}
    response_latencies: list[float] = []
    telemetry_count = 0
    stale_count = 0
    sensor_fault_count = 0
    alcohol_cutoff_violations = 0
    stale_cutoff_violations = 0
    sensor_cutoff_violations = 0
    estop_cutoff_violations = 0
    warmup_cutoff_violations = 0

    for record in frame_records:
        truth = record["ground_truth"]
        if not isinstance(record.get("object_hazard_input"), bool):
            raise ValueError("Each inference frame must include object_hazard_input as bool")
        detections = record.get("sign_detections")
        if not isinstance(detections, list):
            raise ValueError("Each inference frame must include a sign_detections list")
        if any(
            not isinstance(detection, dict)
            or detection.get("class") not in SIGN_CLASSES
            for detection in detections
        ):
            raise ValueError("sign_detections contains an invalid or unsupported class")
        object_truth.append(truth["object_hazard"])
        object_predictions.append(record["object_hazard_input"])

        predicted_signs = {detection["class"] for detection in detections}
        actual_signs = set(truth["sign_classes"])
        for name in SIGN_CLASSES:
            class_truth[name].append(name in actual_signs)
            class_predictions[name].append(name in predicted_signs)

        for key in inference:
            value = record.get(key)
            if isinstance(value, (int, float)):
                inference[key].append(float(value))

        for reading in record.get("controller_telemetry", []):
            if not isinstance(reading, dict):
                raise ValueError("controller_telemetry entries must be objects")
            bool_fields = (
                "command_stale",
                "sensor_fault",
                "alcohol_alert",
                "estop_active",
                "warmup_active",
            )
            if any(not isinstance(reading.get(field), bool) for field in bool_fields):
                raise ValueError(
                    "controller telemetry is missing required boolean fault/state fields"
                )
            if type(reading.get("motor_pwm")) is not int:
                raise ValueError("controller telemetry must include integer motor_pwm")
            telemetry_count += 1
            response = reading.get("command_response_ms")
            if isinstance(response, (int, float)) and response >= 0:
                response_latencies.append(float(response))
            if reading.get("command_stale") is True:
                stale_count += 1
                if reading["motor_pwm"] != 0:
                    stale_cutoff_violations += 1
            if reading.get("sensor_fault") is True:
                sensor_fault_count += 1
                if reading["motor_pwm"] != 0:
                    sensor_cutoff_violations += 1
            if reading["alcohol_alert"] is True and reading["motor_pwm"] != 0:
                alcohol_cutoff_violations += 1
            if reading["estop_active"] is True and reading["motor_pwm"] != 0:
                estop_cutoff_violations += 1
            if reading["warmup_active"] is True and reading["motor_pwm"] != 0:
                warmup_cutoff_violations += 1

    latency_summary = {
        key: {
            "samples": len(values),
            "mean_ms": statistics.fmean(values) if values else None,
            "p95_ms": percentile(values, 0.95),
            "max_ms": max(values) if values else None,
        }
        for key, values in inference.items()
    }
    return {
        "status": "evaluated",
        "evaluation_unit": (
            "frame-level presence; not bounding-box IoU or mAP. Ground truth "
            "must be manually annotated independently of model predictions."
        ),
        "frame_count": len(frame_records),
        "runtime_failure_events": dict(failure_events),
        "object_hazard": binary_metrics(object_truth, object_predictions),
        "sign_classes_frame_presence": {
            name: binary_metrics(class_truth[name], class_predictions[name])
            for name in SIGN_CLASSES
        },
        "latency": {
            **latency_summary,
            "controller_response": {
                "samples": len(response_latencies),
                "mean_ms": statistics.fmean(response_latencies) if response_latencies else None,
                "p95_ms": percentile(response_latencies, 0.95),
                "max_ms": max(response_latencies) if response_latencies else None,
            },
        },
        "controller": {
            "telemetry_samples": telemetry_count,
            "stale_command_samples": stale_count,
            "sensor_fault_samples": sensor_fault_count,
            "alcohol_cutoff_violations": alcohol_cutoff_violations,
            "stale_cutoff_violations": stale_cutoff_violations,
            "sensor_fault_cutoff_violations": sensor_cutoff_violations,
            "estop_cutoff_violations": estop_cutoff_violations,
            "warmup_cutoff_violations": warmup_cutoff_violations,
        },
        "limitations": [
            "Frame-presence metrics do not measure box localization or mAP.",
            "Only telemetry records actually captured in the run are included.",
            "Disconnect and sensor fault behavior requires deliberate bench fault-injection tests.",
            "A zero cutoff violation count is only observational and does not certify safety.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate annotated runtime JSONL logs; never infer ground truth."
    )
    parser.add_argument("input", type=Path, help="runtime_metrics.jsonl with reviewed ground_truth")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "runtime_evaluation.json",
    )
    args = parser.parse_args()
    report = evaluate(read_records(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
