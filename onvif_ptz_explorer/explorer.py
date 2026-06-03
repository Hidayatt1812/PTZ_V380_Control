#!/usr/bin/env python3
"""
ONVIF PTZ Explorer dengan Live Stream + Auto-Test
- Auto-test semua 29 operasi secara otomatis
- Tampilkan laporan: mana yang bisa, mana yang tidak, fungsinya apa
- Live stream kamera di jendela OpenCV
"""

import requests
import hashlib
import base64
import os
import re
import datetime
import xml.dom.minidom
import threading
from time import sleep
from typing import Optional

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ============================================================
# KONFIGURASI
# ============================================================
CAMERA_IP     = "192.168.137.240"
CAMERA_PORT   = 8899
CAMERA_USER   = ""
CAMERA_PASS   = ""
PROFILE_TOKEN = "PROFILE_000"
PTZ_URL       = f"http://{CAMERA_IP}:{CAMERA_PORT}/onvif/ptz"
MOVE_DURATION = 0.4

STREAM_URL = f"rtsp://{CAMERA_IP}:554/onvif/profile1/media.smp"
# STREAM_URL = f"rtsp://{CAMERA_IP}:554/live/ch0"
# STREAM_URL = f"rtsp://{CAMERA_IP}/livestream/11"

LOG_FILE = os.path.join(os.path.dirname(__file__), "onvif_results.log")
XML_DIR  = os.path.join(os.path.dirname(__file__), "xml")

HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction":   '""',
}

# ============================================================
# Deskripsi fungsi setiap operasi (dalam Bahasa Indonesia)
# ============================================================
OP_NAMES = {
    "1":  "GetServiceCapabilities",
    "2":  "GetNodes",
    "3":  "GetNode",
    "4":  "GetConfigurations",
    "5":  "GetConfiguration",
    "6":  "SetConfiguration",
    "7":  "GetConfigurationOptions",
    "8":  "GetCompatibleConfigurations",
    "9":  "GetStatus",
    "10": "ContinuousMove",
    "11": "Stop",
    "12": "RelativeMove",
    "13": "AbsoluteMove",
    "14": "GeoMove",
    "15": "GetPresets",
    "16": "SetPreset",
    "17": "RemovePreset",
    "18": "GotoPreset",
    "19": "GotoHomePosition",
    "20": "SetHomePosition",
    "21": "GetPresetTours",
    "22": "GetPresetTour",
    "23": "GetPresetTourOptions",
    "24": "CreatePresetTour",
    "25": "ModifyPresetTour",
    "26": "OperatePresetTour",
    "27": "RemovePresetTour",
    "28": "SendAuxiliaryCommand",
    "29": "MoveAndStartTracking",
}

OP_DESCRIPTIONS = {
    "1":  "Cek fitur PTZ yang didukung kamera: EFlip, Reverse, ContinuousPan, RemoteReboot, dll",
    "2":  "Daftar semua PTZ node — satu node = satu unit fisik mekanik pan/tilt/zoom",
    "3":  "Detail satu PTZ node: range gerakan, space koordinat, fixed atau bisa gerak",
    "4":  "Daftar semua konfigurasi PTZ yang tersimpan beserta parameternya",
    "5":  "Detail satu konfigurasi PTZ: default speed, timeout, batas koordinat",
    "6":  "Ubah konfigurasi PTZ: max speed, default timeout, batas pan/tilt/zoom",
    "7":  "Range koordinat yang valid: nilai min/max untuk pan, tilt, dan zoom",
    "8":  "Daftar konfigurasi PTZ yang bisa dipakai bersama media profile ini",
    "9":  "Posisi pan/tilt/zoom SAAT INI + status: bergerak / idle / di preset mana",
    "10": "Gerak KONTINU — kamera terus bergerak dengan kecepatan tertentu sampai Stop",
    "11": "HENTIKAN semua gerakan pan, tilt, dan zoom seketika",
    "12": "Gerak RELATIF — pindah sejauh nilai tertentu dari posisi sekarang",
    "13": "Gerak ke POSISI ABSOLUT — koordinat pasti antara -1.0 dan 1.0",
    "14": "Arahkan kamera ke koordinat GPS (lat/lon/elevation) — butuh sensor GPS",
    "15": "Daftar semua PRESET tersimpan — posisi favorit yang sudah diberi nama",
    "16": "Simpan posisi kamera SAAT INI sebagai preset baru dengan nama tertentu",
    "17": "Hapus preset yang sudah ada (permanen, tidak bisa dibatalkan)",
    "18": "Gerakkan kamera ke posisi PRESET yang sudah tersimpan",
    "19": "Kembalikan kamera ke posisi HOME (posisi default/awal)",
    "20": "Simpan posisi kamera saat ini sebagai posisi HOME baru",
    "21": "Daftar semua PRESET TOUR — tur patroli otomatis antar beberapa preset",
    "22": "Detail satu preset tour: daftar spot, urutan, kecepatan, durasi berhenti",
    "23": "Opsi konfigurasi yang tersedia untuk membuat dan mengatur preset tour",
    "24": "Buat PRESET TOUR baru (awalnya kosong, diisi dengan ModifyPresetTour)",
    "25": "Edit isi preset tour: tambah/ubah spot tujuan, kecepatan, durasi di tiap spot",
    "26": "Kontrol tour: Start (mulai patroli), Stop (hentikan), Pause (jeda)",
    "27": "Hapus preset tour yang sudah ada (permanen)",
    "28": "Kirim perintah AUX: nyalakan/matikan IR lamp, wiper, IR-cut filter, dll",
    "29": "Arahkan kamera ke GPS lalu aktifkan object tracking (lacak objek otomatis)",
}

