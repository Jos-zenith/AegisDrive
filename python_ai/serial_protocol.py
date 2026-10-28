from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import time
from typing import Any


VALID_SPEED_LIMITS = frozenset({30, 50, 80})


@dataclass(frozen=True)
class ControllerTelemetry:
    sequence: int
    mq3_adc: int
    rpm: float
    sign_limit: int
    object_hazard: bool
    alcohol_alert: bool
    overspeed_alert: bool
    command_stale: bool
    sensor_fault: bool
    motor_pwm: int
    controller_hazard: bool
    estop_active: bool
    warmup_active: bool
    received_monotonic: float


def encode_command(sequence: int, object_hazard: bool, sign_limit: int | None) -> bytes:
    if not 0 <= sequence <= 2_147_483_647:
        raise ValueError("sequence must be in [0, 2147483647]")
    if not isinstance(object_hazard, bool):
        raise ValueError("object_hazard must be bool")
    limit_value = -1 if sign_limit is None else sign_limit
    if limit_value != -1 and limit_value not in VALID_SPEED_LIMITS:
        raise ValueError("sign_limit must be None, 30, 50, or 80")
    return f"CMD,{sequence},{int(object_hazard)},{limit_value}\n".encode("ascii")


def parse_telemetry(line: bytes | str, received_monotonic: float | None = None) -> ControllerTelemetry:
    if isinstance(line, bytes):
        try:
            text = line.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("telemetry must be ASCII") from exc
    else:
        text = line.strip()

    fields = text.split(",")
    expected_names = (
        "mq3",
        "rpm",
        "limit",
        "object",
        "alcohol",
        "overspeed",
        "stale",
        "sensor_fault",
        "pwm",
        "hazard",
        "estop",
        "warmup",
    )
    if len(fields) != 14 or fields[0] != "TEL":
        raise ValueError("telemetry must contain TEL,sequence and twelve fields")
    try:
        sequence = int(fields[1])
        values = {
            key: value.split("=", 1)[1]
            for key, value in zip(expected_names, fields[2:])
            if value.startswith(f"{key}=")
        }
        if len(values) != len(expected_names):
            raise ValueError("telemetry field names or ordering are invalid")
        telemetry = ControllerTelemetry(
            sequence=sequence,
            mq3_adc=int(values["mq3"]),
            rpm=float(values["rpm"]),
            sign_limit=int(values["limit"]),
            object_hazard=bool(int(values["object"])),
            alcohol_alert=bool(int(values["alcohol"])),
            overspeed_alert=bool(int(values["overspeed"])),
            command_stale=bool(int(values["stale"])),
            sensor_fault=bool(int(values["sensor_fault"])),
            motor_pwm=int(values["pwm"]),
            controller_hazard=bool(int(values["hazard"])),
            estop_active=bool(int(values["estop"])),
            warmup_active=bool(int(values["warmup"])),
            received_monotonic=(
                time.monotonic()
                if received_monotonic is None
                else received_monotonic
            ),
        )
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid telemetry line: {text!r}") from exc

    if not 0 <= telemetry.sequence <= 2_147_483_647:
        raise ValueError("telemetry sequence is outside the allowed range")
    if not 0 <= telemetry.mq3_adc <= 4095:
        raise ValueError("MQ-3 ADC value is outside [0, 4095]")
    if not math.isfinite(telemetry.rpm) or telemetry.rpm < 0:
        raise ValueError("RPM must be a finite nonnegative number")
    if telemetry.sign_limit not in {-1, *VALID_SPEED_LIMITS}:
        raise ValueError("controller reported an unsupported sign limit")
    if not 0 <= telemetry.motor_pwm <= 255:
        raise ValueError("motor PWM is outside [0, 255]")
    boolean_names = (
        "object",
        "alcohol",
        "overspeed",
        "stale",
        "sensor_fault",
        "hazard",
        "estop",
        "warmup",
    )
    try:
        boolean_values = [int(values[name]) for name in boolean_names]
    except ValueError as exc:
        raise ValueError("boolean telemetry fields must be 0 or 1") from exc
    if any(value not in (0, 1) for value in boolean_values):
        raise ValueError("boolean telemetry fields must be 0 or 1")
    return telemetry


def telemetry_to_dict(telemetry: ControllerTelemetry) -> dict[str, Any]:
    return asdict(telemetry)


def write_jsonl_record(stream: Any, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
    stream.flush()
