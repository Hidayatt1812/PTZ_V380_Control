#!/usr/bin/env python

import json
from pathlib import Path
from time import monotonic, sleep

import cv2
import numpy as np
import requests

from config import PTZ_URL, RTSP_URL


HEADERS = {"Content-Type": "application/soap+xml"}
BASE_DIR = Path(__file__).parent
PRESETS_FILE = BASE_DIR / "ptz_presets.json"
WINDOW_NAME = "V380 Debug Stream"

# Mode lama: satu step = kirim ContinuousMove XML lama, tunggu, lalu Stop.
PAN_STEPS = 27
TILT_STEPS = 11
CENTER_PAN = 14
CENTER_TILT = 6
STEP_DUR = 0.5
STEP_PAUSE = 0.12
CALIBRATION_MARGIN = 3
LOOP_SLEEP = 0.02
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0
ZOOM_STEP = 0.25

XML_FILES = {
    "up": "postup.xml",
    "down": "postdown.xml",
    "left": "postleft.xml",
    "right": "postright.xml",
    "stop": "poststop.xml",
}

# Referensi tracker: (0, 0) = hard stop kiri-atas.
step_pos = {"pan": None, "tilt": None}
zoom_level = MIN_ZOOM
save_mode = False


class MovementInterrupted(Exception):
    pass


def read_xml(name):
    with open(BASE_DIR / name, encoding="utf-8") as xml_file:
        return xml_file.read()


XML = {key: read_xml(filename) for key, filename in XML_FILES.items()}


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def is_calibrated():
    return step_pos["pan"] is not None and step_pos["tilt"] is not None


def as_int_step(value, limit):
    return int(clamp(round(float(value)), 0, limit))


def normalize_zoom(value):
    try:
        zoom = float(value)
    except (TypeError, ValueError):
        zoom = MIN_ZOOM
    return round(clamp(zoom, MIN_ZOOM, MAX_ZOOM), 2)


def format_pos(value):
    return "--" if value is None else str(int(value))


def send_ptz_xml(xml_data):
    try:
        response = requests.post(PTZ_URL, data=xml_data, headers=HEADERS, timeout=3)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        print(f"  PTZ gagal: {exc}")
        return False


def send_stop():
    send_ptz_xml(XML["stop"])


def load_presets():
    if not PRESETS_FILE.exists():
        return {}

    with open(PRESETS_FILE, encoding="utf-8") as preset_file:
        data = json.load(preset_file)

    presets = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        try:
            pan = as_int_step(value["pan"], PAN_STEPS)
            tilt = as_int_step(value["tilt"], TILT_STEPS)
        except (KeyError, TypeError, ValueError):
            continue
        presets[str(key)] = {
            "pan": pan,
            "tilt": tilt,
            "zoom": normalize_zoom(value.get("zoom", MIN_ZOOM)),
        }
    return presets


def save_presets(presets):
    with open(PRESETS_FILE, "w", encoding="utf-8") as preset_file:
        json.dump(presets, preset_file, indent=2)
        preset_file.write("\n")


presets = load_presets()


def print_status():
    if not is_calibrated():
        print("  Posisi: [BELUM DIKALIBRASI]")
        return
    print(
        f"  Posisi: pan={step_pos['pan']}/{PAN_STEPS}  "
        f"tilt={step_pos['tilt']}/{TILT_STEPS}  "
        f"zoom={zoom_level:.2f}x"
    )


def apply_digital_zoom(frame):
    if zoom_level <= MIN_ZOOM:
        return frame

    height, width = frame.shape[:2]
    crop_width = max(1, int(width / zoom_level))
    crop_height = max(1, int(height / zoom_level))
    x0 = (width - crop_width) // 2
    y0 = (height - crop_height) // 2

    cropped = frame[y0:y0 + crop_height, x0:x0 + crop_width]
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)