# status: None=belum | "OK" | "FAULT" | "HTTP_ERR" | "CONN_ERR" | "TIMEOUT" | "SKIP"
op_status = {k: {"status": None, "detail": ""} for k in OP_NAMES}


def _set_status(op_key: str, status: str, detail: str = "") -> None:
    if op_key in op_status:
        op_status[op_key]["status"] = status
        op_status[op_key]["detail"] = detail


# ============================================================
# Live Stream
# ============================================================
_stop_stream = threading.Event()


def _stream_fn() -> None:
    if not CV2_AVAILABLE:
        print("[STREAM] cv2 tidak tersedia — install: pip install opencv-python")
        return
    cap = cv2.VideoCapture(STREAM_URL)
    if not cap.isOpened():
        print(f"[STREAM] Gagal membuka stream: {STREAM_URL}")
        return
    print(f"[STREAM] Live view aktif. Tekan Q di jendela untuk menutup.\n")
    while not _stop_stream.is_set():
        ret, frame = cap.read()
        if not ret:
            break
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        ok  = sum(1 for v in op_status.values() if v["status"] == "OK")
        bad = sum(1 for v in op_status.values() if v["status"] and v["status"] not in ("OK", "SKIP", None))
        cv2.putText(frame, f"PTZ Explorer | {CAMERA_IP}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"{ts}  Berhasil:{ok}  Gagal:{bad}",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
        cv2.imshow("V380 Live Stream", frame)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyWindow("V380 Live Stream")


def start_stream() -> None:
    _stop_stream.clear()
    threading.Thread(target=_stream_fn, daemon=True, name="stream").start()
    sleep(1.2)


def stop_stream() -> None:
    _stop_stream.set()


# ============================================================
# WS-Security
# ============================================================
def build_wssec_header(username: str, password: str) -> str:
    if not username:
        return ""
    nonce_raw  = os.urandom(16)
    nonce_b64  = base64.b64encode(nonce_raw).decode()
    created    = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest_raw = hashlib.sha1(
        nonce_raw + created.encode() + password.encode()
    ).digest()
    digest_b64 = base64.b64encode(digest_raw).decode()
    return (
        '<wsse:Security '
        'xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" '
        'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{username}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest_b64}</wsse:Password>"
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{nonce_b64}</wsse:Nonce>"
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken>"
        "</wsse:Security>"
    )


# ============================================================
# XML Template
# ============================================================
def load_xml(filename: str, params: Optional[dict] = None) -> str:
    with open(os.path.join(XML_DIR, filename), encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{AUTH_HEADER}", build_wssec_header(CAMERA_USER, CAMERA_PASS))
    if params:
        for k, v in params.items():
            content = content.replace("{" + k + "}", str(v))
    return content


# ============================================================
# SOAP Request
# ============================================================
def _pretty_xml(raw: str) -> str:
    try:
        lines = xml.dom.minidom.parseString(raw.encode()).toprettyxml(indent="  ").splitlines()
        return "\n".join(ln for ln in lines if ln.strip())
    except Exception:
        return raw


def _detect_result(text: str, http_code: int):
    if http_code != 200:
        return "HTTP_ERR", f"HTTP {http_code}"
    if re.search(r":Fault>|<Fault>", text):
        m = re.search(r"<(?:faultstring|Text|faultcode)>([^<]+)<", text, re.DOTALL)
        return "FAULT", (m.group(1).strip() if m else "SOAP Fault")
    return "OK", f"HTTP {http_code}"


def send_request(
    xml_body: str,
    operation_name: str = "",
    op_key: str = "",
    verbose: bool = True,
) -> Optional[requests.Response]:

    if verbose:
        sep = "=" * 64
        print(f"\n{sep}")
        print(f"  {operation_name}  [{PTZ_URL}]")
        print(sep)
        print(_pretty_xml(xml_body))

    try:
        resp = requests.post(PTZ_URL, data=xml_body.encode(), headers=HEADERS, timeout=5)
        status, detail = _detect_result(resp.text, resp.status_code)
        _set_status(op_key, status, detail)

        if verbose:
            marker = "OK" if status == "OK" else f"!!! {status}: {detail}"
            print(f"\n[{marker}]")
            print(_pretty_xml(resp.text))

        _log(operation_name, xml_body, resp.status_code, resp.text, status)
        return resp

    except requests.exceptions.ConnectionError:
        _set_status(op_key, "CONN_ERR", "Tidak bisa terhubung")
        if verbose:
            print(f"\n[ERROR] Tidak bisa terhubung ke {PTZ_URL}")
        _log(operation_name, xml_body, "CONN_ERR", "", "CONN_ERR")
    except requests.exceptions.Timeout:
        _set_status(op_key, "TIMEOUT", "Request timeout")
        if verbose:
            print(f"\n[ERROR] Timeout")
        _log(operation_name, xml_body, "TIMEOUT", "", "TIMEOUT")
    return None


def _log(op: str, req: str, http, resp: str, result: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'#'*70}\n# [{ts}] {op} | HTTP:{http} | {result}\n{'#'*70}\n")
        f.write(f"--- REQUEST ---\n{req}\n--- RESPONSE ---\n{resp}\n")


# ============================================================
# Token extractor
# ============================================================
def _extract_first_token(text: str) -> Optional[str]:
    # token="..." attribute
    m = re.search(r'\btoken\s*=\s*["\']([^"\']+)["\']', text)
    if m:
        return m.group(1)
    # <PresetToken>...</PresetToken> or <token>...</token>
    m = re.search(r'<(?:\w+:)?(?:PresetToken|PresetTourToken|token)>([^<]+)<', text)
    if m:
        return m.group(1).strip()
    return None


def _extract_all_tokens(text: str) -> list:
    return re.findall(r'\btoken\s*=\s*["\']([^"\']+)["\']', text)


# ============================================================
# AUTO-TEST — jalankan semua 29 operasi otomatis
# ============================================================
def auto_test_all() -> None:
    print("\n" + "=" * 64)
    print("  AUTO-TEST: Menguji semua 29 operasi ONVIF PTZ")
    print("  Kamera akan bergerak sebentar. Jangan matikan kamera.")
    print("=" * 64)

    found = {
        "node_token":        None,
        "config_token":      None,
        "preset_tokens":     [],
        "test_preset_token": None,
        "test_tour_token":   None,
        "tour_token":        None,
    }

    total = len(OP_NAMES)
    done  = [0]

    def step(op_key: str, xml_body: str, label: str) -> Optional[requests.Response]:
        done[0] += 1
        name = OP_NAMES.get(op_key, label)
        print(f"  [{done[0]:>2}/{total}] {name:<35} ... ", end="", flush=True)
        resp = send_request(xml_body, label, op_key, verbose=False)
        s = op_status[op_key]["status"]
        d = op_status[op_key]["detail"]
        icon = {"OK": "OK", "FAULT": "FAULT", "HTTP_ERR": "HTTP_ERR",
                "CONN_ERR": "KONEKSI GAGAL", "TIMEOUT": "TIMEOUT",
                "SKIP": "SKIP"}.get(s, s or "?")
        extra = f"  ({d})" if d and s != "OK" else ""
        print(f"{icon}{extra}")
        sleep(0.3)
        return resp

    def skip(op_key: str, reason: str) -> None:
        done[0] += 1
        name = OP_NAMES.get(op_key, op_key)
        _set_status(op_key, "SKIP", reason)
        print(f"  [{done[0]:>2}/{total}] {name:<35} ... SKIP  ({reason})")

    # ── Phase 1: Informasi & Discovery ──────────────────────
    print("\n[Phase 1] Informasi & Discovery")

    r = step("1", load_xml("01_get_service_capabilities.xml"), "GetServiceCapabilities")

    r = step("2", load_xml("02_get_nodes.xml"), "GetNodes")
    if r:
        tokens = _extract_all_tokens(r.text)
        if tokens:
            found["node_token"] = tokens[0]

    node_tok = found["node_token"] or "PTZNode_1"
    r = step("3", load_xml("03_get_node.xml", {"NODE_TOKEN": node_tok}), "GetNode")

    r = step("4", load_xml("04_get_configurations.xml"), "GetConfigurations")
    if r:
        tokens = _extract_all_tokens(r.text)
        if tokens:
            found["config_token"] = tokens[0]

    cfg = found["config_token"] or "PTZConfig_000"

    r = step("5", load_xml("05_get_configuration.xml", {"CONFIG_TOKEN": cfg}), "GetConfiguration")

    skip("6", "Terlalu berisiko untuk auto-test — gunakan manual")

    r = step("7", load_xml("07_get_configuration_options.xml", {"CONFIG_TOKEN": cfg}), "GetConfigurationOptions")

    r = step("8", load_xml("28_get_compatible_configurations.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetCompatibleConfigurations")

    # ── Phase 2: Status ──────────────────────────────────────
    print("\n[Phase 2] Status Kamera")

    r = step("9", load_xml("13_get_status.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetStatus")

    # ── Phase 3: Preset Discovery ────────────────────────────
    print("\n[Phase 3] Preset")

    r = step("15", load_xml("09_get_presets.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresets")
    if r:
        found["preset_tokens"] = _extract_all_tokens(r.text)

    # Simpan posisi saat ini sebagai test preset
    r = step("16", load_xml("10_set_preset.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "PRESET_NAME": "AutoTest_Preset",
    }), "SetPreset")
    if r and op_status["16"]["status"] == "OK":
        m = re.search(r'<(?:\w+:)?PresetToken>([^<]+)<', r.text)
        if m:
            found["test_preset_token"] = m.group(1).strip()
        elif found["preset_tokens"]:
            found["test_preset_token"] = found["preset_tokens"][0]

    preset_tok = found["test_preset_token"]

    if preset_tok:
        step("18", load_xml("12_goto_preset.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN,
            "PRESET_TOKEN": preset_tok,
            "SPEED": "0.5",
        }), "GotoPreset")
        sleep(0.5)
    else:
        skip("18", "Tidak ada PresetToken ditemukan")

    step("19", load_xml("14_goto_home_position.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "SPEED": "0.5",
    }), "GotoHomePosition")
    sleep(0.5)

    step("20", load_xml("15_set_home_position.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "SetHomePosition")

    # Hapus test preset (cleanup)
    if found["test_preset_token"]:
        step("17", load_xml("11_remove_preset.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN,
            "PRESET_TOKEN": found["test_preset_token"],
        }), "RemovePreset")
    else:
        skip("17", "Tidak ada test preset untuk dihapus")

    # ── Phase 4: Gerakan ─────────────────────────────────────
    print("\n[Phase 4] Gerakan (kamera akan bergerak)")

    step("10", load_xml("16_continuous_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "PAN": "0.3", "TILT": "0", "ZOOM": "0",
    }), "ContinuousMove")
    sleep(MOVE_DURATION)

    step("11", load_xml("20_stop.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "Stop")
    sleep(0.2)

    step("12", load_xml("17_relative_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "PAN": "0.05", "TILT": "0", "ZOOM": "0",
    }), "RelativeMove")
    sleep(0.5)

    step("13", load_xml("18_absolute_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "PAN": "0", "TILT": "0", "ZOOM": "0",
    }), "AbsoluteMove")
    sleep(0.3)

    step("14", load_xml("19_geo_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "LAT": "-6.2", "LON": "106.8", "ELEVATION": "10",
    }), "GeoMove")

    # ── Phase 5: Preset Tour ─────────────────────────────────
    print("\n[Phase 5] Preset Tour (Patroli Otomatis)")

    r = step("21", load_xml("21_get_preset_tours.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresetTours")
    if r:
        tokens = _extract_all_tokens(r.text)
        if tokens:
            found["tour_token"] = tokens[0]

    r = step("23", load_xml("23_get_preset_tour_options.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresetTourOptions")

    r = step("24", load_xml("24_create_preset_tour.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "CreatePresetTour")
    if r and op_status["24"]["status"] == "OK":
        tok = _extract_first_token(r.text)
        if tok:
            found["test_tour_token"] = tok

    tour_tok = found["test_tour_token"] or found["tour_token"]

    if tour_tok:
        step("22", load_xml("22_get_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN,
            "TOUR_TOKEN": tour_tok,
        }), "GetPresetTour")

        if found["preset_tokens"]:
            step("25", load_xml("25_modify_preset_tour.xml", {
                "PROFILE_TOKEN":  PROFILE_TOKEN,
                "TOUR_TOKEN":     tour_tok,
                "TOUR_NAME":      "AutoTest_Tour",
                "PRESET_TOKEN":   found["preset_tokens"][0],
            }), "ModifyPresetTour")
        else:
            skip("25", "Tidak ada preset untuk TourSpot")

        step("26", load_xml("26_operate_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN,
            "TOUR_TOKEN": tour_tok,
            "OPERATION": "Start",
        }), "OperatePresetTour(Start)")
        sleep(0.5)

        # Stop tour segera
        requests.post(PTZ_URL, data=load_xml("26_operate_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN,
            "TOUR_TOKEN": tour_tok,
            "OPERATION": "Stop",
        }).encode(), headers=HEADERS, timeout=5)

        # Hapus test tour (cleanup)
        if found["test_tour_token"]:
            step("27", load_xml("27_remove_preset_tour.xml", {
                "PROFILE_TOKEN": PROFILE_TOKEN,
                "TOUR_TOKEN": found["test_tour_token"],
            }), "RemovePresetTour")
        else:
            skip("27", "Tour bukan buatan test, tidak dihapus")
    else:
        for k in ["22", "25", "26", "27"]:
            skip(k, "Tidak ada TourToken")

    # ── Phase 6: Lainnya ─────────────────────────────────────
    print("\n[Phase 6] Lainnya")

    step("28", load_xml("08_send_auxiliary_command.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "AUX_COMMAND": "tt:IRLamp|On",
    }), "SendAuxiliaryCommand")

    step("29", load_xml("29_move_and_start_tracking.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN,
        "LAT": "-6.2", "LON": "106.8", "ELEVATION": "10",
    }), "MoveAndStartTracking")

    show_final_report()


