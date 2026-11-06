# Laporan Akhir

## 1. Hasil evaluasi

Tempel keluaran `python evaluate.py` setelah `data/ground_truth.csv` dilengkapi.

Dievaluasi: audit.sql, campuran_error.sql, laporan_penjualan.sql, pemeliharaan.sql (27 triple)

Metode   Precision  Recall     F1
parser        1.00    1.00   1.00
regex         0.65    0.81   0.72

[regex]
  salah ditemukan (FP): ('audit.sql', 16, 'sesi', 'R')
  salah ditemukan (FP): ('campuran_error.sql', 4, 'pesanan', 'R')
  salah ditemukan (FP): ('campuran_error.sql', 8, 'keranjang', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pelanggan', 'D')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pelanggan', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'pesanan', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 2, 'rahasia', 'R')
  salah ditemukan (FP): ('laporan_penjualan.sql', 15, 'pesanan', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'crm.alamat', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'crm.pelanggan', 'R')
  salah ditemukan (FP): ('pemeliharaan.sql', 2, 'pelanggan_lama', 'U')
  salah ditemukan (FP): ('pemeliharaan.sql', 15, 'crm.alamat', 'R')
  terlewat (FN):       ('audit.sql', 2, 'pesanan', 'R')
  terlewat (FN):       ('laporan_penjualan.sql', 3, 'pelanggan', 'R')
  terlewat (FN):       ('laporan_penjualan.sql', 3, 'pesanan', 'R')
  terlewat (FN):       ('pemeliharaan.sql', 3, 'crm.alamat', 'R')
  terlewat (FN):       ('pemeliharaan.sql', 3, 'crm.pelanggan', 'R')


## 2. Tiga kasus di mana regex salah

Untuk tiap kasus: SQL-nya, kesalahan regex, dan mengapa parser benar (kaitkan dengan konsep
lexing, parsing, atau resolusi).

1. Komentar dan string literal dibaca sebagai kode, plus nomor baris statement bergeser.
SQL (laporan_penjualan.sql baris 1 - 3):
-- Laporan penjualan bulanan
-- DELETE FROM pelanggan   (baris ini komentar, bukan perintah)
SELECT p.nama, SUM(o.total) AS omzet

Kesalahan regex: baseline tidak memahami komentar -- maupun /* ... */, sehingga
DELETE FROM pelanggan di dalam komentar dipetakan menjadi triple
(laporan_penjualan.sql, 2, pelanggan, D). Pola \bFROM\s+NAME juga cocok di dalam
string 'FROM rahasia' pada baris 6 -> (2, rahasia, R). 
Mengapa parser benar: pada tahap lexing (Bab 4), komentar tidak menghasilkan token
(SPESIFIKASI.md 2.3), dan isi string adalah satu token STRING utuh (2.4), sehingga teks
DELETE FROM di dalam komentar/string tidak pernah menjadi keyword. Baris statement
diambil dari baris token keyword pembuka statement yang sesungguhnya (2.1, bagian 8),
yaitu SELECT di baris 3.

2. DELETE FROM x menghasilkan operasi R palsu.
SQL (audit.sql baris 16): DELETE FROM sesi s WHERE s.kedaluwarsa < :sekarang;
Kesalahan regex: pola \bDELETE\s+FROM\s+NAME menghasilkan (16, sesi, D) yang benar,
tetapi pola terpisah \bFROM\s+NAME juga cocok pada substring FROM sesi, sehingga
muncul FP (16, sesi, R). Gejala yang sama menghasilkan FP keranjang R
(campuran_error.sql:8), pesanan R (laporan_penjualan.sql:15), dan crm.alamat R
(pemeliharaan.sql:15).
Mengapa parser benar: parser hanya membangun satu node ast.Delete untuk statement ini
(grammar delete_stmt, Bab 5–6), dan analyzer menandai tepat satu operasi D pada
tabel target sesuai aturan bagian 5. Operasi ditentukan oleh bentuk statement, bukan
oleh keberadaan substring kata kunci.

