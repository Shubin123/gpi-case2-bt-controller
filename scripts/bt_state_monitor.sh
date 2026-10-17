#!/bin/bash
# Native Bluetooth State & Service Monitor for Lakka / GPi Case 2
# Keeps the adapter connectable but hidden and NOT pairable while Bluetooth is ON;
# pairing is only possible in the timed, confirm-on-screen window of bt_gamepad.py.
# (name, class and Sony Device ID come from /storage/.config/bluetooth/main.conf).
# Starts bt-ssh when BT is ON; stops it and any active controller mode when BT is OFF.

LAST_STATE=""

while true; do
    POWERED=$(bluetoothctl show 2>/dev/null | grep -E "^\s*Powered:" | awk '{print $2}')

    if [ "$POWERED" = "yes" ]; then
        if [ "$LAST_STATE" != "yes" ]; then
            bluetoothctl system-alias "Wireless Controller" >/dev/null 2>&1
            if ! systemctl is-active --quiet gpi-controller-mode.service; then
                bluetoothctl discoverable off >/dev/null 2>&1
                bluetoothctl pairable off >/dev/null 2>&1
            fi
            systemctl start bt-ssh.service >/dev/null 2>&1
            LAST_STATE="yes"
        fi
    elif [ "$POWERED" = "no" ]; then
        if [ "$LAST_STATE" != "no" ]; then
            systemctl stop bt-ssh.service >/dev/null 2>&1
            # Only touch RetroArch if controller mode had taken over the screen
            # (stopping the unit makes run_bt_gamepad.sh restart RetroArch itself).
            if systemctl is-active --quiet gpi-controller-mode.service; then
                systemctl stop gpi-controller-mode.service >/dev/null 2>&1
            fi
            LAST_STATE="no"
        fi
    fi
    sleep 3
done
