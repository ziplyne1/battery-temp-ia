// Multi-channel battery logger for Arduino Nano.
// Each channel = one INA219 (current/voltage) + one DS18B20 (temperature).
// Waits for the Mac to send 'g', then prints one CSV row per channel per second:
//   ch,time_s,temp_C,battery_V,current_mA,capacity_mAh
// Lines starting with '#' are status messages for the Mac script, not data.

#include <Wire.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ---- Configure per setup -------------------------------------------------
const uint8_t N = 3;                                   // number of channels
const uint8_t INA_ADDR[N] = {0x40, 0x41, 0x44};        // set by A0/A1 jumpers
const uint8_t TEMP_PIN[N] = {2, 3, 4};                 // one DS18B20 per pin
const float   CUTOFF_V    = 0.9;                       // end-of-discharge voltage
const unsigned long INTERVAL_MS = 1000;
// --------------------------------------------------------------------------

Adafruit_INA219*   ina[N];
OneWire*           wire[N];
DallasTemperature* temp[N];

float mAh[N];
bool  active[N];
unsigned long startMs, lastTick;
bool running = false;

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < N; i++) {
    ina[i] = new Adafruit_INA219(INA_ADDR[i]);
    if (!ina[i]->begin()) {
      Serial.print("# ERROR: INA219 not found for channel ");
      Serial.println(i + 1);
      while (true) {}
    }
    wire[i] = new OneWire(TEMP_PIN[i]);
    temp[i] = new DallasTemperature(wire[i]);
    temp[i]->begin();
    temp[i]->setWaitForConversion(false);   // don't block while the sensor converts
    active[i] = true;
    mAh[i] = 0;
  }
  Serial.println("ch,time_s,temp_C,battery_V,current_mA,capacity_mAh");
  Serial.println("# ready");
}

void loop() {
  // Wait for the Mac to say go.
  if (!running) {
    if (Serial.available() && Serial.read() == 'g') {
      for (uint8_t i = 0; i < N; i++) temp[i]->requestTemperatures();  // fresh first reading
      startMs = lastTick = millis();
      running = true;
      Serial.println("# started");
    }
    return;
  }

  unsigned long now = millis();
  if (now - lastTick < INTERVAL_MS) return;
  float dt_h = (now - lastTick) / 3600000.0;
  lastTick = now;

  bool anyActive = false;
  for (uint8_t i = 0; i < N; i++) {
    if (!active[i]) continue;

    float tempC = temp[i]->getTempCByIndex(0);   // result of the previous request
    temp[i]->requestTemperatures();              // start the next conversion

    // The INA219 bus voltage is measured on the load side of the shunt;
    // add the shunt drop to get the true cell terminal voltage.
    float batteryV   = ina[i]->getBusVoltage_V() + ina[i]->getShuntVoltage_mV() / 1000.0;
    float current_mA = ina[i]->getCurrent_mA();
    mAh[i] += current_mA * dt_h;

    Serial.print(i + 1);                              Serial.print(',');
    Serial.print((now - startMs) / 1000.0, 1);        Serial.print(',');
    if (tempC != DEVICE_DISCONNECTED_C) Serial.print(tempC, 2);   // blank if sensor missing
    Serial.print(',');
    Serial.print(batteryV, 3);                        Serial.print(',');
    Serial.print(current_mA, 1);                      Serial.print(',');
    Serial.println(mAh[i], 2);

    if (batteryV < CUTOFF_V) {
      active[i] = false;
      Serial.print("# channel "); Serial.print(i + 1); Serial.println(" reached cutoff");
    } else {
      anyActive = true;
    }
  }

  if (!anyActive) {
    Serial.println("# all done");
    running = false;
  }
}