# ============================================================
# Laporan Akhir
# ============================================================
def show_final_report() -> None:
    ok_list, fault_list, err_list, skip_list = [], [], [], []

    for key in sorted(OP_NAMES, key=lambda x: int(x)):
        name = OP_NAMES[key]
        s    = op_status[key]["status"]
        d    = op_status[key]["detail"]
        desc = OP_DESCRIPTIONS.get(key, "")
        entry = (key, name, d, desc)
        if s == "OK":
            ok_list.append(entry)
        elif s == "FAULT":
            fault_list.append(entry)
        elif s in ("HTTP_ERR", "CONN_ERR", "TIMEOUT"):
            err_list.append(entry)
        else:
            skip_list.append(entry)

    bar = "=" * 68

    print(f"\n\n{bar}")
    print("  LAPORAN HASIL AUTO-TEST — ONVIF PTZ EXPLORER")
    print(bar)

    # --- Yang berhasil ---
    print(f"\n  DIDUKUNG KAMERA ({len(ok_list)}/{len(OP_NAMES)} operasi):\n")
    if ok_list:
        for key, name, _, desc in ok_list:
            print(f"  [{key:>2}] {name}")
            print(f"        {desc}\n")
    else:
        print("  Tidak ada operasi yang berhasil.\n")

    # --- SOAP Fault ---
    if fault_list:
        print(f"\n  TIDAK DIDUKUNG / SOAP FAULT ({len(fault_list)} operasi):\n")
        for key, name, detail, desc in fault_list:
            print(f"  [{key:>2}] {name}")
            print(f"        Fungsi : {desc}")
            print(f"        Error  : {detail}\n")

    # --- Error koneksi ---
    if err_list:
        print(f"\n  ERROR KONEKSI / HTTP ({len(err_list)} operasi):\n")
        for key, name, detail, desc in err_list:
            print(f"  [{key:>2}] {name}  —  {detail}")

    # --- Skip ---
    if skip_list:
        print(f"\n  DILEWATI ({len(skip_list)} operasi):\n")
        for key, name, detail, _ in skip_list:
            print(f"  [{key:>2}] {name}  —  {detail or 'Belum dicoba'}")

    print(f"\n{bar}")
    ok_n   = len(ok_list)
    flt_n  = len(fault_list)
    err_n  = len(err_list)
    skp_n  = len(skip_list)
    print(f"  RINGKASAN:  Berhasil {ok_n}  |  Tidak didukung {flt_n}  "
          f"|  Error {err_n}  |  Skip {skp_n}")
    print(f"  Log lengkap disimpan di: {LOG_FILE}")
    print(bar)


