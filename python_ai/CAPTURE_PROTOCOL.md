# Traffic-sign capture and labeling protocol

## Status and scope

This is a proposed collection protocol, not a record of completed collection.
The audited classification dataset does not contain any of the five requested
sign classes as full-scene detection images, and has no boxes. Do not claim
these capture targets, labels, splits, or model results have been achieved until
the work is completed and recorded.

The object classes are `school_zone`, `hospital_zone`, `speed_30`, `speed_50`,
and `speed_80`. `no_sign` is a negative/background image with no target box; it
is not a sixth object label.

## Collection target and sessions

Capture **50 site-and-lighting sessions**, arranged in five lighting strata
with 10 sessions each:

| Lighting stratum | Sessions |
|---|---:|
| Bright daylight, sign not directly facing the sun | 10 |
| Overcast or open shade | 10 |
| Backlit (sun behind the sign/camera view) | 10 |
| Dusk | 10 |
| Night or low light, using only the actual intended camera/lighting setup | 10 |
| **Total** | **50** |

In each session, target 10 unique frames assigned to each sign class as its
primary capture quota, plus 10 no-target-sign background frames. That gives a
**collection target of 500 primary-quota images per sign class and 500
background images** (3,000 unique images). A frame may also contain other
target signs; box and label every clearly visible target instance. Count each
image once toward its primary quota, and additionally record its actual
class-presence labels and box count in the manifest. Do not inflate counts
with crops, synthetic copies, or adjacent near-identical frames.

Sessions should represent separate site/date/lighting capture blocks. Use
different physical sign instances or staged, clearly documented sign boards
across data splits. Never place the same physical sign instance, location
sequence, continuous video burst, or near-duplicate cluster in more than one
split. If a location does not provide all classes, continue collecting in
additional sessions until the per-class targets are met; do not relabel a
different sign as a target class to meet a quota.

Capture with the actual ESP32-CAM/OV2640 at the deployed camera's native
320x240 image size. Keep focus, lens, image settings, and any illumination
consistent with intended use; record changes. Capture a useful range of sign
pixel sizes, distances, centered/off-center positions, frontal and oblique
angles, mild occlusion, and sign condition. For each session, include varied
views rather than taking 10 consecutive frames from a stationary video burst.
Take photos only from a safe, stationary position with permission; do not
operate the camera while driving or enter a roadway. Avoid direct sun into the
lens and do not use lighting unsafe for people or traffic.

## Grouped split plan

Assign whole site/session/sign-instance groups before training or augmentation.
Within each lighting stratum, reserve 8 sessions for train, 1 for validation,
and 1 for the held-out test. This gives:

| Split | Sessions | Primary-quota images per sign class | Target background images |
|---|---:|---:|---:|
| Train | 40 | 400 | 400 |
| Validation | 5 | 50 | 50 |
| Held-out test | 5 | 50 | 50 |
| **Total** | **50** | **500** | **500** |

The table gives primary-quota targets, not observed class-presence totals or
observed counts. Multi-label frames may increase the number of images
containing a class beyond its quota. Ensure every split contains examples from
each class and that all five lighting strata are represented.
If group constraints prevent these exact image counts, keep groups intact,
report the actual counts, and do not move individual frames across splits to
force the ratio. Keep a second **real-device test set** for the final,
assembled ESP32-CAM operating configuration, using new sessions and sign
instances not present in the 50-session split. Do not use it for model
selection or training. Record it separately, and report results on it
independently.

Create a manifest before assigning splits with at least:
`image_path`, `class_labels`, `session_id`, `site_id`, `physical_sign_id`,
`lighting`, `capture_date`, `camera_id`, `width`, `height`, and `split`.
Hash images for exact duplicates and inspect adjacent frames/perceptual
near-duplicates; remove redundant copies or keep the entire cluster in one
split. Apply augmentation only to training images, never before split
assignment. Save the manifest, duplicate decisions, random seed (42), and
training configuration.

## Edge Impulse labeling workflow

1. Create or select an Edge Impulse object-detection project. Add exactly these
   object labels: `school_zone`, `hospital_zone`, `speed_30`, `speed_50`, and
   `speed_80`. Do not add a `no_sign` bounding-box class.
2. Upload original, full-frame 320x240 images with stable unique filenames.
   Keep the session manifest and split assignment alongside the source images.
3. Use Edge Impulse's image labeling/bounding-box tool to draw a tight
   rectangle around each visible target sign. Label the sign face, not the
   surrounding pole or road. Label every target instance in a frame. Do not
   assign a class based only on nearby context when the sign face/value cannot
   be read confidently; send ambiguous images to a review queue.
4. For a `no_sign` image, leave the bounding-box list empty. It is a negative
   background example, not a rectangle around the whole image. If the chosen
   Edge Impulse import path cannot preserve an empty box list, retain the
   image and record it as background in the project workflow rather than
   inventing a box.
5. Review **100% of labels** before export: check class/value, missed signs,
   duplicates, box boundaries, and images that should be negative. Have a
   second reviewer independently check all validation/test labels and a
   documented sample of training labels; resolve disagreements and save review
   status in the manifest. Report the actual reviewed fraction as
   `reviewed annotations / total annotations`; do not claim review before it
   is done.
6. Export a copy in Edge Impulse object-detection format and, if needed, a
   YOLO dataset. Preserve one canonical label source and verify each export
   against the images and class ordering.

For interchange formats, a bounding-box record should contain the class label
and pixel coordinates `x`, `y`, `width`, and `height` in the image coordinate
system. A typical Edge Impulse `bounding_boxes.labels` record is shaped like:

```json
{
  "version": 1,
  "type": "bounding-box-labels",
  "boundingBoxes": [
    {
      "label": "speed_50",
      "x": 104,
      "y": 52,
      "width": 63,
      "height": 71
    }
  ]
}
```

Coordinates above are illustrative only, not a real annotation. Confirm the
current Edge Impulse export schema and image association for the selected
project before batch import. Do not infer boxes from the classification
dataset's class folders.

## Report-ready methodology paragraph

> Traffic-sign data collection is planned using the ESP32-CAM (OV2640) at
> 320x240 resolution across 50 site-and-lighting sessions: 10 each in bright
> daylight, overcast/open shade, backlit conditions, dusk, and low light. The
> target is 500 full-scene images for each of five classes (school_zone,
> hospital_zone, speed_30, speed_50, and speed_80), plus 500 background images
> containing none of these signs. Images will be manually annotated in Edge
> Impulse with tight bounding boxes around every identifiable target sign;
> background images will have no boxes. Before augmentation, entire
> session/site/sign-instance groups will be assigned to training (80%),
> validation (10%), or held-out test (10%) sets, with near-duplicate clusters
> kept within a single split. Additional ESP32-CAM captures made in the final
> operating configuration will be reserved as a separate real-device test set.
> These are collection targets and a planned methodology; detector training
> and held-out evaluation results will be reported only after the data is
> collected, reviewed, and measured.
