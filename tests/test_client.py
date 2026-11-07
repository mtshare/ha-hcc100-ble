import asyncio

import pytest
from cryptography.hazmat.primitives import hashes
from hcc100_ble import AuthenticationError, Hcc100Client


async def test_independent_handshake_small_mtu_and_state(peer):
    client = Hcc100Client(peer)
    state = await client.read_state()
    assert client.ready
    assert state.device.model == "HCC100"
    assert (
        state.device.certificate_fingerprint == peer.certificate.fingerprint(hashes.SHA256()).hex()
    )
    assert list(state.zones) == [1]
    zone = state.zones[1]
    assert zone.temperature == 20.5 and zone.setpoint == 21
    assert zone.open_mask == 1 and zone.closed_mask == 2
    assert zone.outputs_open and zone.open_count == 1 and zone.masks_consistent
    assert {c["Cmd"] for c in peer.commands} <= {"GetDeviceInfo", "GetList", "GetName"}
    assert all(c["Cmd"] != "Set" for c in peer.commands)
    await client.close()
    assert not peer.is_connected


async def test_changed_certificate_rejected_before_client_key(peer):
    client = Hcc100Client(peer, expected_fingerprint="00" * 32)
    with pytest.raises(AuthenticationError, match="changed"):
        await client.open()
    assert not peer.is_connected and not peer.client_points


async def test_fresh_ecdh_key_for_each_connection(peer):
    client = Hcc100Client(peer)
    info = await client.open()
    await client.close()
    client = Hcc100Client(peer, expected_fingerprint=info.certificate_fingerprint)
    await client.open()
    assert len(peer.client_points) == 2 and peer.client_points[0] != peer.client_points[1]
    await client.close()


async def test_timeout_discards_uncertain_cipher_state(peer):
    client = Hcc100Client(peer, timeout=0.02)
    await client.open()
    peer.drop_response = True
    with pytest.raises(TimeoutError):
        await client.get_parameters([224], 1)
    assert not client.ready and not peer.is_connected
    peer.drop_response = False
    await client.open()
    assert client.ready
    await client.close()


async def test_serializes_parallel_reads(peer):
    client = Hcc100Client(peer)
    await client.open()
    results = await asyncio.gather(*(client.get_parameters([224], i) for i in (1, 2, 3)))
    assert results == [{224: 3}, {224: 0}, {224: 0}]
    await client.close()


async def test_write_commands_are_not_exposed(peer):
    client = Hcc100Client(peer)
    await client.open()
    count = len(peer.commands)
    with pytest.raises(ValueError, match="only supports"):
        await client._request({"Cmd": "Set", "ID": 231, "Value": 35})
    assert len(peer.commands) == count
    await client.close()


async def test_connector_retry_disconnect_does_not_poison_new_session(peer):
    connect = peer.connect

    async def retrying_connect():
        peer._disconnected()
        await asyncio.sleep(0)
        await connect()

    peer.connect = retrying_connect
    client = Hcc100Client(peer)
    await client.open()
    assert client.ready
    # Once connected, a real disconnect must still invalidate the session.
    peer._disconnected()
    assert not client.ready
    await client.close()
