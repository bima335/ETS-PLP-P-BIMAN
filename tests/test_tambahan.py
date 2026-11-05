"""Test tambahan buatan kelompok.

Isi dengan:
1. Satu test regresi untuk setiap bug yang kalian perbaiki (gagal sebelum perbaikan,
   lulus sesudahnya). Beri nama yang menjelaskan bug-nya.
2. Lima test kasus tepi, masing-masing dengan komentar singkat mengapa kasus itu berisiko.
"""

from crud.lexer import tokenize, TokenType as T, LexError
import pytest

# --- L2 ---
def test_operator_tidak_sama_satu_token():
    ops = [t for t in tokenize("a <> 1") if t.type == T.OP]
    assert [t.value for t in ops] == ["<>"]