# ============================================================
# Status table (ringkas, untuk tampilan menu)
# ============================================================
def show_status_table() -> None:
    icons = {
        None:       "  - ",
        "OK":       "[ OK]",
        "FAULT":    "[FLT]",
        "HTTP_ERR": "[ERR]",
        "CONN_ERR": "[CON]",
        "TIMEOUT":  "[TMO]",
        "SKIP":     "[SKP]",
    }
    print("\n" + "-" * 68)
    cols = [
        ["1","2","3","4","5","6","7","8","9","10"],
        ["11","12","13","14","15","16","17","18","19","20"],
        ["21","22","23","24","25","26","27","28","29"],
    ]
    for row in cols:
        line = ""
        for k in row:
            icon = icons.get(op_status[k]["status"], "[ ? ]")
            line += f" {icon} {k:>2}.{OP_NAMES[k][:14]:<14}"
        print(line)

    ok  = sum(1 for v in op_status.values() if v["status"] == "OK")
    bad = sum(1 for v in op_status.values() if v["status"] in ("FAULT","HTTP_ERR","CONN_ERR","TIMEOUT"))
    skp = sum(1 for v in op_status.values() if v["status"] in (None, "SKIP"))
    print(f"  Berhasil:{ok}  Gagal:{bad}  Belum/Skip:{skp}")
    print("-" * 68)


