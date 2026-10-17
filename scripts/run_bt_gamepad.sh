#!/bin/bash
# Runs the DualShock 4 emulator (bt_gamepad.py) inside the Ubuntu chroot,
# then restores RetroArch. Started by start_controller_*.sh via systemd-run.
PAIR_ARG="$1"

# 1. Drop CPU to lowest power (600 MHz powersave)
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo powersave > "$g" 2>/dev/null
done

# 2. Chroot mount points
[ -e /storage/ubuntu/dev/fb0 ] || mount --rbind /dev /storage/ubuntu/dev 2>/dev/null
[ -e /storage/ubuntu/proc/cpuinfo ] || mount -t proc proc /storage/ubuntu/proc 2>/dev/null
[ -e /storage/ubuntu/sys/class ] || mount -t sysfs sys /storage/ubuntu/sys 2>/dev/null
[ -e /storage/ubuntu/storage/roms ] || mount --rbind /storage /storage/ubuntu/storage 2>/dev/null
[ -S /storage/ubuntu/run/dbus/system_bus_socket ] || { mkdir -p /storage/ubuntu/run/dbus && mount --bind /run/dbus /storage/ubuntu/run/dbus 2>/dev/null; }

# 3. Wait for RetroArch to exit (releases js0 and the display)
for i in $(seq 1 30); do
    pidof retroarch >/dev/null || break
    sleep 0.2
done

# 4. Bluetooth must be running and powered, even if it was switched off in Lakka's settings
if ! systemctl is-active --quiet bluetooth; then
    rm -f /storage/.cache/services/bluez.disabled
    touch /storage/.cache/services/bluez.conf      # what Lakka's Bluetooth toggle does
    systemctl start bluetooth
    for i in $(seq 1 25); do bluetoothctl show >/dev/null 2>&1 && break; sleep 0.2; done
fi
rfkill unblock bluetooth 2>/dev/null
/usr/bin/hciconfig hci0 up 2>/dev/null
bluetoothctl power on >/dev/null 2>&1

# Restore normal system state on any exit or termination
cleanup() {
    echo "[RUN] Restoring RetroArch and performance settings..."
    # Never leave the handheld visible/pairable after controller mode ends
    bluetoothctl discoverable off >/dev/null 2>&1
    bluetoothctl pairable off >/dev/null 2>&1
    for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo performance > "$g" 2>/dev/null
    done
    dd if=/dev/zero of=/dev/fb0 bs=1M count=4 2>/dev/null
    systemctl start retroarch
}
trap cleanup EXIT
trap 'kill -TERM $PY_PID 2>/dev/null; wait $PY_PID; exit 0' INT TERM

# 5. Run native DualShock 4 Bluetooth Server
chroot /storage/ubuntu python3 -u /storage/scripts/bt_gamepad.py $PAIR_ARG &
PY_PID=$!
wait $PY_PID
