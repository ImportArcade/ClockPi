import clock_driver
import json
import os
import subprocess

def smooth_shutdown():
    print("Initiating theatrical smooth shutdown sequence...")
    
    # 1. Safely park your physical clock hardware at the 12:00 home position first
    try:
        # Assuming True forces a fast-forward/calibration swipe
        clock_driver.move_to_time(12, 0, True) 
        print("Clock face successfully parked at 12:00.")
    except Exception as e:
        print(f"Hardware parking failed, proceeding to hardware safety line: {e}")

    # 2. Trigger the Linux OS shutdown command safely without a password
    try:
        command = ["sudo", "shutdown", "-h", "now"]
        subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"OS Shutdown command failed: {e.stderr}")
    except Exception as e:
        print(f"Unexpected error during system power-off: {e}")

def startup():
    last_time_data = {"Time": "12:00"}
    if os.path.exists("last-time.json") and os.path.getsize("last-time.json") > 0:
        try:
            with open("last-time.json", "r", encoding="utf-8") as file:
                last_time_data = json.load(file)
        except Exception as e:
            print(f"Error reading JSON: {e}")
            
    current_time_str = last_time_data.get("Time", "12:00")
    
    return current_time_str
        

    