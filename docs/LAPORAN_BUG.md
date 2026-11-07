# Laporan Bug

Salin blok di bawah untuk setiap bug. Bagian **Akar masalah** wajib ditulis dengan kata-kata
sendiri dan memakai konsep dari *Crafting Interpreters* (sebutkan bab). Bagian ini diuji lisan.

---

## Bug L2: Operator Tidak Sama (<>) Terpecah Menjadi Dua Token

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Input `a <> 1` menghasilkan dua token terpisah yaitu token OP `<` dan token OP `>`, padahal menurut SPESIFIKASI.md bagian 2.5 lexer harus menerapkan aturan *maximal munch*, di mana operator terpanjang yang cocok diambil sebagai satu kesatuan sehingga `<>` harus berupa satu token `OP`.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
SELECT 1 FROM t WHERE a <> 1;
```

**Akar masalah.** Pelanggaran prinsip *maximal munch* (Crafting Interpreters Bab 4: Scanning). Pada fungsi `_scan_token()` di `crud/lexer.py`, cabang karakter `<` hanya memeriksa karakter `=` berikutnya untuk membentuk `<=`, tetapi tidak memeriksa kemungkinan karakter `>`. Akibatnya, karakter `<` langsung diemisikan sebagai token tersendiri dan karakter `>` sesudahnya diproses sebagai token berikutnya secara terpisah.

**Perbaikan.** Pada `crud/lexer.py` di fungsi `_scan_token()`, cabang `ch == "<"` diperbaiki dengan menambahkan lookahead menggunakan `self._match(">")` sebelum memeriksa `=`. Jika cocok, nilai operator yang diemisikan adalah `<>`.
- *Alternatif yang ditolak:* Menggabungkan `<` dan `>` di tingkat parser. Ditolak karena melanggar batasan arsitektur modularitas; lexer bertanggung jawab penuh menghasilkan token leksikal yang utuh dan benar sebelum diserahkan ke parser.

**Test regresi.** `test_regress_L2_neq_satu_token` di `tests/test_tambahan.py`.

---

## Bug T3: Komentar Blok (/* ... */) Belum Didukung

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Menemukan query yang memuat komentar blok seperti `/* komentar */` langsung melempar `LexError: Baris 1, kolom 1: komentar blok belum didukung`. Menurut SPESIFIKASI.md bagian 2.3, komentar blok boleh lintas baris, boleh memuat karakter `*`, tidak bersarang, tidak menghasilkan token apa pun, dan hanya melempar `LexError` jika tidak ditutup hingga EOF.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
/* komentar */ SELECT 1 FROM t;
```

**Akar masalah.** Fitur TODO(T3) pada lexer belum diimplementasikan (Crafting Interpreters Bab 4: Scanning). Pada cabang `ch == "/" and self._peek() == "*"` di `_scan_token()`, kode sebelumnya langsung melempar `LexError`. Selain itu, pemindaian komentar blok memerlukan lookahead dua karakter (`_peek()` dan `_peek(1)`) agar karakter `*` tunggal di dalam komentar tidak dianggap sebagai penutup sebelum bertemu `/`.

**Perbaikan.** Pada `crud/lexer.py` di cabang `ch == "/" and self._peek() == "*"`, karakter pembuka dilewati lalu dilakukan perulangan karakter demi karakter menggunakan `self._advance()`. Loop mencari pasangan `*` dan `/` secara bersamaan menggunakan `self._peek() == "*"` dan `self._peek(1) == "/"`. Jika akhir input (`self._at_end()`) tercapai sebelum penutup ditemukan, dilempar `LexError("komentar blok tidak ditutup", line, col)` mengacu pada baris dan kolom awal komentar. Karena komentar tidak menghasilkan token, fungsi langsung melakukan `return`.
- *Alternatif yang ditolak:* Menggunakan regex `r"/\*.*?\*/"`. Ditolak karena melanggar batasan arsitektur (komentar harus dipindai oleh scanner lexer untuk menghitung nomor baris dan kolom secara akurat melalui `_advance()`).

