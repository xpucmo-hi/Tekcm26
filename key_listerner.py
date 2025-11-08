#!/usr/bin/env python3
from evdev import InputDevice, ecodes
from collections import deque
import os, time

#ここをあなたのテンキー by-id バスに
DEV="/dev/input/by-id/usb-MOSART_Semi._ELECOM_TK-TDM017BK-event-kbd"
KEY_TOGGLE = ecodes.KEY_KPENTER #一録音トグルに使うキー
KEY_SHUT = ecodes.KEY_KPDOT #-3連打でシャットダウン
WINDOW = 1.5 #3連打の判定窓

dev = InputDevice(DEV)

hist = deque(maxlen=3)

def voice(cmd):
    if cmd == "toggle": os.system("pkill -USR1 -f run_voice.py")

for e in dev.read_loop():
    if e.type != ecodes.EV_KEY:
        continue
    if e.code == KEY_TOGGLE and e.value == 1:
        voice("toggle")
    elif e.code == KEY_SHUT and e.value == 1:
        now = time.time(); hist.append(now)
        if len(hist)==3 and (hist[-1]-hist[0]) <= WINDOW:
            os.system("sudo -n /sbin/shutdown -h now")
            hist.clear()
