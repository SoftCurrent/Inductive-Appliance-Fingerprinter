const int PIN_SENSE = 4;
const float BURDEN   = 220.0;
const float CT_RATIO = 2000.0;
const float VREF     = 3.3;
const float ADC_MAX  = 4095.0;

float offset = 1880.0;

float countsToAmps(float rmsCounts) {
  float volts = rmsCounts * (VREF / ADC_MAX);
  return volts * CT_RATIO / BURDEN;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);
  Serial.println("rms_counts\tamps\twatts\tpeak");
}

void loop() {
  const int N = 2000;
  double sumSq = 0;
  double sum   = 0;
  int peak     = 0;

  for (int i = 0; i < N; i++) {
    int raw = analogRead(PIN_SENSE);
    sum += raw;
    float d = raw - offset;
    sumSq += d * d;
    if (abs((int)d) > peak) peak = abs((int)d);
    delayMicroseconds(100);
  }

  offset = offset * 0.99 + (sum / N) * 0.01;

  float rmsCounts = sqrt(sumSq / N);
  float amps = countsToAmps(rmsCounts);
  float watts = amps * 230.0;

  Serial.print(rmsCounts, 1); Serial.print('\t');
  Serial.print(amps, 3);      Serial.print('\t');
  Serial.print(watts, 0);     Serial.print('\t');
  Serial.println(peak);

  delay(500);
}
