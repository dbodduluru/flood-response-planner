from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import ollama
import json
import random
import time
import threading
import logging
from twilio.rest import Client
from dotenv import load_dotenv
import os
import re
from queue import Queue

load_dotenv()
app = Flask(__name__)
socketio = SocketIO(app)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")
APPROVER_PHONE = os.getenv("APPROVER_PHONE")
client = Client(TWILIO_SID, TWILIO_TOKEN)

with open('mock_flood_data.txt', 'r') as f:
    MOCK_FLOOD_DATA = f.read()

env_data = {"rainfall": 50, "flood_zone": "None", "road_status": "Clear", "plan": "None", "approved": False}
actions = []
flood_history = ["None"]
plan_id_counter = 0
model_queue = Queue()  # Queue for model responses

def clean_json(text):
    try:
        match = re.search(r'\[\s*(".*?"\s*,?\s*)*\]', text, re.DOTALL)
        return match.group(0) if match else '[]'
    except Exception as e:
        logger.error(f"Error in clean_json: {e}")
        return '[]'

def send_whatsapp_alert(plan):
    global plan_id_counter
    plan_id_counter += 1
    plan_id = plan_id_counter
    message = (f"Flood Alert: Rainfall {env_data['rainfall']}mm, Zone {env_data['flood_zone']}.\n"
               f"Plan: {plan[0]}\nApprove? http://localhost:5000/approve?plan_id={plan_id}")
    logger.debug(f"Attempting WhatsApp: {message}")
    try:
        response = client.messages.create(body=message, from_=TWILIO_WHATSAPP, to=APPROVER_PHONE)
        logger.debug(f"WhatsApp sent, SID: {response.sid}")
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
    return plan_id

def model_worker():
    while True:
        env, prompt_type = model_queue.get()
        try:
            prompt = env["prompt"]
            response = ollama.chat(model="deepseek-r1:7b", messages=[{"role": "user", "content": prompt}])
            result = json.loads(clean_json(response['message']['content'].strip()))
            env[prompt_type] = result or (["Low risk"] if prompt_type == "risks" else ["Monitor conditions"])
            if prompt_type == "risks":
                # Queue draft plan after risks
                plan_prompt = (
                    f"Risks: {json.dumps(result)}, Flood Zone: {env['flood_zone']}, "
                    f"Road Status: {env['road_status']}\n\nGenerate a detailed evacuation plan as JSON list, "
                    f"e.g., ['Evacuate Zone X via Route Y']."
                )
                model_queue.put(({"prompt": plan_prompt, "env": env}, "draft_plan"))
        except Exception as e:
            logger.error(f"Model {prompt_type} failed: {e}")
            env[prompt_type] = ["Low risk"] if prompt_type == "risks" else ["Monitor conditions"]
        model_queue.task_done()

def agent_sensor():
    logger.debug("Sensor thread started")
    zones = ["Zone A", "Zone B", "Zone C", "None"]
    roads = ["Route 1", "Route 2", "Route 3", "Closed"]
    while True:
        env_data["rainfall"] = random.randint(50, 300)
        env_data["flood_zone"] = random.choice(zones[:-1]) if env_data["rainfall"] > 150 else "None"
        env_data["road_status"] = random.choice(roads)
        flood_history.append(env_data["flood_zone"])
        logger.debug(f"New env data: {env_data}")

        risks_prompt = (
            f"Rainfall: {env_data['rainfall']}mm, Flood Zone: {env_data['flood_zone']}, "
            f"Road Status: {env_data['road_status']}\n\nExtract flood risks as JSON list, "
            f"e.g., ['High flood risk in Zone X']."
        )
        model_queue.put(({"prompt": risks_prompt, "env": env_data.copy()}, "risks"))

        risks = env_data.get("risks", ["Pending risks"])
        draft_plan = env_data.get("draft_plan", ["Evacuate " + env_data["flood_zone"]])
        if not env_data["approved"] and env_data["rainfall"] > 150:
            plan_id = send_whatsapp_alert(draft_plan)
            env_data["plan"] = draft_plan
            logger.debug(f"Plan set for approval: {draft_plan}")

        logger.debug(f"Emitting update_data: {env_data}")
        socketio.emit('update_data', {"env": env_data, "risks": risks, "draft_plan": draft_plan})
        time.sleep(5)

# Start threads
threading.Thread(target=model_worker, daemon=True).start()
threading.Thread(target=agent_sensor, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html', initial_data=env_data)

@app.route('/approve')
def approve_plan():
    plan_id = request.args.get('plan_id')
    if plan_id:
        env_data["approved"] = True
        logger.debug(f"Plan {plan_id} approved via link")
        socketio.emit('update_plan', {"plan": env_data["plan"]})
        return "Plan Approved! Return to dashboard."
    return "Invalid plan ID."

@socketio.on('approve_plan')
def handle_approve(data):
    env_data["approved"] = True
    actions.extend(data["draft_plan"])
    logger.debug(f"Plan approved via socket: {data['draft_plan']}")
    socketio.emit('update_plan', {"plan": data["draft_plan"]})

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)