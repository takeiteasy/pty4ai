from pty4ai.ring import RingBuffer


def test_append_and_read_since_zero():
    r = RingBuffer(capacity=1024)
    r.append(b"hello")
    data, seq, truncated = r.read_since(0)
    assert data == b"hello"
    assert seq == 5
    assert not truncated


def test_cursor_advances():
    r = RingBuffer(capacity=1024)
    r.append(b"abc")
    _, seq1, _ = r.read_since(0)
    r.append(b"def")
    data, seq2, truncated = r.read_since(seq1)
    assert data == b"def"
    assert seq2 == 6
    assert not truncated


def test_overflow_trims_and_flags_truncation():
    r = RingBuffer(capacity=4)
    r.append(b"abcd")
    r.append(b"efgh")  # buffer now holds only "efgh"; "abcd" is gone
    data, seq, truncated = r.read_since(0)
    assert truncated is True
    assert data == b"efgh"
    assert seq == 8


def test_empty_append_is_noop():
    r = RingBuffer(capacity=4)
    r.append(b"")
    assert r.seq == 0
