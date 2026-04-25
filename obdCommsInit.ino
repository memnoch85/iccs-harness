#include <SPI.h>

#define CS_PIN 17
#define LED_PIN 0
bool hasValidatedComms = false;
bool quietAfterLock = true;

enum CanProfile {
  PROFILE_125K,
  PROFILE_250K,
  PROFILE_500K
};

const char* profileNames[] = {
  "Profile 125kbps",
  "Profile 250kbps",
  "Profile 500kbps"
};

const uint32_t profileBitrates[] = {
  125000,
  250000,
  500000
};

// Locked profile state
CanProfile lockedProfile = PROFILE_125K;
bool profileLocked = false;
unsigned long discoveryStartTime = 0;
const unsigned long DISCOVERY_TIMEOUT = 10000; // 10 seconds max discovery

uint16_t lastRxId = 0;
byte lastData[8];
byte lastDlc = 0;
unsigned long lastPrintTime = 0;

// ================= LOW-LEVEL FUNCTIONS =================

void mcpReset() {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0xC0);
  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
  delay(10);
}

byte mcpRead(byte reg) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x03);
  SPI.transfer(reg);
  byte data = SPI.transfer(0x00);
  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
  return data;
}

void mcpWrite(byte reg, byte data) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x02);
  SPI.transfer(reg);
  SPI.transfer(data);
  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
  delay(1);
}

void mcpBitModify(byte reg, byte mask, byte data) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x05);
  SPI.transfer(reg);
  SPI.transfer(mask);
  SPI.transfer(data);
  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
  delay(1);
}

// ================= LED FUNCTIONS =================

void blinkSuccess() {
  for(int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(80);
    digitalWrite(LED_PIN, LOW);
    delay(80);
  }
}

void blinkSending() {
  digitalWrite(LED_PIN, HIGH);
  delay(50);
  digitalWrite(LED_PIN, LOW);
}

void blinkProfileSwitch() {
  for(int i = 0; i < 2; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(300);
    digitalWrite(LED_PIN, LOW);
    delay(300);
  }
}

void blinkBoot() {
  digitalWrite(LED_PIN, HIGH);
  delay(1000);
  digitalWrite(LED_PIN, LOW);
  delay(500);
}

void blinkLocked() {
  digitalWrite(LED_PIN, HIGH);
  delay(2000);
  digitalWrite(LED_PIN, LOW);
}

// ================= CONFIGURATION =================

bool configureProfile(CanProfile profile) {
  Serial.print("Configuring ");
  Serial.println(profileNames[profile]);

  mcpReset();
  delay(10);

  mcpBitModify(0x0F, 0xE0, 0x80);
  delay(5);

  if(profile == PROFILE_125K) {
    // 16MHz, 125kbps
    mcpWrite(0x28, 0x03);
    mcpWrite(0x29, 0xB0);
    mcpWrite(0x2A, 0x86);
  }
  else if(profile == PROFILE_250K) {
    // 16MHz, 250kbps
    mcpWrite(0x28, 0x86);
    mcpWrite(0x29, 0xF0);
    mcpWrite(0x2A, 0x00);
  }
  else { // PROFILE_500K
    // 16MHz, 500kbps
    mcpWrite(0x28, 0x00);
    mcpWrite(0x29, 0xF0);
    mcpWrite(0x2A, 0x87);
  }

  // Simplified filter config (accept all)
  for(byte reg = 0x00; reg <= 0x15; reg++) {
    mcpWrite(reg, 0x00);
  }
  for(byte reg = 0x20; reg <= 0x27; reg++) {
    mcpWrite(reg, 0x00);
  }

  mcpBitModify(0x0B, 0x04, 0x04);
  mcpWrite(0x2B, 0x03);

  mcpBitModify(0x0F, 0xE0, 0x00);
  delay(10);

  byte canStat = mcpRead(0x0F) & 0xE0;
  return (canStat == 0x00);
}

// ================= CAN FUNCTIONS =================

bool sendCANFrame(uint16_t id, byte dlc, byte* data) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x40);

  byte sidh = id >> 3;
  byte sidl = (id & 0x07) << 5;

  SPI.transfer(sidh);
  SPI.transfer(sidl);
  SPI.transfer(0x00);
  SPI.transfer(0x00);
  SPI.transfer(dlc);

  for(int i = 0; i < dlc; i++) {
    SPI.transfer(data[i]);
  }

  digitalWrite(CS_PIN, HIGH);

  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x81);
  digitalWrite(CS_PIN, HIGH);

  SPI.endTransaction();

  delay(2);
  return (mcpRead(0x30) & 0x08);
}