# ============================================================
# 29 Operasi Manual
# ============================================================
def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def confirm(prompt: str) -> bool:
    return ask(prompt + " (y/n)", "n").lower() == "y"


def op_get_service_capabilities():
    send_request(load_xml("01_get_service_capabilities.xml"), "GetServiceCapabilities", "1")

def op_get_nodes():
    send_request(load_xml("02_get_nodes.xml"), "GetNodes", "2")

def op_get_node():
    t = ask("NodeToken", "PTZNode_1")
    send_request(load_xml("03_get_node.xml", {"NODE_TOKEN": t}), "GetNode", "3")

def op_get_configurations():
    send_request(load_xml("04_get_configurations.xml"), "GetConfigurations", "4")

def op_get_configuration():
    t = ask("PTZConfigurationToken", "PTZConfig_000")
    send_request(load_xml("05_get_configuration.xml", {"CONFIG_TOKEN": t}), "GetConfiguration", "5")

def op_set_configuration():
    print("  PERINGATAN: Ubah konfigurasi PTZ kamera.")
    if not confirm("Lanjutkan?"):
        return
    t = ask("PTZConfigurationToken", "PTZConfig_000")
    s = ask("Max Speed (0.0-1.0)", "1.0")
    send_request(load_xml("06_set_configuration.xml", {
        "CONFIG_TOKEN": t, "PROFILE_TOKEN": PROFILE_TOKEN, "MAX_SPEED": s,
    }), "SetConfiguration", "6")

