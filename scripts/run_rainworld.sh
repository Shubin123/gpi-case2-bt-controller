#!/bin/bash
# 1. Performance and swap
[ -f /storage/swapfile ] && swapon /storage/swapfile 2>/dev/null
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$g" 2>/dev/null
done

# 2. Chroot mount points
[ -e /storage/ubuntu/dev/fb0 ] || mount --rbind /dev /storage/ubuntu/dev 2>/dev/null
[ -e /storage/ubuntu/proc/cpuinfo ] || mount -t proc proc /storage/ubuntu/proc 2>/dev/null
[ -e /storage/ubuntu/sys/class ] || mount -t sysfs sys /storage/ubuntu/sys 2>/dev/null
[ -e /storage/ubuntu/storage/roms ] || mount --rbind /storage /storage/ubuntu/storage 2>/dev/null

# 3. Stop RetroArch to release DRM master on /dev/dri/card0
systemctl stop retroarch
for i in $(seq 1 30); do
    if ! pidof retroarch >/dev/null; then
        break
    fi
    sleep 0.2
done
sleep 1

# Cleanup & restore RetroArch on any exit or termination
cleanup() {
    echo "[RUN] Restoring RetroArch after Rain World..."
    pkill -9 -f RainWorld 2>/dev/null
    pkill -9 -f box64 2>/dev/null
    pkill -9 -f wine64 2>/dev/null
    pkill -9 -f wineserver 2>/dev/null
    pkill -9 -f xinit 2>/dev/null
    pkill -9 -f Xorg 2>/dev/null
    sleep 0.5
    dd if=/dev/zero of=/dev/fb0 bs=1M count=2 2>/dev/null
    systemctl start retroarch
}
trap cleanup EXIT INT TERM

# 4. Run Xorg + Rain World inside chroot
chroot /storage/ubuntu xinit /storage/scripts/rainworld_xinit.sh -- /usr/bin/Xorg :0 vt1 -s 0 -dpms -logfile /storage/xorg-rainworld.log

