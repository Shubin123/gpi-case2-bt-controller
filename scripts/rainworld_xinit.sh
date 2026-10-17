#!/bin/bash
# Configure display: primary GPi Case 2 DSI-1, turn off secondary virtual HDMI-1
xrandr --output HDMI-1 --off --output DSI-1 --primary --mode FIXED_MODE 2>/dev/null
xsetroot -solid black 2>/dev/null
xset s off -dpms 2>/dev/null

# Environment settings
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
export WINESERVER=/storage/wine-proton8/bin/wineserver-wrapper
export WINEPREFIX=/storage/wineprefix
export WINEDEBUG=-all
export BOX64_DYNAREC=1
export BOX64_DYNAREC_FASTNAN=1
export BOX64_DYNAREC_FASTROUND=1
export BOX64_DYNAREC_BIGBLOCK=1
export BOX64_DYNAREC_FORWARD=128
export BOX64_DYNAREC_CALLRET=1
export BOX64_LOG=0
export BOX64_NOBANNER=1

# Mesa overrides for WineD3D / Direct3D 11 support on V3D
export MESA_GL_VERSION_OVERRIDE=4.3COMPAT
export MESA_GLSL_VERSION_OVERRIDE=430

# Start hotkey exit daemon (Menu button or Select+Start quits)
python3 /storage/scripts/gpi_exit_daemon.py &
DAEMON_PID=$!

cd /storage/roms/windows/RainWorld
/usr/local/bin/box64 /storage/wine-proton8/bin/wine64 RainWorld.exe > /storage/rainworld.log 2>&1

# Cleanup
kill $DAEMON_PID 2>/dev/null
/storage/wine-proton8/bin/wineserver-wrapper -w 2>/dev/null
