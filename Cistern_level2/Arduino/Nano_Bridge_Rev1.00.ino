// nano_hc12_bridge_rev1_bidirectional.ino
#include <SoftwareSerial.h>

// HC-12 TXD -> D10 (RX), HC-12 RXD -> D11 (TX)
SoftwareSerial hc12(10, 11);

String inLine;   // HC-12 -> PC
String outLine;  // PC -> HC-12

void setup() {
  Serial.begin(115200); // USB to PC
  hc12.begin(9600);     // HC-12
  Serial.println("NANO_BRIDGE_READY");
}

void loop() {
  // ---- HC-12 -> PC ----
  while (hc12.available()) {
    char c = (char)hc12.read();
    if (c == '\n') {
      inLine.trim();
      if (inLine.length() > 0) Serial.println(inLine);
      inLine = "";
    } else if (c != '\r') {
      if (inLine.length() < 220) inLine += c;
      else inLine = "";
    }
  }

  // ---- PC -> HC-12 ----
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      outLine.trim();
      if (outLine.length() > 0) {
        hc12.print(outLine);
        hc12.print("\n");   // important: cistern PCB expects newline to process command
      }
      outLine = "";
    } else if (c != '\r') {
      if (outLine.length() < 80) outLine += c;
      else outLine = "";
    }
  }
}
