/*
 * Inductive Appliance Fingerprinter — Stage 2: Event Capture
 * ---------------------------------------------------------------
 * Hardware: ESP32-S3, SCT-013-000 clamp -> 220R burden -> GPIO4,
 *           biased to 1.65V by a 10k/10k divider with 10uF + 100nF.
 *
 * Captures an appliance "event" in three parts:
 *   1. TURN-ON transient  — 500 ms at full rate, including
 *      pre-trigger history from a ring buffer.
 *   2. STEADY STATE       — 1 Hz summary rows, variable length
 *      (handles a 2 s blend and a 4 min toaster equally).
 *   3. TURN-OFF transient — 500 ms at full rate.
 *
 * Output is CSV over USB serial, framed with markers the Python
 * listener splits on. Offset is measured, not assumed (ADC reads
 * ~1879 for 1.65V on this chip, not the theoretical 2048).
 */

const int   PIN_SENSE   = 4;
const int   SAMPLE_US   = 100;        // ~10 kHz
const int   RMS_WIN     = 200;        // samples per RMS estimate (~20 ms)

// Ring buffer: pre-trigger history at full rate.
const int   RING_LEN    = 3000;       // ~300 ms at 10 kHz
int16_t     ring[RING_LEN];
int         ringHead    = 0;

// Transient capture length either side of an edge.
const int   TRANSIENT_SAMPLES = 5000; // ~500 ms at 10 kHz

// Calibration (see README component-choices section).
const float BURDEN   = 220.0;
const float CT_RATIO = 2000.0;
const float VREF     = 3.3;
const float ADC_MAX  = 4095.0;

// Detection thresholds, in RMS *counts*. Tune to your noise floor.
// Idle sits ~0.2 A; these correspond to roughly 0.35 A on / 0.30 A off,
// with hysteresis so a device hovering near the line doesn't chatter.
float THRESH_ON   = 80.0;
float THRESH_OFF  = 65.0;

// Debounce — generous, as requested. A motor dipping mid-run or a
// blend changing speed must NOT read as a turn-off.
const unsigned long DEBOUNCE_OFF_MS = 1200;  // must stay below OFF this long to end
const unsigned long DEBOUNCE_ON_MS  = 150;   // must stay above ON this long to start

float offset = 1879.0;

enum State { ARMED, RUNNING };
State state = ARMED;

unsigned long eventId       = 0;
unsigned long belowSinceMs  = 0;
unsigned long aboveSinceMs  = 0;
bool          maybeOff      = false;
bool          maybeOn       = false;

// ---- helpers ---------------------------------------------------

float countsToAmps(float rmsCounts) {
  float volts = rmsCounts * (VREF / ADC_MAX);
  return volts * CT_RATIO / BURDEN;
}

// One RMS estimate over RMS_WIN samples, feeding the ring buffer
// and tracking offset as it goes. Returns RMS in counts.
float sampleWindow(float &peakOut) {
  double sumSq = 0, sum = 0;
  int    peak  = 0;
  for (int i = 0; i < RMS_WIN; i++) {
    int raw = analogRead(PIN_SENSE);
    ring[ringHead] = (int16_t)raw;
    ringHead = (ringHead + 1) % RING_LEN;

    sum += raw;
    float d = raw - offset;
    sumSq += d * d;
    if (abs((int)d) > peak) peak = abs((int)d);
    delayMicroseconds(SAMPLE_US);
  }
  // Slow offset tracking — insensitive to the signal (averages ~0),
  // tracks thermal drift only.
  offset = offset * 0.995 + (sum / RMS_WIN) * 0.005;
  peakOut = peak;
  return sqrt(sumSq / RMS_WIN);
}

// Dump the ring buffer (oldest -> newest) as the pre-trigger history.
void dumpRing() {
  Serial.println("PRE_TRIGGER");
  int idx = ringHead;                 // oldest sample
  for (int i = 0; i < RING_LEN; i++) {
    Serial.println(ring[idx] - (int)offset);
    idx = (idx + 1) % RING_LEN;
  }
}

// Capture a fast transient of TRANSIENT_SAMPLES, offset-removed.
void captureTransient(const char *label) {
  Serial.print("TRANSIENT ");
  Serial.println(label);
  for (int i = 0; i < TRANSIENT_SAMPLES; i++) {
    int raw = analogRead(PIN_SENSE);
    ring[ringHead] = (int16_t)raw;    // keep ring current through capture
    ringHead = (ringHead + 1) % RING_LEN;
    Serial.println(raw - (int)offset);
    delayMicroseconds(SAMPLE_US);
  }
}

// ---- setup -----------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(1000);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);

  // Prime the ring and settle the offset before arming.
  float p;
  for (int i = 0; i < 20; i++) sampleWindow(p);

  Serial.println("# Inductive Appliance Fingerprinter - event capture");
  Serial.println("READY");
}

// ---- main loop -------------------------------------------------

void loop() {
  float peak;
  float rms = sampleWindow(peak);
  unsigned long now = millis();

  if (state == ARMED) {
    // Watch for a sustained rise above THRESH_ON.
    if (rms > THRESH_ON) {
      if (!maybeOn) { maybeOn = true; aboveSinceMs = now; }
      else if (now - aboveSinceMs >= DEBOUNCE_ON_MS) {
        // Confirmed turn-on.
        eventId++;
        maybeOn = false;
        Serial.print("EVENT_START ");
        Serial.println(eventId);
        dumpRing();                       // history from before the edge
        captureTransient("ONSET");        // the turn-on transient
        Serial.println("STEADY_BEGIN");
        state = RUNNING;
      }
    } else {
      maybeOn = false;
    }

  } else { // RUNNING
    // 1 Hz-ish steady-state summary. sampleWindow() is ~20 ms, so
    // print roughly every 50th window.
    static int subcount = 0;
    if (++subcount >= 50) {
      subcount = 0;
      float amps = countsToAmps(rms);
      float crest = (rms > 1e-3) ? (peak / rms) : 0.0;
      Serial.print("STEADY ");
      Serial.print(rms, 1);   Serial.print(',');
      Serial.print(amps, 3);  Serial.print(',');
      Serial.println(crest, 2);
    }

    // Watch for a sustained fall below THRESH_OFF (generous debounce).
    if (rms < THRESH_OFF) {
      if (!maybeOff) { maybeOff = true; belowSinceMs = now; }
      else if (now - belowSinceMs >= DEBOUNCE_OFF_MS) {
        // Confirmed turn-off.
        maybeOff = false;
        Serial.println("STEADY_END");
        captureTransient("OFFSET");       // the turn-off transient
        Serial.print("EVENT_END ");
        Serial.println(eventId);
        Serial.println("READY");
        state = ARMED;
      }
    } else {
      maybeOff = false;                   // dipped but recovered — not off
    }
  }
}
