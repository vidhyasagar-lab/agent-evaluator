"""P2 exit criterion: the good run passes clean, and each deliberately broken
run trips exactly the check it was built to trip."""
import json
import os

from luckrate import check, hard
from luckrate.adapters.n8n import from_n8n

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

SPEC = {
    "tools": ["lookup_order", "check_policy", "escalate_to_human", "issue_refund"],
    "required": ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],
    "before": [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
}

TASK = "I want a refund for order 88213, it arrived broken."


def load(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return from_n8n(json.load(f))


def test_good_trajectory_is_extracted_in_order():
    steps = load("n8n_good")
    assert [s.tool for s in steps] == ["lookup_order", "check_policy", "escalate_to_human"]
    assert steps[0].args == {"order_id": "88213"}
    assert all(s.ok for s in steps)
    assert "200" in steps[0].result
    assert steps[0].t < steps[1].t


def test_call_id_is_stripped_from_args():
    # n8n carries the tool-calling layer's own id in inputOverride; if it
    # survived, every call would raise a false ungrounded warning.
    for name in ("n8n_good", "n8n_skips", "n8n_loops", "n8n_fabricates"):
        assert all("id" not in s.args for s in load(name))


def test_good_run_passes_clean():
    assert check(load("n8n_good"), SPEC, TASK) == []


def test_skips_calls_forbidden_tool_and_omits_the_check():
    v = check(load("n8n_skips"), SPEC, TASK)
    assert "called forbidden tool: issue_refund" in v
    assert "missing required tool: check_policy" in v


def test_loops_repeats_a_successful_call():
    steps = load("n8n_loops")
    assert [s.tool for s in steps].count("lookup_order") == 4
    v = check(steps, SPEC, TASK)
    assert len([x for x in v if "repeated call" in x]) == 3
    assert any("steps > max" in x for x in v)
    assert hard(v) == []  # a loop is waste, not a correctness failure


def test_fabricates_flags_the_invented_id_as_warn_only():
    steps = load("n8n_fabricates")
    task = "I want a refund, my item arrived broken."
    assert steps[0].args == {"order_id": "48327"}
    v = check(steps, SPEC, task)
    assert any("48327" in x for x in v if x.startswith("warn:"))
    assert hard(v) == []


def test_fabricates_is_the_luck_rate_case():
    # It escalated correctly, so output passes; the path is invented.
    task = "I want a refund, my item arrived broken."
    v = check(load("n8n_fabricates"), SPEC, task)
    output_ok = True  # "escalated ... for manager approval" - the right answer
    assert output_ok and v and hard(v) == []
