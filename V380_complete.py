#!/usr/bin/env python

import requests
import json
from time import sleep
from pathlib import Path
import cv2

from config import PTZ_URL, RTSP_URL
headers = {'Content-Type': 'application/soap+xml'}

mydir = Path(__file__).parent
presets_file = mydir / "ptz_presets.json"

cam = cv2.VideoCapture(RTSP_URL)
cv2.namedWindow("test")

img_counter = 0
save_mode = False

xml_up    = "postup.xml"
xml_down  = "postdown.xml"
xml_left  = "postleft.xml"
xml_right = "postright.xml"
xml_stop  = "poststop.xml"

SPEED = 0.5          # velocity yang dipakai di semua XML gerak
MOVE_STEP = SPEED * 0.5  # = 0.25 unit ONVIF per keypress (speed × duration)

# Posisi kamera yang di-track secara software (mulai dari 0,0 = tengah)
current_pos = {'pan': 0.0, 'tilt': 0.0}

# Template ContinuousMove dengan pan/tilt arbitrary (untuk go_to_tracked_position)
CONTINUOUS_MOVE_XML = """\
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">
      <ProfileToken>PROFILE_000</ProfileToken>
      <Velocity>
        <PanTilt x="{pan}" y="{tilt}" xmlns="http://www.onvif.org/ver10/schema"/>
      </Velocity>
    </ContinuousMove>
  </s:Body>
</s:Envelope>"""


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def send_ptz(xml_file):
    try:
        with open(xml_file) as f:
            r = requests.post(PTZ_URL, data=f, headers=headers, timeout=3)
        print("PTZ OK:", xml_file, "->", r.status_code)
    except requests.exceptions.RequestException as e:
        print("PTZ gagal:", e)


def send_ptz_xml(xml_data):
    try:
        r = requests.post(PTZ_URL, data=xml_data, headers=headers, timeout=3)
        return r
    except requests.exceptions.RequestException as e:
        print("PTZ gagal:", e)
        return None


def go_to_tracked_position(target_pan, target_tilt):
    """Gerakkan kamera ke target menggunakan ContinuousMove + timed stop."""
    pan_delta  = target_pan  - current_pos['pan']
    tilt_delta = target_tilt - current_pos['tilt']

    if abs(pan_delta) > 0.01:
        pan_vel  = SPEED if pan_delta > 0 else -SPEED
        duration = abs(pan_delta) / SPEED
        print(f"  [go] pan {'kanan' if pan_vel>0 else 'kiri'} {duration:.2f}s")
        send_ptz_xml(CONTINUOUS_MOVE_XML.format(pan=pan_vel, tilt=0))
        sleep(duration)
        send_ptz(xml_stop)
        sleep(0.15)  # beri waktu motor berhenti sebelum tilt

    if abs(tilt_delta) > 0.01:
        tilt_vel = SPEED if tilt_delta > 0 else -SPEED
        duration = abs(tilt_delta) / SPEED
        print(f"  [go] tilt {'atas' if tilt_vel>0 else 'bawah'} {duration:.2f}s")
        send_ptz_xml(CONTINUOUS_MOVE_XML.format(pan=0, tilt=tilt_vel))
        sleep(duration)
        send_ptz(xml_stop)

    current_pos['pan']  = target_pan
    current_pos['tilt'] = target_tilt
    print(f"  tracker setelah go: pan={current_pos['pan']:.3f}  tilt={current_pos['tilt']:.3f}")


def load_presets():
    if presets_file.exists():
        with open(presets_file) as f:
            return json.load(f)
    return {}


def save_presets(presets):
    with open(presets_file, 'w') as f:
        json.dump(presets, f, indent=2)


def calibrate_set_home(presets, pos):
    presets['home'] = {'pan': round(pos['pan'], 4), 'tilt': round(pos['tilt'], 4)}
    save_presets(presets)
    print(f"[Kalibrasi] Home disimpan: pan={pos['pan']:.3f}  tilt={pos['tilt']:.3f}")


def calibrate_go_home(presets):
    pos = presets.get('home', {'pan': 0.0, 'tilt': 0.0})
    print(f"[Kalibrasi] Menuju home: pan={pos['pan']}  tilt={pos['tilt']}")
    go_to_tracked_position(float(pos['pan']), float(pos['tilt']))


def calibrate_set_preset(num, presets, pos):
    presets[str(num)] = {'pan': round(pos['pan'], 4), 'tilt': round(pos['tilt'], 4)}
    save_presets(presets)
    print(f"[Kalibrasi] Preset {num} disimpan: pan={pos['pan']:.3f}  tilt={pos['tilt']:.3f}")


