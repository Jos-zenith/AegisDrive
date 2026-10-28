import unittest

from evaluate_run import evaluate


class EvaluateRunTests(unittest.TestCase):
    def test_reports_frame_level_false_positives_and_latency(self) -> None:
        records = [
            {
                "ground_truth": {"object_hazard": True, "sign_classes": ["speed_30"]},
                "object_hazard_input": True,
                "sign_detections": [{"class": "speed_30"}],
                "object_inference_ms": 12.0,
                "sign_inference_ms": 8.0,
                "end_to_end_ms": 24.0,
                "controller_telemetry": [
                    {
                        "command_response_ms": 4.0,
                        "command_stale": False,
                        "sensor_fault": False,
                        "alcohol_alert": False,
                        "estop_active": False,
                        "warmup_active": False,
                        "motor_pwm": 90,
                    }
                ],
            },
            {
                "ground_truth": {"object_hazard": False, "sign_classes": []},
                "object_hazard_input": True,
                "sign_detections": [{"class": "speed_30"}],
                "object_inference_ms": 10.0,
                "sign_inference_ms": 6.0,
                "end_to_end_ms": 20.0,
                "controller_telemetry": [
                    {
                        "command_response_ms": 6.0,
                        "command_stale": True,
                        "sensor_fault": False,
                        "alcohol_alert": False,
                        "estop_active": False,
                        "warmup_active": False,
                        "motor_pwm": 0,
                    }
                ],
            },
        ]
        report = evaluate(records)
        self.assertEqual(report["object_hazard"]["false_positive"], 1)
        self.assertEqual(report["object_hazard"]["false_negative"], 0)
        self.assertEqual(
            report["sign_classes_frame_presence"]["speed_30"]["false_positive"],
            1,
        )
        self.assertEqual(report["latency"]["end_to_end_ms"]["samples"], 2)
        self.assertEqual(report["controller"]["stale_cutoff_violations"], 0)

    def test_emits_fault_cutoff_violation_if_motor_pwm_is_nonzero(self) -> None:
        report = evaluate(
            [
                {
                    "ground_truth": {"object_hazard": False, "sign_classes": []},
                    "object_hazard_input": False,
                    "sign_detections": [],
                    "controller_telemetry": [
                        {
                            "command_stale": True,
                            "sensor_fault": True,
                            "alcohol_alert": True,
                            "estop_active": True,
                            "warmup_active": True,
                            "motor_pwm": 90,
                        }
                    ],
                }
            ]
        )
        self.assertEqual(report["controller"]["stale_cutoff_violations"], 1)
        self.assertEqual(report["controller"]["sensor_fault_cutoff_violations"], 1)
        self.assertEqual(report["controller"]["alcohol_cutoff_violations"], 1)
        self.assertEqual(report["controller"]["estop_cutoff_violations"], 1)
        self.assertEqual(report["controller"]["warmup_cutoff_violations"], 1)


if __name__ == "__main__":
    unittest.main()
