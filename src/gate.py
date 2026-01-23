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

from PIL import Image, ImageDraw, ImageFont
import lib.oled.SSD1331 as SSD1331

from common import (
    setup_logger,
    AccessStatus,
    AccessReason,
    TIMEOUTS,
    LED_COLORS,
    TOPIC_REQUEST,
    TOPIC_RESPONSE,
    MQTT_PORT,
    MQTT_KEEPALIVE,
)

from config import *

logger = setup_logger("GATE")


class AccessGate:
    def __init__(self):
        self.running = True
        self.last_rfid = None
        self.waiting_for_server = False

        # --- Hardware Setup ---
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
        self.mqtt_port = MQTT_PORT
        self.mqtt_keepalive = MQTT_KEEPALIVE
        self.topic_request = TOPIC_REQUEST
        self.topic_response = TOPIC_RESPONSE

    def _setup_oled(self):
        self.disp = SSD1331.SSD1331()
        self.disp.Init()
        self.disp.clear()
        self.font_large = ImageFont.truetype("./lib/oled/Font.ttf", 20)
        self.font_small = ImageFont.truetype("./lib/oled/Font.ttf", 13)

    def _setup_ws2812(self):
        self.pixels = neopixel.NeoPixel(board.D18, 8, brightness=0.1, auto_write=False)
        self.set_led_strip((0, 0, 0))

    # --- Feedback Methods ---

    def set_led_strip(self, color):
        """Sets the entire WS2812 strip to a color (R, G, B)."""
        self.pixels.fill(color)
        self.pixels.show()

    def update_display(self, line1, line2="", color="WHITE"):
        """Draws text on the OLED screen."""
        image = Image.new("RGB", (self.disp.width, self.disp.height), "BLACK")
        draw = ImageDraw.Draw(image)
        draw.text((0, 5), line1, font=self.font_small, fill=color)
        draw.text((0, 30), line2, font=self.font_small, fill=color)
        self.disp.ShowImage(image, 0, 0)

    def show_result_image(self, status, reason=""):
        """Display result image with optional text on OLED screen."""
        try:
            if status == AccessStatus.GRANTED:
                image = Image.open("./usmiechniety_skolim.jpeg")
                text = "Access Granted"
            else:
                image = Image.open("./smutny_skolim.jpg")
                if reason == AccessReason.BANNED:
                    text = "User Banned"
                elif reason == AccessReason.DIRECTION_ERROR:
                    text = "Already In/Out"
                else:
                    text = "Access Denied"

            image = image.resize((self.disp.width, self.disp.height), Image.LANCZOS)

            self.disp.ShowImage(image, 0, 0)

        except Exception as e:
            logger.error(f"Error displaying image: {e}")

            self.update_display(text, reason, "YELLOW")

    def wait_for_direction(self):
        """Waits for Green (IN) or Red (OUT) button press."""
        self.update_display("Select Mode:", "Grn:IN | Red:OUT")

        self.set_led_strip((0, 0, 50))

        while True:
            if GPIO.input(buttonGreen) == 0:
                return "in"
            if GPIO.input(buttonRed) == 0:
                return "out"

            time.sleep(0.05)

    def process_access(self, rfid_id, direction):
        """Sends request to server and handles response."""
        self.waiting_for_server = True
        self.update_display("Verifying...", "Please wait")
        self.set_led_strip(LED_COLORS["yellow"])

        payload = {"rfid": rfid_id, "gate_id": self.gate_id, "direction": direction}
        self.mqtt_client.publish(self.topic_request, json.dumps(payload))

        timeout = 0
        while self.waiting_for_server and timeout < TIMEOUTS["mqtt_response"] * 10:
            time.sleep(0.1)
            timeout += 1

        if self.waiting_for_server:
            logger.warning(f"MQTT response timeout for RFID {rfid_id}")
            self.handle_result(AccessStatus.ERROR, AccessReason.NETWORK_FAIL)

    def handle_result(self, status, reason=""):
        """Visual and audio feedback based on server decision."""
        logger.info(f"Result: {status} ({reason})")

        if status == AccessStatus.GRANTED:
            self.show_result_image(status)
            self.set_led_strip(LED_COLORS["green"])
        else:
            self.show_result_image("DENIED", reason)
            self.set_led_strip((255, 0, 0))
            time.sleep(2)

            if reason == "BANNED":
                msg = "USER BANNED"
            elif reason == "DIRECTION_ERROR":
                msg = "ALREADY IN/OUT"
            else:
                msg = "ACCESS DENIED"

            self.update_display(msg, reason)
            time.sleep(3)

        self.waiting_for_server = False

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        logger.info(f"MQTT Connected with code {rc}")
        client.subscribe(self.topic_response)

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            resp_gate = payload.get("gate_id")
            if resp_gate is None:
                logger.warning("Response without gate_id received")
                return
            if resp_gate != self.gate_id:
                logger.debug(f"Ignored message for gate {resp_gate}")
                return

            if self.waiting_for_server:
                status = payload.get("status")
                reason = payload.get("reason", "")
                self.handle_result(status, reason)
        except Exception as e:
            logger.exception(f"Error processing MQTT message: {e}")

    def start(self):
        try:
            self.mqtt_client.connect(
                self.mqtt_broker, self.mqtt_port, self.mqtt_keepalive
            )
            self.mqtt_client.loop_start()

            logger.info("System Ready.")

            while self.running:
                self.update_display("Gate Ready", "Place Card...")
                self.set_led_strip(LED_COLORS["off"])

                try:
                    rfid_id = self.rfid_reader.read_no_block()[0]

                    if rfid_id:
                        logger.info(f"Card Detected: {rfid_id}")

                        direction = self.wait_for_direction()
                        logger.debug(f"Direction: {direction}")

                        self.process_access(rfid_id, direction)

                        time.sleep(1)

                except Exception as e:
                    logger.exception(f"Unexpected Error: {e}")

                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Exiting...")
            self.cleanup()
        finally:
            self.cleanup()

    def cleanup(self):
        logger.debug("Cleaning up resources...")
        self.set_led_strip(LED_COLORS["off"])
        self.disp.clear()
        self.disp.reset()
        GPIO.cleanup()
        self.mqtt_client.loop_stop()
        logger.info("Cleanup complete")


if __name__ == "__main__":
    gate = AccessGate()
    gate.start()