class DebugStream:
    def __init__(self):
        self.camera = cv2.VideoCapture(RTSP_URL)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        self.last_frame = None
        self.last_rendered = None
        self.exit_requested = False

    def read_frame(self):
        ok, frame = self.camera.read()
        if ok:
            self.last_frame = frame
            return True, frame
        if self.last_frame is not None:
            return False, self.last_frame.copy()
        return False, self.blank_frame("Menunggu RTSP stream...")

    def blank_frame(self, message):
        frame = np.zeros((480, 720, 3), dtype=np.uint8)
        draw_text(frame, message, (24, 235), (215, 215, 215), 0.72, 1)
        return frame

    def show(self, status="idle"):
        ok, frame = self.read_frame()
        frame = apply_digital_zoom(frame)
        frame = draw_overlay(frame, ok, status)
        self.last_rendered = frame
        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            self.exit_requested = True
        return key

    def pump(self, seconds, status):
        end_at = monotonic() + seconds
        while monotonic() < end_at:
            key = self.show(status)
            if key == 27:
                return key
            sleep(LOOP_SLEEP)
        return 255

    def screenshot(self, image_counter):
        if self.last_rendered is None:
            self.show("screenshot")
        image_name = f"opencv_frame_{image_counter}.png"
        cv2.imwrite(image_name, self.last_rendered)
        print(f"  Screenshot: {image_name}")

    def close(self):
        self.camera.release()
        cv2.destroyAllWindows()


def draw_text(frame, text, pos, color=(235, 235, 235), scale=0.46, thickness=1):
    cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_debug_map(frame):
    if not is_calibrated():
        return

    _, width = frame.shape[:2]
    map_w, map_h = 150, 74
    x0, y0 = width - map_w - 12, 54
    x1, y1 = x0 + map_w, y0 + map_h

    cv2.rectangle(frame, (x0, y0), (x1, y1), (20, 20, 20), -1)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (220, 220, 220), 1)

    dot_x = int(x0 + (step_pos["pan"] / PAN_STEPS) * map_w)
    dot_y = int(y0 + (step_pos["tilt"] / TILT_STEPS) * map_h)
    cv2.circle(frame, (dot_x, dot_y), 5, (0, 220, 255), -1)

    home = presets.get("home")
    if home:
        home_x = int(x0 + (home["pan"] / PAN_STEPS) * map_w)
        home_y = int(y0 + (home["tilt"] / TILT_STEPS) * map_h)
        cv2.drawMarker(frame, (home_x, home_y), (80, 255, 120), cv2.MARKER_CROSS, 12, 1)


