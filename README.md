# Lyrics PiP

Jendela lirik kecil yang selalu di atas jendela lain (seperti picture-in-picture) untuk lagu yang sedang diputar di **YouTube Music di Firefox**. Lirik tersinkron: baris yang sedang dinyanyikan disorot dan di-scroll otomatis.

Dibuat untuk pemakaian pribadi di Linux (XFCE/X11) dan sengaja ringan: Python + GTK3, tanpa paket pip.

## Cara kerja

- **Deteksi lagu:** membaca MPRIS lewat D-Bus (`Gio`). Firefox melaporkan judul, artis, durasi, dan posisi lagu, jadi tidak perlu ekstensi browser atau scraping.
- **Lirik:** diambil dari [LRCLIB](https://lrclib.net) (gratis, tanpa API key). Kalau lirik bertimestamp tidak ada, ditampilkan lirik biasa tanpa sorotan.
- **Cache:** hasil disimpan di `~/.cache/lyrics-pip/`.

## Kebutuhan

- Linux dengan sesi grafis (diuji di XFCE/X11)
- Python 3.12+ dengan PyGObject dan GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`)
- Firefox yang memutar YouTube Music

## Menjalankan

```bash
./lyrics-pip
```

Putar lagu di YouTube Music, lalu liriknya muncul di jendela.

## Kontrol

| Aksi | Cara |
|------|------|
| Pindahkan jendela | seret di mana saja |
| Ubah ukuran | seret tepi atau sudut jendela |
| Atur transparansi | `Ctrl` + scroll mouse |
| Tutup | tombol `×` di pojok |

Jendela selalu di atas jendela lain, tampil di semua workspace, tidak mengambil fokus keyboard, dan hanya bisa dibuka satu kali (membuka lagi saat sudah berjalan tidak melakukan apa-apa).

## Pengaturan

### Transparansi
`Ctrl` + scroll mouse di atas jendela. Naik = lebih pekat, turun = lebih transparan, per langkah 5%, dalam rentang 0,3 sampai 1,0. Bawaannya 0,92. Nilainya diingat untuk pembukaan berikutnya.

### Posisi dan ukuran
Geser dan ubah ukuran jendela seperti biasa. Nilainya disimpan saat jendela ditutup (lewat `×`, `Alt+F4`, `Ctrl+C`, atau `kill`) di `~/.config/lyrics-pip/config.json`:

```json
{"x": 2690, "y": 373, "w": 380, "h": 300, "opacity": 0.92}
```

- Ukuran bawaan 380 × 300.
- Kalau posisi tersimpan ada di luar semua monitor (misalnya monitor kedua dicabut), posisi itu diabaikan dan jendela dibuka di tempat bawaan.
- **Reset ke bawaan:** tutup aplikasi lalu hapus `~/.config/lyrics-pip/config.json`.
- Mengedit file ini sambil aplikasi berjalan tidak ada gunanya, karena akan ditimpa saat aplikasi ditutup. Tutup aplikasi dulu.

### Tampilan (font, warna)
Belum ada pengaturan lewat file. Ubah konstanta `CSS` di `lyrics_pip/ui.py`:

| Selector | Mengatur |
|----------|----------|
| `window.lyrics` | warna latar jendela dan sudut membulat |
| `.line` | baris lirik biasa (warna, ukuran font) |
| `.line.active` | baris yang sedang dinyanyikan (bawaan putih, tebal, 15pt) |
| `.title` | judul dan artis di bagian atas |

Restart aplikasi setelah mengubahnya.

### Cache lirik
Disimpan di `~/.cache/lyrics-pip/`. Hapus folder itu untuk memaksa semua lirik diunduh ulang, misalnya kalau lirik sebuah lagu salah atau sudah diperbarui di LRCLIB. Lagu yang tidak ditemukan hanya di-cache 1 jam, lalu dicoba lagi.

### Entri menu aplikasi (opsional)
Supaya bisa dibuka dari menu XFCE tanpa terminal, buat `~/.local/share/applications/lyrics-pip.desktop` (ganti path sesuai lokasi proyek Anda):

```ini
[Desktop Entry]
Type=Application
Name=Lyrics PiP
Comment=Lirik mengambang untuk lagu YouTube Music di Firefox
Exec=/path/ke/lyrics-app/lyrics-pip
Icon=multimedia-audio-player
Terminal=false
Categories=AudioVideo;Audio;Player;
```

Untuk menyala otomatis saat login, salin file yang sama ke `~/.config/autostart/`.

## Lirik pribadi

Untuk lagu yang tidak ditemukan di LRCLIB, atau yang liriknya salah, Anda bisa menempel lirik sendiri.

- **Tambah lirik:** saat muncul "Lirik tidak ditemukan", klik tombol **Tambah lirik**, tempel teksnya, klik **Simpan**. Lirik langsung tampil.
- **Ubah lirik:** tombol **✎** di header (muncul saat ada lagu) membuka kotak tempel. Kalau lagu itu sudah punya lirik pribadi, kotaknya terisi lirik tersebut.
- **Hapus lirik pribadi:** kosongkan kotak lalu **Simpan**. Aplikasi kembali memakai lirik dari LRCLIB.
- **Muat ulang:** tombol **⟳** di header menghapus cache lagu yang sedang diputar dan mengambilnya lagi dari awal (misalnya setelah liriknya ditambahkan ke LRCLIB).

Teks boleh berupa lirik biasa (tampil tanpa sorotan) atau format LRC seperti `[00:12.50] baris lirik` (baris aktif tersorot dan mengikuti lagu). Formatnya dikenali otomatis.

Lirik pribadi disimpan sebagai file di folder `lyrics/` di dalam proyek, bernama `Artis - Judul.lrc` atau `Artis - Judul.txt`. Anda juga bisa menaruh file di sana secara manual. File pribadi selalu dipakai lebih dulu daripada LRCLIB.

> **Folder `lyrics/` sengaja di-ignore git dan tidak boleh di-commit.** Lirik lagu berhak cipta, dan repo ini Public. Kalau ingin mencadangkannya, pakai repo Private terpisah atau salin manual.

## Tes

```bash
python3 -m unittest discover -s tests
```

## Struktur

```
lyrics_pip/
  lrc.py      parser LRC dan pencarian baris aktif
  lyrics.py   klien LRCLIB (dengan fallback) dan cache disk
  mpris.py    pembaca MPRIS dari Firefox
  clock.py    penaksir posisi (Firefox hanya melaporkan detik bulat)
  custom.py   lirik pribadi (folder lyrics/) dan urutan pencarian
  ui.py       jendela GTK
  app.py      perangkai dan main()
  instance.py penjaga instance tunggal (file lock)
tests/        tes unittest
docs/superpowers/   desain dan rencana pembuatan
```

## Batasan

- Hanya Firefox (bus MPRIS `org.mpris.MediaPlayer2.firefox*`).
- Tidak semua lagu ada di LRCLIB. Lagu yang tidak ditemukan menampilkan "Lirik tidak ditemukan".
- Pemakaian RAM sekitar 58 MB (GTK3 sendiri sekitar 45 MB); CPU sekitar 1%.
