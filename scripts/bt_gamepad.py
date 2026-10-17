#!/usr/bin/env python3
"""
DualShock 4 (PS4) Wireless Controller Bluetooth HID Emulation
For Retroflag GPi Case 2 / Raspberry Pi CM4 (Lakka 6.1)
Hardware ID: 054C:09CC (Sony DualShock 4 v2)

Requirements (handled by deploy.sh):
  - bluetoothd started with "-P input" so BlueZ does not own L2CAP PSM 17/19
  - main.conf DeviceID = usb:054C:09CC:0100 so the PnP (DID) record says "Sony"
"""

import os
import sys
import time
import zlib
import mmap
import struct
import signal
import socket
import select
import json
import threading
from PIL import Image, ImageDraw, ImageFont, ImageMath

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

PSM_CTRL = 17
PSM_INTR = 19
HOST_FILE = "/storage/.config/bt_gamepad_host"
SETTINGS_FILE = "/storage/.config/bt_gamepad.json"
JS_DEV = "/dev/input/js0"
UI_W, UI_H = 640, 480           # GPi Case 2 DSI panel (top-left of fb0)
REPORT_HZ = 100
RECONNECT_TIMEOUT = 4.0         # seconds spent paging the host per attempt
RECONNECT_INTERVAL = 6.0        # seconds between attempts (listening in between)
PAIR_WINDOW = 120.0             # seconds the adapter stays discoverable/pairable

# L2CAP link security: MEDIUM = encrypted link, requires a bonded (paired) host
SOL_BLUETOOTH = 274
BT_SECURITY = 4
BT_SECURITY_MEDIUM = 2

# ---------------------------------------------------------
# DualShock 4 (PS4) Bluetooth HID Report Descriptor
# Report ID 0x01: Basic input report (sent until host reads a feature report)
# Report ID 0x11: Extended Bluetooth input report (with CRC32)
# ---------------------------------------------------------
DS4_REPORT_DESCRIPTOR_HEX = (
    "05010905a10185010930093109320935150026ff00750895048102093915002507750495"
    "01814205091901290e150025017501950e8102750695018101050109330934150026ff00"
    "7508950281020604ff850209249524b10285a309259530b102850509269528b102850609"
    "279534b102850709289530b10285080929952fb1028509092a9513b1020603ff85030921"
    "9526b10285040922952eb10285f00947953fb10285f10948953fb10285f20949950fb102"
    "0600ff85110920150026ff007508954d81020921910285120922958d8102092391028513"
    "092495cd81020925910285140926960d0181020927910285150928964d01810209299102"
    "8516092a968d018102092b91028517092c96cd018102092d91028518092e960d02810209"
    "2f9102851909309622028102093191020680ff85820922953fb10285830923b102858409"
    "24b10285900930b10285910931b10285920932b10285930933b10285940934b10285a009"
    "40b10285a40944b10285a70945b10285a80945b10285a90945b10285aa0945b10285ab09"
    "45b10285ac0945b10285ad0945b10285b30945b10285b40946b10285b50947b10285d009"
    "40b10285d40944b102c0"
)

# ---------------------------------------------------------
# Service Discovery Protocol (SDP) Record for DualShock 4 HID.
# The Device ID (PnP) record comes from BlueZ itself via main.conf DeviceID,
# registering a second one here would leave the host with two conflicting IDs.
# ---------------------------------------------------------
SDP_XML_HID = f"""<?xml version="1.0" encoding="UTF-8" ?>
<record>
\t<attribute id="0x0001">
\t\t<sequence>
\t\t\t<uuid value="0x1124" />
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0004">
\t\t<sequence>
\t\t\t<sequence>
\t\t\t\t<uuid value="0x0100" />
\t\t\t\t<uint16 value="0x0011" />
\t\t\t</sequence>
\t\t\t<sequence>
\t\t\t\t<uuid value="0x0011" />
\t\t\t</sequence>
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0005">
\t\t<sequence>
\t\t\t<uuid value="0x1002" />
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0006">
\t\t<sequence>
\t\t\t<uint16 value="0x656e" />
\t\t\t<uint16 value="0x006a" />
\t\t\t<uint16 value="0x0100" />
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0009">
\t\t<sequence>
\t\t\t<sequence>
\t\t\t\t<uuid value="0x1124" />
\t\t\t\t<uint16 value="0x0100" />
\t\t\t</sequence>
\t\t</sequence>
\t</attribute>
\t<attribute id="0x000d">
\t\t<sequence>
\t\t\t<sequence>
\t\t\t\t<sequence>
\t\t\t\t\t<uuid value="0x0100" />
\t\t\t\t\t<uint16 value="0x0013" />
\t\t\t\t</sequence>
\t\t\t\t<sequence>
\t\t\t\t\t<uuid value="0x0011" />
\t\t\t\t</sequence>
\t\t\t</sequence>
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0100">
\t\t<text value="Wireless Controller" />
\t</attribute>
\t<attribute id="0x0101">
\t\t<text value="Game Controller" />
\t</attribute>
\t<attribute id="0x0102">
\t\t<text value="Sony Interactive Entertainment" />
\t</attribute>
\t<attribute id="0x0200">
\t\t<uint16 value="0x0100" />
\t</attribute>
\t<attribute id="0x0201">
\t\t<uint16 value="0x0111" />
\t</attribute>
\t<attribute id="0x0202">
\t\t<uint8 value="0x08" />
\t</attribute>
\t<attribute id="0x0203">
\t\t<uint8 value="0x00" />
\t</attribute>
\t<attribute id="0x0204">
\t\t<boolean value="true" />
\t</attribute>
\t<attribute id="0x0205">
\t\t<boolean value="true" />
\t</attribute>
\t<attribute id="0x0206">
\t\t<sequence>
\t\t\t<sequence>
\t\t\t\t<uint8 value="0x22" />
\t\t\t\t<text encoding="hex" value="{DS4_REPORT_DESCRIPTOR_HEX}" />
\t\t\t</sequence>
\t\t</sequence>
\t</attribute>
\t<attribute id="0x0207">
\t\t<sequence>
\t\t\t<sequence>
\t\t\t\t<uint16 value="0x0409" />
\t\t\t\t<uint16 value="0x0100" />
\t\t\t</sequence>
\t\t</sequence>
\t</attribute>
\t<attribute id="0x020b">
\t\t<uint16 value="0x0100" />
\t</attribute>
\t<attribute id="0x020c">
\t\t<uint16 value="0x0c80" />
\t</attribute>
\t<attribute id="0x020d">
\t\t<boolean value="true" />
\t</attribute>
\t<attribute id="0x020e">
\t\t<boolean value="false" />
\t</attribute>
\t<attribute id="0x020f">
\t\t<uint16 value="0x0640" />
\t</attribute>
\t<attribute id="0x0210">
\t\t<uint16 value="0x0320" />
\t</attribute>
</record>
"""

