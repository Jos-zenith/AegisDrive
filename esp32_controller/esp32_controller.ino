#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include "esp_system.h"

// Prototype-only wiring. Verify against the exact board and modules.
static const int MQ3_PIN = 34;
static const int SPEED_PIN = 27;
static const int ENA_PIN = 25;
static const int IN1_PIN = 26;
static const int IN2_PIN = 14;
static const int BUZZER_PIN = 33;
static const int SOFTWARE_ESTOP_PIN = 32;

LiquidCrystal_I2C lcd(0x27, 16, 2);

// Bench calibration placeholders only. Never interpret these as road speed.
static const int ALCOHOL_THRESHOLD = 1800;
static const int PULSES_PER_REVOLUTION = 1;
static const float RPM_PER_SIMULATED_SPEED_UNIT = 20.0f;
static const int NORMAL_PWM = 160;
static const int REDUCED_PWM = 90;

static const unsigned long SERIAL_TIMEOUT_MS = 2500;
static const unsigned long SIGN_TIMEOUT_MS = 3000;
static const unsigned long MQ3_WARMUP_MS = 30000;
static const unsigned long MQ3_RAIL_FAULT_MS = 2000;
static const unsigned long RPM_SENSOR_FAULT_MS = 4000;
static const unsigned long RPM_SAMPLE_MS = 1000;
static const unsigned long TELEMETRY_INTERVAL_MS = 250;
static const unsigned long LCD_INTERVAL_MS = 500;
static const unsigned long RPM_STALE_MS = 2500;

volatile unsigned long pulseCount = 0;
volatile unsigned long lastPulseMs = 0;

unsigned long bootMs = 0;
unsigned long lastCommandMs = 0;
unsigned long lastSignMs = 0;
unsigned long lastRpmSampleMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastLcdMs = 0;
unsigned long railStartMs = 0;
unsigned long motorRunStartedMs = 0;
unsigned long lastValidSequence = 0;
uint32_t syncEpoch = 0;
bool haveSequence = false;
bool objectHazard = false;
bool commandStale = true;
bool sensorFault = false;
bool alcoholAlert = false;
bool overspeedAlert = false;
bool eStopActive = false;
bool mq3RailFault = false;
bool pwmReady = false;
int signLimit = -1;
int mq3Adc = 0;
int motorPwm = 0;
float rpm = 0.0f;
float simulatedSpeed = 0.0f;
unsigned long lastPulseSnapshot = 0;
char serialLine[64];
size_t serialLength = 0;

void IRAM_ATTR onSpeedPulse() {
  pulseCount++;
  lastPulseMs = millis();
}

void motorStop() {
  ledcWrite(ENA_PIN, 0);
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
  motorPwm = 0;
  motorRunStartedMs = 0;
}

void motorRun(int pwm) {
  pwm = constrain(pwm, 0, 255);
  if (pwm == 0) {
    motorStop();
    return;
  }
  if (motorPwm == 0) motorRunStartedMs = millis();
  digitalWrite(IN1_PIN, HIGH);
  digitalWrite(IN2_PIN, LOW);
  ledcWrite(ENA_PIN, pwm);
  motorPwm = pwm;
}

bool validSpeedLimit(int value) {
  return value == -1 || value == 30 || value == 50 || value == 80;
}

bool parseCommandNumber(const char **cursor, bool allowNegative, long *value) {
  const char *start = *cursor;
  if (allowNegative && **cursor == '-') (*cursor)++;
  if (**cursor < '0' || **cursor > '9') return false;
  while (**cursor >= '0' && **cursor <= '9') (*cursor)++;
  char *end = NULL;
  errno = 0;
  *value = strtol(start, &end, 10);
  if (errno == ERANGE || end == start || end != *cursor) return false;
  return true;
}

bool processCommand(const char *line) {
  if (strncmp(line, "CMD,", 4) != 0) return false;
  const char *cursor = line + 4;
  long values[3];
  for (int index = 0; index < 3; index++) {
    if (!parseCommandNumber(&cursor, index == 2, &values[index])) return false;
    if (index < 2) {
      if (*cursor != ',') return false;
      cursor++;
    } else if (*cursor != '\0') {
      return false;
    }
  }
  if (values[0] < 0 || values[0] > INT32_MAX) return false;
  if (values[1] != 0 && values[1] != 1) return false;
  if (values[2] < INT_MIN || values[2] > INT_MAX) return false;
  unsigned long sequence = (unsigned long)values[0];
  int hazard = (int)values[1];
  int limit = (int)values[2];
  if (!validSpeedLimit(limit)) return false;
  if (haveSequence && (int32_t)(sequence - lastValidSequence) <= 0) return false;

  lastValidSequence = sequence;
  haveSequence = true;
  lastCommandMs = millis();
  commandStale = false;
  objectHazard = (hazard == 1);
  signLimit = limit;
  lastSignMs = (limit == -1) ? 0 : lastCommandMs;
  return true;
}

