"""Test tambahan buatan kelompok.

Bagian 1: satu test regresi untuk tiap bug di docs/LAPORAN_BUG.md
(L2, T3, P2, T1, R2, A1). Tiap test gagal pada kode lama dan lulus
sesudah perbaikan.

Bagian 2: lima test kasus tepi. Masing-masing diberi komentar
mengapa kasus itu berisiko — yaitu bagian spesifikasi yang mudah
"terlompati" oleh implementasi yang naif.
"""

from crud.lexer import tokenize, TokenType as T, LexError
from crud.parser import parse_sql, ParseError
from crud.resolver import Resolver
from crud.pipeline import analyze_source
from crud import ast_nodes as ast
import pytest


# ============================================================
# Bagian 1 — Test regresi per bug
# ============================================================

# --- Bug L2: maximal munch untuk operator '<>' -------------------------
# Kode lama memecah '<>' menjadi OP '<' lalu OP '>' karena cabang
# ch == "<" tidak memeriksa karakter '>' berikutnya.
def test_regress_L2_neq_satu_token():
    ops = [t for t in tokenize("a <> 1") if t.type == T.OP]
    # Maximal munch: operator terpanjang harus jadi SATU token OP '<>'.
    assert [t.value for t in ops] == ["<>"]


# --- Bug T3: komentar blok (/* ... */) belum didukung -----------------
# Kode lama melempar LexError begitu melihat '/*'. Perbaikan harus juga
# menangani komentar tidak ditutup (LexError) dan menjaga posisi baris.
def test_regress_T3_komentar_blok():
    # Komentar lintas baris tidak boleh menghasilkan token, dan SELECT
    # yang mengikutinya harus tetap tercatat di baris 2.
    toks = tokenize("/* baris pertama\n * baris kedua */ SELECT 1")
    assert toks[0].type == T.KEYWORD and toks[0].value == "SELECT"
    assert toks[0].line == 2
    # Komentar blok yang tidak ditutup hingga EOF adalah LexError.
    with pytest.raises(LexError):
        tokenize("SELECT /* tidak pernah ditutup")


# --- Bug P2: panic mode menelan seluruh statement berikutnya ----------
# _synchronize() lama membuang semua token sampai EOF; perbaikan berhenti
# pada ';' berikutnya sehingga statement valid setelahnya tetap diproses.
def test_regress_P2_recovery_tidak_menelan_sisa_script():
    s = parse_sql("SELECT FROM x; SELECT a FROM t; SELECT b FROM u;")
    # Statement rusak menghasilkan TEPAT satu ParseError ...
    assert len(s.errors) == 1
    assert isinstance(s.errors[0], ParseError)
    # ... dan dua statement valid setelahnya tetap diparse.
    assert len(s.statements) == 2


# --- Bug T1: INSERT INTO ... SELECT ditolak -----------------------------
# Cabang SELECT di _insert() lama masih placeholder yang melempar
# ParseError; kode benar menghasilkan ast.Insert dengan query terisi.
def test_regress_T1_insert_select():
    s = parse_sql("INSERT INTO t (a, b) SELECT x, y FROM u;")
    assert not s.errors
    ins = s.statements[0]
    assert isinstance(ins, ast.Insert)
    # Kolom target terbaca, dan sumbernya adalah sub-SELECT, bukan VALUES.
    assert ins.columns == ["a", "b"]
    assert ins.query is not None
    assert ins.values == []


# --- Bug R2: scope DELETE bocor ke statement berikutnya -----------------
# _delete() lama tidak memanggil _pop(), sehingga alias 's' tetap hidup
# dan dipakai lagi oleh SELECT berikutnya tanpa error.
def test_regress_R2_alias_delete_tidak_bocor():
    script = parse_sql("DELETE FROM sesi s WHERE s.k < 1; SELECT s.id FROM pengguna u;")
    diags = Resolver().resolve_script(script)
    # Alias 's' milik DELETE sudah hancur; pemakaiannya di SELECT berikutnya
    # harus menimbulkan error "alias tidak terdefinisi" (bukan warning).
    assert any(d.level == "error" and "'s'" in d.message for d in diags)


# --- Bug A1: subquery dalam UPDATE salah diberi operasi U ---------------
# _collect() untuk assignment.value / stmt.where lama disuplai "U";
# aturan bagian 5: tabel yang dibaca lewat subquery SELALU R.
def test_regress_A1_subquery_update_selalu_read():
    r = analyze_source("UPDATE p SET a = 1 WHERE id IN (SELECT id FROM q);")
    # p memang di-update (U), tetapi q hanya dibaca lewat subquery (R).
    assert r.matrix() == {"p": "U", "q": "R"}


