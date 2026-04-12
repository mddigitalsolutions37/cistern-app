// cistern_pcb_rev1_04.ino
#include <EEPROM.h>

// ---------------- CONFIG ----------------
static const uint8_t SENSOR_PIN = A0;          // ADC0
static unsigned long intervalMs = 60000;       // 1 minute default

// Tank geometry (baseline math uses this)
// 9.5 ft = 2.8956 m
static const float TANK_HEIGHT_M = 2.8956f;

// Sensor range: 0–5 m water, 4–20 mA, 250Ω => 1–5 V
static const float SENSOR_RANGE_M = 5.0f;

// ADC ref assumption (your AVCC ~5V from buck)
static const float ADC_REF_V = 5.0f;
static const int   ADC_MAX   = 1023;

// Capacity (imperial gallons) – you can adjust later via SET_CAP
static float TANK_FULL_IMP_GAL_DEFAULT = 2974.0f;

// ADC smoothing
static const uint8_t SAMPLES = 20;
static const uint8_t SAMPLE_DELAY_MS = 5;

// ---------------- EEPROM LAYOUT ----------------
// calMode:
// 0 = none
// 1 = true calibration (CAL_EMPTY/CAL_FULL used)
// 2 = baseline calibration (SET_BASELINE used)
struct CalData {
  uint16_t magic;
  uint8_t  calMode;
  uint16_t adcEmpty;
  uint16_t adcFull;
  float    tankFullGal;
};

static const uint16_t CAL_MAGIC = 0xC157;
static const int EEPROM_ADDR = 0;
static CalData cal;

// ---------------- HELPERS ----------------
static uint16_t readAdcAveraged(uint8_t pin) {
  uint32_t sum = 0;
  for (uint8_t i = 0; i < SAMPLES; i++) {
    sum += analogRead(pin);
    delay(SAMPLE_DELAY_MS);
  }
  return (uint16_t)(sum / SAMPLES);
}

