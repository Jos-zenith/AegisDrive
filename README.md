# AI Accident Prevention System — Starter Project

This is a **bench-top prototype starter**, not a certified vehicle safety system.

## What it includes
- Python AI inference using two YOLO models:
  - COCO model (`yolo11n.pt`) for common road objects such as cars, people, motorcycles and bicycles.
  - A custom traffic-sign model (`best_signs.pt`) for speed-limit signs.
- Sends simple serial commands from the laptop to an ESP32 DevKit.
- ESP32 reads an MQ-3 analogue output and an LM393 pulse sensor, controls an L298N-connected low-voltage DC motor, buzzer and I2C LCD.
- ESP32-CAM can provide the camera stream; Python reads its `/stream` URL.

## Important limitations
1. `best_signs.pt` is NOT included. You must train it on a labelled traffic-sign dataset or obtain a compatible trained model. The code cannot identify speed signs until that file exists and its class names match the code.
2. The COCO model does not detect traffic signs. It is only used for general objects.
3. This starter estimates motor RPM, not road speed in km/h. The speed-limit comparison is only meaningful after you calibrate your prototype's motor RPM to a simulated/appropriate speed scale. Do not use this to control a real vehicle.
4. MQ-3 readings are not a blood-alcohol measurement. The threshold is a placeholder and must be calibrated; test with safe sensor procedures only.
5. AI detection is advisory. Do not use automatic braking/steering or this prototype on public roads.
6. This code assumes ESP32 Arduino core 3.x and an I2C LCD address of 0x27. Adjust pins/address for your actual board and wiring.
7. Never feed 5 V into ESP32 GPIO. Verify module output levels and power ratings. Motor supply must suit the motor and driver; use common ground.

## Folder contents
- `esp32_controller.ino` — ESP32 DevKit firmware.
- `python_ai/app.py` — camera inference and serial integration.
- `python_ai/train_signs.py` — fine-tune a YOLO model for traffic signs.
- `python_ai/data_signs.yaml.example` — example dataset YAML to adapt.
- `python_ai/requirements.txt` — Python dependencies.

## Recommended order

### 1. Test the ESP32 controller alone
Open `esp32_controller.ino` in Arduino IDE, select your ESP32 board and COM port, then upload.
For the first test, keep the motor wheels off the ground and have a physical power switch available.
The firmware accepts these serial lines from Python:
- `LIMIT:40` — set a simulated speed limit value (0–120)
- `HAZARD:1` or `HAZARD:0` — hazard detected/not detected
- `SIGN:30`, `SIGN:40`, `SIGN:50`, etc. — detected speed sign; Python uses `LIMIT:` for this starter
- `AI:0` — clear AI hazard flag

### 2. Test the ESP32-CAM stream
Use the Arduino IDE example **File > Examples > ESP32 > Camera > CameraWebServer** for your installed ESP32 package. Select the correct camera model (commonly `CAMERA_MODEL_AI_THINKER`), enter Wi-Fi credentials, upload, and open the IP printed in Serial Monitor.
Confirm that `http://CAMERA_IP/stream` works in a browser before running Python.
ESP32-CAM and laptop must be on the same Wi-Fi network. Power the camera board with a stable supply.

### 3. Set up Python
From `python_ai` in a Windows terminal:
```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure `app.py`
Edit:
- `CAMERA_STREAM_URL` to `http://YOUR_CAMERA_IP/stream`
- `SERIAL_PORT` to your ESP32 DevKit COM port (for example `COM11`)
- `SIGN_MODEL_PATH` to your trained model file, `best_signs.pt`

If the sign model file is absent, Python will still run COCO object detection, but will report that speed-sign detection is disabled.

### 5. Audit data before training a traffic-sign detector

The uploaded `archive (1)/Indian-Traffic-Sign-Dataset` is classification-style
32x32 imagery, not scene-level object-detection data. Its labels do not include
the requested `school_zone`, `hospital_zone`, `speed_30`, `speed_50`, or
`speed_80` classes, and it has no bounding boxes. Do not treat its class labels
as detection boxes or train the configured detector on it as-is.

Run the reproducible dataset audit and Tamil Nadu district index from
`python_ai`:
```bat
py analyze_data.py
```
The script writes its reports and CSV/JSON outputs to `python_ai/artifacts`.
It verifies monthly district totals against the district summary and reports
the detector as not trained/evaluated until suitable labeled data is supplied.

For detector training, first collect full-scene OV2640 images and manually
review bounding boxes in YOLO/Edge Impulse format. Split by scene and
near-duplicate cluster before augmentation; keep a separate ESP32-CAM test set.
`python_ai/train_signs.py` is the existing laptop-side Ultralytics YOLO trainer;
it does not export or deploy an Edge Impulse model. Do not treat its weights as
an ESP32-CAM Arduino library. Only after labels exist should you configure
`data_signs.yaml.example` and run:
```bat
python train_signs.py
```
After training, copy the resulting `best.pt` to `python_ai/best_signs.pt`.

Do not report precision, recall, mAP, confusion matrices, or ESP32-CAM
deployment measurements until measured using untouched, manually labeled test
data on the relevant test device. The uploaded Tamil Nadu tables are aggregate
statistics and are used only for a documented statistical risk index; they
cannot train a per-trip detector or risk model.

#### Sign data-collection and labeling plan

The current dataset is not suitable for this detector. The proposed capture
protocol specifies sessions, lighting, image targets, Edge Impulse labeling,
and grouped train/validation/test splits. See
[`python_ai/CAPTURE_PROTOCOL.md`](./python_ai/CAPTURE_PROTOCOL.md). These are
planned collection targets, not completed data or measured detector results.

## Wiring assumed by the ESP32 sketch
| Module | Pin | ESP32 DevKit |
|---|---|---|
| MQ-3 AO | Analog out | GPIO 34 (voltage must stay <= 3.3 V) |
| LM393 speed sensor DO | Digital out | GPIO 27 |
| L298N ENA | PWM | GPIO 25 (remove ENA jumper if appropriate) |
| L298N IN1 | Direction | GPIO 26 |
| L298N IN2 | Direction | GPIO 14 |
| Active buzzer signal | Signal | GPIO 33 (use a driver transistor if required by buzzer current) |
| I2C LCD SDA | SDA | GPIO 21 |
| I2C LCD SCL | SCL | GPIO 22 |

Power the motor separately with a suitable supply. Connect grounds together. Do not power the motor from an ESP32 pin. Do not connect a 5 V logic output directly to ESP32 GPIO.

## What the project does
- Detects common road objects using the COCO model.
- Detects speed signs only if a compatible custom model is trained and installed.
- Sends hazard status and recognised sign limit to ESP32.
- ESP32 reads the speed pulses and MQ-3 sensor and applies simple prototype control logic.

This is a starting implementation. It does not prove accident prediction or road safety.
