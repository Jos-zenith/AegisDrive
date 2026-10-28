# Signal handling, fault response, and evaluation

## Signals and outputs

| Signal | Source | Controller input/use | Prototype output effect |
|---|---|---|---|
| Object detections | COCO object detector on host | `object_hazard` boolean in each serial heartbeat; not the sign class | Potential hazard sets the buzzer and limits PWM to `REDUCED_PWM`. It is not treated as a collision prediction. |
| Traffic-sign detections | Custom sign detector on host | Recognized classes remain in host log/UI. `speed_30`, `speed_50`, or `speed_80` sends only the selected sign limit. School/hospital signs do not set a speed limit. | A speed sign is compared only with the calibrated RPM-derived prototype speed scale. Exceeding the sign limit reduces PWM and sounds the buzzer. No fresh recognized speed sign means no sign-limit comparison. |
| Measured RPM | ESP32 pulse input | Locally sampled pulse count; sent in telemetry as RPM. It is not the sign class or an object detection. | Used to derive a simulated speed scale with `RPM_PER_SIMULATED_SPEED_UNIT`; only the derived comparison with a currently recognized sign can set overspeed. Calibrate before interpreting. |
| MQ-3 ADC | ESP32 analog input | Local ADC reading; sent in telemetry. It is not a blood-alcohol estimate. | ADC at/above the placeholder threshold (1800) after startup warm-up causes motor cutoff and buzzer. Calibrate using a safe sensor procedure. |
| Controller hazard state | ESP32 arbitration | Derived independently from object hazard, overspeed, alcohol alert, link timeout, sensor fault, startup warm-up, and software E-stop. | Object hazard/overspeed reduce PWM; alcohol/fault/stale-link/warm-up/E-stop cut PWM to zero. A fixed priority prevents a lower-severity input from overriding a cutoff. |

These are bench-prototype behaviors, not vehicle-safety logic. The RPM scale,
MQ-3 threshold, PWM values, warm-up interval, and sensor fault limits require
calibration and validation for the exact hardware. Do not use the system on
public roads.

## Serial protocol and fail-safe behavior

The host sends `CMD,<sequence>,<object_hazard>,<sign_limit>\n` at each
successfully processed frame. `object_hazard` must be `0` or `1`; `sign_limit`
must be `-1`, `30`, `50`, or `80`. `-1` means no current speed-limit sign.
Class labels and confidence remain distinct in the host-side detections/log.
The controller rejects malformed, repeated/out-of-order, out-of-range, or
unsupported commands.

The ESP32 emits `TEL` records at 4 Hz with the accepted sequence, raw MQ-3 ADC,
RPM, sign limit, object-hazard flag, alcohol/overspeed alerts, stale-command
state, sensor-fault state, aggregated controller-hazard state, software E-stop,
warm-up state, and actual PWM. Host serial reads have a finite
timeout. A camera frame failure or serial write failure exits the host process;
the controller watchdog independently cuts PWM if no valid command arrives for
2.5 seconds. A recognized speed limit expires if it is not refreshed.

At controller startup, the motor remains cut off during the 30-second
prototype MQ-3 warm-up. A sustained MQ-3 ADC reading near either ADC rail after
warm-up, a missing RPM pulse stream while commanded to run, or a failed PWM
attachment latches a sensor fault and cuts off the motor until reset. The
active-low software E-stop input is GPIO 32. Add a separate, reachable,
normally-closed emergency cutoff switch in series with the motor supply; the
GPIO E-stop and firmware are not substitutes for this independent physical
power disconnect. Verify the cutoff with the motor supply isolated before
running powered tests.

## Reproducible dataset and model workflow

1. Capture and manually box-label full-scene OV2640 images per
   [`CAPTURE_PROTOCOL.md`](./CAPTURE_PROTOCOL.md). The existing 32x32
   classification images are not detector training examples.
2. Export reviewed labels to YOLO format. Build a CSV manifest with columns
   `image_path,label_path,group_id,class_labels,reviewed`. `group_id` must
   keep a session, scene, physical sign instance, and near-duplicate cluster
   together. `class_labels` is a `|`-separated list; use `no_sign` for negative
   images with empty YOLO files.
3. Run `py prepare_yolo_split.py reviewed_manifest.csv --output-dir
   data_signs_split --seed 42`. It validates boxes and reviewed labels,
   preserves groups, creates fixed-seed 80/10/10 splits and fails rather than
   silently allowing a class to disappear from a split.
4. Configure a local `data_signs.yaml` from the generated YAML/example. Create
   deterministic brightness/blur/JPEG variants of the training split only,
   then train and evaluate once on the held-out test split:

   ```bat
   py augment_training.py --data data_signs.yaml --output data_signs_augmented.yaml --seed 42
   py train_signs.py --data data_signs_augmented.yaml --seed 42 --image-size 160
   ```

   The trainer requires a local checkpoint and never downloads one implicitly.
   It evaluates the held-out test split once and writes
   `artifacts/detector_test_metrics.json`.
5. That Ultralytics checkpoint is a host-side model, **not** an ESP32-CAM
   deployment. Edge Impulse training/export and model quantization must be
   completed separately; verify size, RAM, and latency on the actual board.

## Runtime measurement and fault tests

`app.py` records per-frame object/sign detections, separate signal fields,
object/sign inference time, total host frame-to-command time, controller
telemetry, and response time for acknowledged command sequences in
`artifacts/runtime_metrics.jsonl`. It also saves one evaluation frame per
second under `artifacts/evaluation_frames/<run_id>/`. Label the sampled frames
interactively; this creates a separate JSONL with ground truth and leaves the
original log intact:

```json
{"object_hazard": false, "sign_classes": ["speed_50"]}
```

Run the review tool, answer object hazard `y`/`n`, and enter every visible
target class as a comma-separated list (blank means none). Then evaluate:

```bat
py label_runtime_frames.py artifacts\runtime_metrics.jsonl
py evaluate_run.py artifacts\runtime_metrics_labeled.jsonl --output artifacts\runtime_evaluation.json
```

The report calculates frame-level object-hazard false positives/negatives,
per-class sign-presence false positives/negatives, latency summaries, sensor
fault counts, and observed motor-cutoff violations. It does **not** calculate
box-IoU or mAP; use the held-out detector test metrics for localization metrics.
For disconnect testing, use the bench-only
`py controller_watchdog_test.py --port COM11` with secured raised wheels,
current-limited low-voltage supply, RPM sensor functioning, and the independent
physical cutoff reachable. It first verifies a healthy nonzero-PWM state, then
stops sending heartbeats and requires stale-link telemetry with PWM zero. Do
not perform powered fault injection on a vehicle or with people near moving
parts.
