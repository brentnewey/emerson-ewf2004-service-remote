// Emerson/Funai IR service remote, Arduino Uno build. Same serial protocol as
// esp32.cpp, so host/remote.py works with either board.
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
// IRremote takes whole kHz on AVR, so the carrier is 37 kHz here. The carrier is
// generated in software (SEND_PWM_BY_TIMER is not defined), which keeps the receive
// timer running during sends so the board can hear its own LED.

#include <Arduino.h>
#define DECODE_NEC  // keep flash use down; raw timings are printed regardless
#include <IRremote.hpp>

const uint8_t kIrSendPin = 3;   // drives the NPN transistor base via 1k
const uint8_t kIrRecvPin = 11;  // optional TSOP38238 output

const uint8_t kEmersonKhz = 37;
const uint16_t kEmersonUnit = 872;
const uint8_t kEmersonGapMs = 39UL * kEmersonUnit / 1000;
const uint8_t kEmersonLen = 2 + 24 * 2 + 1;

const uint8_t kMaxRaw = 72;  // enough for an NEC frame; the Uno has 2 KB of RAM

bool listening = true;
uint16_t rawBuf[kMaxRaw];

uint32_t emersonData(uint8_t device, uint8_t function) {
  uint32_t d = device & 0x3F, f = function & 0x3F;
  return d | (f << 6) | ((~d & 0x3F) << 12) | ((~f & 0x3F) << 18);
}

void sendEmerson(uint8_t device, uint8_t function, uint8_t frames) {
  uint32_t data = emersonData(device, function);
  uint8_t n = 0;
  rawBuf[n++] = 4 * kEmersonUnit;
  rawBuf[n++] = 4 * kEmersonUnit;
  for (uint8_t i = 0; i < 24; i++) {
    rawBuf[n++] = kEmersonUnit;
    rawBuf[n++] = (data >> i) & 1 ? 3 * kEmersonUnit : kEmersonUnit;
  }
  rawBuf[n++] = kEmersonUnit;
  for (uint8_t i = 0; i < frames; i++) {
    IrSender.sendRaw(rawBuf, kEmersonLen, kEmersonKhz);
    delay(kEmersonGapMs);
  }
}

bool parseNum(const char *tok, long *out) {
  if (tok == nullptr) return false;
  char *end;
  *out = strtol(tok, &end, 0);
  return *end == '\0';
}

void reply(const char *msg) { Serial.println(msg); }

void handleLine(char *line) {
  char *cmd = strtok(line, " \t");
  if (cmd == nullptr) return;
  long a, b, c;
  char out[48];

  if (!strcasecmp(cmd, "PING")) {
    reply("OK PONG");
  } else if (!strcasecmp(cmd, "E")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || !parseNum(strtok(nullptr, " \t"), &b) ||
        a < 0 || a > 63 || b < 0 || b > 63) {
      reply("ERR usage: E <device 0-63> <function 0-63> [frames]");
      return;
    }
    char *t = strtok(nullptr, " \t");
    if (t == nullptr) c = 2;
    else if (!parseNum(t, &c) || c < 1 || c > 50) { reply("ERR frames 1-50"); return; }
    sendEmerson(a, b, c);
    snprintf(out, sizeof(out), "OK E %ld %ld %ld data=0x%06lX", a, b, c, emersonData(a, b));
    reply(out);
  } else if (!strcasecmp(cmd, "N")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || !parseNum(strtok(nullptr, " \t"), &b) ||
        a < 0 || a > 0xFFFF || b < 0 || b > 0xFF) {
      reply("ERR usage: N <address 0-0xFFFF> <command 0-0xFF> [repeats]");
      return;
    }
    char *t = strtok(nullptr, " \t");
    if (t == nullptr) c = 0;
    else if (!parseNum(t, &c) || c < 0 || c > 20) { reply("ERR repeats 0-20"); return; }
    IrSender.sendNEC(a, b, c);  // addresses above 0xFF are sent as 16-bit (NECext)
    snprintf(out, sizeof(out), "OK N 0x%04lX 0x%02lX", a, b);
    reply(out);
  } else if (!strcasecmp(cmd, "R")) {
    if (!parseNum(strtok(nullptr, " \t"), &a) || a < 10000 || a > 60000) {
      reply("ERR usage: R <freq_hz> <t1> <t2> ...");
      return;
    }
    uint8_t n = 0;
    for (char *t = strtok(nullptr, " \t"); t != nullptr; t = strtok(nullptr, " \t")) {
      if (n >= kMaxRaw || !parseNum(t, &b) || b <= 0 || b > 65535) {
        reply("ERR bad or too many timings (max 72 on Uno)");
        return;
      }
      rawBuf[n++] = b;
    }
    if (n == 0) { reply("ERR no timings"); return; }
    IrSender.sendRaw(rawBuf, n, (a + 500) / 1000);
    snprintf(out, sizeof(out), "OK R %u timings", n);
    reply(out);
  } else if (!strcasecmp(cmd, "L")) {
    if (!parseNum(strtok(nullptr, " \t"), &a)) { reply("ERR usage: L <0|1>"); return; }
    listening = a != 0;
    reply(listening ? "OK L 1" : "OK L 0");
  } else {
    reply("ERR unknown command");
  }
}

void setup() {
  Serial.begin(115200);
  IrSender.begin(kIrSendPin);
  IrReceiver.begin(kIrRecvPin, DISABLE_LED_FEEDBACK);
  reply("READY emerson-remote");
}

void loop() {
  static char line[480];  // fits an R command with a full NEC frame
  static uint16_t len = 0;
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

  if (IrReceiver.decode()) {
    if (listening) {
      Serial.print("RAW");
      for (uint16_t i = 1; i < IrReceiver.irparams.rawlen; i++) {
        Serial.print(' ');
        Serial.print((uint32_t)IrReceiver.irparams.rawbuf[i] * MICROS_PER_TICK);
      }
      Serial.println();
    }
    IrReceiver.resume();
  }
}
