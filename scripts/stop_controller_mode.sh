#!/bin/bash
# Stops controller mode; run_bt_gamepad.sh's cleanup restores CPU governor, screen and RetroArch.
systemctl stop gpi-controller-mode 2>/dev/null
# Fallback if the unit was already gone but processes linger
pkill -9 -f "^python3 -u /storage/scripts/bt_gamepad.py" 2>/dev/null
systemctl reset-failed gpi-controller-mode 2>/dev/null
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$g" 2>/dev/null
done
systemctl start retroarch
