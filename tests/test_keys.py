import pytest

from pty4ai.keys import UnknownKey, key_bytes


def test_enter_and_aliases():
    assert key_bytes("Enter") == b"\r"
    assert key_bytes("return") == b"\r"


def test_control_c_is_byte_three():
    assert key_bytes("C-c") == b"\x03"
    assert key_bytes("^c") == b"\x03"


def test_arrow_keys_are_csi_sequences():
    assert key_bytes("Up") == b"\x1b[A"
    assert key_bytes("left") == b"\x1b[D"


def test_case_insensitive():
    assert key_bytes("ESCAPE") == key_bytes("esc") == b"\x1b"


def test_unknown_key_raises():
    with pytest.raises(UnknownKey):
        key_bytes("not-a-real-key")
