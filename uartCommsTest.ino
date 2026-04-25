void setupPiUart() {
  Serial2.setTX(4);     // Pico GP4 -> Pi RX
  Serial2.setRX(5);     // Pico GP5 <- Pi TX
  Serial2.begin(115200);

  Serial.println("Pi UART initialized on GP4/GP5");
  Serial2.println("PICO UART READY");
}

void sendPiUartTest() {
  static unsigned long lastSend = 0;
  static unsigned long count = 0;

  if (millis() - lastSend >= 1000) {
    lastSend = millis();

    Serial.print("UART test sent: ");
    Serial.println(count);

    Serial2.print("HELLO_FROM_PICO ");
    Serial2.println(count);

    count++;
  }
}
