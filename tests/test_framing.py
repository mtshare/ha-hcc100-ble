import pytest
from hcc100_ble import ProtocolError
from hcc100_ble.framing import ENCRYPTED, HANDSHAKE, FrameReader, FrameWriter


@pytest.mark.parametrize("limit", [4, 16, 178, 255])
@pytest.mark.parametrize("length", [0, 5, 80, 692, 2048])
def test_fragmentation_and_counter_wrap(limit, length):
    writer, reader = FrameWriter(limit), FrameReader()
    writer.sequence = 254
    payload = bytes(i % 256 for i in range(length))
    messages = [m for f in writer.encode(payload, ENCRYPTED) if (m := reader.feed(f))]
    assert len(messages) == 1 and messages[0].payload == payload


def test_descriptor_does_not_become_message_payload():
    reader = FrameReader()
    frames = FrameWriter(16).encode(b"x" * 80, HANDSHAKE)
    assert reader.feed(frames[0]) is None
    result = None
    for frame in frames[1:]:
        result = reader.feed(frame)
    assert result.payload == b"x" * 80


def test_sequence_gap_is_fatal():
    frames = FrameWriter(16).encode(b"x" * 80, HANDSHAKE)
    reader = FrameReader()
    reader.feed(frames[0])
    with pytest.raises(ProtocolError, match="gap"):
        reader.feed(frames[2])


@pytest.mark.parametrize("bad", [b"", b"\x80\x00\x01\x00", b"\x80\x01\x00\x00"])
def test_malformed_frames(bad):
    with pytest.raises(ProtocolError):
        FrameReader().feed(bad)


def test_incomplete_fragmented_message():
    reader = FrameReader()
    reader.feed(bytes.fromhex("8200040000500002"))
    with pytest.raises(ProtocolError, match="Incomplete"):
        reader.feed(bytes.fromhex("84000001"))
