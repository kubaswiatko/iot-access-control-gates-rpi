#!/usr/bin/env python3
"""
Common utilities for all server scripts
Includes: logging configuration, enums, constants
"""

import logging
from strenum import StrEnum

# --- Logging Configuration ---


def setup_logger(name: str) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)

    # Only add handlers if not already configured
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # Formatter with timestamp and level
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.setLevel(logging.DEBUG)

    return logger


# --- Status Enums ---


class AccessStatus(StrEnum):
    """Access decision status"""

    GRANTED = "GRANTED"
    DENIED = "DENIED"
    ERROR = "ERROR"


class AccessReason(StrEnum):
    """Reasons for access decisions"""

    BANNED = "BANNED"
    DIRECTION_ERROR = "DIRECTION_ERROR"
    GATE_LOCKED = "GATE_LOCKED"
    NETWORK_FAIL = "NETWORK_FAIL"
    SERVER_ERROR = "SERVER_ERROR"
    UNKNOWN = "UNKNOWN"


class RFIDAssignmentStatus(StrEnum):
    """RFID assignment status"""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


# --- Constants ---

API_ENDPOINTS = {
    "entry_access": "/entry-access",
    "users_without_rfid": "/users/without-rfid",
    "assign_rfid": "/users/assign-rfid",
}

TIMEOUTS = {
    "api_request": 10,
    "rfid_card": 10,
    "encoder_selection": 30,
    "mqtt_response": 15,
}

LED_COLORS = {
    "off": (0, 0, 0),
    "blue": (0, 0, 50),
    "yellow": (50, 50, 0),
    "green": (0, 255, 0),
    "red": (255, 0, 0),
}

# Parameters used in MQTT configuration
TOPIC_REQUEST = "gate/request"
TOPIC_RESPONSE = "gate/response"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
