from hcc100_ble.models import ZoneState


def test_inconsistent_masks_never_report_a_false_open_or_closed_state():
    zone = ZoneState(1, "test", 3, 1, 1, 20, 21)
    assert not zone.masks_consistent
    assert zone.outputs_open is None and zone.open_count is None


def test_unknown_masks_are_unavailable():
    zone = ZoneState(1, "test", 3, None, 3, 20, 21)
    assert zone.outputs_open is None
