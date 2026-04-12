#!/bin/sh

INTERFACE="wlan0"
WPA_CONF="/data/wpa_supplicant.conf"
HOSTNAME_FILE="/usr/resource/hostname"

# 1. Process cleanup
# usleep 100000 = 0.1 seconds
killall -q udhcpc wpa_supplicant
usleep 100000
killall -9 -q udhcpc wpa_supplicant 2>/dev/null
rm -f /var/run/wpa_supplicant/$INTERFACE 2>/dev/null

# 2. Hostname configuration
HOSTNAME="HiBy_R3ProII"
if [ -s "$HOSTNAME_FILE" ]; then
    HOSTNAME=$(cat "$HOSTNAME_FILE")
fi

# 3. Setup Driver
NV_P=$(sa_config bcmpatch_path /firmware/nvram_patch.txt)
FW_P=$(sa_config bcmpatch_path /firmware/fw_patch.txt)
[ -f "$NV_P" ] && echo "$NV_P" > /sys/module/bcmdhd/parameters/nvram_path
[ -f "$FW_P" ] && echo "$FW_P" > /sys/module/bcmdhd/parameters/firmware_path

# 4. turn on hardware and WPA Supplicant
ifconfig $INTERFACE up
wpa_supplicant -Dnl80211 -i$INTERFACE -c"$WPA_CONF" -B

# 5. Polling with usleep
# Control 20 times with 0.25s pauses (Total max 5 seconds)
LIMIT=20
while [ $LIMIT -gt 0 ]; do
    if grep -q "up" /sys/class/net/$INTERFACE/operstate 2>/dev/null; then
        # WiFi connected
        break
    fi
    
    usleep 250000
    LIMIT=$((LIMIT - 1))
done

# 6. IP reuqest
# -n: Exit if no answer (Avoid hanging if the password is wrong)
# -t 5: Send 5 DHCP requests before giving up
udhcpc -i $INTERFACE -b -n -t 5 -x hostname:"$HOSTNAME" &

exit 0