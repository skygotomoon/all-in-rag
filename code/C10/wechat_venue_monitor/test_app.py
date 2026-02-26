from app import parse_payload


def test_parse_payload_ok():
    snap = parse_payload({"total_slots": 10, "occupied_slots": 4})
    assert snap.total == 10
    assert snap.occupied == 4


def test_parse_payload_invalid():
    try:
        parse_payload({"total_slots": 2, "occupied_slots": 5})
        assert False, "expected ValueError"
    except ValueError:
        assert True
