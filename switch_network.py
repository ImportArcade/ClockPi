import sys
import os
import time
import subprocess

def connect_to_theatre_wifi(ssid, password):
    print(f"Initiating connection to {ssid}...")
    
    # 1. Pull down the Hotspot connection explicitly
    # This frees up the wlan0 interface from hosting duties
    subprocess.run(["nmcli", "connection", "down", "Hotspot"], check=False)
    
    # Give the wireless driver a brief moment to settle its state
    time.sleep(2)
    
    # 2. Check if a connection profile for this SSID already exists, and clean it up
    subprocess.run(["nmcli", "connection", "delete", ssid], check=False)
    
    # 3. Attempt to connect to the new theater network
    # NetworkManager automatically creates and saves a profile matching the SSID name
    result = subprocess.run(
        ["nmcli", "device", "wifi", "connect", ssid, "password", password],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("Successfully connected to the new network!")
        # Optional: Clean up the Hotspot profile entirely so it doesn't try to auto-resume
        subprocess.run(["nmcli", "connection", "delete", "Hotspot"], check=False)
    else:
        print(f"Connection failed: {result.stderr}")
        # FALLBACK: If the theater connection fails (wrong password, poor signal),
        # run your boot script again to resurrect the setup hotspot so you aren't locked out.
        os.system("sudo bash /home/colbybarrett/theatre_clock/boot_check.sh")

if __name__ == "__main__":
    # Expects SSID and Password passed as command-line arguments from Flask's Popen
    if len(sys.argv) >= 3:
        target_ssid = sys.argv[1]
        target_password = sys.argv[2]
        connect_to_theatre_wifi(target_ssid, target_password)
