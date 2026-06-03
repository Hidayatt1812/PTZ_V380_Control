#!/usr/bin/env python3
"""
ptz_solo.py — Semua 29 operasi ONVIF PTZ dalam SATU FILE
Tidak butuh folder xml/ — semua SOAP template sudah inline di sini.

Operasi yang digabungkan (COMBINED):
  C1  scan_camera()         = 1+2+4+7+8+9+15+21+23  (semua read-only)
  C2  move(arah, detik)     = 10 ContinuousMove + 11 Stop
  C3  full_move_test()      = 10+11+12+13+14  (semua jenis gerakan)
  C4  preset_cycle(nama)    = 16 SetPreset + 18 GotoPreset + 17 RemovePreset
  C5  discover_tokens()     = 2+4+15+21  (kumpulkan semua token)
  C6  patrol(preset_list)   = 24+25+26+27  (buat tour, jalankan, hapus)
  C7  camera_info()         = 1+2+4+9  (snapshot info kamera lengkap)
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
STREAM_URL    = f"rtsp://{CAMERA_IP}:554/onvif/profile1/media.smp"
MOVE_DURATION = 0.4
LOG_FILE      = os.path.join(os.path.dirname(__file__), "ptz_solo.log")

HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction":   '""',
}

# ============================================================
# SOAP TEMPLATES — semua 29 operasi inline sebagai Python string
# Placeholder: {AUTH_HEADER}, {PROFILE_TOKEN}, dll
# ============================================================

def _env(body: str) -> str:
    """Bungkus body dengan SOAP Envelope + inject WS-Security."""
    auth = _wssec(CAMERA_USER, CAMERA_PASS)
    return (
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"<s:Header>{auth}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )

# Shortcut namespace
_PTZ  = 'xmlns="http://www.onvif.org/ver20/ptz/wsdl"'
_SCH  = 'xmlns="http://www.onvif.org/ver10/schema"'
_SCHp = 'xmlns:tt="http://www.onvif.org/ver10/schema"'

# ── 1. GetServiceCapabilities ──────────────────────────────
def xml_get_service_capabilities() -> str:
    return _env(f'<GetServiceCapabilities {_PTZ}/>')

# ── 2. GetNodes ────────────────────────────────────────────
def xml_get_nodes() -> str:
    return _env(f'<GetNodes {_PTZ}/>')

# ── 3. GetNode ─────────────────────────────────────────────
def xml_get_node(node_token: str) -> str:
    return _env(
        f'<GetNode {_PTZ}>'
        f'<NodeToken>{node_token}</NodeToken>'
        f'</GetNode>'
    )

# ── 4. GetConfigurations ───────────────────────────────────
def xml_get_configurations() -> str:
    return _env(f'<GetConfigurations {_PTZ}/>')

# ── 5. GetConfiguration ────────────────────────────────────
def xml_get_configuration(config_token: str) -> str:
    return _env(
        f'<GetConfiguration {_PTZ}>'
        f'<PTZConfigurationToken>{config_token}</PTZConfigurationToken>'
        f'</GetConfiguration>'
    )

# ── 6. SetConfiguration ────────────────────────────────────
def xml_set_configuration(config_token: str, max_speed: str = "1.0") -> str:
    return _env(
        f'<SetConfiguration {_PTZ}>'
        f'<PTZConfiguration token="{config_token}">'
        f'<Name>PTZConfig</Name>'
        f'<UseCount>1</UseCount>'
        f'<NodeToken>PTZNode_1</NodeToken>'
        f'<DefaultAbsolutePantTiltPositionSpace>'
        f'http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace'
        f'</DefaultAbsolutePantTiltPositionSpace>'
        f'<DefaultContinuousPanTiltVelocitySpace>'
        f'http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace'
        f'</DefaultContinuousPanTiltVelocitySpace>'
        f'<DefaultPTZSpeed {_SCHp}>'
        f'<tt:PanTilt x="{max_speed}" y="{max_speed}"/>'
        f'<tt:Zoom x="{max_speed}"/>'
        f'</DefaultPTZSpeed>'
        f'<DefaultPTZTimeout>PT1S</DefaultPTZTimeout>'
        f'<PanTiltLimits {_SCHp}>'
        f'<tt:Range>'
        f'<tt:URI>http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace</tt:URI>'
        f'<tt:XRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:XRange>'
        f'<tt:YRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:YRange>'
        f'</tt:Range></PanTiltLimits>'
        f'<ZoomLimits {_SCHp}>'
        f'<tt:Range>'
        f'<tt:URI>http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace</tt:URI>'
        f'<tt:XRange><tt:Min>0</tt:Min><tt:Max>1</tt:Max></tt:XRange>'
        f'</tt:Range></ZoomLimits>'
        f'</PTZConfiguration>'
        f'<ForcePersistence>true</ForcePersistence>'
        f'</SetConfiguration>'
    )

# ── 7. GetConfigurationOptions ─────────────────────────────
def xml_get_configuration_options(config_token: str) -> str:
    return _env(
        f'<GetConfigurationOptions {_PTZ}>'
        f'<ConfigurationToken>{config_token}</ConfigurationToken>'
        f'</GetConfigurationOptions>'
    )

# ── 8. GetCompatibleConfigurations ─────────────────────────
def xml_get_compatible_configurations(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetCompatibleConfigurations {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</GetCompatibleConfigurations>'
    )

# ── 9. GetStatus ───────────────────────────────────────────
def xml_get_status(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetStatus {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</GetStatus>'
    )

# ── 10. ContinuousMove ─────────────────────────────────────
def xml_continuous_move(pan: float, tilt: float, zoom: float = 0,
                         profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<ContinuousMove {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<Velocity>'
        f'<PanTilt x="{pan}" y="{tilt}" {_SCH}/>'
        f'<Zoom x="{zoom}" {_SCH}/>'
        f'</Velocity>'
        f'</ContinuousMove>'
    )

# ── 11. Stop ───────────────────────────────────────────────
def xml_stop(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<Stop {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PanTilt>true</PanTilt>'
        f'<Zoom>true</Zoom>'
        f'</Stop>'
    )

# ── 12. RelativeMove ───────────────────────────────────────
def xml_relative_move(pan: float, tilt: float, zoom: float = 0,
                       speed: float = 0.5, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<RelativeMove {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<Translation>'
        f'<PanTilt x="{pan}" y="{tilt}" {_SCH}/>'
        f'<Zoom x="{zoom}" {_SCH}/>'
        f'</Translation>'
        f'<Speed>'
        f'<PanTilt x="{speed}" y="{speed}" {_SCH}/>'
        f'<Zoom x="{speed}" {_SCH}/>'
        f'</Speed>'
        f'</RelativeMove>'
    )

# ── 13. AbsoluteMove ───────────────────────────────────────
def xml_absolute_move(pan: float, tilt: float, zoom: float = 0,
                       speed: float = 0.5, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<AbsoluteMove {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<Position>'
        f'<PanTilt x="{pan}" y="{tilt}" {_SCH}/>'
        f'<Zoom x="{zoom}" {_SCH}/>'
        f'</Position>'
        f'<Speed>'
        f'<PanTilt x="{speed}" y="{speed}" {_SCH}/>'
        f'<Zoom x="{speed}" {_SCH}/>'
        f'</Speed>'
        f'</AbsoluteMove>'
    )

# ── 14. GeoMove ────────────────────────────────────────────
def xml_geo_move(lat: float, lon: float, elevation: float = 0,
                  profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GeoMove {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<Target {_SCHp}>'
        f'<tt:Lat>{lat}</tt:Lat>'
        f'<tt:Lon>{lon}</tt:Lon>'
        f'<tt:Elevation>{elevation}</tt:Elevation>'
        f'</Target>'
        f'</GeoMove>'
    )

# ── 15. GetPresets ─────────────────────────────────────────
def xml_get_presets(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetPresets {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</GetPresets>'
    )

# ── 16. SetPreset ──────────────────────────────────────────
def xml_set_preset(name: str, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<SetPreset {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetName>{name}</PresetName>'
        f'</SetPreset>'
    )

# ── 17. RemovePreset ───────────────────────────────────────
def xml_remove_preset(preset_token: str, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<RemovePreset {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetToken>{preset_token}</PresetToken>'
        f'</RemovePreset>'
    )

# ── 18. GotoPreset ─────────────────────────────────────────
def xml_goto_preset(preset_token: str, speed: float = 0.5,
                     profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GotoPreset {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetToken>{preset_token}</PresetToken>'
        f'<Speed>'
        f'<PanTilt x="{speed}" y="{speed}" {_SCH}/>'
        f'<Zoom x="{speed}" {_SCH}/>'
        f'</Speed>'
        f'</GotoPreset>'
    )

# ── 19. GotoHomePosition ───────────────────────────────────
def xml_goto_home(speed: float = 0.5, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GotoHomePosition {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<Speed>'
        f'<PanTilt x="{speed}" y="{speed}" {_SCH}/>'
        f'<Zoom x="{speed}" {_SCH}/>'
        f'</Speed>'
        f'</GotoHomePosition>'
    )

# ── 20. SetHomePosition ────────────────────────────────────
def xml_set_home(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<SetHomePosition {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</SetHomePosition>'
    )

# ── 21. GetPresetTours ─────────────────────────────────────
def xml_get_preset_tours(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetPresetTours {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</GetPresetTours>'
    )

# ── 22. GetPresetTour ──────────────────────────────────────
def xml_get_preset_tour(tour_token: str, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetPresetTour {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetTourToken>{tour_token}</PresetTourToken>'
        f'</GetPresetTour>'
    )

# ── 23. GetPresetTourOptions ───────────────────────────────
def xml_get_preset_tour_options(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<GetPresetTourOptions {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</GetPresetTourOptions>'
    )

# ── 24. CreatePresetTour ───────────────────────────────────
def xml_create_preset_tour(profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<CreatePresetTour {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'</CreatePresetTour>'
    )

# ── 25. ModifyPresetTour ───────────────────────────────────
def xml_modify_preset_tour(tour_token: str, preset_tokens: list,
                            name: str = "Patroli", stay_sec: int = 5,
                            speed: float = 0.5,
                            profile: str = PROFILE_TOKEN) -> str:
    spots = "".join(
        f'<TourSpot>'
        f'<PresetDetail><PresetToken>{pt}</PresetToken></PresetDetail>'
        f'<Speed><PanTilt x="{speed}" y="{speed}" {_SCH}/></Speed>'
        f'<StayTime>PT{stay_sec}S</StayTime>'
        f'</TourSpot>'
        for pt in preset_tokens
    )
    return _env(
        f'<ModifyPresetTour {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetTour {_SCHp}>'
        f'<token>{tour_token}</token>'
        f'<Name>{name}</Name>'
        f'<StartingCondition>'
        f'<tt:RecurringTime>0</tt:RecurringTime>'
        f'<tt:RecurringDuration>PT0S</tt:RecurringDuration>'
        f'<tt:Direction>Forward</tt:Direction>'
        f'</StartingCondition>'
        f'{spots}'
        f'</PresetTour>'
        f'</ModifyPresetTour>'
    )

# ── 26. OperatePresetTour ──────────────────────────────────
def xml_operate_preset_tour(tour_token: str, operation: str = "Start",
                              profile: str = PROFILE_TOKEN) -> str:
    # operation: "Start" | "Stop" | "Pause"
    return _env(
        f'<OperatePresetTour {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetTourToken>{tour_token}</PresetTourToken>'
        f'<Operation>{operation}</Operation>'
        f'</OperatePresetTour>'
    )

# ── 27. RemovePresetTour ───────────────────────────────────
def xml_remove_preset_tour(tour_token: str, profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<RemovePresetTour {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<PresetTourToken>{tour_token}</PresetTourToken>'
        f'</RemovePresetTour>'
    )

# ── 28. SendAuxiliaryCommand ───────────────────────────────
def xml_send_auxiliary(command: str, profile: str = PROFILE_TOKEN) -> str:
    # command: "tt:IRLamp|On" | "tt:IRLamp|Off" | "tt:IRCutFilter|on" | dll
    return _env(
        f'<SendAuxiliaryCommand {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<AuxiliaryData>{command}</AuxiliaryData>'
        f'</SendAuxiliaryCommand>'
    )

# ── 29. MoveAndStartTracking ───────────────────────────────
def xml_move_and_start_tracking(lat: float, lon: float, elevation: float = 0,
                                  profile: str = PROFILE_TOKEN) -> str:
    return _env(
        f'<MoveAndStartTracking {_PTZ}>'
        f'<ProfileToken>{profile}</ProfileToken>'
        f'<GeoLocation {_SCHp}>'
        f'<tt:Lat>{lat}</tt:Lat>'
        f'<tt:Lon>{lon}</tt:Lon>'
        f'<tt:Elevation>{elevation}</tt:Elevation>'
        f'</GeoLocation>'
        f'</MoveAndStartTracking>'
    )


# ============================================================
# WS-Security PasswordDigest
# ============================================================
def _wssec(username: str, password: str) -> str:
    if not username:
        return ""
    nonce_raw  = os.urandom(16)
    nonce_b64  = base64.b64encode(nonce_raw).decode()
    created    = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest_b64 = base64.b64encode(
        hashlib.sha1(nonce_raw + created.encode() + password.encode()).digest()
    ).decode()
    ns_wsse = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    ns_wsu  = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    ns_pt   = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
    ns_b64  = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
    return (
        f'<wsse:Security xmlns:wsse="{ns_wsse}" xmlns:wsu="{ns_wsu}">'
        f'<wsse:UsernameToken>'
        f'<wsse:Username>{username}</wsse:Username>'
        f'<wsse:Password Type="{ns_pt}">{digest_b64}</wsse:Password>'
        f'<wsse:Nonce EncodingType="{ns_b64}">{nonce_b64}</wsse:Nonce>'
        f'<wsu:Created>{created}</wsu:Created>'
        f'</wsse:UsernameToken>'
        f'</wsse:Security>'
    )


# ============================================================
# HTTP Request
# ============================================================
op_results: dict = {}   # {label: {"status": str, "detail": str}}


def _pretty(raw: str) -> str:
    try:
        lines = xml.dom.minidom.parseString(raw.encode()).toprettyxml("  ").splitlines()
        return "\n".join(ln for ln in lines if ln.strip())
    except Exception:
        return raw[:800]


def _detect(text: str, code: int):
    if code != 200:
        return "HTTP_ERR", f"HTTP {code}"
    if re.search(r":Fault>|<Fault>", text):
        m = re.search(r"<(?:faultstring|Text|faultcode)>([^<]+)<", text)
        return "FAULT", (m.group(1).strip() if m else "SOAP Fault")
    return "OK", f"HTTP {code}"


def send(xml_body: str, label: str, verbose: bool = True) -> Optional[requests.Response]:
    if verbose:
        print(f"\n{'='*60}\n  {label}\n{'='*60}")
        print(_pretty(xml_body))

    try:
        r = requests.post(PTZ_URL, data=xml_body.encode(), headers=HEADERS, timeout=5)
        status, detail = _detect(r.text, r.status_code)
        op_results[label] = {"status": status, "detail": detail}

        if verbose:
            tag = "OK" if status == "OK" else f"!!! {status}: {detail}"
            print(f"\n[{tag}]")
            print(_pretty(r.text))

        _log(label, xml_body, r.status_code, r.text, status)
        return r

    except requests.exceptions.ConnectionError:
        op_results[label] = {"status": "CONN_ERR", "detail": "Tidak bisa terhubung"}
        if verbose:
            print(f"\n[ERROR] Tidak bisa terhubung ke {PTZ_URL}")
    except requests.exceptions.Timeout:
        op_results[label] = {"status": "TIMEOUT", "detail": "Timeout"}
        if verbose:
            print(f"\n[ERROR] Timeout")
    return None


def _log(label: str, req: str, code, resp: str, result: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'#'*70}\n# [{ts}] {label} | {result}\n{'#'*70}\n")
        f.write(f"--- REQUEST ---\n{req}\n--- RESPONSE ---\n{resp}\n")


# ============================================================
# Token extractor
# ============================================================
def _first_token(text: str) -> Optional[str]:
    m = re.search(r'\btoken\s*=\s*["\']([^"\']+)["\']', text)
    if m:
        return m.group(1)
    m = re.search(r'<(?:\w+:)?(?:PresetToken|PresetTourToken|token)>([^<]+)<', text)
    return m.group(1).strip() if m else None


def _all_tokens(text: str) -> list:
    return re.findall(r'\btoken\s*=\s*["\']([^"\']+)["\']', text)


# ============================================================
# ╔══════════════════════════════════════════════════════╗
# ║   OPERASI GABUNGAN — hasil temuan yang bisa digabung ║
# ╚══════════════════════════════════════════════════════╝
# ============================================================

def camera_info() -> dict:
    """
    C7 — Gabungan: GetServiceCapabilities + GetNodes + GetConfigurations + GetStatus
    Ambil semua info dasar kamera dalam satu panggilan.
    Return dict berisi token yang ditemukan.
    """
    print("\n[C7] camera_info — 4 operasi sekaligus")
    found = {}

    r = send(xml_get_service_capabilities(), "GetServiceCapabilities")

    r = send(xml_get_nodes(), "GetNodes")
    if r:
        tokens = _all_tokens(r.text)
        if tokens:
            found["node_token"] = tokens[0]
            print(f"  >>> NodeToken ditemukan: {tokens[0]}")

    r = send(xml_get_configurations(), "GetConfigurations")
    if r:
        tokens = _all_tokens(r.text)
        if tokens:
            found["config_token"] = tokens[0]
            print(f"  >>> ConfigToken ditemukan: {tokens[0]}")

    r = send(xml_get_status(), "GetStatus")

    return found


def scan_camera() -> dict:
    """
    C1 — Gabungan: semua 9 operasi read-only sekaligus
    GetCapabilities + GetNodes + GetConfigurations + GetConfigOptions +
    GetCompatibleConfigs + GetStatus + GetPresets + GetPresetTours + GetTourOptions
    """
    print("\n[C1] scan_camera — 9 operasi read-only sekaligus")
    found = {"node_token": None, "config_token": None,
             "preset_tokens": [], "tour_tokens": []}

    send(xml_get_service_capabilities(), "GetServiceCapabilities")

    r = send(xml_get_nodes(), "GetNodes")
    if r:
        ts = _all_tokens(r.text)
        if ts:
            found["node_token"] = ts[0]

    r = send(xml_get_configurations(), "GetConfigurations")
    if r:
        ts = _all_tokens(r.text)
        if ts:
            found["config_token"] = ts[0]

    cfg = found["config_token"] or "PTZConfig_000"
    send(xml_get_configuration_options(cfg), "GetConfigurationOptions")
    send(xml_get_compatible_configurations(), "GetCompatibleConfigurations")
    send(xml_get_status(), "GetStatus")

    r = send(xml_get_presets(), "GetPresets")
    if r:
        found["preset_tokens"] = _all_tokens(r.text)

    r = send(xml_get_preset_tours(), "GetPresetTours")
    if r:
        found["tour_tokens"] = _all_tokens(r.text)

    send(xml_get_preset_tour_options(), "GetPresetTourOptions")

    print(f"\n  >>> Ditemukan: NodeToken={found['node_token']} | "
          f"ConfigToken={found['config_token']} | "
          f"Presets={len(found['preset_tokens'])} | "
          f"Tours={len(found['tour_tokens'])}")
    return found


def move(direction: str, duration: float = MOVE_DURATION) -> None:
    """
    C2 — Gabungan: ContinuousMove + Stop
    Gerak ke arah tertentu selama X detik lalu stop otomatis.
    direction: "up" | "down" | "left" | "right" | "zoom_in" | "zoom_out"
    """
    dirs = {
        "up":       (0,    0.5,  0),
        "down":     (0,   -0.5,  0),
        "left":     (-0.5, 0,    0),
        "right":    (0.5,  0,    0),
        "zoom_in":  (0,    0,    0.5),
        "zoom_out": (0,    0,   -0.5),
    }
    pan, tilt, zoom = dirs.get(direction.lower(), (0, 0, 0))
    print(f"\n[C2] move({direction}, {duration}s) — ContinuousMove + Stop")
    send(xml_continuous_move(pan, tilt, zoom), f"ContinuousMove ({direction})")
    print(f"  Bergerak {duration} detik...")
    sleep(duration)
    send(xml_stop(), "Stop")


def full_move_test() -> None:
    """
    C3 — Gabungan: ContinuousMove + Stop + RelativeMove + AbsoluteMove + GeoMove
    Test semua jenis gerakan sekaligus.
    """
    print("\n[C3] full_move_test — 5 jenis gerakan")
    send(xml_continuous_move(0.3, 0, 0), "ContinuousMove (kanan)")
    sleep(MOVE_DURATION)
    send(xml_stop(), "Stop")
    sleep(0.3)

    send(xml_relative_move(0.05, 0), "RelativeMove (+pan 0.05)")
    sleep(0.5)

    send(xml_absolute_move(0, 0, 0), "AbsoluteMove (0,0,0)")
    sleep(0.3)

    send(xml_geo_move(-6.2, 106.8, 10), "GeoMove (Jakarta)")
    sleep(0.3)

    send(xml_goto_home(0.5), "GotoHomePosition")


def preset_cycle(name: str = "Test_Preset") -> Optional[str]:
    """
    C4 — Gabungan: SetPreset + GotoHomePosition + GotoPreset + RemovePreset
    Simpan posisi → ke Home → kembali ke preset → hapus preset.
    Return PresetToken yang dibuat, atau None jika gagal.
    """
    print(f"\n[C4] preset_cycle('{name}') — SetPreset + GotoHome + GotoPreset + Remove")

    r = send(xml_set_preset(name), f"SetPreset ('{name}')")
    if not r or op_results.get(f"SetPreset ('{name}')", {}).get("status") != "OK":
        print("  SetPreset GAGAL, preset_cycle dibatalkan.")
        return None

    preset_token = None
    m = re.search(r'<(?:\w+:)?PresetToken>([^<]+)<', r.text)
    if m:
        preset_token = m.group(1).strip()

    if not preset_token:
        tokens = _all_tokens(r.text)
        preset_token = tokens[0] if tokens else None

    if not preset_token:
        print("  Tidak bisa ekstrak PresetToken dari response.")
        return None

    print(f"  >>> PresetToken: {preset_token}")

    send(xml_goto_home(), "GotoHomePosition")
    sleep(1.0)

    send(xml_goto_preset(preset_token), f"GotoPreset ('{name}')")
    sleep(1.0)

    send(xml_remove_preset(preset_token), f"RemovePreset ('{name}')")
    return preset_token


def discover_tokens() -> dict:
    """
    C5 — Gabungan: GetNodes + GetConfigurations + GetPresets + GetPresetTours
    Kumpulkan semua token yang ada di kamera.
    """
    print("\n[C5] discover_tokens — 4 operasi untuk kumpulkan semua token")
    found = {"node_tokens": [], "config_tokens": [],
             "preset_tokens": [], "tour_tokens": []}

    r = send(xml_get_nodes(), "GetNodes")
    if r:
        found["node_tokens"] = _all_tokens(r.text)

    r = send(xml_get_configurations(), "GetConfigurations")
    if r:
        found["config_tokens"] = _all_tokens(r.text)

    r = send(xml_get_presets(), "GetPresets")
    if r:
        found["preset_tokens"] = _all_tokens(r.text)

    r = send(xml_get_preset_tours(), "GetPresetTours")
    if r:
        found["tour_tokens"] = _all_tokens(r.text)

    print(f"\n  >>> TOKENS DITEMUKAN:")
    for k, v in found.items():
        print(f"      {k:<20}: {v if v else '(kosong)'}")
    return found


def patrol(preset_tokens: list, name: str = "Patroli", stay_sec: int = 5) -> None:
    """
    C6 — Gabungan: CreatePresetTour + ModifyPresetTour + OperatePresetTour(Start)
         + OperatePresetTour(Stop) + RemovePresetTour
    Buat tour patroli dari daftar preset, jalankan, lalu hapus.
    """
    if not preset_tokens:
        print("  [SKIP] patrol() butuh minimal 1 preset_token.")
        return

    print(f"\n[C6] patrol({preset_tokens}, stay={stay_sec}s) — Create+Modify+Run+Remove Tour")

    r = send(xml_create_preset_tour(), "CreatePresetTour")
    if not r or op_results.get("CreatePresetTour", {}).get("status") != "OK":
        print("  CreatePresetTour GAGAL.")
        return

    tour_token = _first_token(r.text)
    if not tour_token:
        print("  Tidak bisa ekstrak TourToken.")
        return

    print(f"  >>> TourToken: {tour_token}")

    send(xml_modify_preset_tour(tour_token, preset_tokens, name, stay_sec),
         "ModifyPresetTour")

    send(xml_operate_preset_tour(tour_token, "Start"), "OperatePresetTour (Start)")
    print(f"  Tour berjalan {stay_sec + 2} detik...")
    sleep(stay_sec + 2)

    send(xml_operate_preset_tour(tour_token, "Stop"), "OperatePresetTour (Stop)")
    sleep(0.5)

    send(xml_remove_preset_tour(tour_token), "RemovePresetTour")


# ============================================================
# Live Stream
# ============================================================
_stop_stream = threading.Event()


def _stream_fn() -> None:
    if not CV2_AVAILABLE:
        return
    cap = cv2.VideoCapture(STREAM_URL)
    if not cap.isOpened():
        print(f"[STREAM] Gagal: {STREAM_URL}")
        return
    print(f"[STREAM] Live view — tekan Q untuk tutup stream\n")
    while not _stop_stream.is_set():
        ret, frame = cap.read()
        if not ret:
            break
        ok  = sum(1 for v in op_results.values() if v["status"] == "OK")
        bad = sum(1 for v in op_results.values() if v["status"] not in ("OK", None))
        cv2.putText(frame, f"PTZ Solo | {CAMERA_IP}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"OK:{ok}  Gagal:{bad}",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
        cv2.imshow("V380 PTZ Solo", frame)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyWindow("V380 PTZ Solo")


def start_stream() -> None:
    _stop_stream.clear()
    threading.Thread(target=_stream_fn, daemon=True).start()
    sleep(1.2)


# ============================================================
# Report
# ============================================================
OP_DESC = {
    "GetServiceCapabilities":    "Cek fitur PTZ yang didukung: EFlip, Reverse, ContinuousPan, dll",
    "GetNodes":                  "Daftar unit fisik pan/tilt/zoom (node) di kamera",
    "GetNode":                   "Detail satu node: range gerakan, space koordinat",
    "GetConfigurations":         "Daftar semua konfigurasi PTZ tersimpan",
    "GetConfiguration":          "Detail satu konfigurasi: speed, timeout, batas koordinat",
    "SetConfiguration":          "Ubah konfigurasi PTZ: max speed, batas pan/tilt/zoom",
    "GetConfigurationOptions":   "Range koordinat valid: min/max pan, tilt, zoom",
    "GetCompatibleConfigurations":"Konfigurasi PTZ kompatibel dengan media profile",
    "GetStatus":                 "Posisi pan/tilt/zoom SAAT INI + status bergerak/idle",
    "ContinuousMove":            "Gerak kontinu — terus bergerak sampai Stop dikirim",
    "Stop":                      "Hentikan semua gerakan seketika",
    "RelativeMove":              "Gerak relatif — pindah sejauh X dari posisi sekarang",
    "AbsoluteMove":              "Gerak ke posisi absolut (-1.0 s/d 1.0)",
    "GeoMove":                   "Arahkan ke koordinat GPS (butuh sensor GPS)",
    "GetPresets":                "Daftar semua preset tersimpan (posisi favorit)",
    "SetPreset":                 "Simpan posisi saat ini sebagai preset bernama",
    "RemovePreset":              "Hapus preset yang sudah ada",
    "GotoPreset":                "Gerak ke posisi preset tersimpan",
    "GotoHomePosition":          "Kembalikan kamera ke posisi Home",
    "SetHomePosition":           "Simpan posisi saat ini sebagai Home",
    "GetPresetTours":            "Daftar semua preset tour (patroli otomatis)",
    "GetPresetTour":             "Detail satu tour: spot, urutan, timing",
    "GetPresetTourOptions":      "Opsi yang tersedia untuk konfigurasi tour",
    "CreatePresetTour":          "Buat preset tour baru (awalnya kosong)",
    "ModifyPresetTour":          "Isi/edit tour: tambah spot, atur kecepatan & durasi",
    "OperatePresetTour":         "Kontrol tour: Start / Stop / Pause",
    "RemovePresetTour":          "Hapus preset tour",
    "SendAuxiliaryCommand":      "Perintah AUX: nyalakan IR lamp, wiper, IR-cut filter",
    "MoveAndStartTracking":      "Gerak ke GPS lalu aktifkan object tracking otomatis",
}

COMBINE_DESC = {
    "C1 scan_camera()":      "GetCapabilities+GetNodes+GetConfigurations+GetConfigOptions+GetCompatible+GetStatus+GetPresets+GetPresetTours+GetTourOptions",
    "C2 move(dir, sec)":     "ContinuousMove + Stop (gerak + berhenti otomatis)",
    "C3 full_move_test()":   "ContinuousMove+Stop+RelativeMove+AbsoluteMove+GeoMove+GotoHome",
    "C4 preset_cycle(nama)": "SetPreset + GotoHome + GotoPreset + RemovePreset",
    "C5 discover_tokens()":  "GetNodes + GetConfigurations + GetPresets + GetPresetTours",
    "C6 patrol(presets)":    "CreatePresetTour + ModifyPresetTour + OperatePresetTour(Start/Stop) + RemovePresetTour",
    "C7 camera_info()":      "GetServiceCapabilities + GetNodes + GetConfigurations + GetStatus",
}


def show_report() -> None:
    if not op_results:
        print("  Belum ada operasi yang dijalankan.")
        return

    ok_list, fail_list, err_list = [], [], []
    for label, r in op_results.items():
        s = r["status"]
        d = r["detail"]
        # cari deskripsi berdasarkan nama operasi
        base = re.split(r'\s+\(', label)[0]
        desc = OP_DESC.get(base, "")
        if s == "OK":
            ok_list.append((label, desc))
        elif s == "FAULT":
            fail_list.append((label, d, desc))
        else:
            err_list.append((label, d, desc))

    bar = "=" * 68
    print(f"\n{bar}")
    print("  LAPORAN HASIL — ptz_solo.py")
    print(bar)

    print(f"\n  BERHASIL ({len(ok_list)}):\n")
    for label, desc in ok_list:
        print(f"  [OK] {label}")
        if desc:
            print(f"       {desc}")
        print()

    if fail_list:
        print(f"\n  TIDAK DIDUKUNG / SOAP FAULT ({len(fail_list)}):\n")
        for label, detail, desc in fail_list:
            print(f"  [FAULT] {label}")
            print(f"          Error  : {detail}")
            if desc:
                print(f"          Fungsi : {desc}")
            print()

    if err_list:
        print(f"\n  ERROR KONEKSI ({len(err_list)}):\n")
        for label, detail, _ in err_list:
            print(f"  [ERR] {label}  —  {detail}")

    print(f"\n{bar}")
    print(f"  Berhasil:{len(ok_list)}  Fault:{len(fail_list)}  Error:{len(err_list)}")
    print(f"  Log: {LOG_FILE}")
    print(bar)


def show_combined_info() -> None:
    bar = "=" * 68
    print(f"\n{bar}")
    print("  OPERASI YANG BISA DIGABUNGKAN")
    print(bar)
    for name, desc in COMBINE_DESC.items():
        print(f"\n  {name}")
        for part in desc.split("+"):
            print(f"    + {part.strip()}")
    print(bar)


# ============================================================
# Auto-Test
# ============================================================
def auto_test() -> None:
    print("\n[AUTO-TEST] Menjalankan semua 29 operasi + 7 gabungan\n")
    found = scan_camera()

    cfg         = found.get("config_token") or "PTZConfig_000"
    node        = found.get("node_token")   or "PTZNode_1"
    preset_list = found.get("preset_tokens", [])
    tour_list   = found.get("tour_tokens",   [])

    # GetNode, GetConfiguration, GetConfigurationOptions individual
    send(xml_get_node(node),                    "GetNode",            verbose=False)
    send(xml_get_configuration(cfg),            "GetConfiguration",   verbose=False)
    send(xml_get_configuration_options(cfg),    "GetConfigurationOptions", verbose=False)
    send(xml_get_compatible_configurations(),   "GetCompatibleConfigurations", verbose=False)

    # Test gerakan
    full_move_test()

    # Test SetHomePosition
    send(xml_set_home(), "SetHomePosition", verbose=False)

    # Preset cycle (simpan, pergi ke home, balik ke preset, hapus)
    preset_cycle("AutoTest")

    # Tour (pakai preset yang ada, atau skip)
    if preset_list:
        patrol(preset_list[:2], "AutoTest_Tour", stay_sec=3)
    else:
        print("\n  [SKIP] patrol — tidak ada preset token (GetPresets tidak berhasil)")
        op_results["CreatePresetTour"]  = {"status": "SKIP", "detail": "Tidak ada preset"}
        op_results["ModifyPresetTour"]  = {"status": "SKIP", "detail": "Tidak ada preset"}
        op_results["OperatePresetTour"] = {"status": "SKIP", "detail": "Tidak ada preset"}
        op_results["RemovePresetTour"]  = {"status": "SKIP", "detail": "Tidak ada preset"}

    # GetPresetTour dengan tour yang ada
    if tour_list:
        send(xml_get_preset_tour(tour_list[0]), "GetPresetTour", verbose=False)

    # SendAuxiliaryCommand
    send(xml_send_auxiliary("tt:IRLamp|On"),  "SendAuxiliaryCommand", verbose=False)

    # MoveAndStartTracking
    send(xml_move_and_start_tracking(-6.2, 106.8), "MoveAndStartTracking", verbose=False)

    # SetConfiguration (skip auto-test, terlalu berisiko)
    op_results["SetConfiguration"] = {"status": "SKIP", "detail": "Dilewati (berisiko)"}

    show_report()
    show_combined_info()


# ============================================================
# Menu
# ============================================================
MENU = """
+---------------------------------------------------------------+
|   ptz_solo.py — Semua XML inline, tanpa file eksternal       |
+---------------------------------------------------------------+
 INDIVIDU (1-29):
  1  GetServiceCapabilities   2  GetNodes          3  GetNode
  4  GetConfigurations        5  GetConfiguration  6  SetConfig(!)
  7  GetConfigOptions         8  GetCompatible     9  GetStatus
 10  ContinuousMove          11  Stop             12  RelativeMove
 13  AbsoluteMove            14  GeoMove          15  GetPresets
 16  SetPreset(!)            17  RemovePreset(!)  18  GotoPreset
 19  GotoHome                20  SetHome(!)       21  GetPresetTours
 22  GetPresetTour           23  GetTourOptions   24  CreateTour(!)
 25  ModifyTour(!)           26  OperateTour(!)   27  RemoveTour(!)
 28  AuxCommand(!)           29  MoveAndTrack(!)

 GABUNGAN:
  C1  scan_camera()       — semua 9 read-only sekaligus
  C2  move(arah, detik)   — ContinuousMove + Stop
  C3  full_move_test()    — semua 5 jenis gerakan
  C4  preset_cycle(nama)  — SetPreset+GotoHome+GotoPreset+Remove
  C5  discover_tokens()   — kumpulkan semua token
  C6  patrol(presets)     — buat+jalankan+hapus tour
  C7  camera_info()       — snapshot info lengkap

  T   AUTO-TEST semua (29 operasi + 7 gabungan)
  R   Laporan hasil
  CB  Info tentang operasi yang digabungkan
  Q   Keluar