# ============================================================
# Bagian 2 — Lima test kasus tepi
# ============================================================

# --- Tepi 1: komentar blok berisi '*' dan '--' --------------------------
# Berisiko: penutup komentar harus dicari sebagai PASANGAN '*/', bukan '*'
# sendirian. Komentar yang berisi '*' tunggal (atau tanda '--') di tengahnya
# tidak boleh keliru dianggap penutup — kalau tidak, sisanya komentar ikut
# dianggap kode SQL dan memicu error / token palsu.
def test_tepi_komentar_blok_berisi_bintang_dan_strip_ganda():
    toks = tokenize("/* a * b -- c\nSELECT */ SELECT 1")
    isi = [t.value for t in toks if t.type != T.EOF]
    # Semua isi komentar lenyap; hanya SELECT 1 sesudahnya yang menjadi token.
    # (SELECT di dalam komentar juga tidak ikut ke-tokenisasi.)
    assert isi == ["SELECT", "1"]


# --- Tepi 2: ';;' berurutan dan file kosong ----------------------------
# Berisiko: aturan script = { ";" | statement ... } memungkinkan titik koma
# muncul tanpa statement. Grammar yang ditulis naif sering memaksa tepat
# satu statement per ';' atau meminta statement pertama wajib ada.
def test_tepi_semicolon_berurutan_dan_file_kosong():
    s = parse_sql(";;SELECT 1 FROM t;;")
    assert s.errors == []            # tidak ada ParseError sama sekali
    assert len(s.statements) == 1    # tiga ';' di antaranya hanya pemisah
    s_kosong = parse_sql("")
    assert s_kosong.errors == []     # file kosong: bukan error sintaks
    assert s_kosong.statements == []


# --- Tepi 3: dua statement rusak → tepat dua ParseError -----------------
# Berisiko: panic mode harus jalan DUA kali secara independen. Implementasi
# yang buruk biasanya menghasilkan error berantakan (cascading errors)
# atau menelan statement valid di antara dua statement rusak.
def test_tepi_dua_error_pada_dua_statement():
    s = parse_sql("SELECT FROM x; SELECT a FROM t; SELECT y z w FROM;")
    assert len(s.errors) == 2                    # tepat dua, tidak lebih
    assert all(isinstance(e, ParseError) for e in s.errors)
    assert len(s.statements) == 1              # statement valid di tengah selamat


# --- Tepi 4: 'x BETWEEN 1 AND 5 AND y = 2' (AND milik BETWEEN) -----------
# Berisiko: parser presedensi tingkat-tiga (OR < AND < comparison) cenderung
# menelan AND kedua ke dalam hirarki AND dan salah membaca batas atas
# BETWEEN. Spesifikasi 3.2: batas BETWEEN adalah additive, jadi
# '1 AND 5' tertutup di dalam Between dan 'AND y = 2' adalah AND logika.
def test_tepi_between_and_milik_between():
    s = parse_sql("SELECT a FROM t WHERE x BETWEEN 1 AND 5 AND y = 2;")
    assert not s.errors
    where = s.statements[0].where
    # Akar adalah AND logika, bukan Between: Between hanya anak kiri.
    assert isinstance(where, ast.BinaryOp) and where.op == "AND"
    assert isinstance(where.left, ast.Between)
    # Batas atas BETWEEN berhenti di 5 (bukan menelan 'AND y = 2').
    assert where.left.high.value == "5"
    assert where.left.low.value == "1"
    # Sisa 'AND y = 2' menjadi anak kanan: perbandingan '=' pada y.
    assert isinstance(where.right, ast.BinaryOp) and where.right.op == "="


# --- Tepi 5: 'FROM a x, b x' → alias ganda -----------------------------
# Berisiko: dua tabel di klausa FROM yang sama keduanya memakai alias
# identik. Resolver harus menolaknya (spesifikasi 4.2: nama yang
# dideklarasikan dua kali di scope sama adalah error), bukan diam-diam
# menimpa alias pertama — kalau ditimpa, resolusi kolom 'x.id' jadi ambigu
# atau salah arah.
def test_tepi_alias_ganda_pada_scope_yang_sama():
    script = parse_sql("SELECT x.id FROM a x, b x;")
    diags = Resolver().resolve_script(script)
    assert any(d.level == "error" and "dideklarasikan dua kali" in d.message
               for d in diags)