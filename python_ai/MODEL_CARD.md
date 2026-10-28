# Traffic-sign detector model card

## Status

No detector has been trained or evaluated. `artifacts/metrics.json` records
unmeasured metrics as `null`; there is no confusion matrix, model file, model
size, RAM measurement, or inference-time measurement. These values must not be
presented as measured results.

## Intended use

An experimental, advisory traffic-sign detector for an ESP32-CAM (OV2640) in a
bench-top accident-prevention prototype. The proposed detector labels are
`school_zone`, `hospital_zone`, `speed_30`, `speed_50`, and `speed_80`.
`no_sign` means a negative/background image with an empty object-label file; it
is not an object class.

This is not a certified vehicle safety system. Do not rely on it for driving,
braking, steering, or other safety-critical decisions.

## Data sources and license

- The local Indian-Traffic-Sign-Dataset folder contains `Images/` and
  `traffic_sign.csv`. Its images are class-folder classification images, not
  scene images with bounding boxes. No license statement was present in the
  inspected dataset files; licensing and redistribution permissions remain
  unverified.
- Tamil Nadu 2023 accident CSVs are aggregate statistics and are used only for
  the separate district statistical risk index. They were not used to train
  this detector.

## Audit findings

The reproducible audit is `python_ai/analyze_data.py`; outputs are under
`python_ai/artifacts/`. The inspected source has 13,971 PNG images, all 32x32;
58 class directories; class ID 39 is missing from the source class list; no
corrupt PNGs; and 344 exact-duplicate groups (1,041 extra copies). Near
duplicates were not analyzed.

None of the requested target classes are represented in the source taxonomy.
The source contains speed-limit classes for 90 and 110 km/h, not 30, 50, or
80 km/h; it has no school-zone or hospital-zone class. Each requested sign
class therefore has zero mapped source images and is below the 150-image
threshold. There are also zero no-sign road-scene background images. The source
images are not usable as detector positives because they have no bounding boxes
and are tiny cropped classification images.

## Collection and annotation requirements

The detailed proposed session schedule, lighting strata, image counts, Edge
Impulse labeling steps, grouped splits, and report-ready methodology are in
[`CAPTURE_PROTOCOL.md`](./CAPTURE_PROTOCOL.md). At present, no target sign
images have been collected or reviewed. The planned method is manual
annotation; no pseudo-labels are reported.

## Evaluation and deployment

Once labels and both test sets exist, report per-class precision, recall,
mAP@0.5, confusion matrix, failure examples, and the metric gap between the
source-image test and separate ESP32-CAM test. Evaluate only once on untouched
test data. Export an int8 Edge Impulse Arduino library or TFLite model only
after evaluation. Measure compiled model size, peak RAM, and inference latency
on the actual ESP32-CAM; no hardware estimates are asserted in this card.

## Known limitations and exclusions

- Likely domain gap between 32x32 source crops and low-resolution OV2640 scene
  captures.
- No bounding boxes, target-class samples, held-out scene test, or real-device
  test set are currently available.
- The model was **not trained on** the Tamil Nadu accident CSVs, sensor values,
  per-trip records, or any of the existing sign images.
- The separate district index is descriptive and rule-based, not a trained
  accident-risk predictor.
