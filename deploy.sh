#!/bin/bash
# ==============================================================================
# CM4 Deployment Script for Retroflag GPi Case 2 (Lakka 6.1 / LibreELEC)
# Deploys:
#   - Sony DualShock 4 (PS4) Wireless Controller Bluetooth HID Emulation
#   - Secure pairing (timed window, code confirmed on the handheld)
#   - Bluetooth RFCOMM SSH Server (bt-ssh.service, public-key only)
#   - Bluetooth state monitor
#   - Rain World Box64 + Wine-Proton 8 execution scripts & exit daemons
# ==============================================================================

set -e

TARGET_HOST="${1:-192.168.1.96}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== GPi Case 2 (CM4) Deployment: DualShock 4 Mode ==="
echo "Target: $TARGET_HOST"

if ! ping -c 1 -W 2 "$TARGET_HOST" >/dev/null 2>&1; then
    if ping -c 1 -W 2 lakka.local >/dev/null 2>&1; then
        TARGET_HOST="lakka.local"
        echo "Auto-detected target via mDNS: $TARGET_HOST"
    else
        echo "Error: Cannot reach $TARGET_HOST. Ensure handheld is powered on and connected to Wi-Fi."
        exit 1
    fi
fi

echo "[1/5] Syncing scripts to /storage/scripts/..."
ssh "root@$TARGET_HOST" "mkdir -p /storage/scripts /storage/.config/system.d/bluetooth.service.d /storage/.config/bluetooth /storage/playlists"
scp -q "$SCRIPT_DIR/scripts/"* "root@$TARGET_HOST:/storage/scripts/"
ssh "root@$TARGET_HOST" '
    chmod +x /storage/scripts/*.sh /storage/scripts/*.py
    # Obsolete files from earlier controller approaches
    rm -f /storage/scripts/bt_state_monitor.py /storage/scripts/controller_streamer.py \
          /storage/scripts/run_controller_streamer.sh /storage/scripts/start_host_controller_mode.sh \
          "/storage/playlists/Host Controller Mode.lpl"
'

echo "[2/5] Configuring BlueZ (main.conf + bluetoothd flags)..."
scp -q "$SCRIPT_DIR/services/bluetooth.service.d/gamepad.conf" "root@$TARGET_HOST:/storage/.config/system.d/bluetooth.service.d/"
ssh "root@$TARGET_HOST" '
    # Undo the old approach: Lakka rewrites bluez.conf, so flags live in the drop-in instead
    : > /storage/.cache/services/bluez.conf

    # main.conf = stock config + DualShock 4 identity
    sed -e "/^\[General\]/a Name = Wireless Controller\nClass = 0x000508\nDeviceID = usb:054C:09CC:0100" \
        /etc/bluetooth/main.conf > /storage/.config/bluetooth/main.conf

    # Bash Launcher core info typo ("smeupports_no_game")
    sed -i "s/^smeupports_no_game/supports_no_game/" /storage/cores/bash_launcher_libretro.info 2>/dev/null || true
'

echo "[3/5] Installing systemd units, playlists and menu icons..."
scp -q "$SCRIPT_DIR/services/"*.service "root@$TARGET_HOST:/storage/.config/system.d/"
scp -q "$SCRIPT_DIR/playlists/"* "root@$TARGET_HOST:/storage/playlists/"
scp -q "$SCRIPT_DIR/assets/bt_controller_white.png" "$SCRIPT_DIR/assets/bt_controller_color.png" "root@$TARGET_HOST:/tmp/"
ssh "root@$TARGET_HOST" '
    # XMB playlist icon = <assets>/xmb/<theme>/png/<playlist name>.png (+ -content.png for its entries).
    # Write through RetroArch'"'"'s /tmp/assets overlay (its upper layer is /storage/assets, so it persists).
    A=/tmp/assets; mountpoint -q $A || A=/storage/assets
    for theme in $(ls /usr/share/retroarch/assets/xmb); do
        case "$theme" in flatui|pixel|dot-art) src=/tmp/bt_controller_color.png ;; *) src=/tmp/bt_controller_white.png ;; esac
        d=$A/xmb/$theme/png
        mkdir -p "$d"
        cp "$src" "$d/Bluetooth Controller.png"
        cp "$src" "$d/Bluetooth Controller-content.png"
        rm -f "$d/Host Controller Mode.png" "$d/Host Controller Mode-content.png"
    done
    rm -f /tmp/bt_controller_white.png /tmp/bt_controller_color.png
'

echo "[4/5] Restarting Bluetooth stack..."
ssh "root@$TARGET_HOST" '
    rm -f /storage/.config/system.d/multi-user.target.wants/bt-ssh.service \
          /storage/.config/system.d/bluetooth.target.wants/bt-ssh.service
    systemctl daemon-reload
    systemctl enable bt-ssh.service bt-state-monitor.service 2>/dev/null || true
    systemctl stop gpi-controller-mode.service 2>/dev/null || true
    systemctl restart bluetooth
    sleep 2
    systemctl restart bt-state-monitor.service bt-ssh.service || true
'

echo "[5/5] Verifying..."
ssh "root@$TARGET_HOST" '
    echo "bluetoothd: $(tr "\0" " " < /proc/$(pidof bluetoothd)/cmdline)"
    echo "bluetooth:  $(systemctl is-active bluetooth.service)"
    echo "bt-ssh:     $(systemctl is-active bt-ssh.service)"
    echo "monitor:    $(systemctl is-active bt-state-monitor.service)"
    bluetoothctl show | grep -E "Alias|Class|Discoverable:|Pairable|Modalias"
'

echo ""
echo "=== Deployment complete ==="
echo "Pair (once): on the GPi choose RetroArch > Bluetooth Controller > 'Pair a New Mac / PC',"
echo "             then on the Mac: System Settings > Bluetooth > 'Wireless Controller' > Connect."
echo "Use:         RetroArch > Bluetooth Controller > 'Controller Mode'."
