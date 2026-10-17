#!/usr/bin/env python3
import struct, os, sys, time

JS_EVENT_BUTTON = 0x01

def main():
    try:
        js = open('/dev/input/js0', 'rb')
    except Exception as e:
        sys.exit(0)

    btn_state = {}
    while True:
        try:
            data = js.read(8)
            if not data:
                break
            t, val, ev_type, number = struct.unpack('IhBB', data)
            ev_type = ev_type & ~0x80
            if ev_type & JS_EVENT_BUTTON:
                btn_state[number] = val
                # Button 8 is GPi Case 2 Menu button
                # Or Select (6) + Start (7) simultaneously
                if (number == 8 and val == 1) or (btn_state.get(6, 0) == 1 and btn_state.get(7, 0) == 1):
                    print("[EXIT_DAEMON] Hotkey triggered! Terminating game processes...", flush=True)
                    os.system("pkill -TERM -f RainWorld 2>/dev/null")
                    os.system("pkill -TERM -f box64 2>/dev/null")
                    time.sleep(0.5)
                    os.system("pkill -KILL -f RainWorld 2>/dev/null")
                    os.system("pkill -KILL -f box64 2>/dev/null")
                    os.system("pkill -KILL -f wine64 2>/dev/null")
                    os.system("pkill -KILL -f wineserver 2>/dev/null")
                    os.system("pkill -TERM -f xinit 2>/dev/null")
                    break
        except Exception:
            break

if __name__ == '__main__':
    main()
