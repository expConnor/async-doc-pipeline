from scenarios import SCENARIOS


def test_registry_is_a_dict():
    assert isinstance(SCENARIOS, dict)


def test_unregistered_name_is_absent():
    assert SCENARIOS.get("nonexistent-scenario") is None
