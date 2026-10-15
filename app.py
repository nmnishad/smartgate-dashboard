import os
import json
import time
import random
import threading
from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt

app = Flask(__name__)

# Shared global telemetry state
latest_telemetry = {
    "weir": {
        "depth": 0.0,
        "pct": 0,
        "gate": 0,
        "state": "INITIALIZING",
        "last_seen": 0
    },
    "upstream": {
        "temp": 0.0,
        "hum": 0.0,
        "soil": 0,
        "rain": 0.0,
        "runoff": 0.0,
        "last_seen": 0
    }
}

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_WEIR = "smartgate/weir/telemetry"
TOPIC_UPSTREAM = "smartgate/upstream/telemetry"
TOPIC_COMMAND = "smartgate/weir/command"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[MQTT] Successfully connected to HiveMQ broker!")
        client.subscribe(TOPIC_WEIR)
        client.subscribe(TOPIC_UPSTREAM)
        print(f"[MQTT] Subscribed to {TOPIC_WEIR} and {TOPIC_UPSTREAM}")
    else:
        print(f"[MQTT] Connection failed with result code {rc}")

def on_message(client, userdata, msg):
    global latest_telemetry
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic = msg.topic
        current_time = time.time()
        
        if topic == TOPIC_WEIR:
            latest_telemetry["weir"]["depth"] = float(payload.get("depth", 0.0))
            latest_telemetry["weir"]["pct"] = int(payload.get("pct", 0))
            latest_telemetry["weir"]["gate"] = int(payload.get("gate", 0))
            latest_telemetry["weir"]["state"] = str(payload.get("state", "UNKNOWN"))
            latest_telemetry["weir"]["last_seen"] = current_time
            print(f"[RX WEIR] Depth: {latest_telemetry['weir']['depth']}cm | Gate: {latest_telemetry['weir']['gate']} deg")
            
        elif topic == TOPIC_UPSTREAM:
            latest_telemetry["upstream"]["temp"] = float(payload.get("temp", 0.0))
            latest_telemetry["upstream"]["hum"] = float(payload.get("hum", 0.0))
            latest_telemetry["upstream"]["soil"] = int(payload.get("soil", 0))
            latest_telemetry["upstream"]["rain"] = float(payload.get("rain", 0.0))
            latest_telemetry["upstream"]["runoff"] = float(payload.get("runoff", 0.0))
            latest_telemetry["upstream"]["last_seen"] = current_time
            print(f"[RX UPSTREAM] Rain: {latest_telemetry['upstream']['rain']}mm/h | Soil: {latest_telemetry['upstream']['soil']}%")
            
    except Exception as e:
        print(f"[MQTT ERROR] Failed to parse message: {e}")

# Initialize and connect MQTT client at top-level so Gunicorn starts it
client_id = f"SMART_GATE_Flask_Server_{random.randint(1000, 9999)}"
mqtt_client = mqtt.Client(client_id=client_id)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt_loop():
    try:
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[MQTT] Connection exception: {e}")

# Start the background thread immediately upon load
threading.Thread(target=start_mqtt_loop, daemon=True).start()

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    return jsonify(latest_telemetry)

@app.route('/api/override', methods=['POST'])
def post_override():
    data = request.get_json()
    if not data or 'angle' not in data:
        return jsonify({"status": "error", "message": "Missing angle parameter"}), 400
    
    angle = int(data.get('angle', 0))
    mode = data.get('mode', 'MANUAL')
    cmd_payload = json.dumps({"mode": mode, "gate": angle})
    
    mqtt_client.publish(TOPIC_COMMAND, cmd_payload)
    print(f"[TX COMMAND] Published: {cmd_payload} to {TOPIC_COMMAND}")
    return jsonify({"status": "success", "command_sent": cmd_payload})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
