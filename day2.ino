#include <SPI.h>

#define CS_PIN 17
#define LED_PIN 0  // GPIO 0 for LED

// ================= ENUM DEFINITION (MUST BE AT TOP) =================
enum CanProfile {
  PROFILE_1,  // 16MHz, 250kbps (most common for OBD2)
  PROFILE_2   // 16MHz, 500kbps (some vehicles use this)
};

const char* profileNames[] = {
  "Profile 1 (16MHz, 250kbps)",
  "Profile 2 (16MHz, 500kbps)"
};

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

void blinkLed(int times, int delayMs) {
  for(int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(delayMs);
    digitalWrite(LED_PIN, LOW);
    if(i < times - 1) delay(delayMs);
  }
}

void blinkSend() {
  // Single blink when sending request
  blinkLed(1, 200);
}

void blinkResponse() {
  // 5 fast blinks when response received
  blinkLed(5, 100);
}

// ================= CONFIGURATION PROFILES =================

bool configureProfile(CanProfile profile) {
  Serial.print("Configuring ");
  Serial.println(profileNames[profile]);
  
  mcpReset();
  delay(10);
  
  // Enter config mode
  mcpBitModify(0x0F, 0xE0, 0x80);
  delay(5);
  
  // Set bitrate based on profile
  if(profile == PROFILE_1) {
    // Profile 1: 16MHz, 250kbps (most OBD2 vehicles)
    mcpWrite(0x28, 0x86);  // CNF1
    mcpWrite(0x29, 0xF0);  // CNF2
    mcpWrite(0x2A, 0x00);  // CNF3
  } 
  else { // PROFILE_2
    // Profile 2: 16MHz, 500kbps (some vehicles)
    mcpWrite(0x28, 0x00);  // CNF1
    mcpWrite(0x29, 0xF0);  // CNF2
    mcpWrite(0x2A, 0x87);  // CNF3
  }
  
  // Configure receive masks and filters to accept ALL messages
  mcpWrite(0x20, 0x00);  // RXB0 SIDH mask - accept all
  mcpWrite(0x21, 0x00);  // RXB0 SIDL mask
  mcpWrite(0x22, 0x00);  // RXB0 EID8 mask
  mcpWrite(0x23, 0x00);  // RXB0 EID0 mask
  
  mcpWrite(0x00, 0x00);  // RXF0 SIDH
  mcpWrite(0x01, 0x00);  // RXF0 SIDL
  mcpWrite(0x04, 0x00);  // RXF1 SIDH
  mcpWrite(0x05, 0x00);  // RXF1 SIDL
  
  mcpWrite(0x24, 0x00);  // RXB1 SIDH mask
  mcpWrite(0x25, 0x00);  // RXB1 SIDL mask
  mcpWrite(0x26, 0x00);  // RXB1 EID8 mask
  mcpWrite(0x27, 0x00);  // RXB1 EID0 mask
  
  mcpWrite(0x08, 0x00);  // RXF2 SIDH
  mcpWrite(0x09, 0x00);  // RXF2 SIDL
  mcpWrite(0x0C, 0x00);  // RXF3 SIDH
  mcpWrite(0x0D, 0x00);  // RXF3 SIDL
  mcpWrite(0x10, 0x00);  // RXF4 SIDH
  mcpWrite(0x11, 0x00);  // RXF4 SIDL
  mcpWrite(0x14, 0x00);  // RXF5 SIDH
  mcpWrite(0x15, 0x00);  // RXF5 SIDL
  
  // Enable rollover and receive interrupts
  mcpBitModify(0x0B, 0x04, 0x04);
  mcpWrite(0x2B, 0x03);  // CANINTE: RX0IE and RX1IE
  
  // Verify configuration
  byte cnf1 = mcpRead(0x28);
  byte cnf2 = mcpRead(0x29);
  byte cnf3 = mcpRead(0x2A);
  
  Serial.print("  CNF1=0x"); Serial.print(cnf1, HEX);
  Serial.print(", CNF2=0x"); Serial.print(cnf2, HEX);
  Serial.print(", CNF3=0x"); Serial.println(cnf3, HEX);
  
  // Enter normal mode
  mcpBitModify(0x0F, 0xE0, 0x00);
  delay(10);
  
  // Check if configuration was successful
  byte canStat = mcpRead(0x0F) & 0xE0;
  if(canStat == 0x00) {
    Serial.println("------ Normal mode active - ready to send/receive\n");
    return true;
  } else {
    Serial.print("-----Failed to enter normal mode (CANSTAT=0x");
    Serial.print(canStat, HEX);
    Serial.println(")\n");
    return false;
  }
}

