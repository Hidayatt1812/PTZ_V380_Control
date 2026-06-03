# PTZ V380 Control

Kontrol kamera V380 menggunakan Python dan protokol ONVIF: live streaming, PTZ movement, kalibrasi posisi, home, dan preset.

## Fitur

- Live streaming via RTSP
- Kontrol PTZ pan/tilt via ONVIF ContinuousMove XML lama (`post*.xml`)
- Kalibrasi posisi dari hard stop kiri-atas
- Home dan preset 1-9 dengan tracker posisi software
- Digital zoom via OpenCV, tersimpan bersama Home dan preset
- Debug stream dengan overlay pan/tilt, crosshair, dan peta posisi kecil
- Capture screenshot

## Instalasi

```bash
git clone https://github.com/Hidayatt1812/PTZ_V380_Control.git
cd PTZ_V380_Control

python -m venv V380.venv
V380.venv\Scripts\activate

pip install opencv-contrib-python requests
```

## Konfigurasi

Salin file konfigurasi contoh lalu isi dengan data kamera:

```bash
cp config.example.py config.py
```

Edit `config.py`:

```python
CAMERA_IP = "192.168.x.x"
ONVIF_PORT = 8899
USERNAME = "admin"
PASSWORD = "your_password"
```

`config.py` sudah ada di `.gitignore`, jadi credentials tidak ikut ter-commit.

## Jalankan

```bash
python V380_complete.py
```

## Kontrol Keyboard

| Tombol | Fungsi |
|--------|--------|
| `c` / `C` | Kalibrasi ke kiri-atas, lalu menuju Home tersimpan |
| `i` | Tilt atas |
| `,` | Tilt bawah |
| `j` | Pan kiri |
| `l` | Pan kanan |
| `+` / `=` | Zoom in digital |
| `-` / `_` | Zoom out digital |
| `0` | Reset zoom digital |
| `H` | Set posisi sekarang sebagai Home |
| `h` | Kembali ke Home |
| `s` | Toggle mode Simpan Preset |
| `1`-`9` | Go to preset / Simpan preset saat mode simpan aktif |
| `SPACE` | Screenshot frame debug |
| `ESC` | Keluar |

## Cara Kalibrasi

1. Jalankan program.
2. Tekan `c`.
3. Kamera akan mencari hard stop kiri-atas.
4. Jika sudah ada **Home** tersimpan, kamera bergerak ke Home itu.
5. Jika belum ada Home, kamera bergerak ke tengah default lalu menyimpannya ke `ptz_presets.json`.
6. Untuk mengganti Home permanen, gerakkan kamera dan atur zoom ke posisi yang diinginkan lalu tekan `H`.
7. Kalibrasi berikutnya dengan `c` akan memakai Home yang terakhir disimpan lewat `H`.
8. Tekan `h` untuk kembali ke Home.

Untuk menyimpan preset:

1. Pastikan sudah kalibrasi dengan `c`.
2. Arahkan kamera dan atur zoom ke posisi yang diinginkan.
3. Tekan `s`.
4. Tekan angka `1`-`9`.
5. Untuk kembali ke preset tersebut, tekan angka yang sama tanpa `s`.

## Deskripsi File

| File | Deskripsi |
|------|-----------|
| `V380_complete.py` | File utama: streaming debug, PTZ, kalibrasi, home, dan preset |
| `V380_complete_public.py` | Versi sederhana tanpa kalibrasi |
| `v380.py` | Live stream saja |
| `v380cap.py` | Live stream + screenshot |
| `v380post.py` | PTZ via terminal tanpa video |
| `config.example.py` | Template konfigurasi |
| `post*.xml` | ONVIF SOAP command dasar untuk gerak PTZ |

## Catatan Teknis

Kamera V380 tidak mengimplementasikan `AbsoluteMove` ONVIF dengan baik, jadi posisi dikendalikan memakai **ContinuousMove + timed stop**.

- `c` mencari hard stop kiri-atas dengan margin supaya tracker punya titik nol yang konsisten.
- Setelah titik nol ditemukan, `c` memakai Home yang tersimpan. Home tidak ditimpa lagi kecuali tombol `H` ditekan.
- Gerakan kembali memakai mode lama: kirim XML `post*.xml`, tunggu `0.5` detik, lalu kirim Stop.
- Posisi home dan preset disimpan sebagai integer step agar penyimpanan dan pemanggilan preset lebih konsisten.
- Zoom memakai crop/resize OpenCV pada stream debug, bukan zoom optik ONVIF kamera.
- Field preset sekarang berisi `pan`, `tilt`, dan `zoom`. Preset lama tanpa `zoom` otomatis dianggap `1.0x`.