# ---------------------------------------------------------
# HIDP (Bluetooth HID transport) message types
# ---------------------------------------------------------
HIDP_HANDSHAKE = 0x0
HIDP_CONTROL = 0x1
HIDP_GET_REPORT = 0x4
HIDP_SET_REPORT = 0x5
HIDP_GET_PROTOCOL = 0x6
HIDP_SET_PROTOCOL = 0x7
HIDP_GET_IDLE = 0x8
HIDP_SET_IDLE = 0x9
HIDP_DATA = 0xA

HS_SUCCESSFUL = 0x00
HS_ERR_INVALID_REPORT_ID = 0x02
HS_ERR_UNSUPPORTED_REQUEST = 0x03

CTRL_VIRTUAL_CABLE_UNPLUG = 0x05

REPORT_INPUT = 1
REPORT_FEATURE = 3


def parse_feature_sizes(desc):
    """Return {report_id: payload_bytes} for every Feature report in a HID descriptor."""
    sizes = {}
    rsize = rcount = rid = 0
    i = 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:  # long item
            i += 3 + desc[i + 1]
            continue
        n = (0, 1, 2, 4)[b & 3]
        val = int.from_bytes(desc[i + 1:i + 1 + n], "little")
        i += 1 + n
        tag = b & 0xFC
        if tag == 0x74:
            rsize = val
        elif tag == 0x94:
            rcount = val
        elif tag == 0x84:
            rid = val
        elif tag == 0xB0:
            sizes[rid] = sizes.get(rid, 0) + rsize * rcount
    return {k: v // 8 for k, v in sizes.items()}


def ds4_crc(seed, data):
    return struct.pack("<I", zlib.crc32(bytes([seed]) + data) & 0xFFFFFFFF)


def build_feature_reports():
    """Static DS4 feature reports, keyed by report ID (payload excludes the ID byte)."""
    sizes = parse_feature_sizes(bytes.fromhex(DS4_REPORT_DESCRIPTOR_HEX))
    reports = {rid: bytes(size) for rid, size in sizes.items()}

    # Neutral IMU calibration: zero bias, symmetric +/- ranges.
    gyro_bias = (0, 0, 0)
    gyro_speed = (540, 540)
    accel = (8192, -8192, 8192, -8192, 8192, -8192)
    # 0x02 (USB layout): pitch+, yaw+, roll+, pitch-, yaw-, roll-
    calib_usb = struct.pack("<3h6h2h6h", *gyro_bias, 8192, 8192, 8192, -8192, -8192, -8192,
                            *gyro_speed, *accel)
    reports[0x02] = calib_usb.ljust(sizes[0x02], b"\0")
    # 0x05 (Bluetooth layout): pitch+, pitch-, yaw+, yaw-, roll+, roll-, then CRC32
    calib_bt = struct.pack("<3h6h2h6h", *gyro_bias, 8192, -8192, 8192, -8192, 8192, -8192,
                           *gyro_speed, *accel).ljust(sizes[0x05] - 4, b"\0")
    reports[0x05] = calib_bt + ds4_crc(0xA3, bytes([0x05]) + calib_bt)
    # 0xA3: firmware build info
    fw = b"Sep 21 2018".ljust(16, b"\0") + b"04:50:51".ljust(16, b"\0")
    fw += struct.pack("<HIHH", 0x0100, 0xB400, 0x8001, 0x0008)
    reports[0xA3] = fw.ljust(sizes[0xA3], b"\0")
    return reports


class Framebuffer:
    """Writes a UI_W x UI_H PIL image to the top-left of /dev/fb0 in its native format."""

    def __init__(self, path="/dev/fb0"):
        base = "/sys/class/graphics/" + os.path.basename(path)
        self.width, self.height = (int(v) for v in open(base + "/virtual_size").read().split(","))
        self.bpp = int(open(base + "/bits_per_pixel").read())
        self.stride = int(open(base + "/stride").read())
        self.fd = os.open(path, os.O_RDWR)
        self.mm = mmap.mmap(self.fd, self.stride * self.height)
        print(f"[FB] {path}: {self.width}x{self.height} {self.bpp}bpp stride {self.stride}")

    def _pack(self, img):
        if self.bpp == 16:
            r, g, b = img.split()
            hi = ImageMath.eval("(r & 248) | (g >> 5)", r=r, g=g).convert("L")
            lo = ImageMath.eval("((g << 3) & 224) | (b >> 3)", g=g, b=b).convert("L")
            return Image.merge("LA", (lo, hi)).tobytes()  # little-endian RGB565
        r, g, b = img.split()
        return Image.merge("RGBA", (b, g, r, Image.new("L", img.size, 255))).tobytes()

    def show(self, img):
        w, h = min(img.width, self.width), min(img.height, self.height)
        if (w, h) != img.size:
            img = img.crop((0, 0, w, h))
        data = self._pack(img)
        row = w * self.bpp // 8
        for y in range(h):
            off = y * self.stride
            self.mm[off:off + row] = data[y * row:(y + 1) * row]

    def clear(self):
        self.mm[:] = bytes(len(self.mm))


class PairingAgent(dbus.service.Object):
    """Standard "click Connect on the Mac" pairing, gated by the GPi.

    Capability NoInputNoOutput gives the normal macOS/Windows flow (no codes).
    Pairing is only accepted while the pairing window opened from the GPi menu
    is running; at any other time every request is rejected.
    """

    def __init__(self, bus, path, server):
        super().__init__(bus, path)
        self.server = server

    def _check(self, device):
        addr = str(device).rsplit("dev_", 1)[-1].replace("_", ":")
        if not self.server.pair_window_open():
            print(f"[Agent] Pairing from {addr} rejected: pairing window closed")
            raise rejected()
        print(f"[Agent] Pairing with {addr} accepted (pairing window open)")
        self.server.set_status(f"Pairing with {addr}...")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        print("[Agent] Released")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        self._check(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        self._check(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        if not self.server.pair_window_open() and not self.server.is_bonded(str(device)):
            print(f"[Agent] AuthorizeService {uuid} for unpaired {device} rejected")
            raise rejected()

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        self._check(device)
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        self._check(device)
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        print("[Agent] Pairing cancelled by remote")


def rejected():
    return dbus.DBusException("Pairing rejected", name="org.bluez.Error.Rejected")


class BluezProfile(dbus.service.Object):
    """Holds the HID SDP record. L2CAP channels are served by our own sockets."""

    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        print("[Profile] Released by BlueZ")

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, path, fd, properties):
        os.close(fd.take())
        print(f"[Profile] Unexpected NewConnection from {path} (is bluetoothd running with -P input?)")

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, path):
        print(f"[Profile] RequestDisconnection: {path}")


class DualShock4Server:
    def __init__(self, force_pair_mode=False):
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.ui_dirty = threading.Event()

        self.bus = None
        self.pair_until = 0.0           # monotonic deadline of the pairing window
        self.start_in_pair_mode = force_pair_mode
        self.connected = False
        self.remote_addr = None
        self.status_note = ""
        self.disconnect_requested = False
        self.reconnect_now = not force_pair_mode
        self.last_host = self.load_last_host()

        self.feature_reports = build_feature_reports()
        self.extended_reports = False   # switch to 0x11 once host reads calibration
        self.report_counter = 0
        self.sensor_ts = 0

        # Physical GPi Case 2 controls: D-pad, A/B/X/Y, L1/R1, L2/R2, Select/Start, MENU.
        # There are no analog sticks; the D-pad can optionally also drive the left stick.
        self.dpad_x = self.dpad_y = 0
        self.held = set()               # DS4 button names currently held
        self.l2_analog = self.r2_analog = 0
        self.settings = self.load_settings()

        # On-screen menu (D-pad Up/Down, [A] select, [B] back, [MENU] open/close)
        self.menu_open = False
        self.menu_index = 0
        self.confirm_forget = False
        self.reconnect_paused = False   # user chose Disconnect: don't page the host again

        # D-pad Hat switch: 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW, 8=Released
        self.hat_map = {
            (0, 0): 8, (0, -1): 0, (1, -1): 1, (1, 0): 2, (1, 1): 3,
            (0, 1): 4, (-1, 1): 5, (-1, 0): 6, (-1, -1): 7,
        }

        font_dir = "/usr/share/fonts/truetype/dejavu/"
        try:
            self.font_large = ImageFont.truetype(font_dir + "DejaVuSans-Bold.ttf", 24)
            self.font_medium = ImageFont.truetype(font_dir + "DejaVuSans-Bold.ttf", 16)
            self.font_small = ImageFont.truetype(font_dir + "DejaVuSans.ttf", 13)
            self.font_tiny = ImageFont.truetype(font_dir + "DejaVuSansMono.ttf", 11)
        except Exception:
            self.font_large = self.font_medium = self.font_small = self.font_tiny = ImageFont.load_default()

        try:
            self.fb = Framebuffer()
        except Exception as e:
            print(f"[FB] Framebuffer unavailable, UI disabled: {e}")
            self.fb = None

    # -----------------------------------------------------
    # Persistence / BlueZ helpers
    # -----------------------------------------------------
    @staticmethod
    def load_last_host():
        try:
            addr = open(HOST_FILE).read().strip().upper()
            return addr if len(addr) == 17 else None
        except OSError:
            return None

    @staticmethod
    def load_settings():
        settings = {"dpad_stick": False}
        try:
            settings.update(json.load(open(SETTINGS_FILE)))
        except (OSError, ValueError):
            pass
        return settings

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f)
        except OSError as e:
            print(f"[PS4] Could not save settings: {e}")

    def save_last_host(self, addr):
        self.last_host = addr
        try:
            with open(HOST_FILE, "w") as f:
                f.write(addr + "\n")
        except OSError as e:
            print(f"[PS4] Could not save host address: {e}")

    def device_props(self, addr):
        path = "/org/bluez/hci0/dev_" + addr.replace(":", "_")
        return dbus.Interface(self.bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")

    def trust_host(self, addr):
        try:
            self.device_props(addr).Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
        except Exception as e:
            print(f"[PS4] Could not mark {addr} trusted: {e}")

    def forget_host(self, addr):
        try:
            adapter = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez/hci0"), "org.bluez.Adapter1")
            adapter.RemoveDevice("/org/bluez/hci0/dev_" + addr.replace(":", "_"))
        except Exception as e:
            print(f"[PS4] Could not remove {addr}: {e}")
        if self.last_host == addr:
            self.last_host = None
            try:
                os.remove(HOST_FILE)
            except OSError:
                pass

    def forget_all_hosts(self):
        try:
            om = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
            for ifaces in om.GetManagedObjects().values():
                dev = ifaces.get("org.bluez.Device1")
                if dev and dev.get("Paired"):
                    self.forget_host(str(dev["Address"]).upper())
        except Exception as e:
            print(f"[PS4] Could not list paired devices: {e}")
        self.last_host = None
        try:
            os.remove(HOST_FILE)
        except OSError:
            pass

    def paired_host(self):
        """Last connected host if still paired, else any paired device."""
        try:
            om = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
            paired = [str(ifaces["org.bluez.Device1"]["Address"]).upper()
                      for ifaces in om.GetManagedObjects().values()
                      if "org.bluez.Device1" in ifaces and ifaces["org.bluez.Device1"].get("Paired")]
        except Exception as e:
            print(f"[PS4] Could not list paired devices: {e}")
            return self.last_host
        if self.last_host in paired:
            return self.last_host
        return paired[0] if paired else None

    # -----------------------------------------------------
    # Bluetooth setup
    # -----------------------------------------------------
    def setup_bluetooth(self):
        print("[PS4] Configuring Bluetooth adapter for DualShock 4 emulation...")
        self.bus = dbus.SystemBus()
        self.set_adapter(Powered=True, Alias="Wireless Controller", DiscoverableTimeout=0, PairableTimeout=0)

        self.agent = PairingAgent(self.bus, "/org/bluez/ds4_agent", self)
        agents = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
        try:
            agents.RegisterAgent("/org/bluez/ds4_agent", "NoInputNoOutput")
            agents.RequestDefaultAgent("/org/bluez/ds4_agent")
            print("[PS4] Pairing agent registered (accepts only inside the GPi pairing window)")
        except Exception as e:
            print(f"[PS4] Warning registering agent: {e}")

        if self.start_in_pair_mode:
            self.open_pair_window()
        else:
            self.close_pair_window()

        self.profile = BluezProfile(self.bus, "/org/bluez/ds4_hid")
        profiles = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1")
        try:
            profiles.RegisterProfile("/org/bluez/ds4_hid", "00001124-0000-1000-8000-00805f9b34fb", {
                "ServiceRecord": SDP_XML_HID,
                "Role": "server",
                "RequireAuthentication": False,
                "RequireAuthorization": False,
            })
            print("[PS4] HID SDP record registered")
        except Exception as e:
            print(f"[PS4] HID registration note: {e}")

    def start_l2cap_servers(self):
        self.s_ctrl = self.l2cap_socket()
        self.s_intr = self.l2cap_socket()
        try:
            self.s_ctrl.bind((socket.BDADDR_ANY, PSM_CTRL))
            self.s_intr.bind((socket.BDADDR_ANY, PSM_INTR))
        except OSError as e:
            sys.exit(f"[PS4] Cannot bind HID PSMs ({e}); is bluetoothd running with -P input?")
        self.s_ctrl.listen(1)
        self.s_intr.listen(1)
        print("[PS4] L2CAP listening on PSM 17 (Control) & PSM 19 (Interrupt)")

    @staticmethod
    def l2cap_socket():
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(SOL_BLUETOOTH, BT_SECURITY, struct.pack("BB", BT_SECURITY_MEDIUM, 0))
        return s

    # -----------------------------------------------------
    # Pairing window (opened from the GPi menu)
    # -----------------------------------------------------
    def set_adapter(self, **props):
        adapter = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez/hci0"), "org.freedesktop.DBus.Properties")
        for prop, val in props.items():
            if isinstance(val, bool):
                val = dbus.Boolean(val)
            elif isinstance(val, int):
                val = dbus.UInt32(val)
            else:
                val = dbus.String(val)
            try:
                adapter.Set("org.bluez.Adapter1", prop, val)
            except Exception as e:
                print(f"[PS4] Warning setting {prop}: {e}")

    @property
    def pair_mode(self):
        return self.pair_window_open()

    def pair_window_open(self):
        return time.monotonic() < self.pair_until

    def open_pair_window(self):
        self.pair_until = time.monotonic() + PAIR_WINDOW
        self.set_adapter(Pairable=True, Discoverable=True)
        self.set_status(f"Pairing window open for {int(PAIR_WINDOW)}s")

    def close_pair_window(self):
        was_open = self.pair_until > 0
        self.pair_until = 0.0
        self.set_adapter(Discoverable=False, Pairable=False)
        if was_open:
            self.set_status("Pairing window closed")

    def is_bonded(self, device):
        """device: BlueZ object path or BD address."""
        if not device.startswith("/"):
            device = "/org/bluez/hci0/dev_" + device.upper().replace(":", "_")
        try:
            props = dbus.Interface(self.bus.get_object("org.bluez", device), "org.freedesktop.DBus.Properties")
            return bool(props.Get("org.bluez.Device1", "Paired"))
        except Exception:
            return False

    def housekeeping(self):
        now = time.monotonic()
        if self.pair_until and now >= self.pair_until:
            self.close_pair_window()

    # -----------------------------------------------------
    # Connection management (main thread)
    # -----------------------------------------------------
    def set_status(self, note):
        print(f"[PS4] {note}")
        self.status_note = note
        self.ui_dirty.set()

    def accept_incoming(self, timeout):
        r, _, _ = select.select([self.s_ctrl], [], [], timeout)
        if not r:
            return None
        c_ctrl, addr = self.s_ctrl.accept()
        r, _, _ = select.select([self.s_intr], [], [], 3.0)
        if not r:
            print(f"[PS4] {addr[0]} opened control channel but not interrupt channel")
            c_ctrl.close()
            return None
        c_intr, addr_intr = self.s_intr.accept()
        addr = addr[0].upper()
        if addr_intr[0].upper() != addr or not self.is_bonded(addr):
            print(f"[PS4] Rejected HID connection from unpaired device {addr}")
            c_ctrl.close()
            c_intr.close()
            return None
        return c_ctrl, c_intr, addr

    def connect_l2cap(self, addr, psm):
        """Non-blocking connect that gives up early if we are asked to stop."""
        s = self.l2cap_socket()
        s.setblocking(False)
        try:
            s.connect((addr, psm))
        except BlockingIOError:
            pass
        except OSError:
            s.close()
            raise
        deadline = time.monotonic() + RECONNECT_TIMEOUT
        while not self.stop_event.is_set():
            _, w, _ = select.select([], [s], [], 0.25)
            if w:
                err = s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err:
                    s.close()
                    raise OSError(err, os.strerror(err))
                s.setblocking(True)
                return s
            if time.monotonic() >= deadline:
                break
        s.close()
        raise OSError(f"no answer on PSM {psm}")

    def connect_outgoing(self, addr):
        c_ctrl = c_intr = None
        try:
            c_ctrl = self.connect_l2cap(addr, PSM_CTRL)
            c_intr = self.connect_l2cap(addr, PSM_INTR)
            return c_ctrl, c_intr, addr
        except OSError as e:
            for s in (c_ctrl, c_intr):
                if s:
                    s.close()
            print(f"[PS4] Reconnect to {addr} failed: {e}")
            return None

    def run(self):
        next_reconnect = 0.0
        failures = 0
        auto_paired = self.start_in_pair_mode   # never reopen the window on our own twice
        self.set_status("Waiting for host")
        while not self.stop_event.is_set():
            self.housekeeping()
            link = self.accept_incoming(0.25)

            if link is None and not self.pair_mode and (
                    self.reconnect_now or (not self.reconnect_paused and time.monotonic() >= next_reconnect)):
                self.reconnect_now = False
                self.reconnect_paused = False
                host = self.paired_host()
                if host is None:
                    next_reconnect = time.monotonic() + RECONNECT_INTERVAL
                    if not auto_paired:
                        auto_paired = True
                        self.open_pair_window()
                    else:
                        self.set_status("No paired host - choose 'Pair a new Mac / PC'")
                    continue
                self.set_status(f"Reconnecting to {host}...")
                link = self.connect_outgoing(host)
                if link is None:
                    failures += 1
                    next_reconnect = time.monotonic() + (RECONNECT_INTERVAL if failures < 10 else 30.0)
                    self.set_status(f"Host {host} not reachable, retrying")
                    continue

            if link is None:
                continue
            failures = 0
            self.session(*link)
            # After the host drops us, try to get it back quickly.
            next_reconnect = time.monotonic() + 2.0

    def session(self, c_ctrl, c_intr, addr):
        with self.lock:
            self.connected = True
            self.remote_addr = addr
            self.disconnect_requested = False
            self.extended_reports = False
            self.menu_open = False
        if self.pair_until:
            self.close_pair_window()
        self.set_status(f"Connected to {addr}")
        self.save_last_host(addr)
        self.trust_host(addr)

        c_intr.settimeout(0.5)
        period = 1.0 / REPORT_HZ
        next_send = time.monotonic()
        unplugged = False
        try:
            while not self.stop_event.is_set() and not self.disconnect_requested:
                wait = max(0.0, next_send - time.monotonic())
                r, _, _ = select.select([c_ctrl, c_intr], [], [], wait)
                for sock in r:
                    data = sock.recv(1024)
                    if not data:
                        raise ConnectionError("channel closed by host")
                    if sock is c_ctrl:
                        unplugged = self.handle_control(c_ctrl, data)
                        if unplugged:
                            raise ConnectionError("host removed the pairing (virtual cable unplug)")
                    # Interrupt channel data is output reports (rumble / lightbar): ignored.

                now = time.monotonic()
                if now >= next_send:
                    try:
                        c_intr.send(self.build_input_report(now))
                    except socket.timeout:
                        pass
                    next_send = max(next_send + period, now)
        except (OSError, ConnectionError) as e:
            print(f"[PS4] Session with {addr} ended: {e}")
        finally:
            for s in (c_intr, c_ctrl):
                try:
                    s.close()
                except OSError:
                    pass
            with self.lock:
                self.connected = False
                self.remote_addr = None
            if unplugged:
                self.forget_host(addr)
            self.set_status(f"Disconnected from {addr}")

    # -----------------------------------------------------
    # HIDP protocol
    # -----------------------------------------------------
    def handle_control(self, ctrl, data):
        """Answer one HIDP control-channel message. Returns True on virtual cable unplug."""
        mtype, param = data[0] >> 4, data[0] & 0x0F

        if mtype == HIDP_CONTROL:
            return param == CTRL_VIRTUAL_CABLE_UNPLUG

        if mtype == HIDP_GET_REPORT:
            rtype = param & 0x03
            rid = data[1] if len(data) > 1 else 0
            max_len = struct.unpack("<H", data[2:4])[0] if param & 0x08 and len(data) >= 4 else None
            if rtype == REPORT_FEATURE and rid in self.feature_reports:
                payload = bytes([rid]) + self.feature_reports[rid]
                if rid in (0x02, 0x05):
                    self.extended_reports = True
                    print(f"[HIDP] Host read calibration (0x{rid:02x}); switching to full DS4 reports")
            elif rtype == REPORT_INPUT and rid in (0x01, 0x11):
                payload = self.build_input_report(time.monotonic(), rid)[1:]
            else:
                print(f"[HIDP] GET_REPORT type {rtype} id 0x{rid:02x} unsupported")
                ctrl.send(bytes([HS_ERR_INVALID_REPORT_ID]))
                return False
            if max_len:
                payload = payload[:max_len]
            ctrl.send(bytes([(HIDP_DATA << 4) | rtype]) + payload)
        elif mtype == HIDP_GET_PROTOCOL:
            ctrl.send(bytes([(HIDP_DATA << 4) | 0, 0x01]))  # report protocol
        elif mtype == HIDP_GET_IDLE:
            ctrl.send(bytes([(HIDP_DATA << 4) | 0, 0x00]))
        elif mtype in (HIDP_SET_REPORT, HIDP_SET_PROTOCOL, HIDP_SET_IDLE):
            ctrl.send(bytes([HS_SUCCESSFUL]))
        elif mtype == HIDP_DATA:
            pass  # output report on control channel
        else:
            ctrl.send(bytes([HS_ERR_UNSUPPORTED_REQUEST]))
        return False

    def build_input_report(self, now, rid=None):
        """DATA|INPUT header + report 0x01 (basic) or 0x11 (extended with CRC)."""
        if rid is None:
            rid = 0x11 if self.extended_reports else 0x01
        with self.lock:
            forwarding = self.connected and not self.menu_open
            held = self.held if forwarding else set()
            dx, dy = (self.dpad_x, self.dpad_y) if forwarding else (0, 0)
            l2, r2 = (self.l2_analog, self.r2_analog) if forwarding else (0, 0)
        lx = ly = 128
        if self.settings["dpad_stick"]:
            lx, ly = 128 + dx * 127, 128 + dy * 127
        bit = lambda name: 1 if name in held else 0
        b4 = self.hat_map.get((dx, dy), 8)
        b4 |= bit("square") << 4 | bit("cross") << 5 | bit("circle") << 6 | bit("triangle") << 7
        b5 = (bit("l1") | bit("r1") << 1 | (l2 > 64) << 2 | (r2 > 64) << 3 |
              bit("share") << 4 | bit("options") << 5 | bit("l3") << 6 | bit("r3") << 7)
        b6 = (self.report_counter & 0x3F) << 2
        common = bytes([lx, ly, 128, 128, b4, b5, b6, l2, r2])
        self.report_counter += 1

        if rid == 0x01:
            return b"\xa1\x01" + common

        self.sensor_ts = int(now * 1e6 / 5.33) & 0xFFFF
        body = bytes([0xC0, 0x00]) + common
        body += struct.pack("<HB3h3h", self.sensor_ts, 0, 0, 0, 0, 0, 8192, 0)
        body += bytes(5) + bytes([0x08, 0x00, 0x00])            # battery ~85%, no cable
        body += bytes([0x01, 0x00, 0x80, 0, 0, 0, 0x80, 0, 0, 0])  # 1 touch frame, no fingers
        body = body.ljust(77 - 4, b"\0")
        report = b"\x11" + body
        return b"\xa1" + report + ds4_crc(0xA1, report)

    # -----------------------------------------------------
    # Framebuffer UI (own thread)
    # -----------------------------------------------------
    def ui_loop(self):
        # Redraw on change (input/status), at most 10 fps; 1 s tick keeps countdowns fresh.
        while not self.stop_event.is_set():
            self.ui_dirty.wait(1.0)
            self.ui_dirty.clear()
            if self.fb:
                try:
                    self.fb.show(self.render_ui())
                except Exception as e:
                    print(f"[FB] Draw error: {e}")
            self.stop_event.wait(0.1)
        if self.fb:
            self.fb.clear()

    # -----------------------------------------------------
    # On-screen menu
    # -----------------------------------------------------
    def menu_visible(self):
        return not self.connected or self.menu_open

    def menu_items(self):
        items = []
        if self.connected:
            items.append(("Resume controller", "resume"))
        elif self.last_host:
            items.append((f"Reconnect to {self.last_host}", "reconnect"))
        else:
            items.append(("Reconnect (no paired host yet)", "reconnect"))
        if self.pair_mode:
            items.append((f"Pairing open... {max(0, int(self.pair_until - time.monotonic()))}s  (A: stop)", "pair_stop"))
        else:
            items.append(("Pair a new Mac / PC", "pair"))
        items.append(("D-pad sends: " + ("D-pad + Left stick" if self.settings["dpad_stick"] else "D-pad only"),
                      "dpad_mode"))
        if self.connected:
            items.append(("Disconnect from host", "disconnect"))
        items.append(("Press A again to forget ALL" if self.confirm_forget else "Forget paired devices", "forget"))
        items.append(("Exit to RetroArch", "exit"))
        return items

    def menu_activate(self, action):
        if action != "forget":
            self.confirm_forget = False
        if action == "resume":
            self.menu_open = False
        elif action == "reconnect":
            if self.pair_until:
                self.close_pair_window()
            self.reconnect_now = True
            self.set_status("Reconnecting...")
        elif action == "pair":
            self.open_pair_window()
        elif action == "pair_stop":
            self.close_pair_window()
        elif action == "dpad_mode":
            self.settings["dpad_stick"] = not self.settings["dpad_stick"]
            self.save_settings()
        elif action == "disconnect":
            self.reconnect_paused = True
            self.disconnect_requested = True
        elif action == "forget":
            if not self.confirm_forget:
                self.confirm_forget = True
            else:
                self.confirm_forget = False
                self.reconnect_paused = True
                self.disconnect_requested = True
                self.forget_all_hosts()
                self.set_status("All paired devices forgotten")
        elif action == "exit":
            print("[PAD] Exit selected, returning to RetroArch", flush=True)
            self.stop()
        self.menu_index = min(self.menu_index, len(self.menu_items()) - 1)
        self.ui_dirty.set()

    def on_input(self, kind, num, down, dy_new):
        """Local UI handling for one physical input event (pad thread)."""
        if kind == "button" and num == 8 and down:      # MENU / Home
            if self.connected:
                self.menu_open = not self.menu_open
                self.menu_index = 0
                self.confirm_forget = False
            return
        if not self.menu_visible():
            return
        if kind == "dpad" and dy_new:
            n = len(self.menu_items())
            self.menu_index = (self.menu_index + dy_new) % n
            self.confirm_forget = False
        elif kind == "button" and down and num == 0:     # A
            self.menu_activate(self.menu_items()[self.menu_index][1])
        elif kind == "button" and down and num == 1:     # B
            self.confirm_forget = False
            if self.connected:
                self.menu_open = False

    # -----------------------------------------------------
    # Rendering (640x480 GPi Case 2 panel)
    # -----------------------------------------------------
    def render_ui(self):
        with self.lock:
            connected, remote = self.connected, self.remote_addr
            dx, dy = self.dpad_x, self.dpad_y
            held = set(self.held)
            l2, r2 = self.l2_analog > 64, self.r2_analog > 64
        note, pair_mode = self.status_note, self.pair_mode

        NAVY, BLUE, LIGHT = (0, 16, 38), (0, 55, 145), (248, 250, 252)
        ON, OFF, LABEL = (0, 112, 209), (40, 62, 100), (147, 197, 253)
        img = Image.new("RGB", (UI_W, UI_H), color=NAVY)
        draw = ImageDraw.Draw(img)

        # Header
        draw.rectangle([(0, 0), (UI_W, 56)], fill=BLUE)
        draw.text((20, 8), "WIRELESS CONTROLLER", font=self.font_large, fill=LIGHT)
        draw.text((20, 36), "GPi Case 2 as a DualShock 4 for your Mac / PC", font=self.font_small, fill=LABEL)

        # Status card
        if connected:
            fill, edge, title, color = (6, 78, 59), (16, 185, 129), "CONNECTED", (52, 211, 153)
        elif pair_mode:
            fill, edge, title, color = (120, 53, 15), (245, 158, 11), "READY TO PAIR", (252, 211, 77)
        else:
            fill, edge, title, color = (15, 30, 65), ON, "NOT CONNECTED", LABEL
        draw.rounded_rectangle([(16, 66), (624, 136)], radius=10, fill=fill, outline=edge, width=2)
        draw.text((32, 74), title, font=self.font_medium, fill=color)
        if connected:
            draw.text((32, 98), f"Host {remote}", font=self.font_small, fill=(209, 250, 229))
            mode = "D-pad + Left stick" if self.settings["dpad_stick"] else "D-pad only"
            draw.text((32, 116), f"D-pad sends: {mode}", font=self.font_tiny, fill=(167, 243, 208))
        elif pair_mode:
            draw.text((32, 98), "On the Mac: System Settings > Bluetooth >", font=self.font_small, fill=(254, 243, 199))
            draw.text((32, 116), "click Connect next to 'Wireless Controller'", font=self.font_small, fill=(254, 243, 199))
        else:
            draw.text((32, 98), note[:70], font=self.font_small, fill=(224, 242, 254))

        if self.menu_visible():
            items = self.menu_items()
            draw.rounded_rectangle([(16, 150), (624, 400)], radius=10, fill=(10, 25, 55))
            row_h = min(40, 236 // len(items))
            for i, (label, action) in enumerate(items):
                y = 158 + i * row_h
                if i == self.menu_index:
                    draw.rounded_rectangle([(24, y), (616, y + row_h - 4)], radius=8, fill=ON)
                    draw.text((36, y + (row_h - 22) // 2), ">", font=self.font_medium, fill=LIGHT)
                col = (252, 165, 165) if action == "forget" and self.confirm_forget else LIGHT
                draw.text((60, y + (row_h - 22) // 2), label, font=self.font_medium, fill=col)
            hint = "D-pad Up/Down move   A select" + ("   B / MENU back" if connected else "")
        else:
            self.draw_pad(draw, held, dx, dy, l2, r2, ON, OFF, LABEL, LIGHT)
            hint = "MENU  open menu (pauses input to host)"

        draw.rectangle([(0, 412), (UI_W, UI_H)], fill=BLUE)
        draw.text((20, 422), hint, font=self.font_medium, fill=(252, 211, 77))
        draw.text((20, 450), "Pairing is only possible while 'Pair a new Mac / PC' is running on this GPi.",
                  font=self.font_tiny, fill=(209, 250, 229))
        return img

    def draw_pad(self, draw, held, dx, dy, l2, r2, ON, OFF, LABEL, LIGHT):
        """Live view of the GPi Case 2 controls as the host sees them."""
        draw.rounded_rectangle([(16, 150), (624, 400)], radius=10, fill=(10, 25, 55))
        # Shoulders
        for x, name, on in ((40, "L2", l2), (130, "L1", "l1" in held), (430, "R1", "r1" in held), (520, "R2", r2)):
            draw.rounded_rectangle([(x, 162), (x + 80, 190)], radius=6, fill=ON if on else OFF)
            draw.text((x + 28, 167), name, font=self.font_medium, fill=LIGHT)
        # D-pad
        cx, cy = 150, 285
        for (bx, by), on in (((0, -1), dy == -1), ((0, 1), dy == 1), ((-1, 0), dx == -1), ((1, 0), dx == 1)):
            x0, y0 = cx + bx * 38 - 18, cy + by * 38 - 18
            draw.rounded_rectangle([(x0, y0), (x0 + 36, y0 + 36)], radius=5, fill=ON if on else OFF)
        draw.rectangle([(cx - 18, cy - 18), (cx + 18, cy + 18)], fill=OFF)
        draw.text((cx - 24, 345), "D-PAD", font=self.font_small, fill=LABEL)
        # Select / Start
        for x, label, name in ((262, "SELECT", "share"), (338, "START", "options")):
            draw.rounded_rectangle([(x, 272), (x + 62, 296)], radius=12, fill=ON if name in held else OFF)
            draw.text((x + 8, 276), label, font=self.font_tiny, fill=LIGHT)
        # Face buttons, drawn as the PlayStation symbol the host receives
        bx, by = 500, 285
        for (ox, oy), sym, name in (((0, -1), "△", "triangle"), ((0, 1), "✕", "cross"),
                                    ((-1, 0), "□", "square"), ((1, 0), "○", "circle")):
            x, y = bx + ox * 46, by + oy * 46
            draw.ellipse([(x - 21, y - 21), (x + 21, y + 21)], fill=ON if name in held else OFF)
            draw.text((x, y), sym, font=self.font_medium, fill=LIGHT, anchor="mm")

    # -----------------------------------------------------
    # Local gamepad input (own thread)
    # -----------------------------------------------------
    def read_gamepad_loop(self):
        # xpad joystick numbering for the GPi Case 2 ("Microsoft X-Box 360 pad")
        buttons = {0: "cross", 1: "circle", 2: "square", 3: "triangle",
                   4: "l1", 5: "r1", 6: "share", 7: "options", 9: "l3", 10: "r3"}
        dpad_buttons = {11: "left", 12: "right", 13: "up", 14: "down"}   # xpad dpad_to_buttons
        while not self.stop_event.is_set():
            try:
                fd = os.open(JS_DEV, os.O_RDONLY)
            except OSError:
                time.sleep(0.5)
                continue
            print(f"[PAD] Opened {JS_DEV}")
            hat = [0, 0]
            stick = [0, 0]
            dbtn = set()
            try:
                while not self.stop_event.is_set():
                    r, _, _ = select.select([fd], [], [], 0.25)
                    if not r:
                        continue
                    ev = os.read(fd, 8)
                    if len(ev) < 8:
                        break
                    _, val, etype, num = struct.unpack("IhBB", ev)
                    is_init = etype & 0x80
                    etype &= 0x7F
                    down = bool(val)

                    with self.lock:
                        old_dy = self.dpad_y
                        if etype == 1 and num in buttons:
                            (self.held.add if down else self.held.discard)(buttons[num])
                        elif etype == 1 and num in dpad_buttons:
                            (dbtn.add if down else dbtn.discard)(dpad_buttons[num])
                        elif etype == 2 and num in (2, 5):   # L2 / R2: -32767 released .. 32767 full
                            v = max(0, min(255, (val + 32768) >> 8))
                            if num == 2:
                                self.l2_analog = v
                            else:
                                self.r2_analog = v
                        elif etype == 2 and num in (6, 7):   # D-pad hat
                            hat[num - 6] = (val > 10000) - (val < -10000)
                        elif etype == 2 and num in (0, 1):   # D-pad reported as stick on some firmware
                            stick[num] = (val > 16000) - (val < -16000)
                        self.dpad_x = (hat[0] or stick[0] or ("right" in dbtn) - ("left" in dbtn))
                        self.dpad_y = (hat[1] or stick[1] or ("down" in dbtn) - ("up" in dbtn))
                        new_dy = self.dpad_y

                    if not is_init:
                        if etype == 1 and num not in dpad_buttons:
                            self.on_input("button", num, down, 0)
                        if new_dy != old_dy:
                            self.on_input("dpad", None, False, new_dy)
                    self.ui_dirty.set()
            except OSError as e:
                print(f"[PAD] {JS_DEV} read error: {e}")
                time.sleep(1)
            finally:
                os.close(fd)

    def stop(self):
        self.stop_event.set()
        self.disconnect_requested = True
        self.ui_dirty.set()


def main():
    force_pair = "--pair-mode" in sys.argv or "-p" in sys.argv
    DBusGMainLoop(set_as_default=True)
    dbus.mainloop.glib.threads_init()
    server = DualShock4Server(force_pair_mode=force_pair)
    signal.signal(signal.SIGTERM, lambda *_: server.stop())
    signal.signal(signal.SIGINT, lambda *_: server.stop())

    server.setup_bluetooth()
    server.start_l2cap_servers()

    glib_loop = GLib.MainLoop()
    threading.Thread(target=glib_loop.run, daemon=True).start()
    ui_thread = threading.Thread(target=server.ui_loop, daemon=True)
    ui_thread.start()
    threading.Thread(target=server.read_gamepad_loop, daemon=True).start()

    try:
        server.run()
    finally:
        server.stop()
        server.close_pair_window()
        for s in (server.s_ctrl, server.s_intr):
            s.close()
        ui_thread.join(timeout=1.0)
        glib_loop.quit()
        print("[PS4] Stopped")


if __name__ == "__main__":
    main()