// ================= TRANSMIT FUNCTION =================

bool sendCANFrame(uint16_t id, byte dlc, byte* data) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x40);  // Write TXB0 SIDH
  
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
  
  // Request to send
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(0x81);
  digitalWrite(CS_PIN, HIGH);
  
  SPI.endTransaction();
  
  // Check transmission status
  delay(2);
  byte txStatus = mcpRead(0x30);
  
  if(txStatus & 0x08) {
    return true;
  } else {
    Serial.print("    TX Error: Status=0x");
    Serial.println(txStatus, HEX);
    return false;
  }
}

// ================= RECEIVE FUNCTION =================

bool receiveCANFrame(uint16_t* rxId, byte* rxData, byte* rxDlc) {
  byte canIntf = mcpRead(0x2C);
  
  if(canIntf & 0x01) {  // RXB0 interrupt
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    digitalWrite(CS_PIN, LOW);
    SPI.transfer(0x90);  // Read RXB0
    byte sidh = SPI.transfer(0x00);
    byte sidl = SPI.transfer(0x00);
    SPI.transfer(0x00);  // Skip EID8
    SPI.transfer(0x00);  // Skip EID0
    byte dlc = SPI.transfer(0x00) & 0x0F;
    
    for(int i = 0; i < dlc && i < 8; i++) {
      rxData[i] = SPI.transfer(0x00);
    }
    digitalWrite(CS_PIN, HIGH);
    SPI.endTransaction();
    
    mcpWrite(0x2C, 0x01);  // Clear interrupt
    
    *rxId = ((uint16_t)sidh << 3) | (sidl >> 5);
    *rxDlc = dlc;
    return true;
  }
  else if(canIntf & 0x02) {  // RXB1 interrupt
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    digitalWrite(CS_PIN, LOW);
    SPI.transfer(0x94);  // Read RXB1
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
    
    mcpWrite(0x2C, 0x02);  // Clear interrupt
    
    *rxId = ((uint16_t)sidh << 3) | (sidl >> 5);
    *rxDlc = dlc;
    return true;
  }
  
  return false;
}

// ================= OBD2 RPM REQUEST =================