bool receiveCANFrame(uint16_t* rxId, byte* rxData, byte* rxDlc) {
  byte canIntf = mcpRead(0x2C);

  if(canIntf & 0x01) {
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    digitalWrite(CS_PIN, LOW);
    SPI.transfer(0x90);
    byte sidh = SPI.transfer(0x00);
    byte sidl = SPI.transfer(0x00);
    SPI.transfer(0x00);
    SPI.transfer(0x00);
    byte dlc = SPI.transfer(0x00) & 0x0F;

    for(int i = 0; i < dlc && i < 8; i++) {
      rxData[i] = SPI.transfer(0x00);
    }
    digitalWrite(CS_PIN, HIGH);
    SPI.endTransaction();

    mcpWrite(0x2C, 0x01);

    *rxId = ((uint16_t)sidh << 3) | (sidl >> 5);
    *rxDlc = dlc;
    return true;
  }
  else if(canIntf & 0x02) {
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    digitalWrite(CS_PIN, LOW);
    SPI.transfer(0x94);
    byte sidh = SPI.transfer(0x00);
    byte sidl = SPI.transfer(0x00);
    SPI.transfer(0x00);
    SPI.transfer(0x00);
    byte dlc = SPI.transfer(0x00) & 0x0F;

    for(int i = 0; i < dlc && i < 8; i++) {
      rxData[i] = SPI.transfer(0x00);
    }
    digitalWrite(CS_PIN, HIGH);
    SPI.endTransaction();

    mcpWrite(0x2C, 0x02);

    *rxId = ((uint16_t)sidh << 3) | (sidl >> 5);
    *rxDlc = dlc;
    return true;
  }

  return false;
}

// ================= OBD2 RPM REQUEST =================

void sendRPMRequest() {
  byte data[8] = {0x02, 0x01, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00};

  if(!profileLocked) {
    Serial.print("[DISCOVERY] ");
  }
  Serial.print(profileNames[lockedProfile]);
  Serial.println("] RPM request sent");

  blinkSending();
  sendCANFrame(0x7DF, 8, data);
}

// ================= PRINT RESPONSE =================

void printResponse(uint16_t rxId, byte* rxData, byte rxDlc) {
  Serial.print(rxId, HEX);
  Serial.print(" | Data: ");

  for(int i = 0; i < rxDlc; i++) {
    Serial.print("0x");
    if(rxData[i] < 0x10) Serial.print("0");
    Serial.print(rxData[i], HEX);
    Serial.print(" ");
  }

  // Parse RPM if present
  if(rxId >= 0x7E8 && rxId <= 0x7EF && rxDlc >= 5 && rxData[1] == 0x41 && rxData[2] == 0x0C) {
    uint16_t rpm = ((rxData[3] << 8) | rxData[4]) / 4;
    Serial.print("-> RPM: ");
    Serial.print(rpm);
    blinkSuccess();
  }
  Serial.println();
}

bool isValidECUResponse(uint16_t rxId, byte* rxData, byte rxDlc) {
  // ECU responses are typically on IDs 0x7E8 through 0x7EF
  if(rxId < 0x7E8 || rxId > 0x7EF) return false;

  // Need at least 3 bytes to check response type
  if(rxDlc < 3) return false;

  // Check for positive response to PID 0x0C (RPM)
  // Format: [length] 0x41 0x0C [data...]
  if(rxData[1] == 0x41 && rxData[2] == 0x0C) {
    return true;
  }

  // Also accept any positive response (0x41) as valid communication
  if(rxData[1] == 0x41) {
    return true;
  }

  return false;
}

// ================= DISCOVERY =================

