#!/usr/bin/env python3
import json
import paho.mqtt.client as mqtt
import requests
import time
from dotenv import load_dotenv
import os

ENDPOINT_ENTRY = "/entry-access"

class Server:

    def __init__(self):
        #-- MQTT Setup ---
        load_dotenv()
        self.mqtt_broker = os.getenv("MQTT_BROKER")
        self.topic_request = os.getenv("TOPIC_REQUEST")
        self.topic_response = os.getenv("TOPIC_RESPONSE")

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        #-- Load API URL ---
        self.api_url = os.getenv("API_URL")

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
                "direction": direction
            }

            print(f"[API] Posting to {ENDPOINT_ENTRY}: {data}")
            try:
                response = requests.post(self.api_url + ENDPOINT_ENTRY, json=data, timeout=5)
                status = response.status_code
                
                try:
                    resp_json = response.json()
                except json.JSONDecodeError:
                    resp_json = {}
                    
            except requests.exceptions.RequestException as e:
                print(f"[API] Network error: {e}")
                return {"status": "ERROR", "reason": "NETWORK_FAIL", "debug": str(e), "gate_id": gate_id}

            if status == 200:
                return {"status": "GRANTED", "message": "Access Granted", "gate_id": gate_id}
            
            error_code = resp_json.get("error", {}).get("code", "UNKNOWN")
            error_msg = resp_json.get("error", {}).get("message", "Unknown error")

            if error_code == "USER_BANNED":
                return {"status": "DENIED", "reason": "BANNED", "gate_id": gate_id}
            elif error_code in ("USER_ALREADY_IN", "USER_ALREADY_OUT"):
                return {"status": "DENIED", "reason": "DIRECTION_ERROR", "gate_id": gate_id}
            elif error_code == "GATE_INACTIVE":
                return {"status": "ERROR", "reason": "GATE_LOCKED", "gate_id": gate_id}
            else:
                return {"status": "DENIED", "reason": "UNKNOWN", "debug": error_msg, "gate_id": gate_id}

        except Exception as e:
            print(f"[API] Unexpected Logic Error: {e}")
            # Include gate_id if present in payload
            gate_id = payload.get("gate_id") if isinstance(payload, dict) else None
            resp = {"status": "ERROR", "reason": "SERVER_ERROR"}
            if gate_id:
                resp["gate_id"] = gate_id
            return resp

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected to broker (Code: {rc})")
        client.subscribe(os.getenv("TOPIC_REQUEST"))
        print(f"[MQTT] Listening on request...")

    def on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
            print(f"[MQTT] Received: {payload_str}")
            
            request_data = json.loads(payload_str)
            
            # Process logic via API
            decision = self.get_access_decision(request_data)
            
            # Send response back to the specific gate
            response_payload = json.dumps(decision)
            client.publish(os.getenv("TOPIC_RESPONSE"), response_payload)
            print(f"[MQTT] Sent: {response_payload}")

        except json.JSONDecodeError:
            print("[MQTT] Error: Invalid JSON received")
        except Exception as e:
            print(f"[MQTT] Unexpected error: {e}")

    def start(self):
        try:
            self.client.connect(self.mqtt_broker, 1883, 60)
            self.client.loop_forever()

            while True:
                pass

        except KeyboardInterrupt:
            print("\nStopping server...")
            self.client.disconnect()

if __name__ == "__main__":
    server = Server()
    server.start()