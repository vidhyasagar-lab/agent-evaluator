# Contributing

Thanks for looking. This is a small library with a deliberately small surface —
most contributions are **adapters**, and adding one is a single function plus a
recorded fixture.

- [Setup](#setup)
- [Project layout](#project-layout)
- [The adapter contract](#the-adapter-contract)
- [Walkthrough: adding an adapter](#walkthrough-adding-an-adapter)
- [Recording and scrubbing a fixture](#recording-and-scrubbing-a-fixture)
- [Testing policy](#testing-policy)
- [Pull request checklist](#pull-request-checklist)
- [What gets rejected](#what-gets-rejected)
- [Schema stability](#schema-stability)

---

## Setup

```bash
git clone https://github.com/vidhyasagar-lab/agent-evaluator
cd agent-evaluator
pip install -e ".[dev]"
pytest
```

Python 3.9 or newer. Tests run offline in well under a second — no keys, no
network, no LLM.

---

## Project layout

```
src/luckrate/
    schema.py        Step - the frozen public contract
    check.py         check(), _validate(), _repeats(), _ungrounded(), hard()
    runner.py        evaluate(), report(), failed(), n8n_runner()
    adapters/
        n8n.py       from_n8n()
        langgraph.py from_langgraph()
tests/
    fixtures/        recorded payloads, scrubbed
examples/            live suites and a sample n8n workflow
scripts/             fixture capture helper
```

---

## The adapter contract

This is the entire extension API:

> An adapter is a function `from_<framework>(raw, **opts) -> list[Step]`.
> It imports nothing from this library except `Step`, performs no I/O, and ships
> with one recorded fixture of that framework's output.

**No base class, no registry, no entry points, no plugin discovery.** If a plain
`{name: callable}` dict ever stops being enough, that is the next rung — not a
framework.

**No I/O** means the adapter takes an already-fetched payload. Fetching is the
caller's problem. This is what keeps every adapter testable offline, and it is not
negotiable — a PR that puts an HTTP call inside an adapter will be asked to move it.

---

## Walkthrough: adding an adapter

Say you want `from_autogen`.

### 1. Record one real run

Run your agent, dump whatever its SDK gives you to JSON, and save it as
`tests/fixtures/autogen_good.json`. Use a trajectory that is *correct* — the good
path is what proves the adapter extracts faithfully. [Scrub it](#recording-and-scrubbing-a-fixture).

### 2. Write the function

```python
# src/luckrate/adapters/autogen.py
"""AutoGen adapter. Verified against autogen X.Y."""
from luckrate.schema import RESULT_CAP, Step


def from_autogen(messages):
    steps = []
    for m in messages:
        ...
        steps.append(Step(
            tool=name,
            args=args,
            ok=status != "error",
            result=str(output)[:RESULT_CAP],
            t=timestamp_ms - run_start_ms,
        ))
    return steps
```

Four things worth knowing before you write it:

**Append at call time, not result time.** Otherwise ordering depends on when
results arrive, and a tool call that never returned disappears entirely.

**Strip framework plumbing from `args`.** The n8n adapter deletes a tool-call `id`
that the tool-calling layer injects. It is identifier-shaped and grounded in
nothing, so leaving it in raises a false `ungrounded` warning on *every single
call*. Look for the equivalent in your framework.

**Pick one ordering key for the whole trajectory.** n8n has both `executionIndex`
and `startTime`; they live in different number spaces, so falling back per-entry
scrambles the order. Choose all-or-nothing.

**Read attributes and dicts both, if you can do it cheaply.** The LangGraph adapter
uses a three-line `_get()` so it accepts live message objects *and* JSON fixtures.
That is what lets its test run without importing `langchain`.

### 3. Test it against the fixture

```python
def test_extracts_calls_in_issue_order():
    steps = load("autogen_good", from_autogen)
    assert [s.tool for s in steps] == ["lookup_order", "check_policy", "escalate_to_human"]
    assert steps[0].args == {"order_id": "88213"}
    assert all(s.ok for s in steps)
```

**The test that matters most** is that your framework scores identically to an
existing one under the same spec:

```python
def test_same_spec_scores_both_frameworks_identically():
    assert check(load("n8n_good", from_n8n), SPEC, TASK) == \
           check(load("autogen_good", from_autogen), SPEC, TASK) == []
```

If that passes, `Step` held. If it does not, say so in the PR — that is a design
conversation worth having, not a failure.

### 4. Mention it in the README

One row in the adapters list. That is all.

---

## Recording and scrubbing a fixture

Fixtures are real execution payloads going into a public repository.

**Scrub before committing:**

- [ ] credentials, API keys, tokens, auth headers
- [ ] endpoint hostnames, resource names, deployment names
- [ ] real customer data — names, emails, addresses, order ids tied to real accounts
- [ ] internal URLs

**Replace rather than delete**, so the fixture still exercises your parsing. A
deleted field tests nothing; `"test-deployment"` tests the same code path the real
value did.

[`scripts/capture_n8n_fixture.py`](scripts/capture_n8n_fixture.py) is the n8n
version and a reasonable template — it fetches, scrubs, and writes in one step.

Sanity check before you push:

```bash
grep -riE "api[-_]?key|bearer|sk-|password|@gmail|@company" tests/fixtures/
```

---

## Testing policy

**`pytest` must stay offline, free and deterministic.** Fixtures only — no LLM
calls, no live agent, no API keys. CI runs it on every push across 3.9, 3.11 and
3.13.

**Running real evals is a different thing.** It costs money and needs a live agent,
so it lives in `examples/` as a user-invoked command and is never wired into CI.
Please do not add live-agent calls to the test suite.

---

## Pull request checklist

- [ ] `pytest` passes locally
- [ ] new logic has a test that fails without the fix
- [ ] fixture is recorded from a real run, and scrubbed
- [ ] no new runtime dependency
- [ ] no I/O inside an adapter
- [ ] deliberate shortcuts are marked with a comment naming the ceiling and the
      upgrade path
- [ ] README updated if you added an adapter

Small PRs get read quickly. A PR that adds one adapter, one fixture and one test is
the ideal shape.

---

## What gets rejected

Not to be unwelcoming — these are settled decisions, and it is kinder to say so
before you write the code:

| Proposal | Why not |
|---|---|
| Adapter base class, registry, or entry points | Two adapters do not justify an architecture. A `{name: callable}` dict is the next rung. |
| A runtime dependency | Zero is a feature. The adapters use `urllib`; nothing needs `requests`. |
| HTTP calls inside an adapter | Breaks offline testing, which is the point of the contract. |
| A dashboard, database, or web UI | Out of scope until someone other than the author reads the results. |
| Making `ungrounded` a hard failure | It false-positives on enums the model legitimately knows. Warn-only is deliberate. |
| Speculative config options | A config for a value nobody has changed is complexity with a docstring. |

If you think one of these is wrong, open an issue and argue it. Several of the
decisions above changed once already because reality disagreed with the plan.

---

## Schema stability

`Step` is a public contract. Adapters depend on it, so **fields are not added or
renamed without a major version bump**.

If your framework does not fit `Step` — multi-agent delegation is the likely case —
**open an issue before writing the adapter**. That is a design conversation, not a
pull request. The `agent` field exists precisely to absorb the first multi-agent
framework without a breaking change; if it is not enough, we should talk about the
shape before you build against it.

---

## Reporting bugs

Useful bug reports include the trajectory. A scrubbed fixture that reproduces the
problem turns a bug report into a test case, and it will get fixed considerably
faster.