**Test regresi.** `test_regress_T3_komentar_blok` di `tests/test_tambahan.py`.

---

## Bug P2: Panic Mode Recovery Menghilangkan Seluruh Statement Berikutnya

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Jika terdapat statement yang rusak secara sintaks, semua statement valid berikutnya ikut lenyap dari hasil `script.statements`. Menurut SPESIFIKASI.md bagian 6, parser harus menerapkan *panic mode error recovery* di mana parser membuang token hanya sampai dan termasuk `;` berikutnya, lalu melanjutkan parsing statement yang tersisa secara independen.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
SELECT FROM x; SELECT a FROM t;
```

**Akar masalah.** Implementasi fungsi `_synchronize()` yang salah (Crafting Interpreters Bab 6: Parsing Expressions - Panic Mode Error Recovery). Pada `crud/parser.py`, fungsi `_synchronize()` sebelumnya membuang semua token hingga `self._at_end()` tercapai tanpa pernah berhenti pada titik sinkronisasi (delimiter titik koma `;`), sehingga satu kesalahan sintaks mengakibatkan seluruh sisa script diabaikan.

**Perbaikan.** Pada `crud/parser.py` di fungsi `_synchronize()`, loop pengabaian token memeriksa apakah token saat ini bertipe `TokenType.SEMICOLON`. Jika ya, token titik koma tersebut dikonsumsi (`self._advance()`) dan fungsi langsung kembali (`return`), sehingga loop utama `parse_script` dapat melanjutkan parsing statement berikutnya.
- *Alternatif yang ditolak:* Melakukan sinkronisasi dengan berhenti di keyword awal statement berikutnya (`SELECT`, `INSERT`, dll). Ditolak karena keyword seperti `SELECT` sering muncul di dalam subquery, sehingga sinkronisasi berbasis keyword berisiko memulai parsing di tengah struktur ekspresi yang belum tuntas dan memicu rentetan error palsu (cascading errors).

**Test regresi.** `test_regress_P2_recovery_tidak_menelan_sisa_script` di `tests/test_tambahan.py`.

---

## Bug T1: Sintaks INSERT INTO ... SELECT Ditolak oleh Parser

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Statement bentuk `INSERT INTO t SELECT ...` menghasilkan `ParseError: INSERT ... SELECT belum didukung`. Menurut SPESIFIKASI.md bagian 3 (aturan grammar `insert_stmt`) dan bagian 5 (aturan CRUD), konstruksi `INSERT ... SELECT` adalah konstruksi valid yang harus menghasilkan node `ast.Insert` dengan sumber query berupa `ast.Select`.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
INSERT INTO arsip SELECT id FROM pesanan;
```

**Akar masalah.** Fitur TODO(T1) pada parser belum dihubungkan (Crafting Interpreters Bab 5: Representing Code dan Bab 6: Parsing Expressions). Pada fungsi `_insert()` di `crud/parser.py`, cabang `if self._check_kw("SELECT")` masih berupa placeholder yang melempar `ParseError`.

**Perbaikan.** Pada `crud/parser.py` di fungsi `_insert()`, cabang `if self._check_kw("SELECT")` diubah untuk memanggil `query = self._select()` dan mengembalikan node `ast.Insert(table, columns, [], query, line=start.line)`. Atribut `values` diisi list kosong `[]` (bukan `None`) agar tidak menimbulkan `TypeError` saat dilakukan iterasi `for row in stmt.values` pada resolver dan analyzer.
- *Alternatif yang ditolak:* Mengisi `values=None`. Ditolak karena resolver dan analyzer mengasumsikan `stmt.values` selalu berupa iterable (list).

**Test regresi.** `test_regress_T1_insert_select` di `tests/test_tambahan.py`.

---

