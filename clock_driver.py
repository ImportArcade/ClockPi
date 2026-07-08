import RPi.GPIO as GPIO
import time
from datetime import datetime
import threading
import json
import os
import startup_shutdown as startshut

# Pin Configurations (Using BCM numbering)
MINUTE_PINS = [17, 18, 27, 22]
HOUR_PINS   = [23, 24, 25, 26] 

STEP_SEQ = [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1]
]

# Base full-step resolution
STEPS_PER_REV = 2048

# 3D Printed Gear Ratios
MINUTE_GEAR_RATIO = 1.0  
HOUR_GEAR_RATIO   = 1.0  

STEPS_PER_MIN = (STEPS_PER_REV * MINUTE_GEAR_RATIO) / 60   
STEPS_PER_HR  = (STEPS_PER_REV * HOUR_GEAR_RATIO) / 12

# Global tracking variables
current_minute_step = 0.0
current_hour_step = 0.0
minute_step_index = 0
hour_step_index = 0
background_thread = None
stop_ticker = False

minute_residual = 0.0
hour_residual = 0.0

live_tick_enabled = True

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in MINUTE_PINS + HOUR_PINS:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)
    set_time_from_startup()

def step_motor(pins, steps_to_move, is_hour_motor=False):
    global minute_step_index, hour_step_index
    
    if steps_to_move == 0:
        return
        
    abs_steps = abs(int(steps_to_move))
    if steps_to_move < 0:
        direction = 1 if is_hour_motor else -1
    else:
        direction = -1 if is_hour_motor else 1
    current_index = hour_step_index if is_hour_motor else minute_step_index

    for _ in range(abs_steps):
        for pin_idx in range(4):
            GPIO.output(pins[pin_idx], STEP_SEQ[current_index][pin_idx])
        
        if direction == 1:
            current_index = (current_index + 1) % 4
        else:
            current_index = (current_index + 3) % 4
            
        time.sleep(0.003)
    
    if is_hour_motor:
        hour_step_index = current_index
    else:
        minute_step_index = current_index
        
    for pin in pins:
        GPIO.output(pin, 0)

def move_to_time(target_hr, target_min, is_shutdown = False):
    global current_minute_step, current_hour_step

    stop_live_clock()
    TOTAL_MIN_REV_STEPS = int(60 * STEPS_PER_MIN)
    TOTAL_HR_REV_STEPS  = int(12 * STEPS_PER_HR)

    target_min_step = int((target_min % 60) * STEPS_PER_MIN)
    #Calculate position based on minute time
    target_hr_step = int(((target_hr % 12) + target_min / 60) * STEPS_PER_HR)

    min_delta = target_min_step - current_minute_step
    hr_delta = target_hr_step - current_hour_step

    # Modulo keeps the step request strictly positive for our forward clockwise logic loop
    min_delta = min_delta % TOTAL_MIN_REV_STEPS
    hr_delta = hr_delta % TOTAL_HR_REV_STEPS

    print(f"Clockwise Move to {target_hr:02d}:{target_min:02d} -> Min Steps: {min_delta}, Hour Steps: {hr_delta}")

    minute_thread = threading.Thread(
        target=step_motor, 
        args=(MINUTE_PINS, min_delta, False)
    )
    hour_thread = threading.Thread(
        target=step_motor, 
        args=(HOUR_PINS, hr_delta, True)
    )

    # Fire both threads off at the exact same millisecond
    minute_thread.start()
    hour_thread.start()

    # Block the main execution thread until both hands arrive at their targets
    minute_thread.join()
    hour_thread.join()
    
    # Save absolute hand positions
    current_minute_step = target_min_step
    current_hour_step = target_hr_step

    # Clear residuals during explicit time jumps
    global minute_residual, hour_residual
    minute_residual = 0.0
    hour_residual = 0.0
    
    write_last_recorded_time()
    if not is_shutdown and live_tick_enabled:
        start_live_clock()

def tick_one_minute():
    global current_minute_step, current_hour_step

    # 1. Calculate the theoretical exact absolute float position for the next minute
    TOTAL_MIN_REV_STEPS = 60 * STEPS_PER_MIN
    TOTAL_HR_REV_STEPS  = 12 * STEPS_PER_HR

    next_minute_target = (current_minute_step + (STEPS_PER_REV / 60)) % TOTAL_MIN_REV_STEPS
    next_hour_target   = (current_hour_step + (STEPS_PER_REV / 720)) % TOTAL_HR_REV_STEPS

    # 2. The physical steps to take is the difference between where we are 
    # and where we need to be, cast to an integer at the last second
    one_minute_step = int(next_minute_target - current_minute_step)
    hour_step       = int(next_hour_target - current_hour_step)

    # 3. Fire the hardware motors
    if one_minute_step > 0:
        step_motor(MINUTE_PINS, one_minute_step, False)
    if hour_step > 0:
        step_motor(HOUR_PINS, hour_step, True)

    # 4. Save the exact float tracking parameters globally
    current_minute_step = next_minute_target
    current_hour_step   = next_hour_target

    display_tracked_time()
    
