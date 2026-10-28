import unittest

from serial_protocol import (
    encode_command,
    encode_sync_confirmation,
    encode_sync_request,
    parse_sync_confirmation,
    parse_sync_response,
    parse_telemetry,
)


class SerialProtocolTests(unittest.TestCase):
    def test_sync_handshake_is_safe_and_reads_controller_sequence(self) -> None:
        self.assertEqual(encode_sync_request(), b"SYNC\n")
        state = parse_sync_response(b"STATE,800,123\n")
        self.assertEqual(state.sequence, 800)
        self.assertEqual(state.epoch, 123)
        self.assertEqual(encode_sync_confirmation(123), b"SYNC,123\n")
        ready = parse_sync_confirmation(b"READY,800,123\n", 123)
        self.assertEqual(ready.sequence, 800)
        with self.assertRaises(ValueError):
            parse_sync_response(b"STATE,800,enable\n")
        with self.assertRaises(ValueError):
            parse_sync_confirmation(b"READY,800,124\n", 123)
        with self.assertRaises(ValueError):
            parse_sync_response(b"STATE,\xff\n")

    def test_command_encodes_distinct_object_and_sign_inputs(self) -> None:
        self.assertEqual(
            encode_command(12, True, 50),
            b"CMD,12,1,50\n",
        )
        self.assertEqual(
            encode_command(13, False, None),
            b"CMD,13,0,-1\n",
        )

    def test_rejects_invalid_command_values(self) -> None:
        with self.assertRaises(ValueError):
            encode_command(1, True, 40)
        with self.assertRaises(ValueError):
            encode_command(1, 1, None)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            encode_command(-1, False, None)

    def test_parses_valid_controller_telemetry(self) -> None:
        telemetry = parse_telemetry(
            b"TEL,12,mq3=1250,rpm=240.0,limit=50,object=1,alcohol=0,"
            b"overspeed=0,stale=0,sensor_fault=0,pwm=90,hazard=1,estop=0,warmup=0\n",
            received_monotonic=10.5,
        )
        self.assertEqual(telemetry.sequence, 12)
        self.assertEqual(telemetry.mq3_adc, 1250)
        self.assertEqual(telemetry.rpm, 240.0)
        self.assertEqual(telemetry.sign_limit, 50)
        self.assertTrue(telemetry.object_hazard)
        self.assertTrue(telemetry.controller_hazard)
        self.assertFalse(telemetry.alcohol_alert)
        self.assertFalse(telemetry.estop_active)
        self.assertFalse(telemetry.warmup_active)
        self.assertEqual(telemetry.motor_pwm, 90)
        self.assertEqual(telemetry.received_monotonic, 10.5)

    def test_rejects_malformed_and_unsafe_telemetry(self) -> None:
        invalid_lines = (
            b"TEL,12,mq3=1250,rpm=240.0,limit=50,object=1\n",
            b"TEL,12,mq3=1250,rpm=240.0,limit=40,object=1,alcohol=0,"
            b"overspeed=0,stale=0,sensor_fault=0,pwm=90,hazard=1,estop=0,warmup=0\n",
            b"TEL,12,mq3=5000,rpm=240.0,limit=50,object=1,alcohol=0,"
            b"overspeed=0,stale=0,sensor_fault=0,pwm=90,hazard=1,estop=0,warmup=0\n",
            b"TEL,12,mq3=1250,rpm=-1,rpm=240.0,limit=50,object=1,"
            b"alcohol=0,overspeed=0,stale=0,sensor_fault=0,pwm=90,"
            b"hazard=1,estop=0,warmup=0\n",
            b"TEL,12,mq3=1250,rpm=nan,limit=50,object=1,alcohol=0,"
            b"overspeed=0,stale=0,sensor_fault=0,pwm=90,hazard=1,estop=0,warmup=0\n",
            b"TEL,12,mq3=1250,rpm=240.0,limit=50,object=2,alcohol=0,"
            b"overspeed=0,stale=0,sensor_fault=0,pwm=90,hazard=1,estop=0,warmup=0\n",
        )
        for line in invalid_lines:
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_telemetry(line)


if __name__ == "__main__":
    unittest.main()
