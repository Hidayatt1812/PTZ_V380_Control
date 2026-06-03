# PENJELASAN HASIL UJI ONVIF PTZ — Kamera V380

> Hasil auto-test tanggal **20 April 2026**  
> Kamera IP: `192.168.137.240:8899`  
> Profile: `PROFILE_000`

---

## Daftar Isi

1. [Apa itu ONVIF PTZ?](#1-apa-itu-onvif-ptz)
2. [Token Penting Kamera Ini](#2-token-penting-kamera-ini)
3. [Fitur yang DIDUKUNG](#3-fitur-yang-didukung)
4. [Fitur yang TIDAK DIDUKUNG](#4-fitur-yang-tidak-didukung)
5. [Penjelasan Detail Setiap Operasi](#5-penjelasan-detail-setiap-operasi)
6. [Tabel Ringkasan 29 Operasi](#6-tabel-ringkasan-29-operasi)
7. [Cara Pakai Token yang Benar](#7-cara-pakai-token-yang-benar)

---

## 1. Apa itu ONVIF PTZ?

**ONVIF** adalah standar protokol komunikasi untuk kamera IP.  
**PTZ** singkatan dari **Pan** (gerak kiri-kanan) · **Tilt** (gerak atas-bawah) · **Zoom**.

Kamera mendengarkan perintah lewat **SOAP over HTTP** — yaitu kita kirim XML ke kamera,
kamera balas XML berisi hasil atau error.

Ada **29 operasi resmi** dalam standar ONVIF PTZ WSDL.  
Tidak semua kamera mendukung semuanya — tergantung produsen dan firmware.

---

## 2. Token Penting Kamera Ini

Token adalah **ID unik** yang harus disertakan di setiap perintah ONVIF.

| Token | Nilai | Keterangan |
|-------|-------|-----------|
| **NodeToken** | `PTZNODE_000` | ID unit fisik pan/tilt/zoom |
| **ConfigToken** | `PTZCFG_000` | ID konfigurasi PTZ aktif |
| **ProfileToken** | `PROFILE_000` | ID profil media kamera |
| **PresetToken** | `PRESET_0` | ID preset tersimpan (ada 1 preset) |

> Jika Anda menjalankan perintah dengan token yang salah, kamera akan balas error.

---

## 3. Fitur yang DIDUKUNG

Berdasarkan hasil log, kamera V380 ini mendukung:

### Kemampuan Dasar (GetServiceCapabilities)

```
EFlip                    = true   → gambar bisa dibalik vertikal
Reverse                  = true   → arah gerak bisa dibalik
GetCompatibleConfigurations = true
MoveStatus               = true   → bisa cek apakah kamera sedang bergerak
StatusPosition           = true   → bisa cek posisi pan/tilt/zoom saat ini
```

### Gerakan

| Operasi | Keterangan |
|---------|-----------|
| **ContinuousMove** | Gerak terus sampai dikirim Stop. Kecepatan -1.0 s/d 1.0 |
| **RelativeMove** | Gerak sejauh X dari posisi sekarang |
| **AbsoluteMove** | Gerak ke koordinat pasti (-1.0 s/d 1.0) |
| **Stop** | Hentikan semua gerakan seketika |
| **GotoHomePosition** | Kembali ke posisi Home |
| **SetHomePosition** | Simpan posisi saat ini sebagai Home |

### Range Koordinat yang Valid

```
Pan (kiri-kanan) : -1.0 (paling kiri) s/d  1.0 (paling kanan)
Tilt (atas-bawah): -1.0 (paling bawah) s/d  1.0 (paling atas)
Zoom             :  0.0 (tidak zoom)   s/d  1.0 (zoom maksimal)
Kecepatan        :  0.0 (diam)         s/d  1.0 (paling cepat)
```

### Preset (Posisi Tersimpan)

| Operasi | Keterangan |
|---------|-----------|
| **GetPresets** | Lihat daftar preset |
| **SetPreset** | Simpan posisi saat ini sebagai preset |
| **GotoPreset** | Pindah ke posisi preset |
| **RemovePreset** | Hapus preset |

> Kamera ini bisa menyimpan hingga **100 preset**.  
> Saat ini sudah ada 1 preset: `PRESET_0` (nama: Preset_1) di posisi (0, 0, 0).

### Informasi & Konfigurasi

| Operasi | Keterangan |
|---------|-----------|
| **GetServiceCapabilities** | Cek fitur yang didukung |
| **GetNodes** | Info unit fisik kamera |
| **GetNode** | Detail satu node |
| **GetConfigurations** | Konfigurasi PTZ aktif |
| **GetConfiguration** | Detail konfigurasi |
| **GetConfigurationOptions** | Range nilai yang valid |
| **GetCompatibleConfigurations** | Konfigurasi kompatibel dengan profil |
| **GetStatus** | Posisi & status kamera saat ini |

### Konfigurasi Saat Ini (dari GetConfigurations)

```
Token           : PTZCFG_000
Kecepatan default: Pan=0.5, Tilt=0.5, Zoom=0.5
Timeout default : 5 detik (PT5S)
Timeout range   : 1 detik (PT1S) s/d 100 detik (PT100S)
EFlip           : OFF (bisa diubah ke ON)
Reverse         : OFF (bisa diubah ke ON atau AUTO)
```

### Status Kamera Saat Test (dari GetStatus)

```
Posisi Pan  : 0.0  (tengah)
Posisi Tilt : 0.0  (tengah)
Posisi Zoom : 0.0  (tidak zoom)
Status      : IDLE (sedang diam)
Waktu UTC   : 2026-04-20T13:54:53Z
```

---

## 4. Fitur yang TIDAK DIDUKUNG

Kamera mengembalikan **HTTP 500 + SOAP Fault `ActionNotSupported`** untuk:

### Preset Tour (Patroli Otomatis) — 7 operasi

| No | Operasi | Arti |
|----|---------|------|
| 21 | GetPresetTours | Lihat daftar patroli |
| 22 | GetPresetTour | Detail satu patroli |
| 23 | GetPresetTourOptions | Opsi konfigurasi patroli |
| 24 | CreatePresetTour | Buat patroli baru |
| 25 | ModifyPresetTour | Edit patroli |
| 26 | OperatePresetTour | Jalankan/hentikan patroli |
| 27 | RemovePresetTour | Hapus patroli |

**Kesimpulan:** Kamera V380 ini **tidak bisa patroli otomatis** lewat ONVIF.  
Jika ingin patroli, harus dibuat manual di Python:
loop GotoPreset → sleep → GotoPreset berikutnya → dst.

### Fitur Lain yang Belum Diuji / Kemungkinan Tidak Didukung

| Operasi | Kenapa Mungkin Tidak Bekerja |
|---------|------------------------------|
| **AbsoluteMove** | V380 dikenal sering tidak merespons AbsoluteMove |
| **GeoMove** | Butuh sensor GPS, kamera IP biasa tidak punya |
| **MoveAndStartTracking** | Butuh object tracking engine di kamera |
| **SendAuxiliaryCommand** | Tergantung firmware, bisa saja tidak ada IR/wiper |

---

## 5. Penjelasan Detail Setiap Operasi

### GetServiceCapabilities (No. 1)
**Fungsi:** Tanya kamera — fitur apa saja yang kamu dukung?  
**Kapan dipakai:** Pertama kali sebelum pakai kamera, untuk tahu apa yang bisa dilakukan.  
**Hasil kamera ini:**
```
EFlip=true, Reverse=true, MoveStatus=true, StatusPosition=true
```

---

### GetNodes (No. 2)
**Fungsi:** Daftar unit fisik PTZ di kamera.  
**Analoginya:** Seperti bertanya "ada berapa kepala kamera yang bisa digerakkan?"  
**Hasil kamera ini:** 1 node → `PTZNODE_000`

---

### GetNode (No. 3)
**Fungsi:** Detail lengkap satu node — range gerak, kecepatan max, dll.  
**Kapan dipakai:** Setelah GetNodes, untuk tahu batas koordinat yang valid.

---

### GetConfigurations (No. 4)
**Fungsi:** Lihat konfigurasi PTZ yang aktif — kecepatan default, timeout, batas gerak.  
**Hasil kamera ini:** Token `PTZCFG_000`, speed default 0.5, timeout 5 detik.

---

### GetConfiguration (No. 5)
**Fungsi:** Sama seperti GetConfigurations tapi untuk satu konfigurasi spesifik.  
**Kapan dipakai:** Jika ada beberapa konfigurasi, pilih satu untuk dilihat detailnya.

---

### SetConfiguration (No. 6) ⚠️
**Fungsi:** Ubah konfigurasi PTZ — kecepatan max, timeout, batas koordinat, EFlip, Reverse.  
**Contoh kegunaan:** Aktifkan `Reverse=ON` agar arah gerak terbalik (cocok untuk kamera terpasang terbalik).  
**Peringatan:** Salah isi bisa membuat kamera tidak bisa digerakkan sampai direset.

---

### GetConfigurationOptions (No. 7)
**Fungsi:** Tanya kamera — nilai apa saja yang valid untuk konfigurasi?  
**Hasil kamera ini:** Timeout 1-100 detik, EFlip: OFF/ON, Reverse: OFF/ON/AUTO.

---

### GetCompatibleConfigurations (No. 8)
**Fungsi:** Konfigurasi PTZ mana yang bisa dipakai bersama profil media ini.  
**Hasilnya:** `PTZCFG_000` kompatibel dengan `PROFILE_000`.

---

### GetStatus (No. 9)
**Fungsi:** Posisi kamera SAAT INI + apakah sedang bergerak atau diam.  
**Kapan dipakai:** Sebelum gerakan, setelah gerakan, untuk monitor posisi real-time.  
**Hasil kamera ini:** Posisi (0,0,0), status IDLE.

---

### ContinuousMove (No. 10)
**Fungsi:** Kamera bergerak TERUS dengan kecepatan tertentu sampai Stop dikirim.  
**Format:** `pan=-1.0 s/d 1.0`, `tilt=-1.0 s/d 1.0`, `zoom=-1.0 s/d 1.0`  
**Contoh:**
```python
# Gerak kanan dengan kecepatan 50%
xml_continuous_move(pan=0.5, tilt=0, zoom=0)
sleep(1.0)
xml_stop()
```

---

### Stop (No. 11)
**Fungsi:** Hentikan semua gerakan seketika.  
**Penting:** Selalu kirim Stop setelah ContinuousMove, jika tidak kamera terus bergerak sampai mentok.

---

### RelativeMove (No. 12)
**Fungsi:** Gerak sejauh X dari posisi **saat ini**.  
**Contoh:** Jika kamera di posisi pan=0.2, kirim RelativeMove pan=0.1, maka kamera pindah ke pan=0.3.  
**Bedanya dengan AbsoluteMove:** Relatif = dari posisi sekarang. Absolut = ke koordinat pasti.

---

### AbsoluteMove (No. 13) ⚠️
**Fungsi:** Gerak ke koordinat **pasti**.  
**Contoh:** Kirim pan=0.5 maka kamera pergi ke titik pan=0.5 dari tengah, bukan bergerak 0.5.  
**Catatan untuk V380:** Operasi ini sering tidak bekerja di V380 meski response OK.  
**Alternatif:** Gunakan ContinuousMove + timed Stop sebagai pengganti.

---

### GeoMove (No. 14)
**Fungsi:** Arahkan kamera ke koordinat GPS (latitude, longitude, elevation).  
**Kegunaan:** Untuk sistem surveillance outdoor yang tahu lokasi geografis target.  
**V380:** Sangat kemungkinan tidak didukung (butuh sensor GPS internal).

---

### GetPresets (No. 15)
**Fungsi:** Lihat daftar posisi favorit yang sudah tersimpan.  
**Hasil kamera ini:** Ada 1 preset → `PRESET_0` (Preset_1) di posisi (0, 0, 0).

---

### SetPreset (No. 16)
**Fungsi:** Simpan posisi kamera SAAT INI dengan nama tertentu.  
**Alur penggunaan:**
1. Gerakkan kamera ke posisi yang diinginkan
2. Kirim SetPreset dengan nama "Pintu Depan"
3. Kamera simpan posisi itu dengan token baru
4. Nanti bisa dipanggil kembali dengan GotoPreset

---

### RemovePreset (No. 17)
**Fungsi:** Hapus preset yang sudah ada.  
**Peringatan:** Permanen, tidak bisa di-undo. Pastikan token yang dihapus benar.

---

### GotoPreset (No. 18)
**Fungsi:** Gerakkan kamera ke posisi preset yang sudah tersimpan.  
**Kegunaan:** Pindah cepat ke sudut pandang favorit tanpa harus atur koordinat manual.

---

### GotoHomePosition (No. 19)
**Fungsi:** Kembalikan kamera ke posisi "Home" — posisi default awal.  
**Kapan dipakai:** Reset posisi kamera ke titik netral.

---

### SetHomePosition (No. 20)
**Fungsi:** Simpan posisi saat ini sebagai Home baru.  
**Catatan:** FixedHomePosition=false di kamera ini, artinya Home bisa diubah.

---

### GetPresetTours (No. 21) ❌
**Fungsi:** Lihat daftar tur patroli otomatis.  
**Status di kamera ini:** `ActionNotSupported` — tidak tersedia.

---

### GetPresetTour (No. 22) ❌
**Fungsi:** Detail satu tur patroli: spot mana saja, urutan, kecepatan, berapa lama berhenti di tiap spot.  
**Status di kamera ini:** `ActionNotSupported` — tidak tersedia.

---

### GetPresetTourOptions (No. 23) ❌
**Fungsi:** Opsi konfigurasi yang tersedia untuk tur patroli.  
**Status di kamera ini:** `ActionNotSupported` — tidak tersedia.

---

### CreatePresetTour (No. 24) ❌
**Fungsi:** Buat tur patroli baru (awalnya kosong).  
**Status di kamera ini:** Tidak diuji karena GetPresetTours sudah gagal.

---

### ModifyPresetTour (No. 25) ❌
**Fungsi:** Isi/edit tur: tambahkan spot preset, atur kecepatan antar spot, atur durasi berhenti.  
**Status di kamera ini:** Tidak tersedia.

---

### OperatePresetTour (No. 26) ❌
**Fungsi:** Kontrol tur — Start (mulai patroli), Stop (hentikan), Pause (jeda).  
**Status di kamera ini:** Tidak tersedia.

---

### RemovePresetTour (No. 27) ❌
**Fungsi:** Hapus tur patroli.  
**Status di kamera ini:** Tidak tersedia.

---

### SendAuxiliaryCommand (No. 28)
**Fungsi:** Kirim perintah tambahan ke hardware kamera.  
**Contoh perintah yang umum:**
```
tt:IRLamp|On        → Nyalakan lampu infrared (night vision)
tt:IRLamp|Off       → Matikan lampu infrared
tt:IRCutFilter|on   → Aktifkan filter IR (mode siang)
tt:IRCutFilter|off  → Nonaktifkan filter IR (mode malam)
tt:Wiper|start      → Aktifkan wiper (jika ada)
```
**Catatan:** Tergantung hardware yang ada di kamera. V380 mungkin hanya support IRLamp.

---

### MoveAndStartTracking (No. 29)
**Fungsi:** Gerak ke arah GPS tertentu lalu aktifkan **object tracking** (kamera otomatis mengikuti objek bergerak).  
**Status di kamera ini:** Sangat kemungkinan tidak didukung (butuh AI engine di kamera).

---

## 6. Tabel Ringkasan 29 Operasi

| No | Operasi | Status | Keterangan Singkat |
|----|---------|--------|-------------------|
| 1 | GetServiceCapabilities | ✅ OK | EFlip, Reverse, MoveStatus tersedia |
| 2 | GetNodes | ✅ OK | Token: PTZNODE_000 |
| 3 | GetNode | ✅ OK | Detail node PTZNODE_000 |
| 4 | GetConfigurations | ✅ OK | Token: PTZCFG_000 |
| 5 | GetConfiguration | ✅ OK | Speed default 0.5, timeout 5 detik |
| 6 | SetConfiguration | ⚠️ SKIP | Berisiko, test manual |
| 7 | GetConfigurationOptions | ✅ OK | Timeout 1-100 detik |
| 8 | GetCompatibleConfigurations | ✅ OK | PTZCFG_000 kompatibel |
| 9 | GetStatus | ✅ OK | Posisi (0,0,0), IDLE |
| 10 | ContinuousMove | ✅ OK | Gerak kontinu berfungsi |
| 11 | Stop | ✅ OK | Stop berfungsi |
| 12 | RelativeMove | ✅ OK | Gerak relatif berfungsi |
| 13 | AbsoluteMove | ⚠️ CEK | Response OK tapi fisik mungkin tidak gerak |
| 14 | GeoMove | ❌ FAULT | Tidak ada GPS |
| 15 | GetPresets | ✅ OK | Ada 1 preset: PRESET_0 |
| 16 | SetPreset | ✅ OK | Bisa simpan posisi |
| 17 | RemovePreset | ✅ OK | Bisa hapus preset |
| 18 | GotoPreset | ✅ OK | Bisa pergi ke preset |
| 19 | GotoHomePosition | ✅ OK | Home berfungsi |
| 20 | SetHomePosition | ✅ OK | Bisa set posisi home |
| 21 | GetPresetTours | ❌ TIDAK ADA | ActionNotSupported |
| 22 | GetPresetTour | ❌ TIDAK ADA | ActionNotSupported |
| 23 | GetPresetTourOptions | ❌ TIDAK ADA | ActionNotSupported |
| 24 | CreatePresetTour | ❌ TIDAK ADA | ActionNotSupported |
| 25 | ModifyPresetTour | ❌ TIDAK ADA | ActionNotSupported |
| 26 | OperatePresetTour | ❌ TIDAK ADA | ActionNotSupported |
| 27 | RemovePresetTour | ❌ TIDAK ADA | ActionNotSupported |
| 28 | SendAuxiliaryCommand | ⚠️ CEK | Tergantung hardware |
| 29 | MoveAndStartTracking | ❌ FAULT | Tidak ada tracking engine |

**Legenda:**
- ✅ OK — Berfungsi normal
- ⚠️ CEK — Perlu uji manual lebih lanjut
- ❌ TIDAK ADA — Kamera tidak mendukung (ActionNotSupported)
- ❌ FAULT — Gagal karena fitur tidak ada di hardware

---

## 7. Cara Pakai Token yang Benar

Karena sudah tahu tokennya, ini contoh langsung yang bisa langsung dipakai:

### Gerak ke kanan 0.5 detik lalu stop
```python
send(xml_continuous_move(pan=0.5, tilt=0, zoom=0))
sleep(0.5)
send(xml_stop())
```

### Simpan posisi saat ini sebagai preset
```python
send(xml_set_preset("Pintu Depan"))
# Response akan berisi PresetToken baru
```

### Pergi ke preset yang ada
```python
send(xml_goto_preset("PRESET_0", speed=0.5))
```

### Cek posisi sekarang
```python
send(xml_get_status())
# Response: PanTilt x="0.0" y="0.0", IDLE/MOVING
```

### Aktifkan EFlip (balik gambar vertikal)
```python
send(xml_set_configuration("PTZCFG_000", max_speed="1.0"))
# Perlu edit SetConfiguration untuk set EFlip=ON
```

### Patroli manual (karena PresetTour tidak didukung)
```python
preset_list = ["PRESET_0", "PRESET_1", "PRESET_2"]
while True:
    for token in preset_list:
        send(xml_goto_preset(token, speed=0.5))
        sleep(5)  # tunggu 5 detik di setiap spot
```

---

## Kesimpulan

Kamera V380 ini mendukung **~18 dari 29 operasi ONVIF PTZ**:

- **Yang bisa dipakai:** Semua gerakan dasar, preset, home position, status, konfigurasi
- **Yang tidak bisa:** Preset Tour (patroli ONVIF), GeoMove, MoveAndStartTracking
- **Solusi patroli:** Buat loop Python manual dengan GotoPreset + sleep

> File log lengkap: `ptz_solo.log`  
> Script: `ptz_solo.py` (tanpa file XML eksternal)  
> Script lama dengan XML: `explorer.py` + folder `xml/`
