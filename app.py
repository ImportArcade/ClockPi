from flask import Flask, render_template, request, redirect, url_for, jsonify
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
            presets = [] 
            
    # Force the browser to bypass local storage and request clean data every single time
    response = app.make_response(render_template('index.html', presets=presets))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/api/set_time", methods=["POST"])
def set_time():
    data = request.get_json()
    if not data:
        return {"status": "error", "message": "Missing JSON payload"}, 400
        
    raw_time = data.get("time")  # Captures the browser's "HH:MM" string
    if not raw_time:
        return {"status": "error", "message": "Missing time parameter"}, 400
    
    try:
        split_time_array = raw_time.split(":")
        browser_hour = int(split_time_array[0])
        target_minute = int(split_time_array[1])

        # --- Convert 24-hour input down to a pure 12-hour mechanical coordinate ---
        # If hour is 0 (12:00 AM) or 12 (12:00 PM), target_hour becomes 12.
        # If hour is 13 through 23 (1:00 PM - 11:00 PM), it maps cleanly to 1 through 11.
        target_hour = browser_hour % 12
        if target_hour == 0:
            target_hour = 12

        print(f"[Analog Conversion] Browser time '{browser_hour:02d}:{target_minute:02d}' translated to physical hands -> {target_hour}:{target_minute:02d}")
        
        clock_driver.move_to_time(target_hour, target_minute)

        return {"status": "success", "message": f"Clock updating to {target_hour}:{target_minute:02d}"}, 200
        
    except (ValueError, IndexError) as e:
        return {"status": "error", "message": f"Malformed time data configuration: {str(e)}"}, 400

@app.route("/create-preset", methods=["POST"])
def create_preset():
    new_preset = request.get_json()
    print(f"Json object received: {new_preset}")
    
    # Extract structural components safely
    preset_name = new_preset.get('preset_name', '').strip()
    preset_time = new_preset.get('preset_time', '').strip()
    preset_notes = new_preset.get('preset_notes', '').strip()[:100] # Force maximum boundary logic
    target_idx = new_preset.get('index') # Check if an edit operation triggered this call
    
    presets_list = []
    
    # 1. Read existing presets if the file exists and has content
    if os.path.exists("data.json") and os.path.getsize("data.json") > 0:
        try:
            with open("data.json", "r", encoding="utf-8") as file:
                presets_list = json.load(file)
                if not isinstance(presets_list, list):
                    presets_list = [presets_list]
        except json.JSONDecodeError:
            presets_list = []

    # Pack clear key values into the JSON payload dictionary
    preset_entry = {
        "preset_name": preset_name,
        "preset_time": preset_time,
        "preset_notes": preset_notes
    }

    # 2. Check if this is an Edit operation (index exists) or a New creation request
    if target_idx is not None:
        try:
            # Shift back to zero-index pointer mechanics matching Jinja loops
            py_idx = int(target_idx) - 1
            if 0 <= py_idx < len(presets_list):
                presets_list[py_idx] = preset_entry
            else:
                presets_list.append(preset_entry)
        except (ValueError, TypeError):
            presets_list.append(preset_entry)
    else:
        # Append the new structure down onto the end of the data list array
        presets_list.append(preset_entry)

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
    steps = NUDGE_STEPS
    if direction == 'backward':
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
        scan_cmd = ["sudo", "nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"]
        try:
            output = subprocess.check_output(scan_cmd, text=True)
            networks = list(set([line.strip() for line in output.split('\n') if line.strip()]))
        except Exception:
            networks = []
            
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
        
        subprocess.Popen(["sudo", "python3", "/home/colbybarrett/theatre_clock/switch_network.py", ssid, password])
        return "<h1>Connecting...</h1><p>The clock is connecting to the network. This hotspot will close shortly.</p>"
    
@app.route('/system/update', methods=['POST'])
def system_update():
    try:
        project_dir = "/home/colbybarrett/theatre_clock"
        result = subprocess.run(
            ["git", "pull"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
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
    
@app.route('/api/toggle_live_tick', methods=['POST'])
def api_toggle_live_tick():
    data = request.get_json()
    # Expects a payload like: {"enabled": true} or {"enabled": false}
    is_enabled = bool(data.get('enabled', True))
    
    # Update the driver state
    clock_driver.live_tick_enabled = is_enabled
    
    if is_enabled:
        print("[System Control] Live ticking globally enabled.")
        # If the clock is currently sitting still, wake it up immediately
        if not clock_driver.background_thread or not clock_driver.background_thread.is_alive():
            clock_driver.start_live_clock()
        return {"status": "success", "live_tick": "enabled"}, 200
    else:
        print("[System Control] Live ticking globally disabled.")
        # Hard stop the ticking loop right now
        clock_driver.stop_live_clock()
        return {"status": "success", "live_tick": "disabled"}, 200
    
@app.route("/api/rearrange-presets", methods=["POST"])
def rearrange_presets():
    data = request.get_json()
    new_order_strings = data.get("order", []) # Expects list of strings matching data-id values, like ['2', '1', '3']
    
    if not os.path.exists("data.json") or os.path.getsize("data.json") == 0:
        return {"status": "error", "message": "No data found to rearrange"}, 400

    try:
        with open("data.json", "r", encoding="utf-8") as file:
            presets_list = json.load(file)
            
        # Re-sort the python dictionary elements based on the mapped front-end sequence array
        rearranged_list = []
        for str_idx in new_order_strings:
            py_idx = int(str_idx) - 1 # Translate 1-indexed string loop IDs to 0-indexed integer points
            if 0 <= py_idx < len(presets_list):
                rearranged_list.append(presets_list[py_idx])
                
        # Handle safety fallback for unmatched items
        if len(rearranged_list) == 0:
            return {"status": "error", "message": "Reordering structural mismatch"}, 400

        # Save the updated layout array list structure directly back to disk
        with open("data.json", "w", encoding="utf-8") as file:
            json.dump(rearranged_list, file, indent=4)

        return {"status": "success", "message": "Preset sequencing saved locally"}, 200

    except Exception as e:
        return {"status": "error", "message": f"Failed to rewrite sequence file: {str(e)}"}, 500

if __name__ == '__main__':
    clock_driver.setup()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=False)