void runDiscovery() {
  Serial.println("\n==========================================");
  Serial.println("DISCOVERY MODE: Scanning for CAN bitrate");
  Serial.println("==========================================\n");

  unsigned long discoveryStart = millis();
  int currentProfileIndex = 0;
  bool discoveryComplete = false;
  unsigned long lastSendTimeDiscovery = 0;
  bool waitingForResponseDiscovery = false;
  unsigned long responseTimeoutDiscovery = 0;

  while(!discoveryComplete && (millis() - discoveryStart < DISCOVERY_TIMEOUT)) {
    unsigned long currentTime = millis();

    // Check for received frames
    uint16_t rxId;
    byte rxData[8];
    byte rxDlc;

    if(receiveCANFrame(&rxId, rxData, &rxDlc)) {
      if(!quietAfterLock) {
        printResponse(rxId, rxData, rxDlc);
      }

      if(isValidECUResponse(rxId, rxData, rxDlc)) {
        Serial.println("\n==========================================");
        Serial.print("VALID RESPONSE FOUND on ");
        Serial.println(profileNames[currentProfileIndex]);
        Serial.println("==========================================\n");

        lockedProfile = (CanProfile)currentProfileIndex;
        hasValidatedComms = true;
        profileLocked = true;
        discoveryComplete = true;
        quietAfterLock = true;
        blinkLocked();
        return;
      }
    }

    // Send request logic
    if(!waitingForResponseDiscovery && (currentTime - lastSendTimeDiscovery >= 2000)) {
      Serial.print("[DISCOVERY] Testing ");
      Serial.println(profileNames[currentProfileIndex]);

      // Configure the MCP2515 for this bitrate
      configureProfile((CanProfile)currentProfileIndex);

      // Send the request
      byte data[8] = {0x02, 0x01, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00};
      blinkSending();
      sendCANFrame(0x7DF, 8, data);

      lastSendTimeDiscovery = currentTime;
      responseTimeoutDiscovery = currentTime;
      waitingForResponseDiscovery = true;
    }

    // Check for timeout on current profile
    if(waitingForResponseDiscovery && (currentTime - responseTimeoutDiscovery >= 3000)) {
      Serial.println("[DISCOVERY] No response, trying next bitrate");
      waitingForResponseDiscovery = false;

      // Move to next profile
      currentProfileIndex++;
      if(currentProfileIndex >= 3) {
        // Wrap around and start over
        currentProfileIndex = 0;
        Serial.println("[DISCOVERY] Cycle complete, restarting scan");
      }
    }

    delay(10);
  }

  if(!discoveryComplete) {
    Serial.println("\n==========================================");
    Serial.println("DISCOVERY TIMEOUT - No valid response found");
    Serial.println("Defaulting to 250kbps");
    Serial.println("==========================================\n");
    lockedProfile = PROFILE_250K;
    configureProfile(PROFILE_250K);
  }

  profileLocked = true;
}

// ================= SETUP =================

void setup() {
  setupPiUart();
  Serial.begin(115200);
  delay(2000);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  blinkBoot();

  Serial.println("\n==========================================");
  Serial.println("CAN Bus OBD2 Scanner - Auto Discovery");
  Serial.println("==========================================\n");

  pinMode(CS_PIN, OUTPUT);
  digitalWrite(CS_PIN, HIGH);

  SPI.setRX(16);
  SPI.setTX(19);
  SPI.setSCK(18);
  SPI.begin();

  Serial.println("LED Pattern:");
  Serial.println("  Single short blink = Sending request");
  Serial.println("  3 fast blinks = Valid RPM received");
  Serial.println("  2 slow blinks = Switching frequency");
  Serial.println("  1 long blink at boot");
  Serial.println("  2 second solid = Profile locked\n");

  // Run discovery to find correct bitrate
  runDiscovery();

  Serial.println("\n==========================================");
  Serial.print("LOCKED ON: ");
  Serial.println(profileNames[lockedProfile]);
  Serial.print("Bitrate: ");
  Serial.print(profileBitrates[lockedProfile]);
  Serial.println(" bps");
  Serial.println("==========================================\n");
}

// ================= LOOP =================

unsigned long lastSendTime = 0;
unsigned long receiveTimeout = 0;
bool waitingForResponse = false;
const unsigned long SEND_INTERVAL = 5000;
const unsigned long RESPONSE_TIMEOUT = 5000;

void loop() {
  unsigned long currentTime = millis();
  sendPiUartTest();
  // Check for received frames
  uint16_t rxId;
  byte rxData[8];
  byte rxDlc;

  if(receiveCANFrame(&rxId, rxData, &rxDlc)) {
    // Only care about ECU responses (0x7E8 - 0x7EF)
    if((rxId & 0x7F8) == 0x7E8) {

      // Duplicate check
      bool isDuplicate = true;

      if(rxId != lastRxId || rxDlc != lastDlc) {
        isDuplicate = false;
      } else {
        for(int i = 0; i < rxDlc; i++) {
          if(rxData[i] != lastData[i]) {
            isDuplicate = false;
            break;
          }
        }
      }

      // Only print if new or timeout
      if((!isDuplicate || millis() - lastPrintTime > 500) && !(quietAfterLock && hasValidatedComms)) {
        printResponse(rxId, rxData, rxDlc);

        memcpy(lastData, rxData, rxDlc);
        lastRxId = rxId;
        lastDlc = rxDlc;
        lastPrintTime = millis();

        // Valid response clears waiting flag
        if(waitingForResponse &&
           rxDlc >= 5 &&
           rxData[1] == 0x41 &&
           rxData[2] == 0x0C) {
          waitingForResponse = false;
          hasValidatedComms = true;
        }
      }
    }
  }

  // Timeout check
  if(waitingForResponse && (currentTime - receiveTimeout >= RESPONSE_TIMEOUT)) {
    waitingForResponse = false;
  }

  // Send request periodically
  if(!profileLocked) return;

  // Only send until we confirm communication
  if(!hasValidatedComms &&
     !waitingForResponse &&
     (currentTime - lastSendTime >= SEND_INTERVAL)) {

      sendRPMRequest();
      lastSendTime = currentTime;
      receiveTimeout = currentTime;
      waitingForResponse = true;
     }
  delay(10);
}
