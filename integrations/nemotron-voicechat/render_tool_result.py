#!/usr/bin/env python3
"""Example of preserving tool facts while producing ASCII/TTS-friendly text."""

from __future__ import annotations

import json
import sys

from voicemd.ascii import to_ascii


def render_weather(payload: dict) -> str:
    temperature = payload["temperature_c"]
    condition = str(payload["condition"]).replace("_", " ")
    return to_ascii(f"The temperature is {temperature} degrees Celsius. Conditions are {condition}.")


if __name__ == "__main__":
    data = json.load(sys.stdin)
    print(render_weather(data))
