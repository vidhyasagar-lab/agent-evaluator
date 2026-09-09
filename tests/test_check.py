from luckrate import Step, check, hard

TASK = "refund for order 88213, it arrived broken"

SPEC = {
    # issue_refund is attached to the agent -- that is why it can be called at
    # all -- but forbidden for this case, which is over the refund limit.
    "tools": ["lookup_order", "check_policy", "escalate_to_human", "issue_refund"],
    "required": ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],
    "before": [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
}


def good():
    return [
        Step("lookup_order", {"order_id": "88213"}, result="broken, total 200"),
        Step("check_policy", {"amount": 200}, result="over limit, escalate"),
        Step("escalate_to_human", {"reason": "over refund limit"}),
    ]


def test_clean_run_has_no_violations():
    assert check(good(), SPEC, TASK) == []


def test_unknown_tool():
    steps = good() + [Step("send_sms", {})]
    assert any(x.startswith("unknown tool") for x in check(steps, SPEC, TASK))


def test_unknown_tool_silent_without_vocabulary():
    spec = {k: v for k, v in SPEC.items() if k != "tools"}
    steps = good() + [Step("send_sms", {})]
    assert not any("unknown tool" in x for x in check(steps, spec, TASK))


def test_missing_required():
    steps = [s for s in good() if s.tool != "check_policy"]
    assert any("missing required tool: check_policy" in x for x in check(steps, SPEC, TASK))


def test_forbidden():
    steps = good() + [Step("issue_refund", {"order_id": "88213"})]
    assert any("forbidden" in x for x in check(steps, SPEC, TASK))


def test_ordering_violated():
    steps = good()
    steps[0], steps[1] = steps[1], steps[0]
    assert any("must come before" in x for x in check(steps, SPEC, TASK))


def test_ordering_dependency_absent():
    steps = [Step("check_policy", {"amount": 200})]
    v = check(steps, SPEC, TASK)
    assert any("check_policy called without lookup_order" in x for x in v)


def test_max_steps_is_soft():
    v = [x for x in check(good() * 2, SPEC, TASK) if "steps > max" in x]
    assert v and all(x.startswith("soft:") for x in v)


def test_repeat_is_soft():
    steps = good() + [Step("lookup_order", {"order_id": "88213"})]
    v = [x for x in check(steps, SPEC, TASK) if "repeated call" in x]
    assert v and all(x.startswith("soft:") for x in v)


def test_retry_after_failure_is_not_a_repeat():
    steps = [
        Step("lookup_order", {"order_id": "88213"}, ok=False, result="timeout"),
        Step("lookup_order", {"order_id": "88213"}, result="broken, total 200"),
        Step("check_policy", {"amount": 200}),
    ]
    assert not any("repeated call" in x for x in check(steps, SPEC, TASK))


def test_repeat_after_a_success_is_flagged():
    steps = [
        Step("lookup_order", {"order_id": "88213"}, ok=False, result="timeout"),
        Step("lookup_order", {"order_id": "88213"}, result="ok"),
        Step("lookup_order", {"order_id": "88213"}, result="ok"),
        Step("check_policy", {"amount": 200}),
    ]
    assert any("repeated call" in x for x in check(steps, SPEC, TASK))


def test_ungrounded_arg_is_warn_not_hard():
    steps = [Step("lookup_order", {"order_id": "99999"})]
    v = [x for x in check(steps, {}, TASK) if "ungrounded" in x]
    assert v and all(x.startswith("warn:") for x in v)
    assert hard(v) == []


def test_grounding_traces_through_prior_tool_results():
    # 200 appears only in step 1's result, never in the task text
    assert not any("ungrounded" in x for x in check(good(), {}, TASK))


def test_grounding_ignores_literals_and_prose():
    steps = [Step("escalate_to_human", {
        "urgent": True,
        "reason": "customer reports the item arrived in several pieces",
    })]
    assert not any("ungrounded" in x for x in check(steps, {}, TASK))


def test_empty_trajectory_reports_only_missing_tools():
    v = check([], SPEC, TASK)
    assert len(v) == 2 and all("missing required" in x for x in v)


def test_hard_filters_soft_and_warn():
    steps = good() + [Step("issue_refund", {"order_id": "99999"})]
    v = check(steps, SPEC, TASK)
    assert hard(v) == ["called forbidden tool: issue_refund"]
    assert any(x.startswith("warn:") for x in v)
