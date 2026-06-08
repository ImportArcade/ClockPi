#!/bin/bash

sleep 25

if ! hostname -I | grep -q '[0-9]'; then
    echo "No network connection deteted. Launching setup hotspot..."
    sudo nmcli connection down Hotspot 2>dev/null
    sudo nmcli connection delete Hotspot 2>/dev/null
    sudo pkill dnsmasq 2>/dev/null

      sudo nmcli connection add type wifi ifname wlan0 con-name Hotspot autoconnect no ssid Theatre-Clock-Setup mode ap
      sudo nmcli connection modify Hotspot ipv4.method shared ipv4.addresses 10.42.0.1/24
      sudo nmcli connection modify Hotspot wifi-sec.key-mgmt wpa-psk
      sudo nmcli connection modify Hotspot wifi-sec.psk "12345678"
    
    sudo nmcli device set wlan0 autoconnect no

    sudo nmcli connection up Hotspot
    
    # 4. MODERN CAPTIVE PORTAL FIREWALL RULES (nftables):
    sudo nft add table ip nat
    sudo nft add chain ip nat prerouting { type nat hook prerouting priority dstnat \; }
    
    # Intercept DNS traffic so 'captive.apple.com' resolves to the Pi's IP
    sudo nft add rule ip nat prerouting iifname "wlan0" udp dport 53 dnat to 10.42.0.1
    sudo nft add rule ip nat prerouting iifname "wlan0" tcp dport 53 dnat to 10.42.0.1
    
    # NEW CAPTIVE PORTAL TRIGGER: Intercept all HTTP web requests (Port 80) 
    # and force-route them to your Flask app instead of letting them time out
    sudo nft add rule ip nat prerouting iifname "wlan0" tcp dport 80 dnat to 10.42.0.1:5000
fi
