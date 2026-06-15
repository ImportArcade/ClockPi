from flask import Flask, render_template, request, redirect, url_for
import clock_driver
import startup_shutdown as startshut
import json
import os
import subprocess

app = Flask(__name__)

def is_hotspot():
    try:
        print("Is in hotspot")
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
            capture_output=True, text=True
        )
        print(f"{result.stdout}")
        return "Hotspot:wlan0" in result.stdout
    except Exception:
        return False

@app.route('/hotspot-detect.html')
@app.route('/Library/test/success.html')
def apple_captive_portal():
    return redirect(url_for('wifi_setup'))
@app.route('/generate_204')
def android_captive_portal():
    return '', 204
@app.route('/ncsi.txt')
def captive_portal_trigger():
    return redirect(url_for('wifi_setup'))

@app.before_request
def redirect_to_setup():
    if is_hotspot():
        if request.endpoint and request.endpoint not in ['wifi_setup', 'static']:
            return redirect(url_for('wifi_setup'))

@app.route("/")
def index():
    #Get presets from data.json file
    presets = []
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as file:
                data = json.load(file)

                if isinstance(data, dict):
                    presets = [data]
                elif isinstance(data, list):
                    presets = data
        except json.JSONDecodeError:
            print("Warning: data.json was empty or corrupted.")
            presets = [] 
    return render_template('index.html', presets=presets)

@app.route("/set-time", methods = ["POST"])
def set_time():
    raw_time = request.form.get("clock_input")

    if not raw_time:
        return redirect(url_for('index'))
    
    split_time_array = raw_time.split(":")

    target_hour = int(split_time_array[0])
    target_minute = int(split_time_array[1])

    clock_driver.move_to_time(target_hour, target_minute)

    return redirect(url_for('index'))

@app.route("/create-preset", methods=["POST"])
def create_preset():
    new_preset = request.get_json()
    print(f"Json object received: {new_preset}")
    
    presets_list = []
    
    # 1. Read existing presets if the file exists and has content
    if os.path.exists("data.json") and os.path.getsize("data.json") > 0:
        try:
            with open("data.json", "r", encoding="utf-8") as file:
                presets_list = json.load(file)
                # Ensure it's actually a list we can append to
                if not isinstance(presets_list, list):
                    presets_list = [presets_list]
        except json.JSONDecodeError:
            # If the file was corrupted, reset to an empty list
            presets_list = []

    # 2. Append the incoming new preset to our Python list
    presets_list.append(new_preset)

    # 3. Overwrite the file cleanly with the updated array structure
    with open("data.json", "w", encoding="utf-8") as file:
        json.dump(presets_list, file, indent=4)

    return {"status": "success", "message": "Preset saved locally"}, 200

@app.route("/delete-preset", methods=["POST"])
def delete_preset():
    data = request.get_json()
    # Subtract 1 because Jinja's loop.index starts counting at 1, but Python lists start at 0
    target_index = int(data.get("index")) - 1 
    
    if os.path.exists("data.json") and os.path.getsize("data.json") > 0:
        try:
            with open("data.json", "r", encoding="utf-8") as file:
                presets_list = json.load(file)
            
            # Ensure the index is within the valid range of the array
            if 0 <= target_index < len(presets_list):
                removed_item = presets_list.pop(target_index)
                
                # Save the updated list back to the file
                with open("data.json", "w", encoding="utf-8") as file:
                    json.dump(presets_list, file, indent=4)
                    
                return {
                    "status": "success", 
                    "message": f"Deleted preset '{removed_item.get('preset_name')}'"
                }, 200
            else:
                return {"status": "error", "message": "Preset index out of range"}, 400
                
        except json.JSONDecodeError:
            return {"status": "error", "message": "Failed to read database file"}, 500
            
    return {"status": "error", "message": "No presets found to delete"}, 404

# NUDGE STEP INCREMENT: Adjust this integer to change how far the hands move per click
NUDGE_STEPS = 100
NUDGE_STEPS_PRECISE = 10 

@app.route('/api/nudge', methods=['POST'])
def api_nudge():
    data = request.get_json()
    motor = data.get('hand')
    direction = data.get('direction')
    
    # 1. Stop background time tracking loop so it doesn't interrupt manual adjustment
    clock_driver.stop_live_clock()
    
    # 2. Determine target motor lines
    if motor == 'minute':
        pins = clock_driver.MINUTE_PINS
        is_hour = False
    else:
        pins = clock_driver.HOUR_PINS
        is_hour = True

    # 3. Handle step count direction parameters
    # If stepping backward, we pass it down to your direction assignment engine
    steps = NUDGE_STEPS
    if direction == 'backward':
        # Overriding direction behavior inside step_motor if backward parameter is caught
        steps = -NUDGE_STEPS

    print(f"[Manual Control] Nudging {motor} motor {direction} by {abs(steps)} steps.")
    clock_driver.step_motor(pins, steps, is_hour_motor=is_hour)
    
    return {"status": "success", "motor": motor, "direction": direction}