bool processControlLine(const char *line) {
  if (strcmp(line, "SYNC") == 0) {
    Serial.print("STATE,");
    Serial.print(haveSequence ? lastValidSequence : 0);
    Serial.print(",");
    Serial.println(syncEpoch);
    return true;
  }
  if (strncmp(line, "SYNC,", 5) == 0) {
    char *end = NULL;
    errno = 0;
    unsigned long requestedEpoch = strtoul(line + 5, &end, 10);
    if (errno == ERANGE || end == line + 5 || *end != '\0' ||
        requestedEpoch != syncEpoch) {
      Serial.println("ERR,SYNC_REJECTED");
      return false;
    }
    Serial.print("READY,");
    Serial.print(haveSequence ? lastValidSequence : 0);
    Serial.print(",");
    Serial.println(syncEpoch);
    return true;
  }
  return processCommand(line);
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\n') {
      serialLine[serialLength] = '\0';
      if (serialLength > 0 && !processControlLine(serialLine)) {
        Serial.println("ERR,COMMAND_REJECTED");
      }
      serialLength = 0;
    } else if (ch != '\r') {
      if (serialLength < sizeof(serialLine) - 1) {
        serialLine[serialLength++] = ch;
      } else {
        serialLength = 0;
        Serial.println("ERR,COMMAND_OVERFLOW");
      }
    }
  }
}

void updateSensors(unsigned long now) {
  mq3Adc = analogRead(MQ3_PIN);
  if (now - bootMs >= MQ3_WARMUP_MS) {
    alcoholAlert = (mq3Adc >= ALCOHOL_THRESHOLD);
    if (mq3Adc <= 4 || mq3Adc >= 4091) {
      if (railStartMs == 0) railStartMs = now;
      mq3RailFault = (now - railStartMs >= MQ3_RAIL_FAULT_MS);
    } else {
      railStartMs = 0;
      mq3RailFault = false;
    }
  } else {
    alcoholAlert = false;
    mq3RailFault = false;
    railStartMs = 0;
  }

  if (now - lastRpmSampleMs >= RPM_SAMPLE_MS) {
    noInterrupts();
    unsigned long pulses = pulseCount;
    pulseCount = 0;
    lastPulseSnapshot = lastPulseMs;
    interrupts();
    rpm = (pulses * 60.0f) /
          (max(1, PULSES_PER_REVOLUTION) * ((now - lastRpmSampleMs) / 1000.0f));
    if (lastPulseSnapshot == 0 || now - lastPulseSnapshot > RPM_STALE_MS) rpm = 0.0f;
    lastRpmSampleMs = now;
  }

  simulatedSpeed = rpm / RPM_PER_SIMULATED_SPEED_UNIT;
  overspeedAlert = (signLimit >= 0 && simulatedSpeed > signLimit);
  if (signLimit >= 0 && now - lastSignMs > SIGN_TIMEOUT_MS) {
    signLimit = -1;
    overspeedAlert = false;
  }

  eStopActive = (digitalRead(SOFTWARE_ESTOP_PIN) == LOW);
  commandStale = !haveSequence || (now - lastCommandMs > SERIAL_TIMEOUT_MS);
  bool rpmSensorFault =
      motorPwm > 0 &&
      now - motorRunStartedMs > RPM_SENSOR_FAULT_MS &&
      (lastPulseSnapshot == 0 || now - lastPulseSnapshot > RPM_SENSOR_FAULT_MS);
  sensorFault = sensorFault || !pwmReady || mq3RailFault || rpmSensorFault;
}

