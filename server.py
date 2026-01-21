#!/usr/bin/env python3
import json
import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
import os
from common import (
    setup_logger,
    AccessStatus,
    AccessReason,
    API_ENDPOINTS,
    TIMEOUTS,
    TOPIC_RESPONSE,
    TOPIC_REQUEST,
    MQTT_PORT,
    MQTT_KEEPALIVE,
)

logger = setup_logger("SERVER")


class Server:
    def __init__(self):
        # -- MQTT Setup ---
        load_dotenv()
        self.mqtt_broker = os.getenv("MQTT_BROKER")
        self.mqtt_port = MQTT_PORT
        self.mqtt_keepalive = MQTT_KEEPALIVE
        self.topic_request = TOPIC_REQUEST
        self.topic_response = TOPIC_RESPONSE

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # -- Load API URL ---
        self.api_url = os.getenv("API_URL")

        logger.info("Server initialized")

    def get_access_decision(self, payload):
        """
        Sends request to Convex HTTP Action and maps the response to a gate command.
        """
        try:
            # Determine direction string required by API ("in" | "out")
            direction = payload.get("direction", "in")
            gate_id = payload.get("gate_id")

            data = {
                "rfid": str(payload.get("rfid")),
                "gateIdentifier": gate_id,
                "direction": direction,
            }

            logger.info(f"Posting to {API_ENDPOINTS['entry_access']}: {data}")
            try:
                response = requests.post(
                    self.api_url + API_ENDPOINTS["entry_access"],
                    json=data,
                    timeout=TIMEOUTS["api_request"],
                )
                status = response.status_code

                try:
                    resp_json = response.json()
                except json.JSONDecodeError:
                    resp_json = {}

            except requests.exceptions.RequestException as e:
                logger.error(f"Network error: {e}")
                return {
                    "status": AccessStatus.ERROR,
                    "reason": AccessReason.NETWORK_FAIL,
                    "debug": str(e),
                    "gate_id": gate_id,
                }

            if status == 200:
                logger.info(f"Access GRANTED for gate {gate_id}")
                return {
                    "status": AccessStatus.GRANTED,
                    "message": "Access Granted",
                    "gate_id": gate_id,
                }

            error_code = resp_json.get("error", {}).get("code", "UNKNOWN")
            error_msg = resp_json.get("error", {}).get("message", "Unknown error")

            if error_code == "USER_BANNED":
                logger.warning(f"User banned for gate {gate_id}")
                return {
                    "status": AccessStatus.DENIED,
                    "reason": AccessReason.BANNED,
                    "gate_id": gate_id,
                }
            elif error_code in ("USER_ALREADY_IN", "USER_ALREADY_OUT"):
                logger.warning(f"Direction error for gate {gate_id}")
                return {
                    "status": AccessStatus.DENIED,
                    "reason": AccessReason.DIRECTION_ERROR,
                    "gate_id": gate_id,
                }
            elif error_code == "GATE_INACTIVE":
                logger.warning(f"Gate inactive: {gate_id}")
                return {
                    "status": AccessStatus.ERROR,
                    "reason": AccessReason.GATE_LOCKED,
                    "gate_id": gate_id,
                }
            else:
                logger.warning(f"Access DENIED for gate {gate_id}: {error_msg}")
                return {
                    "status": AccessStatus.DENIED,
                    "reason": AccessReason.UNKNOWN,
                    "debug": error_msg,
                    "gate_id": gate_id,
                }

        except Exception as e:
            logger.exception(f"Unexpected logic error: {e}")
            gate_id = payload.get("gate_id") if isinstance(payload, dict) else None
            resp = {"status": AccessStatus.ERROR, "reason": AccessReason.SERVER_ERROR}
            if gate_id:
                resp["gate_id"] = gate_id
            return resp

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"MQTT Connected to broker (Code: {rc})")
        client.subscribe(os.getenv("TOPIC_REQUEST"))
        logger.info(f"Listening on {os.getenv('TOPIC_REQUEST')}")

    def on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
            logger.debug(f"MQTT Received: {payload_str}")

            request_data = json.loads(payload_str)

            # Process logic via API
            decision = self.get_access_decision(request_data)

            # Send response back to the specific gate
            response_payload = json.dumps(decision)
            client.publish(os.getenv("TOPIC_RESPONSE"), response_payload)
            logger.debug(f"MQTT Sent: {response_payload}")

        except json.JSONDecodeError:
            logger.error("MQTT: Invalid JSON received")
        except Exception as e:
            logger.exception(f"MQTT: Unexpected error: {e}")

    def start(self):
        try:
            logger.info(
                f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}"
            )
            self.client.connect(self.mqtt_broker, self.mqtt_port, self.mqtt_keepalive)
            self.client.loop_forever()

            while True:
                pass

        except KeyboardInterrupt:
            logger.info("Stopping server...")
            self.client.disconnect()
        except Exception as e:
            logger.exception(f"Server error: {e}")


if __name__ == "__main__":
    server = Server()
    server.start()
