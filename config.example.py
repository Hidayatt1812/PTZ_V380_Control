# Salin file ini menjadi config.py lalu isi dengan data kamera Anda
# cp config.example.py config.py

CAMERA_IP   = "192.168.x.x"   # IP kamera
ONVIF_PORT  = 8899
USERNAME    = "admin"
PASSWORD    = "your_password"

RTSP_URL = f"rtsp://{USERNAME}:{PASSWORD}@{CAMERA_IP}:554/live/ch00_0"
PTZ_URL  = f"http://{CAMERA_IP}:{ONVIF_PORT}/onvif/ptz"
