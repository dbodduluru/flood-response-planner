from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import ollama
import json
import random
import time
import threading
import logging
import re

app = Flask(__name__)
socketio = SocketIO(app)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

with open('mock_flood_data.txt', 'r') as f:
    MOCK_FLOOD_DATA = f.read()

env_data = {"rainfall": 50, "flood_zone": "None", "road_status": "Clear", "plan": "None", "approved": False}
actions = []
flood_history = ["None"]

def clean_json(text):
    match = re.search(r'\[\s*(".*?"\s*,?\s*)*\]', text, re.DOTALL)
    return match.group(0) if match else '[]'

def agent_sensor():
    zones = ["Zone A", "Zone B", "Zone C", "None"]
    roads = ["Route 1", "Route 2", "Route 3", "Closed"]
    while True:
        env_data["rainfall"] = random.randint(50, 300)
        env_data["flood_zone"] = random.choice(zones[:-1]) if env_data["rainfall"] > 150 else "None"
        env_data["road_status"] = random.choice(roads)
        flood_history.append(env_data["flood_zone"])
        
        # Generate risks
        prompt = f"Rainfall: {env_data['rainfall']}mm, Flood Zone: {env_data['flood_zone']}, Road Status: {env_data['road_status']}\n\nExtract flood risks as JSON list (e.g., ['High flood risk in Zone A']). If none, return ['Low risk']. Only JSON—no reasoning."
        response = ollama.chat(model="deepseek-r1:7b", messages=[{"role": "user", "content": prompt}])
        raw = response['message']['content'].strip()
        logger.debug(f"Sensor raw: {raw}")
        risks = json.loads(clean_json(raw)) or ["Low risk"]

        # Generate draft plan
        prompt = f"Risks: {json.dumps(risks)}, Flood Zone: {env_data['flood_zone']}, Road Status: {env_data['road_status']}\n\nGenerate draft evacuation plan as JSON list (e.g., ['Evacuate {env_data['flood_zone']} via {env_data['road_status']}']). Return ['Monitor conditions'] if risks are only 'Low risk'. Only JSON—no reasoning."
        response = ollama.chat(model="deepseek-r1:7b", messages=[{"role": "user", "content": prompt}])
        raw = response['message']['content'].strip()
        logger.debug(f"Draft plan raw: {raw}")
        draft_plan = json.loads(clean_json(raw)) or ["Monitor conditions"]

        # Refine if approved
        if env_data["approved"]:
            latest_zone = flood_history[-1]
            prompt = f"Plan: {json.dumps(env_data['plan'])}, Latest Flood Zone: {latest_zone}, Road Status: {env_data['road_status']}\n\nRefine plan based on latest conditions (e.g., ['Reroute {latest_zone} to Route 2']). Only JSON—no reasoning."
            response = ollama.chat(model="deepseek-r1:7b", messages=[{"role": "user", "content": prompt}])
            raw = response['message']['content'].strip()
            logger.debug(f"Refiner raw: {raw}")
            refined = json.loads(clean_json(raw)) or env_data["plan"]
            if refined != env_data["plan"]:
                env_data["plan"] = refined
                env_data["approved"] = False  # Flag for re-approval

        socketio.emit('update_data', {"env": env_data, "risks": risks, "draft_plan": draft_plan})
        time.sleep(5)

def agent_planner(risks):
    prompt = f"Risks: {json.dumps(risks)}, Flood Zone: {env_data['flood_zone']}, Road Status: {env_data['road_status']}\n\nGenerate evacuation plan as JSON list (e.g., ['Evacuate {env_data['flood_zone']} via {env_data['road_status']}']). Only JSON—no reasoning."
    response = ollama.chat(model="deepseek-r1:7b", messages=[{"role": "user", "content": prompt}])
    raw = response['message']['content'].strip()
    logger.debug(f"Planner raw: {raw}")
    return json.loads(clean_json(raw)) or ["Monitor conditions"]

threading.Thread(target=agent_sensor, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html', initial_data=env_data)

@socketio.on('approve_plan')
def handle_approve(data):
    risks = data.get('risks', [])
    draft_plan = data.get('draft_plan', [])
    logger.debug(f"Approve clicked with risks: {risks}, draft: {draft_plan}")
    plan = agent_planner(risks)
    logger.debug(f"Planner generated: {plan}")
    env_data["plan"] = plan
    env_data["approved"] = True
    actions.extend(plan)
    socketio.emit('update_plan', {"plan": plan})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)