// Emerson/Funai IR service remote: line-based serial front end for an IR LED.
//
// Commands (115200 baud, one per line, replies "OK ..." or "ERR ..."):
//   E <device> <function> [frames]   Emerson/Funai CRT frame (JP1 "Emerson" protocol)
//   N <address> <command> [repeats]  NEC / NECext frame (newer Funai LCD sets)
//   R <freq_hz> <t1> <t2> ...        raw mark/space timings in microseconds
//   L <0|1>                          stop/start printing captured IR as "RAW ..."
//   PING
// Numbers accept decimal or 0x hex.
//
// Emerson protocol (IRP): {36.7k,872}<1,-1|1,-3>(4,-4,D:6,F:6,~D:6,~F:6,1,-39)+
// i.e. 24 bits sent LSB-first: device, function, then the complement of both.

#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>

const uint16_t kIrLedPin = 4;     // drives the NPN transistor base via 1k
const uint16_t kIrRecvPin = 15;   // optional TSOP38238 output

const uint16_t kEmersonFreq = 36700;
const uint16_t kEmersonUnit = 872;
const uint16_t kEmersonBits = 24;
const uint32_t kEmersonGap = 39 * kEmersonUnit;

const uint16_t kMaxRaw = 300;
const uint16_t kCaptureBufferSize = 1024;

IRsend irsend(kIrLedPin);
IRrecv irrecv(kIrRecvPin, kCaptureBufferSize, 15, true);
decode_results results;
bool listening = true;
uint16_t rawBuf[kMaxRaw];

uint32_t emersonData(uint8_t device, uint8_t function) {
  uint32_t d = device & 0x3F, f = function & 0x3F;
  return d | (f << 6) | ((~d & 0x3F) << 12) | ((~f & 0x3F) << 18);
}

void sendEmerson(uint8_t device, uint8_t function, uint16_t frames) {
  irsend.sendGeneric(4 * kEmersonUnit, 4 * kEmersonUnit,
                     kEmersonUnit, 3 * kEmersonUnit,
                     kEmersonUnit, kEmersonUnit,
                     kEmersonUnit, kEmersonGap,
                     emersonData(device, function), kEmersonBits,
                     kEmersonFreq, false, frames - 1, kDutyDefault);
}

bool parseNum(const char *tok, long *out) {
  if (tok == nullptr) return false;
  char *end;
  *out = strtol(tok, &end, 0);
  return *end == '\0';
}

void handleLine(char *line) {
  char *cmd = strtok(line, " \t");
  if (cmd == nullptr) return;
  long a, b, c;

  if (!strcasecmp(cmd, "PING")) {
    Serial.println("OK PONG");
  } else if (!strcasecmp(cmd, "E")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || !parseNum(strtok(nullptr, " \t"), &b) ||
        a < 0 || a > 63 || b < 0 || b > 63) {
      Serial.println("ERR usage: E <device 0-63> <function 0-63> [frames]");
      return;
    }
    char *t = strtok(nullptr, " \t");
    if (t == nullptr) c = 2;
    else if (!parseNum(t, &c) || c < 1 || c > 50) { Serial.println("ERR frames 1-50"); return; }
    sendEmerson(a, b, c);
    Serial.printf("OK E %ld %ld %ld data=0x%06lX\n", a, b, c, (unsigned long)emersonData(a, b));
  } else if (!strcasecmp(cmd, "N")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || !parseNum(strtok(nullptr, " \t"), &b) ||
        a < 0 || a > 0xFFFF || b < 0 || b > 0xFF) {
      Serial.println("ERR usage: N <address 0-0xFFFF> <command 0-0xFF> [repeats]");
      return;
    }
    char *t = strtok(nullptr, " \t");
    if (t == nullptr) c = 0;
    else if (!parseNum(t, &c) || c < 0 || c > 20) { Serial.println("ERR repeats 0-20"); return; }
    uint32_t data = irsend.encodeNEC(a, b);
    irsend.sendNEC(data, kNECBits, c);
    Serial.printf("OK N 0x%04lX 0x%02lX data=0x%08lX\n", a, b, (unsigned long)data);
  } else if (!strcasecmp(cmd, "R")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || a < 10000 || a > 60000) {
      Serial.println("ERR usage: R <freq_hz> <t1> <t2> ...");
      return;
    }
    uint16_t n = 0;
    for (char *t = strtok(nullptr, " \t"); t != nullptr; t = strtok(nullptr, " \t")) {
      if (n >= kMaxRaw || !parseNum(t, &b) || b <= 0 || b > 65535) {
        Serial.println("ERR bad or too many timings");
        return;
      }
      rawBuf[n++] = b;
    }
    if (n == 0) { Serial.println("ERR no timings"); return; }
    irsend.sendRaw(rawBuf, n, a / 1000);
    Serial.printf("OK R %u timings\n", n);
  } else if (!strcasecmp(cmd, "L")) {
    if (!parseNum(strtok(nullptr, " \t"), &a)) { Serial.println("ERR usage: L <0|1>"); return; }
    listening = a != 0;
    Serial.printf("OK L %d\n", listening);
  } else {
    Serial.println("ERR unknown command");
  }
}

void setup() {
  Serial.begin(115200);
  irsend.begin();
  irrecv.enableIRIn();
  Serial.println("READY emerson-remote");
}

void loop() {
  static char line[2048];
  static size_t len = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      line[len] = '\0';
      handleLine(line);
      len = 0;
    } else if (len < sizeof(line) - 1) {
      line[len++] = ch;
    }
  }

  if (irrecv.decode(&results)) {
    if (listening) {
      Serial.print("RAW");
      for (uint16_t i = 1; i < results.rawlen; i++)
        Serial.printf(" %u", results.rawbuf[i] * kRawTick);
      Serial.println();
    }
    irrecv.resume();
  }
}