"""


def _ask(prompt: str, default: str = "") -> str:
    v = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return v if v else default


def _confirm(prompt: str) -> bool:
    return _ask(prompt + " (y/n)", "n").lower() == "y"


def main() -> None:
    print(f"\nptz_solo.py — semua XML inline Python")
    print(f"URL   : {PTZ_URL}")
    print(f"Log   : {os.path.abspath(LOG_FILE)}")
    start_stream()

    while True:
        print(MENU)
        ch = input("Pilih: ").strip().upper()

        try:
            if ch == "Q":
                _stop_stream.set()
                break
            elif ch == "T":
                auto_test()
            elif ch == "R":
                show_report()
            elif ch == "CB":
                show_combined_info()

            # ── GABUNGAN ──
            elif ch == "C1":
                scan_camera()
            elif ch == "C2":
                d = _ask("Arah (up/down/left/right/zoom_in/zoom_out)", "right")
                t = float(_ask("Durasi detik", str(MOVE_DURATION)))
                move(d, t)
            elif ch == "C3":
                full_move_test()
            elif ch == "C4":
                n = _ask("Nama preset", "Test_Preset")
                preset_cycle(n)
            elif ch == "C5":
                discover_tokens()
            elif ch == "C6":
                raw = _ask("PresetTokens (pisah koma)")
                pts = [p.strip() for p in raw.split(",") if p.strip()]
                if pts:
                    patrol(pts)
                else:
                    print("  Minimal 1 preset token.")
            elif ch == "C7":
                camera_info()

            # ── INDIVIDU ──
            elif ch == "1":
                send(xml_get_service_capabilities(), "GetServiceCapabilities")
            elif ch == "2":
                send(xml_get_nodes(), "GetNodes")
            elif ch == "3":
                t = _ask("NodeToken", "PTZNode_1")
                send(xml_get_node(t), "GetNode")
            elif ch == "4":
                send(xml_get_configurations(), "GetConfigurations")
            elif ch == "5":
                t = _ask("ConfigToken", "PTZConfig_000")
                send(xml_get_configuration(t), "GetConfiguration")
            elif ch == "6":
                if _confirm("SetConfiguration — ubah konfigurasi kamera?"):
                    t = _ask("ConfigToken", "PTZConfig_000")
                    s = _ask("Max Speed (0.0-1.0)", "1.0")
                    send(xml_set_configuration(t, s), "SetConfiguration")
            elif ch == "7":
                t = _ask("ConfigToken", "PTZConfig_000")
                send(xml_get_configuration_options(t), "GetConfigurationOptions")
            elif ch == "8":
                send(xml_get_compatible_configurations(), "GetCompatibleConfigurations")
            elif ch == "9":
                send(xml_get_status(), "GetStatus")
            elif ch == "10":
                print("  [1]Atas [2]Bawah [3]Kiri [4]Kanan [5]ZoomIn [6]ZoomOut [7]Kustom")
                dc = _ask("Pilih", "4")
                dm = {"1":(0,.5,0),"2":(0,-.5,0),"3":(-.5,0,0),
                      "4":(.5,0,0),"5":(0,0,.5),"6":(0,0,-.5)}
                if dc in dm:
                    p,t,z = dm[dc]
                else:
                    p = float(_ask("Pan", "0"))
                    t = float(_ask("Tilt", "0"))
                    z = float(_ask("Zoom", "0"))
                send(xml_continuous_move(p, t, z), "ContinuousMove")
                sleep(MOVE_DURATION)
                send(xml_stop(), "Stop")
            elif ch == "11":
                send(xml_stop(), "Stop")
            elif ch == "12":
                p = float(_ask("Pan", "0.1"))
                t = float(_ask("Tilt", "0"))
                z = float(_ask("Zoom", "0"))
                send(xml_relative_move(p, t, z), "RelativeMove")
            elif ch == "13":
                p = float(_ask("Pan", "0"))
                t = float(_ask("Tilt", "0"))
                z = float(_ask("Zoom", "0"))
                send(xml_absolute_move(p, t, z), "AbsoluteMove")
            elif ch == "14":
                la = float(_ask("Latitude",  "-6.2"))
                lo = float(_ask("Longitude", "106.8"))
                el = float(_ask("Elevation", "10"))
                send(xml_geo_move(la, lo, el), "GeoMove")
            elif ch == "15":
                send(xml_get_presets(), "GetPresets")
            elif ch == "16":
                n = _ask("Nama preset", "MyPreset")
                send(xml_set_preset(n), f"SetPreset ('{n}')")
            elif ch == "17":
                t = _ask("PresetToken")
                if t and _confirm(f"Hapus preset '{t}'?"):
                    send(xml_remove_preset(t), "RemovePreset")
            elif ch == "18":
                t = _ask("PresetToken")
                s = float(_ask("Speed", "0.5"))
                if t:
                    send(xml_goto_preset(t, s), "GotoPreset")
            elif ch == "19":
                send(xml_goto_home(), "GotoHomePosition")
            elif ch == "20":
                if _confirm("Simpan posisi ini sebagai Home?"):
                    send(xml_set_home(), "SetHomePosition")
            elif ch == "21":
                send(xml_get_preset_tours(), "GetPresetTours")
            elif ch == "22":
                t = _ask("TourToken")
                if t:
                    send(xml_get_preset_tour(t), "GetPresetTour")
            elif ch == "23":
                send(xml_get_preset_tour_options(), "GetPresetTourOptions")
            elif ch == "24":
                send(xml_create_preset_tour(), "CreatePresetTour")
            elif ch == "25":
                tt = _ask("TourToken")
                tn = _ask("Nama Tour", "Patroli")
                raw = _ask("PresetTokens (pisah koma)")
                pts = [p.strip() for p in raw.split(",") if p.strip()]
                if tt and pts:
                    send(xml_modify_preset_tour(tt, pts, tn), "ModifyPresetTour")
            elif ch == "26":
                tt = _ask("TourToken")
                print("  [1]Start  [2]Stop  [3]Pause")
                op = {"1":"Start","2":"Stop","3":"Pause"}.get(_ask("Pilih","2"), "Stop")
                if tt:
                    send(xml_operate_preset_tour(tt, op), f"OperatePresetTour ({op})")
            elif ch == "27":
                tt = _ask("TourToken")
                if tt and _confirm(f"Hapus tour '{tt}'?"):
                    send(xml_remove_preset_tour(tt), "RemovePresetTour")
            elif ch == "28":
                print("  Contoh: tt:IRLamp|On  tt:IRLamp|Off  tt:IRCutFilter|on")
                cmd = _ask("AuxiliaryData", "tt:IRLamp|On")
                send(xml_send_auxiliary(cmd), "SendAuxiliaryCommand")
            elif ch == "29":
                la = float(_ask("Latitude",  "-6.2"))
                lo = float(_ask("Longitude", "106.8"))
                el = float(_ask("Elevation", "10"))
                send(xml_move_and_start_tracking(la, lo, el), "MoveAndStartTracking")
            else:
                print("  Pilihan tidak valid.")

        except KeyboardInterrupt:
            print("\n[INTERRUPT] Stop...")
            send(xml_stop(), "Stop")
        except ValueError as e:
            print(f"  Input tidak valid: {e}")


if __name__ == "__main__":
    main()
