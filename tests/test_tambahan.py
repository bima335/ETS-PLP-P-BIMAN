"""Test tambahan buatan kelompok.

Isi dengan:
1. Satu test regresi untuk setiap bug yang kalian perbaiki (gagal sebelum perbaikan,
   lulus sesudahnya). Beri nama yang menjelaskan bug-nya.
2. Lima test kasus tepi, masing-masing dengan komentar singkat mengapa kasus itu berisiko.
"""

from crud.lexer import tokenize, TokenType as T, LexError
from crud.parser import parse_sql
from crud.resolver import Resolver
from crud import ast_nodes as ast
import pytest

# --- L2 ---
def test_operator_tidak_sama_satu_token():
    ops = [t for t in tokenize("a <> 1") if t.type == T.OP]
    assert [t.value for t in ops] == ["<>"]

# --- T3 ---
def test_komentar_blok_lintas_baris_dan_posisi_baris():
    toks = tokenize("/* a\n * b */ SELECT")
    assert toks[0].value == "SELECT" and toks[0].line == 2

def test_komentar_blok_tidak_ditutup():
    with pytest.raises(LexError):
        tokenize("SELECT /* belum selesai")

# --- P2 ---
def test_recovery_satu_error_statement_lain_tetap():
    s = parse_sql("SELECT FROM x; SELECT a FROM t; SELECT b FROM u;")
    assert len(s.errors) == 1
    assert len(s.statements) == 2

# --- T1 ---
def test_insert_select_dengan_kolom():
    s = parse_sql("INSERT INTO t (a, b) SELECT x, y FROM u;")
    assert not s.errors
    ins = s.statements[0]
    assert ins.columns == ["a", "b"] and ins.query is not None

# --- R2 ---
def test_alias_delete_tidak_bocor():
    script = parse_sql("DELETE FROM sesi s WHERE s.k < 1; SELECT s.id FROM pengguna u;")
    diags = Resolver().resolve_script(script)
    assert any(d.level == "error" and "'s'" in d.message for d in diags)