def op_get_configuration_options():
    t = ask("PTZConfigurationToken", "PTZConfig_000")
    send_request(load_xml("07_get_configuration_options.xml", {"CONFIG_TOKEN": t}), "GetConfigurationOptions", "7")

def op_get_compatible_configurations():
    send_request(load_xml("28_get_compatible_configurations.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetCompatibleConfigurations", "8")

def op_get_status():
    send_request(load_xml("13_get_status.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetStatus", "9")

def op_continuous_move():
    print("  [1]Atas [2]Bawah [3]Kiri [4]Kanan [5]ZoomIn [6]ZoomOut [7]Kustom")
    ch = ask("Pilih", "1")
    m  = {"1":("0","0.5","0"),"2":("0","-0.5","0"),"3":("-0.5","0","0"),
          "4":("0.5","0","0"),"5":("0","0","0.5"),"6":("0","0","-0.5")}
    pan, tilt, zoom = m.get(ch, (ask("Pan","0"), ask("Tilt","0"), ask("Zoom","0")))
    send_request(load_xml("16_continuous_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "PAN": pan, "TILT": tilt, "ZOOM": zoom,
    }), "ContinuousMove", "10")
    sleep(MOVE_DURATION)
    send_request(load_xml("20_stop.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "Stop", "11")

def op_stop():
    send_request(load_xml("20_stop.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "Stop", "11")

def op_relative_move():
    pan  = ask("Pan Translation (-1 s/d 1)", "0.1")
    tilt = ask("Tilt Translation (-1 s/d 1)", "0")
    zoom = ask("Zoom Translation (-1 s/d 1)", "0")
    send_request(load_xml("17_relative_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "PAN": pan, "TILT": tilt, "ZOOM": zoom,
    }), "RelativeMove", "12")

def op_absolute_move():
    print("  CATATAN: Kemungkinan tidak didukung V380.")
    pan  = ask("Pan Position (-1 s/d 1)", "0")
    tilt = ask("Tilt Position (-1 s/d 1)", "0")
    zoom = ask("Zoom Position (0 s/d 1)", "0")
    send_request(load_xml("18_absolute_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "PAN": pan, "TILT": tilt, "ZOOM": zoom,
    }), "AbsoluteMove", "13")

def op_geo_move():
    lat  = ask("Latitude", "-6.2")
    lon  = ask("Longitude", "106.8")
    elev = ask("Elevation", "10")
    send_request(load_xml("19_geo_move.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "LAT": lat, "LON": lon, "ELEVATION": elev,
    }), "GeoMove", "14")

def op_get_presets():
    send_request(load_xml("09_get_presets.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresets", "15")

def op_set_preset():
    name = ask("Nama preset", "MyPreset")
    send_request(load_xml("10_set_preset.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "PRESET_NAME": name,
    }), "SetPreset", "16")

def op_remove_preset():
    t = ask("PresetToken")
    if not t:
        return
    if confirm(f"Hapus preset '{t}'?"):
        send_request(load_xml("11_remove_preset.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN, "PRESET_TOKEN": t,
        }), "RemovePreset", "17")

def op_goto_preset():
    t = ask("PresetToken")
    if not t:
        return
    s = ask("Speed", "0.5")
    send_request(load_xml("12_goto_preset.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "PRESET_TOKEN": t, "SPEED": s,
    }), "GotoPreset", "18")

