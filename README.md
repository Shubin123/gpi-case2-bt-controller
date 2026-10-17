# CM4 Deployment Suite for Retroflag GPi Case 2
**Lakka 6.1 (LibreELEC / aarch64) • Bluetooth DualShock 4 Controller Mode • Bluetooth SSH • Rain World (Wine/Proton 8 + Box64)**

The handheld shows up on a Mac/PC as a **Sony DualShock 4 Wireless Controller** (054C:09CC), so no host
drivers or scripts are needed for the controller. Everything is driven from the GPi Case 2's own
buttons (D-pad, A/B/X/Y, L1/R1, L2/R2, Select/Start, MENU); no keyboard is needed.

---

## Directory Structure

```
cm4/
├── deploy.sh                       # One-shot deployment to the CM4 over Wi-Fi
├── README.md
├── scripts/                        # Deployed to /storage/scripts/
│   ├── bt_gamepad.py               # DualShock 4 HID server + on-screen menu (runs in Ubuntu chroot)
│   ├── run_bt_gamepad.sh           # Runner: chroot mounts, powersave CPU, restores RetroArch on exit
│   ├── start_controller_connect.sh # RetroArch entry: controller mode (reconnects to last host)
│   ├── start_controller_pair.sh    # RetroArch entry: controller mode with pairing window open
│   ├── stop_controller_mode.sh     # Manual/SSH recovery: stop controller mode, start RetroArch
│   ├── bt_state_monitor.sh         # Keeps adapter hidden + unpairable, starts/stops bt-ssh with BT power
│   ├── run_rainworld.sh / rainworld_xinit.sh / gpi_exit_daemon.py   # Rain World
├── services/
│   ├── bluetooth.service.d/gamepad.conf  # bluetoothd -C -P input -f /storage/.config/bluetooth/main.conf
│   ├── bt-state-monitor.service
│   └── bt-ssh.service              # SSH over Bluetooth RFCOMM (authenticated+encrypted, keys only)
└── playlists/
    └── Bluetooth Controller.lpl    # "Controller Mode" and "Pair a New Mac / PC"
```

`deploy.sh` also generates `/storage/.config/bluetooth/main.conf` (stock config + `Name = Wireless Controller`,
`Class = 0x000508`, `DeviceID = usb:054C:09CC:0100`).

## Deploy

```bash
./deploy.sh                 # or ./deploy.sh lakka.local / ./deploy.sh <ip>
```

---

## Using it (GPi Case 2 buttons only)

### Pair a Mac / PC (once)
1. On the GPi: RetroArch → **Bluetooth Controller** → **🔗 Pair a New Mac / PC**.
   The GPi becomes visible for **2 minutes** (countdown on screen).
2. On the Mac: **System Settings → Bluetooth → Nearby Devices → Wireless Controller → Connect**.
   That's it; no codes and nothing to press on the GPi.

### Use it
On the GPi: RetroArch → **Bluetooth Controller** → **🎮 Controller Mode**. It reconnects to the paired Mac
by itself (or click Connect in the Mac's Bluetooth menu). Nothing is installed or run on the Mac.

### On-screen menu (GPi buttons only)
| Control | Action |
|---|---|
| D-pad Up/Down | Move |
| A | Select |
| B | Back (when connected) |
| MENU | Open/close the menu while connected (input to the Mac is paused while it is open) |

Menu items: Reconnect / Resume • Pair a new Mac / PC • **D-pad sends: D-pad only / D-pad + Left stick**
(the GPi has no sticks; turn this on for games that only move with the left stick) • Disconnect •
Forget paired devices (press A twice) • Exit to RetroArch.

---

## Security model
- The GPi is **hidden and refuses pairing** except during the 2-minute window opened from its own menu.
- HID channels (L2CAP PSM 17/19) require an **encrypted link** and only accept **bonded** hosts.
- `bt-ssh.service` (SSH over RFCOMM, keys only) is still on the GPi, but macOS cannot use it without
  host software; use normal Wi-Fi SSH.

## Troubleshooting (over Wi-Fi SSH)
```bash
journalctl -u gpi-controller-mode -f              # controller app log
bash /storage/scripts/stop_controller_mode.sh     # force back to RetroArch
cat /sys/kernel/debug/bluetooth/l2cap | grep -E ' (17|19) '   # PSM 17/19 must NOT be bound by bluetoothd
```
Note: bluetoothd runs with `-P input`, so Bluetooth gamepads *paired to Lakka itself* are not supported.

## Rain World
Launch from the **Windows** playlist. Box64 v0.4.5 + Wine-Proton 8.0-5 (`MESA_GL_VERSION_OVERRIDE=4.3COMPAT`).
Press **MENU** or **Select + Start** to exit to RetroArch.