void sendRPMRequest(CanProfile profile) {
  byte data[8] = {0x02, 0x01, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00};
  
  Serial.print(profileNames[profile]);
  Serial.print("] Sending RPM request (ID: 0x7DF) -> ");
  for(int i = 0; i < 8; i++) {
    Serial.print("0x");
    if(data[i] < 0x10) Serial.print("0");
    Serial.print(data[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
  
  // Blink LED once when sending
  blinkSend();
  
  if(sendCANFrame(0x7DF, 8, data)) {
    Serial.println("-----Transmission successful (waiting up to 15 seconds for response)");
  } else {
    Serial.println("-----Transmission failed");
    // Blink 3 times slowly for error
    blinkLed(3, 300);
  }
}

// ================= PRINT RECEIVED FRAME =================

void printReceivedFrame(CanProfile profile, uint16_t rxId, byte* rxData, byte rxDlc) {
  // Blink LED 5 times fast when we get ANY response
  blinkResponse();
  
  Serial.print(profileNames[profile]);
  Serial.print("] RECEIVED CAN FRAME!\n");
  
  Serial.print("   CAN ID: 0x");
  Serial.print(rxId, HEX);
  Serial.print(" (");
  
  switch(rxId) {
    case 0x7E8:
      Serial.print("Engine ECU Response");
      break;
    case 0x7E9:
      Serial.print("Transmission ECU Response");
      break;
    case 0x7EA:
      Serial.print("ABS ECU Response");
      break;
    case 0x7DF:
      Serial.print("Echo of our broadcast");
      break;
    default:
      Serial.print("Unknown ECU");
  }
  Serial.println(")");
  
  Serial.print("   DLC: ");
  Serial.println(rxDlc);
  
  Serial.print("   Data: ");
  for(int i = 0; i < rxDlc; i++) {
    Serial.print("0x");
    if(rxData[i] < 0x10) Serial.print("0");
    Serial.print(rxData[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
  
  // Parse OBD2 response
  if(rxId == 0x7E8 && rxDlc >= 3) {
    if(rxData[0] == 0x04 && rxData[1] == 0x41 && rxData[2] == 0x0C && rxDlc >= 5) {
      uint16_t rpm = ((rxData[3] << 8) | rxData[4]) / 4;
      Serial.print("-----------PARSED: Engine RPM = ");
      Serial.print(rpm);
      Serial.println(" RPM");
    }
    else if(rxData[0] == 0x03 && rxData[1] == 0x7F && rxData[2] == 0x01) {
      Serial.println("-----NEGATIVE RESPONSE: Service not supported");
    }
    else if(rxData[1] == 0x41) {
      Serial.print("---- Positive response for PID 0x");
      Serial.print(rxData[2], HEX);
      Serial.print(": ");
      for(int i = 3; i < rxDlc; i++) {
        Serial.print("0x");
        if(rxData[i] < 0x10) Serial.print("0");
        Serial.print(rxData[i], HEX);
        Serial.print(" ");
      }
      Serial.println();
    }
  }
  
  Serial.println();
}

// ================= SETUP =================

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Boot-up signal: 3 slow blinks
  blinkLed(3, 500);
  
  Serial.println("\n==========================================");
  Serial.println("CAN Bus OBD2 Scanner - Jeep Test");
  Serial.println("Testing Profile 1 & Profile 2 alternately");
  Serial.println("==========================================\n");
  
  // Initialize SPI
  pinMode(CS_PIN, OUTPUT);
  digitalWrite(CS_PIN, HIGH);
  
  SPI.setRX(16);
  SPI.setTX(19);
  SPI.setSCK(18);
  SPI.begin();
  
  Serial.println("SPI initialized\n");
  
  // Start with Profile 1 (250kbps - most common for OBD2)
  configureProfile(PROFILE_1);
  
  Serial.println("-------LED indicates:");
  Serial.println("   - Single blink: Sending RPM request");
  Serial.println("   - 5 fast blinks: Received response from ECU");
  Serial.println("   - 3 slow blinks: Error or bootup");
  Serial.println("\nReady! Plug into your Jeep and watch the LED\n");
}

// ================= LOOP WITH PROFILE SWITCHING =================

unsigned long lastProfileSwitch = 0;
unsigned long lastSendTime = 0;
unsigned long receiveTimeout = 0;
bool waitingForResponse = false;
CanProfile currentProfile = PROFILE_1;
int cycleCount = 0;
const unsigned long PROFILE_DURATION = 30000;  // 30 seconds per profile
const unsigned long SEND_INTERVAL = 1000;      // Send every 1 second for quick testing
const unsigned long RESPONSE_TIMEOUT = 5000;   // Wait 5 seconds for response (faster for LED testing)

void loop() {
  unsigned long currentTime = millis();
  
  // Switch profiles every 30 seconds
  if(currentTime - lastProfileSwitch >= PROFILE_DURATION) {
    waitingForResponse = false;  // Reset waiting state
    currentProfile = (currentProfile == PROFILE_1) ? PROFILE_2 : PROFILE_1;
    lastProfileSwitch = currentTime;
    lastSendTime = 0;  // Reset send timer
    
    Serial.println("\n🔄 ========================================");
    Serial.print("🔄 SWITCHING TO ");
    Serial.println(profileNames[currentProfile]);
    Serial.println("🔄 ========================================\n");
    
    // Reconfigure for new profile
    configureProfile(currentProfile);
    
    // Visual indication of profile switch
    blinkLed(2, 200);  // Two quick blinks on profile change
  }
  
  // Check for received frames at any time
  uint16_t rxId;
  byte rxData[8];
  byte rxDlc;
  
  if(receiveCANFrame(&rxId, rxData, &rxDlc)) {
    printReceivedFrame(currentProfile, rxId, rxData, rxDlc);
    
    // If we were waiting for a response, we can note that we got one
    if(waitingForResponse) {
      Serial.println("Response received within timeout!");
      waitingForResponse = false;
    }
  }
  
  // Check if waiting for response has timed out
  if(waitingForResponse && (currentTime - receiveTimeout >= RESPONSE_TIMEOUT)) {
    Serial.println("\nResponse timeout - no response received\n");
    waitingForResponse = false;
  }
  
  // Send RPM request periodically
  if(!waitingForResponse && (currentTime - lastSendTime >= SEND_INTERVAL)) {
    sendRPMRequest(currentProfile);
    lastSendTime = currentTime;
    receiveTimeout = currentTime;  // Start timeout timer
    waitingForResponse = true;
  }
  
  delay(10);  // Small delay to prevent CPU hogging
}
