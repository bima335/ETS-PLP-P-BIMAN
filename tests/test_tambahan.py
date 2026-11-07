"""Test tambahan buatan kelompok (total 17 test; ketentuan minimal 14).

Bagian 1: 9 test regresi, satu per bug yang ditanam di kode awal
(L1, L2, L3, P1, P2, P3, R1, R2, A1). Nama test menyebut ID bug-nya
(`test_regress_<ID>_...`) dan ID itu sama dengan di docs/LAPORAN_BUG.md.

Bagian 2: 3 test untuk fitur yang awalnya berupa TODO di kode (T1, T2, T3).
Bukan bug yang ditanam, tetapi diuji dengan pola yang sama.

Bagian 3: 5 test kasus tepi. Masing-masing diberi komentar mengapa kasus
itu berisiko, yaitu bagian spesifikasi yang mudah "terlompati" oleh
implementasi yang naif.

Semua test regresi (Bagian 1 dan 2) gagal pada kode awal (commit 2969d29)
dan lulus pada kode sesudah perbaikan. Dicek juga per bug: jika perbaikan
satu bug saja dibatalkan, test bug itu yang gagal.
"""

from crud.lexer import tokenize, TokenType as T, LexError
from crud.parser import parse_sql, ParseError
from crud.resolver import Resolver
from crud.pipeline import analyze_source
from crud import ast_nodes as ast
import pytest


# ============================================================
# Bagian 1 — 9 test regresi, satu per bug
# ============================================================

# --- Bug L2: maximal munch untuk operator '<>' -------------------------
# Kode lama memecah '<>' menjadi OP '<' lalu OP '>' karena cabang
# ch == "<" tidak memeriksa karakter '>' berikutnya.
def test_regress_L2_neq_satu_token():
    ops = [t for t in tokenize("a <> 1") if t.type == T.OP]
    # Maximal munch: operator terpanjang harus jadi SATU token OP '<>'.
    assert [t.value for t in ops] == ["<>"]


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


# --- Bug L1: keyword peka huruf besar/kecil -----------------------------
# Kode lama membandingkan teks asli dengan KEYWORDS, sehingga 'select'
# menjadi IDENT. Perbaikan: bandingkan versi huruf besar, simpan nilai
# keyword dalam huruf besar. Kata yang hanya DIAWALI keyword tetap IDENT.
def test_regress_L1_keyword_tidak_peka_huruf():
    toks = tokenize("select Select SELECT selection fromage")
    assert [(t.type, t.value) for t in toks[:3]] == [(T.KEYWORD, "SELECT")] * 3
    assert [(t.type, t.value) for t in toks[3:5]] == [
        (T.IDENT, "selection"), (T.IDENT, "fromage")]


# --- Bug L3: '' di dalam string ----------------------------------------
# Kode lama menutup string di kutip pertama, jadi 'O''Brien' pecah menjadi
# dua STRING. Spesifikasi 2.4: '' adalah SATU karakter kutip.
def test_regress_L3_kutip_ganda_dalam_string():
    toks = [t for t in tokenize("'O''Brien'") if t.type != T.EOF]
    assert [(t.type, t.value) for t in toks] == [(T.STRING, "O'Brien")]
    # string yang diakhiri '' lalu kutip penutup tetap utuh
    assert tokenize("'a'''")[0].value == "a'"


# --- Bug P1: AND dan OR berpresedensi sama -------------------------------
# _logical lama memproses AND/OR dalam satu loop, jadi 'a OR b AND c'
# dibaca '(a OR b) AND c'. Spesifikasi 3.1: AND lebih kuat dari OR.
def test_regress_P1_and_lebih_kuat_dari_or():
    s = parse_sql("SELECT 1 FROM t WHERE a = 1 OR b = 2 AND c = 3;")
    w = s.statements[0].where
    assert isinstance(w, ast.BinaryOp) and w.op == "OR"
    assert w.left.op == "="
    assert w.right.op == "AND"
    # asosiatif kiri: a AND b AND c = (a AND b) AND c
    w2 = parse_sql("SELECT 1 FROM t WHERE a = 1 AND b = 2 AND c = 3;").statements[0].where
    assert w2.op == "AND" and w2.left.op == "AND" and w2.right.op == "="


# --- Bug P3: LEFT OUTER JOIN ditolak -------------------------------------
# Grammar: join = [ INNER | LEFT [ OUTER ] ] JOIN. Kode lama tidak menerima
# OUTER setelah LEFT sehingga statement ditolak.
def test_regress_P3_left_outer_join():
    for sql in ("SELECT 1 FROM a LEFT OUTER JOIN b ON a.x = b.x;",
                "SELECT 1 FROM a LEFT JOIN b ON a.x = b.x;"):
        s = parse_sql(sql)
        assert not s.errors
        assert s.statements[0].joins[0].kind == "LEFT"


# --- Bug R1: pencarian scope dari luar ke dalam ---------------------------
# _lookup lama mencari dari scope terluar, sehingga alias subquery tidak
# menutupi alias luar. Spesifikasi 4.3: terdalam dulu (shadowing), dan
# alias luar tetap terlihat (correlated subquery).
def _resolved(sql):
    script = parse_sql(sql)
    diags = Resolver().resolve_script(script)
    cols = [(n.qualifier, n.name, n.resolved)
            for st in script.statements for n in ast.iter_nodes(st)
            if isinstance(n, ast.ColumnRef)]
    return diags, cols


def test_regress_R1_shadowing_dan_correlated():
    diags, cols = _resolved(
        "SELECT x.a FROM t x WHERE x.a IN (SELECT x.b FROM u x);")
    assert not diags
    # x.b di subquery harus ke u (alias dalam menutupi alias luar)
    assert ("x", "b", "u") in cols
    diags, cols = _resolved(
        "SELECT p.a FROM t p WHERE EXISTS (SELECT 1 FROM u WHERE u.id = p.id);")
    assert not diags
    assert ("p", "id", "t") in cols      # subquery masih melihat alias luar


# ============================================================
# Bagian 2 — 3 test regresi untuk fitur TODO (T1, T2, T3)
# ============================================================

# --- Fitur T1: INSERT INTO ... SELECT ditolak -----------------------------
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


# --- Fitur T2: kolom tanpa qualifier --------------------------------------
# Satu tabel -> resolved; lebih dari satu -> warning dan resolved None.
def test_regress_T2_kolom_tanpa_qualifier():
    diags, cols = _resolved("SELECT a FROM crm.t;")
    assert not diags and cols == [(None, "a", "crm.t")]
    diags, cols = _resolved("SELECT a FROM t, u;")
    assert [d.level for d in diags] == ["warning"]
    assert "ambigu tanpa skema" in diags[0].message
    assert cols == [(None, "a", None)]


# --- Fitur T3: komentar blok (/* ... */) belum didukung -----------------
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


# ============================================================
# Bagian 3 — Lima test kasus tepi
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