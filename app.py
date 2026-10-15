"""
IoT-Enabled Automated Flood Gate and Sluice Spillway Control System (SMART-GATE)
Central Municipal Supervisory Web Dashboard
Author: Nishad Mohamed (LMU ID: 25024582)
Module: CS7080NM Cloud Computing and the Internet of Things
"""

import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# --- IN-MEMORY TELEMETRY STORAGE ---
latest_data = {
    "weir": {
        "depth": 35.0,
        "pct": 17,
        "gate": 0,
        "state": "NORMAL [SAFE]",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    },
    "upstream": {
        "temp": 28.5,
        "hum": 76.0,
        "soil": 35,
        "rain": 4.0,
        "runoff": 22.4,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    },
    "system": {
        "mqtt_connected": False,
        "override_active": False,
        "override_gate": 0
    }
}

history_log = []
MAX_HISTORY = 30

# --- MQTT CLIENT SETUP ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_WEIR = "smartgate/weir/telemetry"
TOPIC_UPSTREAM = "smartgate/upstream/telemetry"
TOPIC_CONTROL = "smartgate/weir/control"

mqtt_client = None

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback triggered when MQTT client establishes connection to broker."""
    rc_code = rc if isinstance(rc, int) else getattr(rc, 'value', 0)
    if rc_code == 0:
        print("[MQTT] Connected successfully to HiveMQ broker!")
        latest_data["system"]["mqtt_connected"] = True
        client.subscribe(TOPIC_WEIR)
        client.subscribe(TOPIC_UPSTREAM)
        print(f"[MQTT] Subscribed to {TOPIC_WEIR} and {TOPIC_UPSTREAM}")
    else:
        print(f"[MQTT] Connection failed with code {rc_code}")
        latest_data["system"]["mqtt_connected"] = False

def on_message(client, userdata, msg):
    """Callback executed when telemetry arrives from ESP32 nodes."""
    try:
        payload_str = msg.payload.decode('utf-8')
        payload = json.loads(payload_str)
        now_str = datetime.now().strftime("%H:%M:%S")

        if msg.topic == TOPIC_WEIR:
            latest_data["weir"]["depth"] = float(payload.get("depth", 0.0))
            latest_data["weir"]["pct"] = int(payload.get("pct", 0))
            latest_data["weir"]["gate"] = int(payload.get("gate", 0))
            latest_data["weir"]["state"] = payload.get("state", "NORMAL [SAFE]")
            latest_data["weir"]["timestamp"] = now_str

        elif msg.topic == TOPIC_UPSTREAM:
            latest_data["upstream"]["temp"] = float(payload.get("temp", 28.0))
            latest_data["upstream"]["hum"] = float(payload.get("hum", 75.0))
            latest_data["upstream"]["soil"] = int(payload.get("soil", 0))
            latest_data["upstream"]["rain"] = float(payload.get("rain", 0.0))
            latest_data["upstream"]["runoff"] = float(payload.get("runoff", 0.0))
            latest_data["upstream"]["timestamp"] = now_str

        # Append snapshot to circular time-series log for Chart.js
        snapshot = {
            "time": now_str,
            "depth": latest_data["weir"]["depth"],
            "pct": latest_data["weir"]["pct"],
            "gate": latest_data["weir"]["gate"],
            "rain": latest_data["upstream"]["rain"],
            "soil": latest_data["upstream"]["soil"],
            "runoff": latest_data["upstream"]["runoff"]
        }
        history_log.append(snapshot)
        if len(history_log) > MAX_HISTORY:
            history_log.pop(0)

    except Exception as e:
        print(f"[MQTT ERROR] Failed to parse message: {e}")

def start_mqtt():
    """Initializes Paho-MQTT client with compatibility for v1 and v2 libraries."""
    global mqtt_client
    try:
        import paho.mqtt.client as paho_mqtt

        client_kwargs = {"client_id": "SMART_GATE_Flask_Dashboard"}
        if hasattr(paho_mqtt, 'CallbackAPIVersion'):
            # paho-mqtt v2.0+ support
            mqtt_client = paho_mqtt.Client(
                paho_mqtt.CallbackAPIVersion.VERSION1,
                **client_kwargs
            )
        else:
            # paho-mqtt v1.x fallback
            mqtt_client = paho_mqtt.Client(**client_kwargs)

        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as ex:
        print(f"[MQTT WARNING] Paho-MQTT network error ({ex}). Continuing in local standalone mode.")

# Start MQTT daemon thread
mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
mqtt_thread.start()

# --- FLASK ROUTES ---
@app.route('/')
def index():
    """Renders the central SCADA dashboard interface."""
    return render_template('index.html')

@app.route('/api/telemetry/latest', methods=['GET'])
def get_latest_telemetry():
    """Provides current telemetry snapshot for web polling."""
    return jsonify(latest_data)

@app.route('/api/telemetry/history', methods=['GET'])
def get_history():
    """Provides historical time-series data for Chart.js rendering."""
    return jsonify(history_log)

@app.route('/api/gate/override', methods=['POST'])
def gate_override():
    """Handles municipal supervisory remote gate positioning commands."""
    data = request.json or {}
    enable_override = bool(data.get('override', False))
    target_angle = int(data.get('angle', 0))

    latest_data["system"]["override_active"] = enable_override
    latest_data["system"]["override_gate"] = target_angle

    if enable_override:
        latest_data["weir"]["gate"] = target_angle
        if mqtt_client and latest_data["system"]["mqtt_connected"]:
            ctrl_payload = json.dumps({"command": "SET_GATE", "angle": target_angle})
            mqtt_client.publish(TOPIC_CONTROL, ctrl_payload)
            print(f"[CONTROL] Published override command: {ctrl_payload}")

    return jsonify({
        "status": "success",
        "override_active": enable_override,
        "gate_angle": target_angle
    })

if __name__ == '__main__':
    print("\n=======================================================")
    print(" SMART-GATE Municipal Supervisory Web Dashboard ")
    print(" CS7080NM Assessment 2 - MSc Artificial Intelligence")
    print(" Access Web Portal at: http://127.0.0.1:5000")
    print("=======================================================\n")
    app.run(host='0.0.0.0', port=5000, debug=True)