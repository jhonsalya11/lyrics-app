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

Posisi, ukuran, dan transparansi disimpan di `~/.config/lyrics-pip/config.json`.

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
  ui.py       jendela GTK
  app.py      perangkai dan main()
tests/        tes unittest
docs/superpowers/   desain dan rencana pembuatan
```

## Batasan

- Hanya Firefox (bus MPRIS `org.mpris.MediaPlayer2.firefox*`).
- Tidak semua lagu ada di LRCLIB. Lagu yang tidak ditemukan menampilkan "Lirik tidak ditemukan".
- Pemakaian RAM sekitar 58 MB (GTK3 sendiri sekitar 45 MB); CPU sekitar 1%.
