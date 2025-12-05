// Debug receiver for Serial4: dump raw bytes and assembled value
const int ledPin = 13;

uint32_t rxValue = 0;
unsigned long frameCounter = 0;

// Buffer and state
static uint8_t buf[4];
static uint8_t idx = 0;

// Timing for non-blocking blink and frame timeout
const unsigned long blinkDuration = 80;      // ms LED on time
const unsigned long frameTimeout = 50;       // ms to wait before discarding partial frame
unsigned long lastByteMillis = 0;
unsigned long ledOnUntil = 0;

void setup() {
  Serial.begin(115200);    // USB debug
  Serial4.begin(9600);     // hardware UART on pins 16/17
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  Serial.println("Debug: waiting for bytes on Serial4...");
}

void loop() {
  // Read all available bytes quickly
  while (Serial4.available() > 0) {
    int r = Serial4.read();            // read returns int; -1 if none
    if (r < 0) break;
    uint8_t b = (uint8_t)r;

    // Immediate raw dump to USB
    Serial.print("RX byte: 0x");
    printHex8(b);
    Serial.print("  (dec ");
    Serial.print(b);
    Serial.print(")  char: ");
    if (b >= 32 && b <= 126) Serial.print((char)b);
    else Serial.print('.');
    Serial.println();

    // Buffer into 32-bit little-endian
    buf[idx++] = b;
    lastByteMillis = millis();

    if (idx >= 4) {
      idx = 0;
      rxValue = ((uint32_t)buf[0]) | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
      frameCounter++;

      // Send a compact binary response over Serial4 (less blocking than long ASCII prints)
      // Frame format (little-endian values):
      // [0] HEADER 0xAA
      // [1] HEADER 0x55
      // [2..5] 4-byte payload value (LE)
      // [6..9] 4-byte frame counter (LE)
      // Total length: 10 bytes
      uint8_t hdr0 = 0xAA;
      uint8_t hdr1 = 0x55;
      Serial4.write(hdr0);
      Serial4.write(hdr1);
      Serial4.write((uint8_t *)&rxValue, 4);
      Serial4.write((uint8_t *)&frameCounter, 4);

      // Keep detailed USB serial debug prints (does not affect Serial4 timing)
      Serial.print("Assembled 0x");
      printHex32(rxValue);
      Serial.print("  dec ");
      Serial.print(rxValue);
      Serial.print("  counter ");
      Serial.println(frameCounter);

      // Start non-blocking LED blink
      digitalWrite(ledPin, HIGH);
      ledOnUntil = millis() + blinkDuration;
    }
  }

  // Handle frame timeout: if partial frame and no bytes for frameTimeout, reset index
  if (idx != 0 && (millis() - lastByteMillis) > frameTimeout) {
    Serial.print("Frame timeout, discarding ");
    Serial.print(idx);
    Serial.println(" bytes.");
    idx = 0;
  }

  // Turn off LED when blink time expires (non-blocking)
  if (ledOnUntil != 0 && millis() >= ledOnUntil) {
    digitalWrite(ledPin, LOW);
    ledOnUntil = 0;
  }

  // Small yield to let background tasks run (optional)
  // delay(1); // avoid long delays; uncomment only if needed for stability
}

// Helper: print a single byte as two hex digits
void printHex8(uint8_t v) {
  if (v < 0x10) Serial.print('0');
  Serial.print(v, HEX);
}

// Helper: print 32-bit value as 8 hex digits with leading zeros (uppercase)
void printHex32(uint32_t v) {
  // Print each byte MSB-first to ensure 8 digits
  uint8_t b3 = (v >> 24) & 0xFF;
  uint8_t b2 = (v >> 16) & 0xFF;
  uint8_t b1 = (v >> 8) & 0xFF;
  uint8_t b0 = v & 0xFF;
  if (b3 < 0x10) Serial.print('0');
  Serial.print(b3, HEX);
  if (b2 < 0x10) Serial.print('0');
  Serial.print(b2, HEX);
  if (b1 < 0x10) Serial.print('0');
  Serial.print(b1, HEX);
  if (b0 < 0x10) Serial.print('0');
  Serial.print(b0, HEX);
}