def op_goto_home():
    s = ask("Speed", "0.5")
    send_request(load_xml("14_goto_home_position.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "SPEED": s,
    }), "GotoHomePosition", "19")

def op_set_home():
    if confirm("Simpan posisi saat ini sebagai Home?"):
        send_request(load_xml("15_set_home_position.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "SetHomePosition", "20")

def op_get_preset_tours():
    send_request(load_xml("21_get_preset_tours.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresetTours", "21")

def op_get_preset_tour():
    t = ask("TourToken")
    if t:
        send_request(load_xml("22_get_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN, "TOUR_TOKEN": t,
        }), "GetPresetTour", "22")

def op_get_preset_tour_options():
    send_request(load_xml("23_get_preset_tour_options.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "GetPresetTourOptions", "23")

def op_create_preset_tour():
    send_request(load_xml("24_create_preset_tour.xml", {"PROFILE_TOKEN": PROFILE_TOKEN}), "CreatePresetTour", "24")

def op_modify_preset_tour():
    tt = ask("TourToken")
    tn = ask("Nama Tour", "PatroliTour")
    pt = ask("PresetToken untuk spot")
    if tt and pt:
        send_request(load_xml("25_modify_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN, "TOUR_TOKEN": tt,
            "TOUR_NAME": tn, "PRESET_TOKEN": pt,
        }), "ModifyPresetTour", "25")

def op_operate_preset_tour():
    t = ask("TourToken")
    if not t:
        return
    print("  [1]Start  [2]Stop  [3]Pause")
    op = {"1":"Start","2":"Stop","3":"Pause"}.get(ask("Pilih","2"), "Stop")
    send_request(load_xml("26_operate_preset_tour.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "TOUR_TOKEN": t, "OPERATION": op,
    }), f"OperatePresetTour ({op})", "26")

def op_remove_preset_tour():
    t = ask("TourToken")
    if t and confirm(f"Hapus tour '{t}'?"):
        send_request(load_xml("27_remove_preset_tour.xml", {
            "PROFILE_TOKEN": PROFILE_TOKEN, "TOUR_TOKEN": t,
        }), "RemovePresetTour", "27")

def op_send_auxiliary():
    print("  Contoh: tt:IRLamp|On  tt:IRLamp|Off  tt:IRCutFilter|on  tt:Wiper|start")
    cmd = ask("AuxiliaryData", "tt:IRLamp|On")
    send_request(load_xml("08_send_auxiliary_command.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "AUX_COMMAND": cmd,
    }), "SendAuxiliaryCommand", "28")

def op_move_and_start_tracking():
    lat  = ask("Latitude", "-6.2")
    lon  = ask("Longitude", "106.8")
    elev = ask("Elevation", "10")
    send_request(load_xml("29_move_and_start_tracking.xml", {
        "PROFILE_TOKEN": PROFILE_TOKEN, "LAT": lat, "LON": lon, "ELEVATION": elev,
    }), "MoveAndStartTracking", "29")


OPERATIONS = {
    "1":  op_get_service_capabilities,  "2":  op_get_nodes,
    "3":  op_get_node,                  "4":  op_get_configurations,
    "5":  op_get_configuration,         "6":  op_set_configuration,
    "7":  op_get_configuration_options, "8":  op_get_compatible_configurations,
    "9":  op_get_status,                "10": op_continuous_move,
    "11": op_stop,                      "12": op_relative_move,
    "13": op_absolute_move,             "14": op_geo_move,
    "15": op_get_presets,               "16": op_set_preset,
    "17": op_remove_preset,             "18": op_goto_preset,
    "19": op_goto_home,                 "20": op_set_home,
    "21": op_get_preset_tours,          "22": op_get_preset_tour,
    "23": op_get_preset_tour_options,   "24": op_create_preset_tour,
    "25": op_modify_preset_tour,        "26": op_operate_preset_tour,
    "27": op_remove_preset_tour,        "28": op_send_auxiliary,
    "29": op_move_and_start_tracking,
}

MENU = """
+------------------------------------------------------------------+
|       ONVIF PTZ EXPLORER  —  V380 / Kamera ONVIF                |
+------------------------------------------------------------------+
 INFO       1-GetCapabilities  2-GetNodes    3-GetNode
            4-GetConfigs       5-GetConfig   6-SetConfig(!)
            7-GetConfigOpts    8-GetCompatibleConfig
 STATUS     9-GetStatus
 GERAK     10-ContinuousMove  11-Stop       12-RelativeMove
           13-AbsoluteMove    14-GeoMove
 PRESET    15-GetPresets      16-SetPreset(!) 17-RemovePreset(!)
           18-GotoPreset      19-GotoHome     20-SetHome(!)
 TOUR      21-GetTours  22-GetTour  23-GetTourOptions
           24-CreateTour(!)  25-ModifyTour(!)
           26-OperateTour(!) 27-RemoveTour(!)
 LAINNYA   28-AuxiliaryCommand(!)  29-MoveAndTrack(!)
------------------------------------------------------------------
  T  AUTO-TEST semua 29 operasi (otomatis + laporan lengkap)
  R  Tampilkan laporan hasil test
  S  Tampilkan status ringkas
  V  Buka/restart live stream kamera
  Q  Keluar
"""


def main() -> None:
    print(f"\nONVIF PTZ Explorer")
    print(f"URL  : {PTZ_URL}")
    print(f"Log  : {os.path.abspath(LOG_FILE)}")
    print("\nMembuka live stream...")
    start_stream()

    while True:
        show_status_table()
        print(MENU)
        choice = input("Pilih (1-29 / T / R / S / V / Q): ").strip().upper()

        if choice == "Q":
            stop_stream()
            print("Selesai.")
            break
        elif choice == "T":
            auto_test_all()
        elif choice == "R":
            show_final_report()
        elif choice == "S":
            show_status_table()
        elif choice == "V":
            start_stream()
        elif choice in OPERATIONS:
            try:
                OPERATIONS[choice]()
            except KeyboardInterrupt:
                print("\n[INTERRUPT] Mengirim Stop...")
                try:
                    op_stop()
                except Exception:
                    pass
        else:
            print(f"  Pilihan '{choice}' tidak valid.")


if __name__ == "__main__":
    main()