def write_last_recorded_time():
    human_time = calc_human_time()

    # 1. Build a native Python dictionary instead of an f-string
    last_time_data = {
        "Time": human_time
    }
    
    # 2. Simplify the file handling. "w" mode will automatically 
    # create the file if it doesn't exist, so you don't need the if/else check!
    try:
        with open("last-time.json", "w", encoding="utf-8") as file:
            json.dump(last_time_data, file, indent=4)
        print(f"Successfully logged timestamp: {human_time}")
    except Exception as e:
        print(f"Error writing to last-time.json: {e}")

def calc_human_time():
    calc_minutes = round(current_minute_step / STEPS_PER_MIN) % 60
    
    calc_hours = int((current_hour_step / STEPS_PER_HR))
    if calc_hours == 0:
        calc_hours = 12

    time_string = f'{calc_hours:02d}:{calc_minutes:02d}'
    return time_string

def display_tracked_time():
    """Helper function to calculate human-readable time from absolute steps."""
    human_time = calc_human_time()
        
    print(f"[Internal Clock Tracking] Current System Time State -> {human_time}")
    write_last_recorded_time()


def live_tick_loop():
    global stop_ticker
    print("Background real-time ticking loop started.")
    
    while not stop_ticker:
        for _ in range(60):
            if stop_ticker:
                break 
            time.sleep(1)
            
        if not stop_ticker:
            tick_one_minute()
            
    for pin in MINUTE_PINS + HOUR_PINS:
        GPIO.output(pin, 0)
    print("Background real-time ticking loop gracefully closed.")

def stop_live_clock():
    """Signor to stop the background thread and waits for it to cleanly finish."""
    global background_thread, stop_ticker
    if background_thread and background_thread.is_alive():
        print("Stopping existing active clock thread...")
        stop_ticker = True
        background_thread.join()  # Pauses script until thread fully shuts down
    background_thread = None

def start_live_clock():
    """Kicks off a brand new background ticking loop thread."""
    global background_thread, stop_ticker
    
    # Clean out any old thread hanging around
    stop_live_clock()
    
    # Arm the switch and spawn the worker
    stop_ticker = False
    background_thread = threading.Thread(target=live_tick_loop, daemon=True)
    background_thread.start()

def set_time_from_startup():
    global current_minute_step, current_hour_step
    
    time_str = startshut.startup() 
    
    try:
        # Example: "06:30" -> hours = 6, minutes = 30
        hours_str, minutes_str = time_str.split(":")
        target_hr = int(hours_str)
        target_min = int(minutes_str)
        
        # 2. Reverse-engineer the human numbers into raw motor steps
        target_min_step = int((target_min % 60) * STEPS_PER_MIN)
        target_hr_step = int(((target_hr % 12) + target_min / 60) * STEPS_PER_HR)
        
        current_minute_step = target_min_step
        current_hour_step = target_hr_step
        
        print(f"[Startup Sync] System successfully synced to positions for {target_hr:02d}:{target_min:02d}")
        print(f"               Min Steps: {current_minute_step}, Hour Steps: {current_hour_step}")
        
    except Exception as e:
        print(f"[Startup Sync Error] Could not parse stored time string '{time_str}': {e}")
        print("               Defaulting internal step tracking to 12:00 alignment.")
        current_minute_step = 0
        current_hour_step = 0

def reset_tracking_to_zero():
    """Forces system to assume current physical orientation is perfect 12:00 alignment."""
    global current_minute_step, current_hour_step
    
    # 1. Kill ticking actions safely
    stop_live_clock()
    
    # 2. Force variables down to literal baseline index values
    current_minute_step = 0
    current_hour_step = 0
    
    # Clear residuals during manual calibration reset
    global minute_residual, hour_residual
    minute_residual = 0.0
    hour_residual = 0.0
    
    # 3. Explicitly overwrite the saved configuration file state
    write_last_recorded_time()
    print("[Calibration] Internal software metrics successfully locked to 12:00 baseline parameters.")
    
    # 4. Turn the live ticking background loop back on automatically
    start_live_clock()



if __name__ == '__main__':
    setup()
    try:
        
        # Keep main main terminal execution alive so background thread can tick
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down clock script.")
    finally:
        stop_live_clock()
        GPIO.cleanup()
