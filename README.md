# luckrate

Trajectory evaluation for AI agents. Grade the **path** the agent took, not just
the answer it returned.

> **Status: v0.1 release candidate, not yet on PyPI.** Scorer, n8n and LangGraph
> adapters, runner and CI gate are done and tested against recorded real runs.
> See [PLAN.md](PLAN.md).

## Who this is for

Platform engineers who run agent infrastructure and own the pipeline — you deploy
agents in n8n or LangGraph, and you want a path regression to fail a build before
it reaches production.

The gap being filled is that **n8n has no path grading at all**, while code-first
frameworks have had it for a while. But the user is the person who owns CI, not
the person on the canvas: this is a Python library configured with Python dicts,
and it is aimed one layer up from the visual editor.

## Why

Every agent eval scores the final output. Right answer, pass.

But an agent can reach the right answer the wrong way — calling a tool it should
never have touched, inventing an order id that happened to exist, retrying five
times, or looping on a failing tool instead of escalating. All of that scores
green today, and all of it is an incident later.

## The metric

**Luck Rate** — of the runs that *looked* green, the share that got there on a
bad path.

```
luck = |output_ok AND NOT path_ok| / |output_ok|
```

The denominator is only the runs that passed on output, because the question is
"of the runs I would have shipped on, how many were fluke?" Dividing by all runs
lets failing outputs dilute the rate and makes a bad agent look luck-free.

It is not a new measurement — it is a cross-tab of output correctness and path
validity, both of which already exist. What is missing is that nobody reports it,
so nobody looks at it.

## Usage

```python
from luckrate import Step, check, hard

steps = [
    Step("lookup_order", {"order_id": "88213"}, result="broken, total 200"),
    Step("check_policy", {"amount": 200}, result="over limit, escalate"),
    Step("issue_refund", {"order_id": "88213"}),
]

spec = {
    # issue_refund is attached to the agent -- that is why it can be called --
    # but forbidden for this case, which is over the refund limit.
    "tools":     ["lookup_order", "check_policy", "escalate_to_human", "issue_refund"],
    "required":  ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],
    "before":    [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
}

check(steps, spec, task_input="refund for order 88213, it arrived broken")
# ['called forbidden tool: issue_refund']
```

References are **constraints, not golden paths**. You describe what must, must not
and may happen — not the exact sequence — so specs stay cheap to write and
tolerant of agents that vary legitimately.

## Checks

| Check | Catches | Severity |
|---|---|---|
| `tools` | tool outside the agent's declared vocabulary | hard |
| `required` | wrong tool for the job | hard |
| `forbidden` | acted when it should have escalated | hard |
| `before` | acted before checking | hard |
| `max_steps` | inefficiency creep, loops | soft |
| `no_repeat` | work already done successfully, redone | soft |
| `ground` | fabricated identifiers | warn |

Severity is encoded as a string prefix: bare is **hard** (fails a build on one
occurrence), `soft:` fails only if most runs in a batch fail, `warn:` never fails
a build. `hard(violations)` filters to the first group.

Two semantics worth knowing:

- **A retry after a failure is not a repeat.** Only a call that already succeeded
  makes a later identical call a repeat, so well-built agents do not fail this.
- **Grounding traces through tool results.** An argument is grounded if it appears
  in the task input *or* any earlier tool output — so ids discovered mid-run are
  legitimate, and only genuinely invented ones are flagged.

## One spec, any framework

Adapters normalize each framework into the same `list[Step]`, so the scorer never
learns which one produced a trajectory:

```python
from luckrate.adapters.n8n import from_n8n            # execution API payload
from luckrate.adapters.langgraph import from_langgraph # message list

assert check(from_n8n(execution), spec, task) == check(from_langgraph(msgs), spec, task)
```

That assertion is a real test, not an aspiration — the same refund spec scores an
n8n agent and a LangGraph agent identically. No eval tool does this today because
each is welded to one framework.

Adding a framework is one function and one recorded fixture. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Running a suite

```python
from luckrate.runner import evaluate, report, failed, n8n_runner

rows = evaluate(cases, n8n_runner(webhook_url, api_key), k=5)
report(rows)
sys.exit(1 if failed(rows) else 0)
```

```
pass   refund_over_limit      run=0 steps=3
LUCKY  refund_over_limit      run=1 steps=3
       - warn: ungrounded arg lookup_order.order_id='48327'

output passed 2/2
luck rate 50%  (1 of 2 green runs were lucky)
```

`k` defaults to 5 because three runs can only produce 0%, 33%, 67% or 100%, and a
rate off that grid is not a rate.

**The gate and the metric use different rules, deliberately.** `failed()` trips on
one hard violation, or on a soft violation in most runs of a case. Luck Rate counts
*any* violation including warnings — a fabricated id never fails a build, but it is
exactly the bad path the metric exists to surface.

## Install

```bash
pip install luckrate          # not yet published
pip install -e ".[dev]"       # from a clone
pytest
```

Zero runtime dependencies, Python 3.9+.

## Contributing

Adapters are the contribution surface — see [CONTRIBUTING.md](CONTRIBUTING.md).
Adding one is a single function plus one recorded fixture.

## License

MIT