## Bug R2: Kebocoran Scope pada Statement DELETE

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Alias tabel yang didefinisikan pada statement `DELETE` tetap terlihat dan dapat diakses oleh statement berikutnya tanpa memicu error `alias tidak terdefinisi`. Menurut SPESIFIKASI.md bagian 4.5, setiap statement berdiri sendiri dan setelah satu statement selesai di-resolve tidak boleh ada scope yang tersisa.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
DELETE FROM sesi s WHERE s.k < 1; SELECT s.id FROM pengguna u;
```

**Akar masalah.** Pelanggaran manajemen siklus hidup scope / *environment cleanup* (Crafting Interpreters Bab 11: Resolving and Binding). Fungsi `_delete()` di `crud/resolver.py` memanggil `self._push()` saat memasuki statement delete untuk mendaftarkan target tabel ke scope lokal, namun lupa memanggil `self._pop()` saat selesai memproses klausa WHERE. Akibatnya scope lokal statement `DELETE` tidak pernah dihancurkan dan bocor ke statement-statement berikutnya.

**Perbaikan.** Pada `crud/resolver.py` di akhir fungsi `_delete()`, ditambahkan pemanggilan `self._pop()`. Hal ini menjamin bahwa rantai scope kembali ke scope induk/bersih setelah statement `DELETE` selesai diproses.
- *Alternatif yang ditolak:* Memaksa reset `self.scope = None` di awal setiap statement. Ditolak karena tidak mengatasi akar masalah bahwa setiap `_push()` harus memiliki pasangan `_pop()` secara berimbang dan simetris (sebagaimana yang sudah diterapkan di `_select` dan `_update`).

**Test regresi.** `test_regress_R2_alias_delete_tidak_bocor` di `tests/test_tambahan.py`.

---

## Bug A1: Subquery pada Statement UPDATE Salah Diberi Operasi U

**Ditemukan oleh:** Iman · **Diperbaiki oleh:** Iman (Reviewer: Bima)

**Gejala.** Tabel yang dibaca di dalam klausa `WHERE` atau penugasan `SET` pada statement `UPDATE` melalui subquery dicatat memiliki operasi `U` (Update), bukan `R` (Read). Misalnya pada `UPDATE p SET a = 1 WHERE id IN (SELECT id FROM q)`, tabel `q` dicatat sebagai `U`. Menurut SPESIFIKASI.md bagian 5, operasi membaca tabel lewat subquery selalu bernilai `R`, apa pun jenis statement luarnya.

**Reproduksi minimal.** SQL terpendek yang memicu bug:

```sql
UPDATE p SET a = 1 WHERE id IN (SELECT id FROM q);
```

**Akar masalah.** Kesalahan penjalaran konteks operasi pada tree-walk AST visitor (Crafting Interpreters Bab 5: A Higher-Level Language). Pada fungsi `analyze_statement()` di `crud/analyzer.py`, cabang `ast.Update` memanggil fungsi pembantu `_collect()` untuk `assignment.value` dan `stmt.where` dengan menyuplai argumen operasi `"U"`, alih-alih `"R"`.

**Perbaikan.** Pada `crud/analyzer.py` di dalam cabang `isinstance(stmt, ast.Update)`, argumen operasi pada pemanggilan `_collect(assignment.value, usage, "U")` dan `_collect(stmt.where, usage, "U")` diubah menjadi `"R"`.
- *Alternatif yang ditolak:* Memeriksa jenis ekspresi di dalam `_collect()` dan mengubah "U" menjadi "R" jika menemukan node subquery. Ditolak karena membuat fungsi `_collect()` menjadi inkonsisten dan menambahkan percabangan khusus yang tidak perlu, padahal pemanggil (`analyze_statement`) sudah tahu secara pasti bahwa evaluasi ekspresi selalu berstatus pembacaan (Read).

**Test regresi.** `test_regress_A1_subquery_update_selalu_read` di `tests/test_tambahan.py`.