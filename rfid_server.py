#!/usr/bin/env python3
"""
RFID Server - Standalone RFID card assignment interface
Allows users to assign RFID cards to users via GUI on OLED display
"""

import requests
import time
from dotenv import load_dotenv
import os
import RPi.GPIO as GPIO
import board
import neopixel
from mfrc522 import SimpleMFRC522
from PIL import Image, ImageDraw, ImageFont
import lib.oled.SSD1331 as SSD1331
from common import setup_logger, API_ENDPOINTS, TIMEOUTS, LED_COLORS

from config import buttonGreen, buzzerPin, encoderLeft, encoderRight

logger = setup_logger("RFID_SERVER")


class RFIDServer:
    """Handles RFID card assignment to users"""

    def __init__(self):
        # --- Load Configuration ---
        load_dotenv()
        self.api_url = os.getenv("API_URL")

        if not self.api_url:
            raise ValueError("API_URL not set in .env file")

        # --- Hardware Setup ---
        self._setup_gpio()
        self._setup_oled()
        self._setup_ws2812()
        self.rfid_reader = SimpleMFRC522()

        # --- State Variables ---
        self.running = True
        self.users_list = []
        self.selected_user_index = 0

        logger.info("RFID Server initialized")

    def _setup_gpio(self):
        """Initialize GPIO and buzzer."""
        self.buzzer_pwm = GPIO.PWM(buzzerPin, 1000)
        self.buzzer_pwm.start(0)

    def _setup_oled(self):
        """Initialize OLED display."""
        self.disp = SSD1331.SSD1331()
        self.disp.Init()
        self.disp.clear()
        self.font_large = ImageFont.truetype("./lib/oled/Font.ttf", 20)
        self.font_small = ImageFont.truetype("./lib/oled/Font.ttf", 13)

    def _setup_ws2812(self):
        """Initialize WS2812 NeoPixel strip."""
        self.pixels = neopixel.NeoPixel(board.D18, 8, brightness=0.1, auto_write=False)
        self.set_led_strip((0, 0, 0))

    def set_led_strip(self, color):
        """Sets the entire WS2812 strip to a color (R, G, B)."""
        self.pixels.fill(color)
        self.pixels.show()

    def play_tone(self, tone_type):
        """Plays a melody based on type: 'success', 'error', 'click'."""
        if tone_type == "click":
            self.buzzer_pwm.ChangeDutyCycle(50)
            self.buzzer_pwm.ChangeFrequency(2000)
            time.sleep(0.05)
            self.buzzer_pwm.ChangeDutyCycle(0)
        elif tone_type == "success":
            self.buzzer_pwm.ChangeDutyCycle(50)
            self.buzzer_pwm.ChangeFrequency(1000)
            time.sleep(0.1)
            self.buzzer_pwm.ChangeFrequency(1500)
            time.sleep(0.1)
            self.buzzer_pwm.ChangeFrequency(2000)
            time.sleep(0.2)
            self.buzzer_pwm.ChangeDutyCycle(0)
        elif tone_type == "error":
            self.buzzer_pwm.ChangeDutyCycle(50)
            self.buzzer_pwm.ChangeFrequency(500)
            time.sleep(0.3)
            self.buzzer_pwm.ChangeFrequency(300)
            time.sleep(0.3)
            self.buzzer_pwm.ChangeDutyCycle(0)

    def update_display(self, line1, line2="", color="WHITE"):
        """Draws text on the OLED screen."""
        image = Image.new("RGB", (self.disp.width, self.disp.height), "BLACK")
        draw = ImageDraw.Draw(image)
        draw.text((0, 5), line1, font=self.font_small, fill=color)
        draw.text((0, 30), line2, font=self.font_small, fill=color)
        self.disp.ShowImage(image, 0, 0)

    # --- RFID Assignment Methods ---

    def get_users_without_rfid(self):
        """Fetch list of users without RFID from backend."""
        try:
            logger.debug("Fetching users without RFID...")
            response = requests.get(
                self.api_url + API_ENDPOINTS["users_without_rfid"],
                timeout=TIMEOUTS["api_request"],
            )

            if response.status_code == 200:
                data = response.json()
                self.users_list = data.get("users", [])
                self.selected_user_index = 0
                logger.info(f"Got {len(self.users_list)} users without RFID")
                return True
            else:
                logger.error(f"Failed to fetch users: {response.status_code}")
                self.update_display("Error", "Failed to fetch users", "RED")
                return False
        except Exception as e:
            logger.exception(f"Error fetching users: {e}")
            self.update_display("Error", str(e), "RED")
            return False

    def display_user_list(self):
        """Display the user list with current selection highlighted."""
        if not self.users_list:
            self.update_display("No users", "available", "YELLOW")
            return

        # Display selected user with scroll info
        user = self.users_list[self.selected_user_index]
        name = user.get("name", "Unknown")
        status = user.get("status", "unknown")

        # Show index info
        info = f"{self.selected_user_index + 1}/{len(self.users_list)}"

        self.update_display(f"> {name}", f"{status}  [{info}]", "GREEN")

    def wait_for_encoder_scroll(self, timeout=30):
        """Wait for encoder input to scroll through user list."""
        self.display_user_list()
        self.play_tone("click")
        self.set_led_strip(LED_COLORS["blue"])

        encoder_left_prev = GPIO.input(encoderLeft)
        encoder_right_prev = GPIO.input(encoderRight)

        start_time = time.time()

        while time.time() - start_time < timeout:
            encoder_left_curr = GPIO.input(encoderLeft)
            encoder_right_curr = GPIO.input(encoderRight)

            # Detect falling edge (1 -> 0)
            if encoder_left_prev == 1 and encoder_left_curr == 0:
                self.selected_user_index = (self.selected_user_index - 1) % len(
                    self.users_list
                )
                self.play_tone("click")
                self.display_user_list()

            if encoder_right_prev == 1 and encoder_right_curr == 0:
                self.selected_user_index = (self.selected_user_index + 1) % len(
                    self.users_list
                )
                self.play_tone("click")
                self.display_user_list()

            # Check green button press
            if GPIO.input(buttonGreen) == 0:
                self.play_tone("click")
                time.sleep(0.2)  # Debounce
                return True

            encoder_left_prev = encoder_left_curr
            encoder_right_prev = encoder_right_curr

            time.sleep(0.05)

        # Timeout
        logger.warning("Encoder selection timeout")
        self.update_display("Timeout", "No selection", "YELLOW")
        return False

    def wait_for_rfid_card(self, timeout=10):
        """Wait for RFID card to be placed."""
        self.update_display("Waiting for card...", "Max 10 seconds", "YELLOW")
        self.set_led_strip(LED_COLORS["yellow"])

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                rfid_data = self.rfid_reader.read_no_block()
                if rfid_data[0]:
                    logger.info(f"Card detected: {rfid_data[0]}")
                    return rfid_data[0]
            except Exception as e:
                logger.debug(f"Error reading RFID: {e}")

            time.sleep(0.1)

        # Timeout
        logger.warning("RFID card read timeout")
        self.update_display("Timeout!", "No card found", "RED")
        self.set_led_strip(LED_COLORS["red"])
        self.play_tone("error")
        time.sleep(2)
        return None

    def assign_rfid_to_user(self, rfid_id):
        """Send RFID assignment request to backend."""
        selected_user = self.users_list[self.selected_user_index]
        user_id = selected_user.get("_id")
        user_name = selected_user.get("name")

        try:
            logger.debug(f"Assigning RFID {rfid_id} to user {user_id}")

            payload = {"userId": user_id, "rfid": str(rfid_id)}

            response = requests.post(
                self.api_url + API_ENDPOINTS["assign_rfid"],
                json=payload,
                timeout=TIMEOUTS["api_request"],
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    logger.info(f"Successfully assigned RFID to {user_name}")
                    self.update_display("Success!", f"{user_name} assigned", "GREEN")
                    self.set_led_strip(LED_COLORS["green"])
                    self.play_tone("success")
                    time.sleep(3)
                    return True

            logger.error(f"Failed to assign RFID: {response.status_code}")
            self.update_display("Failed", "Assignment error", "RED")
            self.set_led_strip(LED_COLORS["red"])
            self.play_tone("error")
            time.sleep(2)
            return False
        except Exception as e:
            logger.exception(f"Error assigning RFID: {e}")
            self.update_display("Error", str(e)[:20], "RED")
            self.set_led_strip(LED_COLORS["red"])
            self.play_tone("error")
            time.sleep(2)
            return False

    def run_assignment_flow(self):
        """Execute complete RFID assignment flow once."""
        logger.info("Starting RFID assignment flow")
        self.set_led_strip(LED_COLORS["off"])

        # Step 1: Fetch users without RFID
        if not self.get_users_without_rfid():
            time.sleep(2)
            return

        if not self.users_list:
            self.update_display("No users", "to assign", "YELLOW")
            time.sleep(2)
            return

        # Step 2: Wait for user selection via encoder
        if not self.wait_for_encoder_scroll():
            time.sleep(2)
            return

        # Step 3: Wait for RFID card
        rfid_id = self.wait_for_rfid_card()
        if not rfid_id:
            time.sleep(2)
            return

        # Step 4: Assign RFID to user
        self.assign_rfid_to_user(rfid_id)
        time.sleep(2)

    def start(self):
        """Main loop - wait for green button and trigger assignment."""
        try:
            logger.info("Starting RFID Server...")
            self.set_led_strip(LED_COLORS["off"])
            self.update_display("RFID Assign", "Press green button")

            logger.debug("Ready for button input")

            while self.running:
                # Check for green button press
                if GPIO.input(buttonGreen) == 0:
                    time.sleep(0.2)  # Debounce
                    if GPIO.input(buttonGreen) == 0:  # Confirm still pressed
                        self.run_assignment_flow()
                        self.update_display("RFID Assign", "Press green button")

                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Stopping RFID Server...")
            self.cleanup()
        except Exception as e:
            logger.exception(f"Error: {e}")
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        logger.debug("Cleaning up resources...")
        self.running = False
        self.set_led_strip(LED_COLORS["off"])
        self.disp.clear()
        self.disp.reset()
        self.buzzer_pwm.stop()
        GPIO.cleanup()
        logger.info("Cleanup complete")


if __name__ == "__main__":
    rfid_server = RFIDServer()
    rfid_server.start()
