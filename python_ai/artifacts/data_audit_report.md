# Traffic-sign dataset audit

- **Dataset:** `C:\Users\Zenith Joshua\Downloads\AI prevention\AI prevention\archive (1)\Indian-Traffic Sign-Dataset`
- **Images audited:** 13,971
- **Format:** PNG images arranged in class folders; classification labels only
- **Resolution counts:** {'32x32': 13971}
- **Corrupt PNG files:** 0
- **Missing class IDs:** [39]
- **Exact duplicates:** 344 groups, 1041 extra copies
- **Near duplicates:** not analyzed

## Source class counts

| ID | Source label | Images | Requested detector mapping |
|---:|---|---:|---|
| 0 | Give way | 201 | none |
| 1 | No entry | 201 | none |
| 2 | One-way traffic | 201 | none |
| 3 | One-way traffic | 201 | none |
| 4 | No vehicles in both directions | 201 | none |
| 5 | No entry for cycles | 321 | none |
| 6 | No entry for goods vehicles | 201 | none |
| 7 | No entry for pedestrians | 201 | none |
| 8 | No entry for bullock carts | 601 | none |
| 9 | No entry for hand carts | 201 | none |
| 10 | No entry for motor vehicles | 201 | none |
| 11 | Height limit | 201 | none |
| 12 | Weight limit | 201 | none |
| 13 | Axle weight limit | 201 | none |
| 14 | Length limit | 201 | none |
| 15 | No left turn | 201 | none |
| 16 | No right turn | 201 | none |
| 17 | No overtaking | 201 | none |
| 18 | Maximum speed limit (90 km/h) | 201 | none |
| 19 | Maximum speed limit (110 km/h) | 201 | none |
| 20 | Horn prohibited | 601 | none |
| 21 | No parking | 201 | none |
| 22 | No stopping | 201 | none |
| 23 | Turn left | 201 | none |
| 24 | Turn right | 201 | none |
| 25 | Steep descent | 201 | none |
| 26 | Steep ascent | 201 | none |
| 27 | Narrow road | 201 | none |
| 28 | Narrow bridge | 201 | none |
| 29 | Unprotected quay | 201 | none |
| 30 | Road hump | 201 | none |
| 31 | Dip | 201 | none |
| 32 | Loose gravel | 201 | none |
| 33 | Falling rocks | 201 | none |
| 34 | Cattle | 201 | none |
| 35 | Crossroads | 201 | none |
| 36 | Side road junction | 201 | none |
| 37 | Side road junction | 201 | none |
| 38 | Oblique side road junction | 201 | none |
| 39 | Oblique side road junction | 0 | none |
| 40 | T-junction | 201 | none |
| 41 | Y-junction | 201 | none |
| 42 | Staggered side road junction | 201 | none |
| 43 | Staggered side road junction | 201 | none |
| 44 | Roundabout | 201 | none |
| 45 | Guarded level crossing ahead | 201 | none |
| 46 | Unguarded level crossing ahead | 201 | none |
| 47 | Level crossing countdown marker | 144 | none |
| 48 | Level crossing countdown marker | 168 | none |
| 49 | Level crossing countdown marker | 58 | none |
| 50 | Level crossing countdown marker | 193 | none |
| 51 | Parking | 600 | none |
| 52 | Bus stop | 220 | none |
| 53 | First aid post | 607 | none |
| 54 | Telephone | 602 | none |
| 55 | Filling station | 616 | none |
| 56 | Hotel | 200 | none |
| 57 | Restaurant | 201 | none |
| 58 | Refreshments | 196 | none |

## Requested class gaps

| Target class | Mapped source images | Below 150? | Additional ESP32-CAM captures planned |
|---|---:|---|---:|
| `school_zone` | 0 | True | 500 |
| `hospital_zone` | 0 | True | 500 |
| `speed_30` | 0 | True | 500 |
| `speed_50` | 0 | True | 500 |
| `speed_80` | 0 | True | 500 |
| `no_sign` | 0 | True | 500 |

## Annotation and split readiness

- Bounding boxes present: False.
- Pseudo-labels generated/reviewed: 0/0; review fraction: not applicable.
- Split: not created (blocked_until_scene_images_are_box_annotated).
- Future split: group by source scene and near-duplicate cluster before an 80/10/10 train/validation/test split. Keep ESP32-CAM captures as a separate real-device test set.

No object boxes were inferred from classification labels. The requested target classes have no matching source classes in this dataset, and it has no no_sign background images. Capture full 320x240 scenes containing each requested sign class and negative road scenes; the suggested 500 captures per class are collection targets, not a guarantee of coverage or model performance.

Licensing was not established from the inspected dataset files.
