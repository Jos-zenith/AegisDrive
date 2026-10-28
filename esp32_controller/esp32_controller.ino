#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Prototype-only wiring. Verify against your exact modules.
static const int MQ3_PIN = 34;
static const int SPEED_PIN = 27;
static const int ENA_PIN = 25;
static const int IN1_PIN = 26;
static const int IN2_PIN = 14;
static const int BUZZER_PIN = 33;

LiquidCrystal_I2C lcd(0x27, 16, 2);

// MUST calibrate these values on your bench prototype.
static const int ALCOHOL_THRESHOLD = 1800; // placeholder ADC value
static const int PULSES_PER_REVOLUTION = 1; // configure for your sensor wheel
static const float RPM_PER_SIMULATED_SPEED_UNIT = 20.0; // placeholder; calibrate
static const int NORMAL_PWM = 160;
static const int REDUCED_PWM = 90;

volatile unsigned long pulseCount = 0;
unsigned long lastSpeedMs = 0;
float rpm = 0.0;
int speedLimit = 50; // simulated prototype limit, not km/h unless calibrated
bool aiHazard = false;
bool alcoholAlert = false;
bool overspeedAlert = false;

String serialLine;

void IRAM_ATTR onSpeedPulse() {
  pulseCount++;
}

void motorStop() {
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
  ledcWrite(ENA_PIN, 0);
}

void motorRun(int pwm) {
  pwm = constrain(pwm, 0, 255);
  if (pwm == 0) {
    motorStop();
    return;
  }
  digitalWrite(IN1_PIN, HIGH);
  digitalWrite(IN2_PIN, LOW);
  ledcWrite(ENA_PIN, pwm);
}

void processSerialLine(String line) {
  line.trim();
  if (line.startsWith("LIMIT:")) {
    int v = line.substring(6).toInt();
    if (v >= 0 && v <= 120) speedLimit = v;
  } else if (line.startsWith("HAZARD:")) {
    aiHazard = (line.substring(7).toInt() != 0);
  } else if (line.startsWith("AI:")) {
    aiHazard = (line.substring(3).toInt() != 0);
  }
}

void readSerialCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      processSerialLine(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < 80) {
      serialLine += c;
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(MQ3_PIN, INPUT);
  pinMode(SPEED_PIN, INPUT_PULLUP);
  pinMode(IN1_PIN, OUTPUT);
  pinMode(IN2_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // ESP32 Arduino core 3.x PWM API
  ledcAttach(ENA_PIN, 1000, 8);
  attachInterrupt(digitalPinToInterrupt(SPEED_PIN), onSpeedPulse, FALLING);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Safety Prototype");
  lcd.setCursor(0, 1);
  lcd.print("Bench test only");

  motorStop();
  lastSpeedMs = millis();
  delay(1500);
}

void loop() {
  readSerialCommands();

  int mq3 = analogRead(MQ3_PIN);
  alcoholAlert = (mq3 >= ALCOHOL_THRESHOLD);

  unsigned long now = millis();
  if (now - lastSpeedMs >= 1000) {
    noInterrupts();
    unsigned long pulses = pulseCount;
    pulseCount = 0;
    interrupts();

    rpm = (pulses * 60.0f) / max(1, PULSES_PER_REVOLUTION);
    lastSpeedMs = now;
  }

  // Convert RPM to a prototype-only speed scale. This is NOT road speed.
  float simulatedSpeed = rpm / RPM_PER_SIMULATED_SPEED_UNIT;
  overspeedAlert = (simulatedSpeed > speedLimit);

  bool alert = alcoholAlert || overspeedAlert || aiHazard;

  // Conservative prototype behaviour: stop motor on alcohol sensor alert;
  // reduce motor PWM for AI hazard/overspeed. Never use on a real vehicle.
  if (alcoholAlert) {
    motorStop();
  } else if (aiHazard || overspeedAlert) {
    motorRun(REDUCED_PWM);
  } else {
    motorRun(NORMAL_PWM);
  }

  digitalWrite(BUZZER_PIN, alert ? HIGH : LOW);

  lcd.clear();
  if (alcoholAlert) {
    lcd.setCursor(0, 0); lcd.print("Alcohol sensor!");
    lcd.setCursor(0, 1); lcd.print("Motor restricted");
  } else if (aiHazard) {
    lcd.setCursor(0, 0); lcd.print("Road hazard!");
    lcd.setCursor(0, 1); lcd.print("Reduce speed");
  } else if (overspeedAlert) {
    lcd.setCursor(0, 0); lcd.print("Speed warning");
    lcd.setCursor(0, 1); lcd.print("RPM:");
    lcd.print((int)rpm);
  } else {
    lcd.setCursor(0, 0); lcd.print("System normal");
    lcd.setCursor(0, 1); lcd.print("RPM:");
    lcd.print((int)rpm);
    lcd.print(" L:");
    lcd.print(speedLimit);
  }

  // Debug telemetry for calibration
  Serial.print("STATUS mq3=");
  Serial.print(mq3);
  Serial.print(" rpm=");
  Serial.print(rpm);
  Serial.print(" limit=");
  Serial.print(speedLimit);
  Serial.print(" hazard=");
  Serial.println(aiHazard ? 1 : 0);

  delay(150);
}