def draw_overlay(frame, frame_ok, status):
    height, width = frame.shape[:2]
    overlay = frame.copy()

    cv2.line(overlay, (width // 2, 0), (width // 2, height), (255, 255, 255), 1)
    cv2.line(overlay, (0, height // 2), (width, height // 2), (255, 255, 255), 1)
    cv2.addWeighted(overlay, 0.14, frame, 0.86, 0, frame)

    cv2.rectangle(frame, (0, 0), (width, 48), (0, 0, 0), -1)
    cv2.rectangle(frame, (0, height - 52), (width, height), (0, 0, 0), -1)

    mode = "SAVE PRESET" if save_mode else status
    if not frame_ok:
        mode = f"{mode} | RTSP reconnecting"

    if is_calibrated():
        pos_label = (
            f"pan {format_pos(step_pos['pan'])}/{PAN_STEPS}  "
            f"tilt {format_pos(step_pos['tilt'])}/{TILT_STEPS}  "
            f"zoom {zoom_level:.2f}x"
        )
    else:
        pos_label = "uncalibrated - press c"

    saved_keys = (["H"] if "home" in presets else []) + sorted(
        (key for key in presets if key.isdigit()), key=int
    )
    saved_label = "saved: " + " ".join(saved_keys) if saved_keys else "saved: -"

    draw_text(frame, f"V380 DEBUG | {mode}", (8, 19), (230, 245, 255), 0.52, 1)
    draw_text(frame, pos_label, (8, 39), (160, 255, 180), 0.48, 1)
    draw_text(frame, saved_label, (8, height - 30), (170, 255, 170), 0.46, 1)
    draw_text(
        frame,
        "c cal | i/,/j/l move | +/- zoom | 0 reset | H set | h home | s save | 1-9 preset | space shot | esc",
        (8, height - 10),
        (225, 225, 225),
        0.42,
        1,
    )
    draw_debug_map(frame)
    return frame


def interrupt_tracker():
    if is_calibrated():
        step_pos["pan"] = None
        step_pos["tilt"] = None
    print("  Gerakan dihentikan. Tekan c untuk kalibrasi ulang.")


def wait_or_interrupt(debug, seconds, status):
    key = debug.pump(seconds, status)
    if key == 27:
        send_stop()
        interrupt_tracker()
        raise MovementInterrupted


def timed_step(xml_data, debug, status):
    send_ptz_xml(xml_data)
    wait_or_interrupt(debug, STEP_DUR, status)
    send_stop()
    wait_or_interrupt(debug, STEP_PAUSE, status)


def step_move(xml_data, count, label, debug, after_step=None):
    for index in range(count):
        status = f"{label} {index + 1}/{count}"
        print(f"  {status}", end="\r")
        timed_step(xml_data, debug, status)
        if after_step:
            after_step()
    if count:
        print()


def set_home_here():
    presets["home"] = {
        "pan": int(step_pos["pan"]),
        "tilt": int(step_pos["tilt"]),
        "zoom": normalize_zoom(zoom_level),
    }
    save_presets(presets)
    print(
        f"  [Home] Disimpan: pan={step_pos['pan']}  "
        f"tilt={step_pos['tilt']} zoom={zoom_level:.2f}x"
    )


def set_zoom(value, label="Zoom"):
    global zoom_level
    zoom_level = normalize_zoom(value)
    print(f"  [{label}] zoom={zoom_level:.2f}x")


def adjust_zoom(delta):
    set_zoom(zoom_level + delta)


def get_home_target():
    home = presets.get("home")
    if home:
        return home["pan"], home["tilt"], home.get("zoom", MIN_ZOOM), True
    return CENTER_PAN, CENTER_TILT, MIN_ZOOM, False


def calibrate_home(debug):
    step_pos["pan"] = None
    step_pos["tilt"] = None

    print("[Kalibrasi] Pakai gerakan lama: mencari hard stop kiri-atas...")
    step_move(XML["left"], PAN_STEPS + CALIBRATION_MARGIN, "kalibrasi pan kiri", debug)
    step_move(XML["up"], TILT_STEPS + CALIBRATION_MARGIN, "kalibrasi tilt atas", debug)

    step_pos["pan"] = 0
    step_pos["tilt"] = 0

    home_pan, home_tilt, home_zoom, has_saved_home = get_home_target()
    if has_saved_home:
        print(
            "[Kalibrasi] Pojok tercapai. Menuju home tersimpan "
            f"({home_pan}, {home_tilt}, zoom {home_zoom:.2f}x)..."
        )
    else:
        print("[Kalibrasi] Pojok tercapai. Belum ada home, pakai home tengah default...")

    go_to_step_pos(home_pan, home_tilt, debug, label="Home", target_zoom=home_zoom)
    if not has_saved_home:
        set_home_here()

    print("[Kalibrasi] Selesai.")
    print_status()


def move_axis(axis, target, debug, label):
    target = as_int_step(target, PAN_STEPS if axis == "pan" else TILT_STEPS)
    current = step_pos[axis]
    delta = target - current
    if delta == 0:
        return

    direction = 1 if delta > 0 else -1
    count = abs(delta)

    if axis == "pan":
        xml_data = XML["right"] if direction > 0 else XML["left"]
        arah = "kanan" if direction > 0 else "kiri"
    else:
        xml_data = XML["down"] if direction > 0 else XML["up"]
        arah = "bawah" if direction > 0 else "atas"

    def update_tracker():
        step_pos[axis] = int(clamp(step_pos[axis] + direction, 0, PAN_STEPS if axis == "pan" else TILT_STEPS))

    step_move(xml_data, count, f"{label} {axis} {arah}", debug, update_tracker)


def go_to_step_pos(target_pan, target_tilt, debug, label="Go", target_zoom=None):
    if not is_calibrated():
        print("  Belum dikalibrasi. Tekan c dulu.")
        return False

    target_pan = as_int_step(target_pan, PAN_STEPS)
    target_tilt = as_int_step(target_tilt, TILT_STEPS)
    print(f"  [{label}] Menuju pan={target_pan} tilt={target_tilt}")

    move_axis("pan", target_pan, debug, label)
    move_axis("tilt", target_tilt, debug, label)
    if target_zoom is not None:
        set_zoom(target_zoom, label)
    print_status()
    return True


def manual_step(name, axis, direction, debug):
    if is_calibrated():
        limit = PAN_STEPS if axis == "pan" else TILT_STEPS
        target = int(clamp(step_pos[axis] + direction, 0, limit))
        if target == step_pos[axis]:
            print("  Sudah di batas gerak.")
            return
        move_axis(axis, target, debug, "Manual")
        print_status()
        return

    xml_key = {
        "atas": "up",
        "bawah": "down",
        "kiri": "left",
        "kanan": "right",
    }[name]
    print(f"  [Manual] {name} (tracker belum aktif)")
    step_move(XML[xml_key], 1, f"manual {name}", debug)


def print_banner():
    print("=== Kontrol V380 PTZ + Debug Stream ===")
    print("  Mode gerak: lama (post*.xml + 0.5s + stop)")
    print("  c/C   : kalibrasi ke kiri-atas lalu menuju home tersimpan")
    print("  i     : tilt atas")
    print("  ,     : tilt bawah")
    print("  j     : pan kiri")
    print("  l     : pan kanan")
    print("  +/=   : zoom in digital")
    print("  -/_   : zoom out digital")
    print("  0     : reset zoom digital")
    print("  H     : set home di posisi sekarang")
    print("  h     : kembali ke home")
    print("  s     : toggle mode simpan preset")
    print("  1-9   : go to preset, atau simpan jika mode simpan ON")
    print("  SPACE : screenshot frame debug")
    print("  ESC   : keluar")
    print()

    saved = ", ".join(
        (["H"] if "home" in presets else [])
        + sorted((key for key in presets if key.isdigit()), key=int)
    )
    if saved:
        print(f"  Preset tersimpan: {saved}")
    print("  Tekan c untuk kalibrasi awal sebelum pakai home/preset.")
    print_status()
    print()


def handle_key(key, debug, image_counter):
    global save_mode

    if key in (255, -1):
        return image_counter

    try:
        if key == 27:
            debug.exit_requested = True
            return image_counter

        if key in (ord("c"), ord("C")):
            calibrate_home(debug)
            return image_counter

        if key == ord("i"):
            manual_step("atas", "tilt", -1, debug)
            return image_counter

        if key == ord(","):
            manual_step("bawah", "tilt", 1, debug)
            return image_counter

        if key == ord("j"):
            manual_step("kiri", "pan", -1, debug)
            return image_counter

        if key == ord("l"):
            manual_step("kanan", "pan", 1, debug)
            return image_counter

        if key in (ord("+"), ord("=")):
            adjust_zoom(ZOOM_STEP)
            return image_counter

        if key in (ord("-"), ord("_")):
            adjust_zoom(-ZOOM_STEP)
            return image_counter

        if key == ord("0"):
            set_zoom(MIN_ZOOM, "Zoom reset")
            return image_counter

        if key == ord("H"):
            if not is_calibrated():
                print("  Belum dikalibrasi. Tekan c dulu.")
            else:
                set_home_here()
            return image_counter

        if key == ord("h"):
            home = presets.get("home")
            if not home:
                print("  Belum ada home. Tekan c untuk kalibrasi atau H untuk set.")
            else:
                go_to_step_pos(
                    home["pan"],
                    home["tilt"],
                    debug,
                    label="Home",
                    target_zoom=home.get("zoom", MIN_ZOOM),
                )
            return image_counter

        if key == ord("s"):
            if not is_calibrated():
                print("  Belum dikalibrasi. Tekan c dulu.")
            else:
                save_mode = not save_mode
                print(f"  Mode simpan: {'ON - tekan 1-9' if save_mode else 'OFF'}")
            return image_counter

        if ord("1") <= key <= ord("9"):
            number = chr(key)
            if save_mode:
                if not is_calibrated():
                    print("  Belum dikalibrasi. Tekan c dulu.")
                else:
                    presets[number] = {
                        "pan": int(step_pos["pan"]),
                        "tilt": int(step_pos["tilt"]),
                        "zoom": normalize_zoom(zoom_level),
                    }
                    save_presets(presets)
                    save_mode = False
                    print(
                        f"  [Preset {number}] Disimpan: pan={step_pos['pan']} "
                        f"tilt={step_pos['tilt']} zoom={zoom_level:.2f}x"
                    )
            else:
                preset = presets.get(number)
                if not preset:
                    print(f"  Preset {number} belum disimpan.")
                else:
                    go_to_step_pos(
                        preset["pan"],
                        preset["tilt"],
                        debug,
                        label=f"Preset {number}",
                        target_zoom=preset.get("zoom", MIN_ZOOM),
                    )
            return image_counter

        if key == 32:
            debug.screenshot(image_counter)
            return image_counter + 1

        try:
            key_name = chr(key)
        except ValueError:
            key_name = str(key)
        print(f"  Tombol tidak dikenal: {key_name}")
        return image_counter
    except MovementInterrupted:
        return image_counter


def run():
    print_banner()
    debug = DebugStream()
    image_counter = 0

    try:
        while not debug.exit_requested:
            key = debug.show("idle")
            image_counter = handle_key(key, debug, image_counter)
            sleep(LOOP_SLEEP)
    finally:
        send_stop()
        debug.close()


if __name__ == "__main__":
    run()