@app.route('/api/nudge_precise', methods=['POST'])
def api_nudge_precise():
    data = request.get_json()
    motor = data.get('hand')
    direction = data.get('direction')
    steps = int(data.get('steps', NUDGE_STEPS_PRECISE))  # Default to precise step count if not provided

    # 1. Stop background time tracking loop so it doesn't interrupt manual adjustment
    clock_driver.stop_live_clock()

    # 2. Determine target motor lines
    if motor == 'minute':
        pins = clock_driver.MINUTE_PINS
        is_hour = False
    else:
        pins = clock_driver.HOUR_PINS
        is_hour = True

    # 3. Handle step count direction parameters
    if direction == 'backward':
        steps = -steps

    print(f"[Manual Control] Nudging {motor} motor {direction} by {abs(steps)} steps.")
    clock_driver.step_motor(pins, steps, is_hour_motor=is_hour)

    return {"status": "success", "motor": motor, "direction": direction, "steps": steps}

@app.route('/api/set_zero', methods=['POST'])
def api_set_zero():
    # Force reset tracking points to perfect zero coordinates
    clock_driver.reset_tracking_to_zero()
    return {"status": "aligned"}

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    startshut.smooth_shutdown()

@app.route('/wifi-setup/', methods=['GET', 'POST'])
def wifi_setup():
    if request.method == 'GET':
        # Scan for nearby Wi-Fi networks to populate a dropdown
        scan_cmd = ["sudo", "nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"]
        try:
            # Get unique, non-empty SSIDs
            output = subprocess.check_output(scan_cmd, text=True)
            networks = list(set([line.strip() for line in output.split('\n') if line.strip()]))
        except Exception:
            networks = []
            
        # Return a simple HTML setup template
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Clock Wi-Fi Setup</title>
            <style>
                body { font-family: sans-serif; background: #1c1c1e; color: white; padding: 20px; text-align: center; }
                .box { background: #2c2c2e; padding: 25px; border-radius: 16px; max-width: 350px; margin: auto; }
                select, input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: none; box-sizing: border-box; font-size: 16px; }
                input, select { background: #3a3a3c; color: white; }
                button { background: #0a84ff; color: white; font-weight: bold; cursor: pointer; }
            </style>
        </head>
        <body>
            <div class="box">
                <h2>Clock Network Setup</h2>
                <form method="POST">
                    <label>Select Venue Wi-Fi:</label>
                    <select name="ssid">
                        {% for net in networks %}
                            <option value="{{ net }}">{{ net }}</option>
                        {% endfor %}
                    </select>
                    <input type="password" name="password" placeholder="Enter Wi-Fi Password" required>
                    <button type="submit">Connect Clock</button>
                </form>
            </div>
        </body>
        </html>
        '''.replace('{% for net in networks %}', ''.join(f'<option value="{n}">{n}</option>' for n in networks))

    if request.method == 'POST':
        ssid = request.form.get('ssid')
        password = request.form.get('password')
        
        # Trigger a detached background script to execute the switchover 
        # so the web request finishes cleanly before the hotspot drops.
        subprocess.Popen(["sudo", "python3", "/home/colbybarrett/theatre_clock/switch_network.py", ssid, password])
        return "<h1>Connecting...</h1><p>The clock is connecting to the network. This hotspot will close shortly.</p>"
    
@app.route('/system/update', methods=['POST'])
def system_update():
    try:
        # 1. Navigate to the project folder and pull the latest code from GitHub
        project_dir = "/home/colbybarrett/theatre_clock"
        
        # Run git pull and capture the output to see if it succeeds
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        
        # 2. Trigger a delayed reboot (gives Flask 2 seconds to send the response back)
        # 'shutdown -r +1' reboots in 1 minute, but we can use an asynchronous sleep for instant execution
        subprocess.Popen("sleep 2 && sudo reboot", shell=True)
        
        return {
            "status": "success",
            "message": "Update pulled successfully! The clock is rebooting to apply changes. Wait ~30 seconds.",
            "git_output": result.stdout
        }

    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": "Git pull failed. Check repository status or credentials.",
            "error_details": e.stderr
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == '__main__':
    clock_driver.setup()
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=False)
