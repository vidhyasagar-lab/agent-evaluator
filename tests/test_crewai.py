import json
import pytest
from luckrate.adapters.crewai import from_crewai
from luckrate.schema import Step


def test_from_crewai_parses_steps_and_strips_plumbing():
    with open("tests/fixtures/crewai_sample.json") as f:
        data = json.load(f)

    steps = from_crewai(data)

    assert len(steps) == 2

    # Verify first step
    s1 = steps[0]
    assert isinstance(s1, Step)
    assert s1.tool == "lookup_order"
    assert s1.agent == "Senior Researcher"
    assert s1.ok is True
    assert "id" not in s1.args  # Internal call ID stripped
    assert s1.args["order_id"] == "ORD-12345"

    # Verify second step (failure state)
    s2 = steps[1]
    assert s2.tool == "send_email"
    assert s2.agent == "Customer Support Agent"
    assert s2.ok is False
    assert "SMTP connection timed out" in s2.result
