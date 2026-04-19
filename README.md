# PTZ V380 Control

Kontrol kamera V380 menggunakan Python dan protokol ONVIF — live streaming, PTZ movement, dan kalibrasi posisi (home + preset).

## Fitur

- Live streaming via RTSP
- Kontrol PTZ (pan, tilt) via ONVIF ContinuousMove
- **Kalibrasi posisi** — simpan home dan preset 1-9, kamera kembali otomatis
- Capture screenshot
- Software position tracker (overlay pan/tilt realtime di video)

## Instalasi

```bash
git clone https://github.com/Hidayatt1812/PTZ_V380_Control.git
cd PTZ_V380_Control

python -m venv V380.venv
V380.venv\Scripts\activate        # Windows
# atau: source V380.venv/bin/activate   # Linux/Mac

pip install opencv-contrib-python requests
```

## Konfigurasi

Salin file konfigurasi contoh lalu isi dengan data kamera Anda:

```bash
cp config.example.py config.py
```

Edit `config.py`:

```python
CAMERA_IP  = "192.168.x.x"   # IP kamera
ONVIF_PORT = 8899
USERNAME   = "admin"
PASSWORD   = "your_password"
```

> `config.py` sudah ada di `.gitignore` — credentials tidak akan ter-commit.

## Jalankan

```bash
python V380_complete.py
```

## Kontrol Keyboard

| Tombol | Fungsi |
|--------|--------|
| `i` | Tilt atas |
| `,` | Tilt bawah |
| `j` | Pan kiri |
| `l` | Pan kanan |
| `k` | Stop |
| `H` (Shift+H) | Set posisi sekarang sebagai Home |
| `h` | Kembali ke Home |
| `s` | Toggle mode Simpan Preset |
| `1`–`9` | Go to preset / Simpan preset (saat mode simpan aktif) |
| `SPACE` | Screenshot |
| `ESC` | Keluar |

## Cara Kalibrasi

1. Jalankan program — tracker mulai di `pan=0.0 tilt=0.0`
2. Gerakkan kamera ke posisi yang diinginkan sebagai **Home**
3. Tekan `H` — posisi tersimpan ke `ptz_presets.json`
4. Gerakkan kamera ke posisi lain
5. Tekan `h` — kamera otomatis kembali ke Home

Untuk menyimpan **preset** (hingga 9 posisi):
1. Arahkan kamera ke posisi yang diinginkan
2. Tekan `s` (mode simpan aktif, overlay berubah hijau)
3. Tekan angka `1`–`9`
4. Untuk kembali ke preset tersebut, tekan angka yang sama (tanpa `s`)

## Deskripsi File

| File | Deskripsi |
|------|-----------|
| `V380_complete.py` | **File utama** — streaming + PTZ + kalibrasi |
| `V380_complete_public.py` | Versi sederhana tanpa kalibrasi |
| `v380.py` | Live stream saja |
| `v380cap.py` | Live stream + screenshot |
| `v380post.py` | PTZ via terminal (tanpa video) |
| `config.example.py` | Template konfigurasi |
| `post*.xml` | ONVIF SOAP command untuk gerak PTZ |

## Catatan Teknis

Kamera V380 tidak mengimplementasikan `AbsoluteMove` ONVIF (meskipun return HTTP 200).  
Kalibrasi posisi menggunakan **ContinuousMove + timed stop**:
- Hitung delta posisi dari tracker software
- Kirim ContinuousMove ke arah yang tepat selama `|delta| / speed` detik
- Kirim Stop