3. Statement rusak tetap diekstrak, dan error recovery tidak ada.
SQL (campuran_error.sql baris 4): SELECT id nama, FROM pesanan;
Kesalahan regex: statement ini salah sintaks, setelah id dengan alias nama, koma
menuntut select_item baru, tetapi FROM tidak dapat memulai ekspresi. Regex tetap
melaporkan (4, pesanan, R).
Mengapa parser benar: parser recursive descent (Bab 6) gagal di titik itu dan melempar
ParseError, lalu panic mode membuang token sampai ; berikutnya sehingga statement
valid sesudahnya (UPDATE produk, baris 6) tetap diproses.
Mengapa parser benar: parser recursive descent (Bab 6) gagal di titik itu dan melempar
ParseError, lalu panic mode membuang token sampai ; berikutnya sehingga statement
valid sesudahnya (UPDATE produk, baris 6) tetap diproses. Sesuai SPESIFIKASI.md bagian 5,
statement yang gagal di-parse tidak dihitung, sehingga pesanan tidak muncul di matrix.

## 3. Batas pendekatan kami

Minimal tiga hal yang **tidak bisa** ditangani dengan benar oleh tool ini meskipun semua bug
sudah diperbaiki. Untuk tiap batas: contoh SQL atau situasinya, akibatnya pada CRUD matrix,
dan informasi apa yang dibutuhkan untuk mengatasinya.

1. Tidak ada skema database, sehingga kolom tanpa qualifier pada multi-tabel selalu ambigu.
Contoh: SELECT nama FROM pelanggan p, pesanan o; nama tidak bisa dipastikan milik
tabel mana. Akibat: resolver hanya bisa memberi warning "kolom 'nama' ambigu tanpa skema"
dan resolved tetap None, sehingga baris untuk kolom itu tidak punya tabel di keluaran
--kolom. Yang dibutuhkan: metadata katalog/skema database (nama tabel -> daftar kolom)
agar resolusi bisa dibuktikan, bukan ditebak.

2. Kolom hasil subquery di FROM tidak bisa ditelusuri ke tabel dasar.
Contoh: SELECT s.nama FROM (SELECT nama FROM pelanggan) s; sesuai SPESIFIKASI.md 4.2,
kolom yang merujuk subquery di-resolve ke string placeholder "<subquery alias>", bukan ke
pelanggan. Akibat: CRUD matrix tabel masih benar (subquery tetap R), tetapi laporan
pemakaian kolom berhenti di batas derived table. Yang dibutuhkan: ekspansi derived table
secara rekursif dengan mempertahankan pemetaan kolom output -> kolom sumber, yang berarti
tool harus mengevaluasi proyeksi select_list, bukan sekadar scope alias.

3. Subset grammar sengaja terbatas; fitur di luar lingkup dibuang, bukan ditoleransi.
Contoh: WITH aktif AS (SELECT id FROM pelanggan) SELECT * FROM aktif;  WITH bukan
keyword dalam subset kami, sehingga statement ini gagal di-parse. Karena statement yang
gagal di-parse tidak dihitung (bagian 5), CRUD matrix untuk file itu menjadi tidak lengkap
(padahal querynya valid SQL). Hal yang sama berlaku untuk UNION, MERGE, DDL, dan quoted
identifier (bagian 9). Yang dibutuhkan: perluasan grammar, daftar keyword, dan aturan
resolver di luar cakupan 6 jam tugas ini.

## 4. Pembagian kerja

Siapa mengerjakan apa, dan bagaimana kalian memastikan keduanya memahami seluruh kode.

### 4.1 Pembagian peran per bug

Setiap bug ditangani dengan pola Pemilik (menulis test regresi, memperbaiki, commit,
push) dan Reviewer (pull, menjalankan test sendiri, membaca diff, meminta penjelasan,
menulis entri di `docs/LAPORAN_BUG.md`).

**Bima sebagai Pemilik, Iman sebagai Reviewer:**

| Bug | Lapis | Lokasi | Inti perbaikan |
| --- | --- | --- | --- |
| L1 | Lexer | `_word` | Keyword tidak peka huruf besar/kecil; nilai token keyword dinormalisasi ke huruf besar, IDENT tidak diubah |
| L3 | Lexer | `_string` | `''` di dalam string menjadi satu karakter kutip (`'O''Brien'` -> `O'Brien`) |
| T3 | Lexer | `_scan_token` cabang `/` | Komentar blok `/* ... */` lintas baris; LexError di posisi awal bila tidak ditutup; komentar tidak menghasilkan token |
| P1 | Parser | `_logical` | Presedensi AND/OR dipecah menjadi tiga fungsi: `_or` -> `_and` -> `_not` (satu fungsi per tingkat) |
| P3 | Parser | `_join` | Setelah `LEFT`, `OUTER` dicocokkan secara opsional (LEFT JOIN dan LEFT OUTER JOIN sama-sama valid) |
| T1 | Parser | `_insert` | Cabang `SELECT` memanggil `self._select()` dan membuat `ast.Insert` dengan `values=[]` (bukan `None`) |
| R1 | Resolver | `_lookup` | Pencarian scope dari terdalam ke luar; temuan pertama dipakai (shadowing dan correlated subquery) |
| T2 | Resolver | `_column` | Kolom tanpa qualifier: tepat satu tabel -> resolve; lebih dari satu -> warning "kolom 'x' ambigu tanpa skema" (`resolved=None`); nol tabel -> warning. Level `warning`, bukan `error` |
| A1 | Analyzer | cabang `ast.Update` di `analyze_statement` | Tabel yang dibaca lewat subquery di `UPDATE` ditandai `R` (selalu `R` berapapun statement luarnya), disamakan dengan cabang `Delete` |

