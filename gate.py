#!/usr/bin/env python3
import time
import json
import RPi.GPIO as GPIO
import board
import neopixel
from mfrc522 import SimpleMFRC522
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

# OLED Imports
from PIL import Image, ImageDraw, ImageFont
import lib.oled.SSD1331 as SSD1331

# Hardware Config
from config import *

class AccessGate:
    def __init__(self):
        self.running = True
        self.last_rfid = None
        self.waiting_for_server = False
        
        # --- Hardware Setup ---
        self._setup_gpio()
        self._setup_oled()
        self._setup_ws2812()
        self.rfid_reader = SimpleMFRC522()
        
        # --- MQTT Setup ---
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        load_dotenv()
        self.gate_id = os.getenv("GATE_ID")
        self.mqtt_broker = os.getenv("MQTT_BROKER")
        self.topic_request = os.getenv("TOPIC_REQUEST")
        self.topic_response = os.getenv("TOPIC_RESPONSE")

    def _setup_gpio(self):
        self.buzzer_pwm = GPIO.PWM(buzzerPin, 1000) # Initial 1kHz

    def _setup_oled(self):
        self.disp = SSD1331.SSD1331()
        self.disp.Init()
        self.disp.clear()
        self.font_large = ImageFont.truetype('./lib/oled/Font.ttf', 20)
        self.font_small = ImageFont.truetype('./lib/oled/Font.ttf', 13)

    def _setup_ws2812(self):
        # Initialize NeoPixels on GPIO 18
        self.pixels = neopixel.NeoPixel(board.D18, 8, brightness=0.1, auto_write=False)
        self.set_led_strip((0, 0, 0)) # Off

    # --- Feedback Methods ---
    
    def set_led_strip(self, color):
        """Sets the entire WS2812 strip to a color (R, G, B)."""
        self.pixels.fill(color)
        self.pixels.show()

    def play_tone(self, tone_type):
        """Plays a melody based on type: 'success', 'error', 'click'."""
        if tone_type == "click":
            self.buzzer_pwm.start(50)
            self.buzzer_pwm.ChangeFrequency(2000)
            time.sleep(0.05)
            self.buzzer_pwm.stop()
        elif tone_type == "success":
            self.buzzer_pwm.start(50)
            self.buzzer_pwm.ChangeFrequency(1000)
            time.sleep(0.1)
            self.buzzer_pwm.ChangeFrequency(1500)
            time.sleep(0.1)
            self.buzzer_pwm.ChangeFrequency(2000)
            time.sleep(0.2)
            self.buzzer_pwm.stop()
        elif tone_type == "error":
            self.buzzer_pwm.start(50)
            self.buzzer_pwm.ChangeFrequency(500)
            time.sleep(0.3)
            self.buzzer_pwm.ChangeFrequency(300)
            time.sleep(0.3)
            self.buzzer_pwm.stop()

    def update_display(self, line1, line2="", color="WHITE"):
        """Draws text on the OLED screen."""
        image = Image.new("RGB", (self.disp.width, self.disp.height), "BLACK")
        draw = ImageDraw.Draw(image)
        draw.text((0, 5), line1, font=self.font_small, fill=color)
        draw.text((0, 30), line2, font=self.font_small, fill=color)
        self.disp.ShowImage(image, 0, 0)

    # --- Core Logic ---
    def wait_for_direction(self):
        """Waits for Green (IN) or Red (OUT) button press."""
        self.update_display("Select Mode:", "Grn:IN | Red:OUT")
        self.play_tone("click")
        
        # Blue indication on LEDs
        self.set_led_strip((0, 0, 50)) 

        while True:
            if GPIO.input(buttonGreen) == 0: # Pressed (Low)
                self.play_tone("click")
                return "in"
            if GPIO.input(buttonRed) == 0: # Pressed (Low)
                self.play_tone("click")
                return "out"
            
            time.sleep(0.05)

    def process_access(self, rfid_id, direction):
        """Sends request to server and handles response."""
        self.waiting_for_server = True
        self.update_display("Verifying...", "Please wait")
        self.set_led_strip((50, 50, 0)) # Yellow wait

        payload = {
            "rfid": rfid_id,
            "gate_id": self.gate_id,
            "direction": direction
        }
        self.mqtt_client.publish(self.topic_request, json.dumps(payload))

        # Wait for response (handled in _on_mqtt_message)
        timeout = 0
        while self.waiting_for_server and timeout < 50: # 5 seconds timeout
            time.sleep(0.1)
            timeout += 1
        
        if self.waiting_for_server:
            # Timeout happened
            self.handle_result("ERROR", "Timeout")

    def handle_result(self, status, reason=""):
        """Visual and audio feedback based on server decision."""
        print(f"[LOGIC] Result: {status} ({reason})")
        
        if status == "GRANTED":
            self.update_display("ACCESS GRANTED", "Welcome!")
            self.set_led_strip((0, 255, 0)) # Green
            self.play_tone("success")
        else:
            # Error or Denied
            if reason == "BANNED":
                msg = "USER BANNED"
            elif reason == "DIRECTION_ERROR":
                msg = "ALREADY IN/OUT"
            else:
                msg = "ACCESS DENIED"
            
            self.update_display(msg, reason)
            self.set_led_strip((255, 0, 0)) # Red
            self.play_tone("error")

        time.sleep(3) # Show result for 3 seconds
        self.waiting_for_server = False

    # --- MQTT Callbacks ---

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected with code {rc}")
        client.subscribe(self.topic_response)

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if self.waiting_for_server:
                self.handle_result(payload.get("status"), payload.get("reason", ""))
        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")

    # --- Main Loop ---

    def start(self):
        try:
            self.mqtt_client.connect(self.mqtt_broker, 1883, 60)
            self.mqtt_client.loop_start() # Run MQTT in background thread

            print("[GATE] System Ready.")
            
            while self.running:
                # 1. Idle State
                self.update_display("Gate Ready", "Place Card...")
                self.set_led_strip((0, 0, 0)) # Off or faint white
                
                # 2. Read RFID
                try:
                    rfid_id = self.rfid_reader.read_no_block()[0]

                    if rfid_id:
                        print(f"[GATE] Card Detected: {rfid_id}")
                        
                        # 3. Select Direction
                        direction = self.wait_for_direction()
                        print(f"[GATE] Direction: {direction}")
                        
                        # 4. Verify Access
                        self.process_access(rfid_id, direction)
                        
                        # Prevent immediate re-read
                        time.sleep(1)

                except Exception as e:
                    print(f"[GATE] Unexpected Error: {e}")

                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.cleanup()

    def cleanup(self):
        self.set_led_strip((0, 0, 0))
        self.disp.clear()
        self.disp.reset()
        self.buzzer_pwm.stop()
        GPIO.cleanup()
        self.mqtt_client.loop_stop()

if __name__ == "__main__":
    gate = AccessGate()
    gate.start()