def calibrate_goto_preset(num, presets):
    pos = presets.get(str(num))
    if not pos:
        print(f"[Kalibrasi] Preset {num} belum disimpan")
        return
    print(f"[Kalibrasi] Menuju preset {num}: pan={pos['pan']}  tilt={pos['tilt']}")
    go_to_tracked_position(float(pos['pan']), float(pos['tilt']))


def draw_overlay(frame, mode, presets, pos):
    h, w = frame.shape[:2]
    overlay = frame.copy()

    # Bar atas: mode + posisi terkini
    cv2.rectangle(overlay, (0, 0), (w, 32), (0, 0, 0), -1)
    if mode:
        label = "[ SIMPAN PRESET - tekan 1-9 ]"
        color = (0, 220, 0)
    else:
        label = f"PTZ  pan={pos['pan']:+.2f}  tilt={pos['tilt']:+.2f}  |  H=SetHome  h=Home  s+1-9=Simpan  1-9=Go"
        color = (220, 220, 220)
    cv2.putText(overlay, label, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # Bar bawah: preset tersimpan
    num_keys = sorted((k for k in presets if k.isdigit()), key=int)
    if num_keys or 'home' in presets:
        tags = (["[H]"] if 'home' in presets else []) + [f"[{k}]" for k in num_keys]
        saved = "Tersimpan: " + "  ".join(tags)
        cv2.rectangle(overlay, (0, h - 26), (w, h), (0, 0, 0), -1)
        cv2.putText(overlay, saved, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (180, 255, 180), 1)

    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    return frame


presets = load_presets()

print("=== Kontrol V380 PTZ ===")
print("  i / , / j / l  — Atas / Bawah / Kiri / Kanan")
print("  k               — Stop")
print("  H (Shift+H)     — Set posisi sekarang sebagai Home")
print("  h               — Kembali ke Home")
print("  s               — Toggle mode Simpan Preset")
print("  1-9             — Go to preset / Simpan preset (mode simpan)")
print("  SPACE           — Screenshot")
print("  ESC             — Keluar")
print(f"  [Posisi awal tracker: pan=0.0  tilt=0.0]")

while True:
    ret, frame = cam.read()
    if not ret:
        break

    frame = draw_overlay(frame, save_mode, presets, current_pos)
    cv2.imshow("test", frame)
    k = cv2.waitKey(1) % 256

    if k == 27:
        print("Escape hit, closing...")
        break
    elif k == 32:
        img_name = "opencv_frame_{}.png".format(img_counter)
        cv2.imwrite(img_name, frame)
        print("{} written!".format(img_name))
        img_counter += 1

    # --- Kalibrasi PTZ ---
    elif k == ord('H'):
        calibrate_set_home(presets, current_pos)
    elif k == ord('h'):
        calibrate_go_home(presets)
    elif k == ord('s'):
        save_mode = not save_mode
        print("[Kalibrasi] Mode simpan:", "ON - tekan 1-9" if save_mode else "OFF")
    elif ord('1') <= k <= ord('9'):
        num = k - ord('0')
        if save_mode:
            calibrate_set_preset(num, presets, current_pos)
            save_mode = False
        else:
            calibrate_goto_preset(num, presets)

    # --- Gerak PTZ (update tracker setelah gerak) ---
    elif k == 105:  # i = atas
        send_ptz(xml_up)
        sleep(0.5)
        send_ptz(xml_stop)
        current_pos['tilt'] = clamp(current_pos['tilt'] + MOVE_STEP)
        print(f"  tracker: pan={current_pos['pan']:.3f}  tilt={current_pos['tilt']:.3f}")
    elif k == 44:   # , = bawah
        send_ptz(xml_down)
        sleep(0.5)
        send_ptz(xml_stop)
        current_pos['tilt'] = clamp(current_pos['tilt'] - MOVE_STEP)
        print(f"  tracker: pan={current_pos['pan']:.3f}  tilt={current_pos['tilt']:.3f}")
    elif k == 106:  # j = kiri
        send_ptz(xml_left)
        sleep(0.5)
        send_ptz(xml_stop)
        current_pos['pan'] = clamp(current_pos['pan'] - MOVE_STEP)
        print(f"  tracker: pan={current_pos['pan']:.3f}  tilt={current_pos['tilt']:.3f}")
    elif k == 108:  # l = kanan
        send_ptz(xml_right)
        sleep(0.5)
        send_ptz(xml_stop)
        current_pos['pan'] = clamp(current_pos['pan'] + MOVE_STEP)
        print(f"  tracker: pan={current_pos['pan']:.3f}  tilt={current_pos['tilt']:.3f}")
    elif k == 107:  # k = stop
        send_ptz(xml_stop)

cam.release()
cv2.destroyAllWindows()
