from __future__ import annotations

import argparse
import time

import serial

from serial_protocol import (
    encode_command,
    encode_sync_confirmation,
    encode_sync_request,
    parse_sync_response,
    parse_sync_confirmation,
    parse_telemetry,
)


def read_valid_telemetry(controller: serial.Serial, deadline: float) -> dict[str, object] | None:
    while time.monotonic() < deadline:
        line = controller.readline()
        if not line:
            continue
        try:
            telemetry = parse_telemetry(line)
        except ValueError:
            continue
        return {
            "sequence": telemetry.sequence,
            "rpm": telemetry.rpm,
            "sign_limit": telemetry.sign_limit,
            "object_hazard": telemetry.object_hazard,
            "alcohol_alert": telemetry.alcohol_alert,
            "overspeed_alert": telemetry.overspeed_alert,
            "command_stale": telemetry.command_stale,
            "sensor_fault": telemetry.sensor_fault,
            "motor_pwm": telemetry.motor_pwm,
            "controller_hazard": telemetry.controller_hazard,
            "estop_active": telemetry.estop_active,
            "warmup_active": telemetry.warmup_active,
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bench-only check that lost serial heartbeats cause motor cutoff."
    )
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--baseline-timeout", type=float, default=60.0)
    parser.add_argument("--watchdog-timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.baseline_timeout <= 0 or args.watchdog_timeout < 3.0:
        parser.error("timeouts must be positive; watchdog timeout must be at least 3 seconds")

    print(
        "BENCH TEST ONLY: raise/secure wheels, use low-voltage motor supply, "
        "keep the physical motor-supply cutoff reachable. This test spins the motor."
    )
    sequence = 0
    with serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=0.5) as controller:
        time.sleep(2.0)
        controller.reset_input_buffer()
        controller.write(encode_sync_request())
        controller.flush()
        sync_deadline = time.monotonic() + 2.0
        sequence = None
        while time.monotonic() < sync_deadline:
            line = controller.readline()
            if not line:
                continue
            try:
                sync_state = parse_sync_response(line)
                controller.write(encode_sync_confirmation(sync_state.epoch))
                controller.flush()
                confirmation = controller.readline()
                sequence = parse_sync_confirmation(
                    confirmation, sync_state.epoch
                ).sequence
                break
            except ValueError:
                continue
        if sequence is None:
            raise RuntimeError("Could not synchronize sequence with controller")
        baseline_deadline = time.monotonic() + args.baseline_timeout
        stable_motor_samples = 0
        while time.monotonic() < baseline_deadline:
            sequence = sequence + 1
            controller.write(encode_command(sequence, False, None))
            controller.flush()
            telemetry = read_valid_telemetry(controller, time.monotonic() + 0.35)
            if telemetry and telemetry["motor_pwm"] > 0 and not telemetry["sensor_fault"]:
                stable_motor_samples += 1
                if stable_motor_samples >= 4:
                    break
            else:
                stable_motor_samples = 0
        if stable_motor_samples < 4:
            raise RuntimeError(
                "Could not observe four healthy nonzero-PWM telemetry samples. "
                "Check MQ-3 warm-up, RPM sensor pulses, wiring, and motor supply."
            )

        print("Healthy motor state observed. Stopping serial heartbeats now.")
        cutoff_deadline = time.monotonic() + args.watchdog_timeout
        stale_cutoff_seen = False
        while time.monotonic() < cutoff_deadline:
            telemetry = read_valid_telemetry(controller, time.monotonic() + 0.35)
            if telemetry and telemetry["command_stale"]:
                if telemetry["motor_pwm"] != 0:
                    raise RuntimeError(
                        "FAIL: controller reported a stale command while motor PWM was nonzero"
                    )
                stale_cutoff_seen = True
        if not stale_cutoff_seen:
            raise RuntimeError("FAIL: no stale-command motor cutoff observed")

    print("PASS: stale serial command was reported and motor PWM was zero.")


if __name__ == "__main__":
    main()