void applyControllerOutput(unsigned long now) {
  bool warmupActive = (now - bootMs < MQ3_WARMUP_MS);
  bool forcedCutoff =
      eStopActive || commandStale || sensorFault || alcoholAlert || warmupActive;

  if (forcedCutoff) {
    motorStop();
  } else if (objectHazard || overspeedAlert) {
    motorRun(REDUCED_PWM);
  } else {
    motorRun(NORMAL_PWM);
  }

  digitalWrite(
      BUZZER_PIN,
      (eStopActive || commandStale || sensorFault || alcoholAlert ||
       objectHazard || overspeedAlert) ? HIGH : LOW);
}

void sendTelemetry(unsigned long now) {
  if (now - lastTelemetryMs < TELEMETRY_INTERVAL_MS) return;
  lastTelemetryMs = now;
  Serial.print("TEL,");
  Serial.print(haveSequence ? lastValidSequence : 0);
  Serial.print(",mq3=");
  Serial.print(mq3Adc);
  Serial.print(",rpm=");
  Serial.print(rpm, 1);
  Serial.print(",limit=");
  Serial.print(signLimit);
  Serial.print(",object=");
  Serial.print(objectHazard ? 1 : 0);
  Serial.print(",alcohol=");
  Serial.print(alcoholAlert ? 1 : 0);
  Serial.print(",overspeed=");
  Serial.print(overspeedAlert ? 1 : 0);
  Serial.print(",stale=");
  Serial.print(commandStale ? 1 : 0);
  Serial.print(",sensor_fault=");
  Serial.print(sensorFault ? 1 : 0);
  Serial.print(",pwm=");
  Serial.print(motorPwm);
  Serial.print(",hazard=");
  Serial.print((eStopActive || commandStale || sensorFault || alcoholAlert ||
                objectHazard || overspeedAlert ||
                now - bootMs < MQ3_WARMUP_MS) ? 1 : 0);
  Serial.print(",estop=");
  Serial.print(eStopActive ? 1 : 0);
  Serial.print(",warmup=");
  Serial.println(now - bootMs < MQ3_WARMUP_MS ? 1 : 0);
}

void updateDisplay(unsigned long now) {
  if (now - lastLcdMs < LCD_INTERVAL_MS) return;
  lastLcdMs = now;
  lcd.clear();
  if (eStopActive || commandStale || sensorFault || alcoholAlert ||
      now - bootMs < MQ3_WARMUP_MS) {
    lcd.setCursor(0, 0);
    if (eStopActive) lcd.print("E-STOP ACTIVE");
    else if (commandStale) lcd.print("LINK TIMEOUT");
    else if (sensorFault) lcd.print("SENSOR FAULT");
    else if (alcoholAlert) lcd.print("MQ3 ALERT");
    else lcd.print("MQ3 WARMING");
    lcd.setCursor(0, 1);
    lcd.print("MOTOR CUTOFF");
  } else if (objectHazard || overspeedAlert) {
    lcd.setCursor(0, 0);
    lcd.print(objectHazard ? "Object hazard" : "RPM over limit");
    lcd.setCursor(0, 1);
    lcd.print("RPM:");
    lcd.print((int)rpm);
    lcd.print(" PWM:");
    lcd.print(motorPwm);
  } else {
    lcd.setCursor(0, 0);
    lcd.print("System normal");
    lcd.setCursor(0, 1);
    lcd.print("RPM:");
    lcd.print((int)rpm);
    lcd.print(" L:");
    if (signLimit < 0) lcd.print("--");
    else lcd.print(signLimit);
  }
}

void setup() {
  bootMs = millis();
  syncEpoch = esp_random();
  lastRpmSampleMs = bootMs;
  lastPulseMs = 0;
  Serial.begin(115200);
  pinMode(MQ3_PIN, INPUT);
  pinMode(SPEED_PIN, INPUT_PULLUP);
  pinMode(IN1_PIN, OUTPUT);
  pinMode(IN2_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(SOFTWARE_ESTOP_PIN, INPUT_PULLUP);
  digitalWrite(BUZZER_PIN, LOW);
  motorStop();

  pwmReady = ledcAttach(ENA_PIN, 1000, 8);
  if (!pwmReady) motorStop();
  attachInterrupt(digitalPinToInterrupt(SPEED_PIN), onSpeedPulse, FALLING);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Safety Prototype");
  lcd.setCursor(0, 1);
  lcd.print("Motor cutoff");
}

void loop() {
  readSerialCommands();
  unsigned long now = millis();
  updateSensors(now);
  applyControllerOutput(now);
  updateDisplay(now);
  sendTelemetry(now);
  delay(10);
}
