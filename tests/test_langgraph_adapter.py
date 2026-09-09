"""P4 exit criterion: the same spec scores an n8n agent and a LangGraph agent
identically. If Step needs to change to fit LangGraph, it changes here -- before
v0.1 freezes the contract for contributors."""
import json
import os

from luckrate import Step, check
from luckrate.adapters.langgraph import from_langgraph
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


def load(name, adapter):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        raw = json.load(f)
    return adapter(raw["messages"] if "messages" in raw else raw)


def test_extracts_calls_in_issue_order():
    steps = load("langgraph_good", from_langgraph)
    assert [s.tool for s in steps] == ["lookup_order", "check_policy", "escalate_to_human"]
    assert steps[0].args == {"order_id": "88213"}
    assert "200" in steps[0].result
    assert all(s.ok for s in steps)


def test_same_spec_scores_both_frameworks_identically():
    n8n = load("n8n_good", from_n8n)
    lang = load("langgraph_good", from_langgraph)
    assert [s.tool for s in n8n] == [s.tool for s in lang]
    assert check(n8n, SPEC, TASK) == check(lang, SPEC, TASK) == []


def test_reads_message_objects_as_well_as_dicts():
    class AI:
        tool_calls = [{"id": "c1", "name": "lookup_order", "args": {"order_id": "88213"}}]

    class ToolMsg:
        tool_call_id, content, status = "c1", "found, total 200", "success"

    steps = from_langgraph([AI(), ToolMsg()])
    assert steps == [Step("lookup_order", {"order_id": "88213"}, True, "found, total 200")]


def test_failed_tool_is_not_ok():
    class AI:
        tool_calls = [{"id": "c1", "name": "lookup_order", "args": {"order_id": "88213"}}]

    class ToolErr:
        tool_call_id, content, status = "c1", "connection refused", "error"

    assert from_langgraph([AI(), ToolErr()])[0].ok is False


def test_unanswered_tool_call_still_appears():
    class AI:
        tool_calls = [{"id": "c1", "name": "lookup_order", "args": {"order_id": "88213"}}]

    steps = from_langgraph([AI()])
    assert len(steps) == 1 and steps[0].result == ""
