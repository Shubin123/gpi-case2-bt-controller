#!/bin/bash
systemctl reset-failed gpi-controller-mode 2>/dev/null
systemd-run --unit=gpi-controller-mode /storage/scripts/run_bt_gamepad.sh --pair-mode
systemctl stop retroarch