**Iman sebagai Pemilik, Bima sebagai Reviewer:**

| Bug | Lapis | Lokasi | Inti perbaikan |
| --- | --- | --- | --- |
| L2 | Lexer | `_scan_token` cabang `<` | Maximal munch: cek `>` setelah `<` sebelum `<=` atau `<` tunggal, sehingga `<>` terbaca satu token |
| T3/L2* | Lexer | `_scan_token` cabang `/` | (lihat catatan kolaborasi di bawah) |
| P2 | Parser | `_synchronize` | Recovery panic mode: buang token sampai dan termasuk `;`, berhenti di EOF; error tepat di `;` dan dua `;` berurutan ditangani |
| T1* | Parser | `_insert` | (reviewer pada T1, Pemilik pada kasus tepi `SELECT` di `INSERT`) |
| R2 | Resolver | `_delete` | `_delete` memanggil `_pop()` seperti `_update`, sehingga scope tidak bocor ke statement berikutnya |
| A1* | Analyzer | cabang `ast.Update` | (reviewer; analisis subquery di `SET`, kasus tabel target sekaligus sumber `RU`, subquery bersarang dua tingkat) |

*Catatan kolaborasi:* audit tambahan lexer (bagian 4.4 spesifikasi) dan parser (bagian 5.5)
dikerjakan bersama berpasangan, begitu pula audit kasus tepi: Bima menulis test komentar
blok berisi `*` dan `--`, `;;` berurutan, file kosong, dan dua error menghasilkan tepat
dua `ParseError`; Iman menulis test `x BETWEEN 1 AND 5 AND y = 2` serta alias ganda
`FROM a x, b x`.

### 4.2 Pembagian pekerjaan di luar perbaikan kode

- **Bima**: setup repositori (`git init`, bersih-bersih `__MACOSX`/`.DS_Store`, commit awal,
push), triase lima perintah awal ke `catatan.md`, label ground truth `audit.sql`,
penulisan `KARTU_DESAIN.md` untuk keputusan `*` vs perkalian, presedensi AND/OR,
dan recovery di `;`; bagian 1 dan 2 `LAPORAN_AKHIR.md`.
- **Iman**: clone dan konfigurasi git, cadangan `tests_asli`, pembacaan spesifikasi dua
kali dengan penandaan kata "harus/selalu/tidak boleh/tepat satu", label ground truth
`pemeliharaan.sql`, `KARTU_DESAIN.md` untuk urutan pencarian scope dan kolom tanpa
qualifier; bagian 3 `LAPORAN_AKHIR.md`.
- **Bersama (silang)**: masing-masing mengecek silang label ground truth rekannya,
menjalankan `evaluate.py` hanya setelah label lengkap dan disepakati, dan saling
menjelaskan assert di `tests/test_tambahan.py` milik rekannya.

### 4.3 Cara memastikan keduanya memahami seluruh kode

1. **Rotasi driver/navigator yang ketat.** Commit message setiap perbaikan mencantumkan
pasangan `(driver: Pemilik, navigator: Reviewer)`, sehingga jejak kertas siapa sedang
mengetik dan siapa yang mengarahkan selalu jelas dari `git log`.
2. **Prosedur dua commit terpisah.** Test regresi di-commit dulu dalam keadaan gagal
(Commit 1), baru perbaikannya (Commit 2), sehingga kedua anggota sama-sama menyaksikan
bahwa test tersebut benar-benar mengunci bug.
3. **Silang pada data dan test.** Label ground truth dicek silang, dan tiap anggota
menjelaskan assert milik rekannya; ini mencegah "paham hanya bagian sendiri".