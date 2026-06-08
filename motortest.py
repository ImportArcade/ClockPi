import RPi.GPIO as GPIO
import time

# Define the BCM GPIO pins we wired up
MINUTE_PINS = [17, 18, 27, 22]
HOUR_PINS   = [23, 24, 25, 7]

# Standard 4-step sequence for quick testing
STEP_SEQUENCE = [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1]
]

# Initialize GPIO settings
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for pin in MINUTE_PINS + HOUR_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, 0)

print("Starting dual motor test TEST. Press Ctrl+C to stop.")

try:
    while True:
        # Loop through the 4 steps of the sequence
        for step in STEP_SEQUENCE:
            for i in range(4):
                # Update Minute Motor Pins
                GPIO.output(MINUTE_PINS[i], step[i])
                # Update Hour Motor Pins
                GPIO.output(HOUR_PINS[i], step[i])
            
            # The delay controls the speed (0.002 to 0.005 seconds is ideal)
            time.sleep(0.003)

except KeyboardInterrupt:
    print("\nTest stopped by user.")
finally:
    # Clean up and turn off all pin power safely
    GPIO.cleanup()
    print("GPIO cleared safely.")