static float clampf(float x, float lo, float hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static void saveCal() {
  EEPROM.put(EEPROM_ADDR, cal);
}

static void loadCal() {
  EEPROM.get(EEPROM_ADDR, cal);
  if (cal.magic != CAL_MAGIC) {
    cal.magic = CAL_MAGIC;
    cal.calMode = 0;
    cal.adcEmpty = 0;
    cal.adcFull = 0;
    cal.tankFullGal = TANK_FULL_IMP_GAL_DEFAULT;
    saveCal();
  }
  if (!(cal.tankFullGal > 10.0f && cal.tankFullGal < 50000.0f)) {
    cal.tankFullGal = TANK_FULL_IMP_GAL_DEFAULT;
    saveCal();
  }
}

static bool calValid() {
  return (cal.adcFull > cal.adcEmpty) && (cal.adcEmpty > 0) && (cal.adcFull <= 1023);
}

static float adcToPercent(uint16_t adc) {
  if (!calValid()) return -1.0f;
  float pct = (float)(adc - cal.adcEmpty) / (float)(cal.adcFull - cal.adcEmpty);
  pct *= 100.0f;
  return clampf(pct, 0.0f, 100.0f);
}

static float percentToGallons(float pct) {
  if (pct < 0.0f) return -1.0f;
  return (pct / 100.0f) * cal.tankFullGal;
}

// ---- Baseline calibration math ----
// Derive expected ADC span for *your tank height* using sensor physics:
// 0–5m => 1–5V across shunt => 4V span over 5m => 0.8V per meter
// ADC counts per volt: 1023/5V = 204.6
// counts per meter: 0.8 * 204.6 ≈ 163.7
static uint16_t expectedAdcSpanForTank() {
  float counts_per_v = (float)ADC_MAX / ADC_REF_V; // ~204.6
  float v_per_m = 4.0f / SENSOR_RANGE_M;           // 0.8 V/m
  float counts_per_m = v_per_m * counts_per_v;     // ~163.7
  float span = counts_per_m * TANK_HEIGHT_M;       // ~474 counts for 2.8956m
  if (span < 50) span = 50;
  if (span > 900) span = 900;
  return (uint16_t)(span + 0.5f);
}

// Apply baseline using measured percent at current level
static void setBaselineFromPercent(float pctMeasured) {
  pctMeasured = clampf(pctMeasured, 0.0f, 100.0f);

  uint16_t adcNow = readAdcAveraged(SENSOR_PIN);
  uint16_t span = expectedAdcSpanForTank();

  // adcEmpty = adcNow - pct*span
  float emptyF = (float)adcNow - (pctMeasured / 100.0f) * (float)span;
  float fullF  = emptyF + (float)span;

  uint16_t adcEmpty = (uint16_t)clampf(emptyF, 1.0f, 1023.0f);
  uint16_t adcFull  = (uint16_t)clampf(fullF,  (float)adcEmpty + 1.0f, 1023.0f);

  cal.adcEmpty = adcEmpty;
  cal.adcFull  = adcFull;
  cal.calMode  = 2; // baseline mode
  saveCal();

  Serial.print("OK BASELINE ADC_NOW=");
  Serial.print(adcNow);
  Serial.print(";ADC_EMPTY=");
  Serial.print(cal.adcEmpty);
  Serial.print(";ADC_FULL=");
  Serial.print(cal.adcFull);
  Serial.print(";SPAN=");
  Serial.print(span);
  Serial.print(";PCT=");
  Serial.println(pctMeasured, 1);
}

static void sendPacket(uint16_t adc, float pct, float gal) {
  Serial.print("LVL:");
  if (pct < 0) Serial.print("NA");
  else Serial.print(pct, 1);

  Serial.print(";G:");
  if (gal < 0) Serial.print("NA");
  else Serial.print((int)gal);

  Serial.print(";ADC:");
  Serial.print(adc);

  Serial.print(";CAL:");
  // 0 none, 1 true, 2 baseline
  Serial.print(calValid() ? cal.calMode : 0);

  Serial.println();
}

// ---------------- COMMANDS ----------------
static String cmdLine;

static void processCommand(String s) {
  s.trim();
  if (s.length() == 0) return;

  String up = s;
  up.toUpperCase();

  if (up == "PING") { Serial.println("PONG"); return; }

  if (up == "GET_CAL") {
    Serial.print("CAL_MODE=");
    Serial.print(calValid() ? cal.calMode : 0);
    Serial.print(";CAL_EMPTY_ADC=");
    Serial.print(cal.adcEmpty);
    Serial.print(";CAL_FULL_ADC=");
    Serial.print(cal.adcFull);
    Serial.print(";TANK_FULL_GAL=");
    Serial.print(cal.tankFullGal, 1);
    Serial.print(";INTERVAL_MS=");
    Serial.print(intervalMs);
    Serial.print(";TANK_HEIGHT_M=");
    Serial.println(TANK_HEIGHT_M, 4);
    return;
  }

  // Clear any calibration (baseline or true)
  if (up == "CLR_CAL" || up == "CLEAR_CAL") {
    cal.calMode = 0;
    cal.adcEmpty = 0;
    cal.adcFull = 0;
    saveCal();
    Serial.println("OK CAL CLEARED");
    return;
  }

  // True calibration points
  if (up == "CAL_EMPTY") {
    uint16_t adc = readAdcAveraged(SENSOR_PIN);
    cal.adcEmpty = adc;
    if (cal.adcFull <= cal.adcEmpty) cal.adcFull = cal.adcEmpty + 1;
    cal.calMode = 1; // true
    saveCal();
    Serial.print("OK CAL_EMPTY ADC=");
    Serial.println(adc);
    return;
  }

  if (up == "CAL_FULL") {
    uint16_t adc = readAdcAveraged(SENSOR_PIN);
    cal.adcFull = adc;
    if (cal.adcFull <= cal.adcEmpty) cal.adcEmpty = (cal.adcFull > 1) ? (cal.adcFull - 1) : 1;
    cal.calMode = 1; // true
    saveCal();
    Serial.print("OK CAL_FULL ADC=");
    Serial.println(adc);
    return;
  }

  // Baseline calibration from measured percent (0..100)
  if (up.startsWith("SET_BASELINE ")) {
    float pct = s.substring(13).toFloat();
    if (pct >= 0.0f && pct <= 100.0f) {
      setBaselineFromPercent(pct);
    } else {
      Serial.println("ERR BAD_BASELINE_PCT");
    }
    return;
  }

  // Set capacity (imperial gallons)
  if (up.startsWith("SET_CAP ")) {
    float v = s.substring(8).toFloat();
    if (v > 10.0f && v < 50000.0f) {
      cal.tankFullGal = v;
      saveCal();
      Serial.print("OK SET_CAP ");
      Serial.println(cal.tankFullGal, 1);
    } else {
      Serial.println("ERR BAD_CAP");
    }
    return;
  }

  // Change interval (ms) 1s .. 1hr
  if (up.startsWith("SET_INT ")) {
    unsigned long v = (unsigned long)s.substring(8).toInt();
    if (v >= 1000UL && v <= 3600000UL) {
      intervalMs = v;
      Serial.print("OK SET_INT ");
      Serial.println(intervalMs);
    } else {
      Serial.println("ERR BAD_INT");
    }
    return;
  }

  Serial.println("ERR UNKNOWN_CMD");
}

static void serviceCommandsNonBlocking() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      processCommand(cmdLine);
      cmdLine = "";
    } else if (c != '\r') {
      if (cmdLine.length() < 80) cmdLine += c;
      else cmdLine = "";
    }
  }
}

// ---------------- MAIN ----------------
static unsigned long lastTick = 0;

void setup() {
  Serial.begin(9600); // HC-12 UART
  loadCal();
  Serial.println("CISTERN_REV1_04_BOOT");
}

void loop() {
  serviceCommandsNonBlocking();

  unsigned long now = millis();
  if (now - lastTick >= intervalMs) {
    lastTick = now;

    uint16_t adc = readAdcAveraged(SENSOR_PIN);
    float pct = adcToPercent(adc);
    float gal = percentToGallons(pct);

    sendPacket(adc, pct, gal);
  }
}
