# Agent Evaluator

Trajectory evaluation for AI agents, across frameworks. Grade the **path** the
agent took, not just the answer it returned.

---

## 0. Decisions

| Decision | Choice |
|---|---|
| Name | **`luckrate`** — free on PyPI, and it names the contribution |
| Audience | Open source, for **platform engineers** who run agent infra and own CI |
| Language | Python, `requires-python >= 3.9`, zero runtime dependencies |
| License | MIT |
| First adapter | n8n. LangGraph second, **before** v0.1 ships |
| n8n environment | Self-hosted Docker, pinned `2.38.1`, SQLite |
| Runs per case | `k = 5` |
| Token / cost fields | Excluded from the schema — see §4.1 |

Two of these are load-bearing and easy to drift from.

**The user is the platform engineer, not the person on the canvas.** The gap this
fills is that n8n has no path grading at all — but the buyer is whoever runs the
n8n instance and owns the pipeline, and they write Python. Do not market a Python
library to non-programmers on the strength of a gap that exists in their tool.
The gap is real; the user is one layer up.

**`Step` becomes a public contract at v0.1.** Contributors write adapters against
it, so a later field addition breaks all of them. Everything in §4.1 is settled
before release, not after.

## 1. The problem

Every agent eval today — including n8n's native Evaluations — scores the final
output. Right answer, pass.

But an agent can reach the right answer the wrong way:

- called a tool it should never have touched
- invented an order ID that happened to exist
- retried the same call five times before converging
- burned ten API calls where two would do
- recovered from a tool error by looping instead of escalating

All of that scores green today. All of it is an incident later.

## 2. The metric

> **Luck Rate** — of the runs that *looked* green, the share that got there on a
> bad path.
>
> `luck = |output_ok AND NOT path_ok| / |output_ok|`
>
> Undefined when no run passes on output. Report `—`, never `0`.

The denominator is the part that is easy to get wrong. Dividing by *all* runs lets
failing outputs dilute the rate, so a bad agent scores as luck-free. The question
being answered is "of the runs I would have shipped on, how many were fluke?" —
so only output-passing runs belong in the denominator.

Always print counts beside the percentage (`3 of 7 green runs were lucky`). A bare
rate invites reading 33% off three runs as though it meant something.

**Honest framing.** Luck Rate is not a new measurement. It is a cross-tab of two
signals that already exist — output correctness × path validity — and anyone
running an output evaluator beside `agentevals` could compute it in a line. The
contribution is that nobody reports it, so nobody looks at it. That is a defaults
and framing contribution. Claimed that way it holds up; claimed as a novel
measurement it falls to the first informed reader.

**It measures the spec as much as the agent.** An over-strict spec inflates Luck
Rate and reads like an agent problem. The known-good fixture from P1 is the spec's
own test: if the correct run does not pass clean, fix the spec before believing
any number the tool prints.

## 3. Prior art

Revised after actually researching the market. The first version of this table was
too flattering and produced an over-claim that shipped in the README.

| Tool | Covers | Gap |
|---|---|---|
| n8n Evaluations | dataset in, answer out, model comparison | no path grading at all |
| `agentevals` | trajectory match: strict, unordered, LLM-judge | code-first; reference is a literal golden path |
| **DeepEval** | tool correctness, argument correctness, plan adherence, step efficiency, task completion | argument checking needs an LLM judge; no visual-runtime reach |
| **MLflow** | Agent GPA: tool selection, plan quality, execution efficiency | heavyweight; tied to MLflow tracing |
| **Arize Phoenix** | OTel-native trajectory evals | requires instrumentation |
| **Langfuse** | tool calls as structured fields, **native n8n integration** | observability + judges, not constraint-based gating |
| LangSmith | traces, run and thread eval | SaaS |

Trajectory evaluation is **not** new, and neither is framework-agnosticism. What
survives scrutiny is narrower:

1. **Constraint specs**, not `expected_tools` lists or golden paths — `forbidden`
   plus partial ordering plus a budget is a different model.
2. **Deterministic argument provenance.** DeepEval's equivalent uses an LLM judge;
   this is substring tracing — free, instant, reproducible.
3. **No instrumentation for n8n.** Langfuse needs tracing wired into the workflow;
   this reads execution data the platform already stores.
4. **Luck Rate.** Nothing found reports right-answer-wrong-path.

Pitch those four. Never "nobody grades the path" — that has been wrong twice.

## 4. Design

The canonical `Step` schema is the product. Adapters churn, frameworks die, n8n's
internals shift. A stable intermediate representation is the durable asset.

```
n8n ────────► from_n8n() ───────┐
LangGraph ──► from_langgraph() ─┼──► list[Step] ──► check(steps, spec) ──► violations
CrewAI ─────► from_crewai() ────┤                          │
anything ───► from_*() ─────────┘                          ▼
                                          evaluate() ──► report() ──► Luck Rate
```

The scorer never learns which framework produced the steps. If a framework cannot
be expressed as `list[Step]`, the model is wrong — not the framework.

### 4.1 Data model

```python
@dataclass
class Step:
    tool:   str            # node / tool name
    args:   dict           # call arguments
    ok:     bool = True    # did the call succeed
    result: str = ""       # output text; feeds provenance checking
    t:      float = 0.0    # ms from run start
    agent:  str = "main"   # multi-agent hook, unused until CrewAI
```

A trajectory is `list[Step]`. That is the entire schema.

`t` and `agent` are speculative, and both are deliberate exceptions to YAGNI. The
schema freezes at v0.1, so a field added later breaks every contributed adapter —
and both of these cost nothing to fill:

- **`t`** — every source has timing (`startTime` in n8n, span starts elsewhere).
  Without it, latency and time-to-recovery can never be added non-breakingly.
- **`agent`** — one unused string, cheaper than a migration when CrewAI lands.
  If CrewAI never happens, delete it *before* v0.1.

**`tokens` is excluded.** n8n's `runData` does not reliably carry per-node token
counts, so no adapter could fill it uniformly. Cost-per-successful-trajectory is
therefore out of scope for v0.1 — do not promise it in the README.

### 4.2 Spec format

References are **constraints, not golden paths**. Plain Python dicts — no YAML, no
parser, no validation layer.

```python
spec = {
    "tools":     ["lookup_order", "check_policy", "escalate_to_human"],
    "required":  ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],          # over limit -> must escalate
    "before":    [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
    "ground":    True,
}
```

Partial ordering, not sequence equality. Tolerant of legitimate variation, strict
about what matters. Authoring drops from "transcribe a full path" to five lines.

`tools` can be **auto-derived** in graph runtimes — n8n's `ai_tool` connections and
LangGraph's `get_graph()` both give the legal vocabulary statically. Anything
outside it is a hallucinated tool call, caught with zero labeling.

### 4.3 Checks

| Check | Catches | Severity |
|---|---|---|
| unknown tool | tool outside the graph vocabulary | hard |
| missing required | wrong tool for the job | hard |
| forbidden called | acted when it should have escalated | hard |
| ordering violated | acted before checking | hard |
| max steps exceeded | inefficiency creep | soft |
| repeated call | wasted spend, loop symptom | soft |
| ungrounded arg | fabricated identifier | warn |

Four semantics that are decided here, in P0, rather than discovered in P2:

- **A repeat after a failure is not a repeat.** If the earlier identical call had
  `ok=False`, the retry is correct behaviour. Only flag a duplicate when the first
  one succeeded — otherwise every well-built agent fails this check.
- **`before` uses first occurrence.** `(a, b)` means the *first* `a` precedes the
  *first* `b`. With repeated calls, any other rule is arbitrary.
- **Hard fails on one occurrence; soft fails on a majority of `k`.** `forbidden`
  and `unknown tool` are correctness, not variance — one is enough. `max_steps`
  and `repeated call` vary run to run, so they fail only if most runs fail.
- **`warn:` never fails a build.** It is a review signal.

**`k = 5`.** Three runs can only produce 0%, 33%, 67% or 100%, and a rate off that
grid is not a rate. Five is the floor at which the number stops being theatre, and
it is still small enough to print counts beside.

**Evaluate at the temperature you ship.** Pin temperature 0 while debugging a spec
— unintended variance wastes hours — then run the real suite at production
settings. Evaluating a temperature-0 agent you deploy at 0.7 measures a system
nobody runs. If the agent genuinely is deterministic, set `k=1` and stop paying
for identical runs.

**Ungrounded argument detection** is the most novel signal. For each argument, try
to trace the value to the task input or any prior tool result; untraceable
identifier-shaped values get flagged.

Scope it to identifier-shaped args only — ids, emails, dates, numbers, enums —
and skip prose, where synthesis is the point and every summary would
false-positive. It stays warn-only regardless: enums the model legitimately knows
(`"high"`, `"pending"`) will trip it. That restriction is what makes it a signal
worth reading rather than noise.

### 4.4 Runner contract

`evaluate(cases, runner, k)` needs `runner(input) -> (steps, output)`. For
LangGraph that is one function call. For n8n it is four, and the Public API makes
two of them awkward:

1. **Trigger.** The v1 Public API has no execute-workflow endpoint. Give the
   workflow a Webhook trigger and POST to it.
2. **Correlate.** The webhook response carries no execution id. Add a *Respond to
   Webhook* node returning `{{ $execution.id }}` beside the agent output —
   without it you are guessing which execution you caused.
3. **Wait.** Executions are async. Poll `GET /api/v1/executions/:id` until
   `finished` is true, with a timeout and a cap on polls.
4. **Fetch and adapt.** Re-fetch with `?includeData=true`, then `from_n8n()`.

Auth is the `X-N8N-API-KEY` header on every Public API call.

**Final output** comes from the same payload: `resultData.lastNodeExecuted` names
the terminal node, and its `runData` entry holds the output. Take it from there,
not from the webhook response — Luck Rate compares output against trajectory, so
both must come from the same execution record or the metric is meaningless.

Two things that cost an afternoon if met by surprise:

- **Use the production webhook URL on an activated workflow.** The test URL
  (`/webhook-test/...`) only listens while the editor is open and you have clicked
  Execute, and it fires once. Only `/webhook/...` works unattended.
- **Run cases serially.** Concurrent POSTs interleave executions, and n8n in main
  mode does not isolate them the way you would hope. This is also why parallel
  k-runs sit in the skipped list — same decision, stated once.

## 5. Components

| Component | Signature | ~Lines |
|---|---|---|
| Schema | `@dataclass Step` | 10 |
| Scorer | `check(steps, spec, task_input) -> list[str]` | 40 |
| Provenance | `_ungrounded(steps, task_input) -> list[str]` | 15 |
| n8n adapter | `from_n8n(execution, tools=None) -> list[Step]` | 25 |
| LangGraph adapter | `from_langgraph(messages) -> list[Step]` | 15 |
| n8n runner | `n8n_runner(webhook_url, api_key) -> callable` | 30 |
| Runner | `evaluate(cases, runner, k=5) -> list[dict]` | 15 |
| Report | `report(rows) -> float` | 15 |
| Spec validation | `_validate(spec)` | 15 |
| Tests | 5 files, fixture-based | 300 |

Five modules, ~220 lines of logic. No service, no database, no dashboard, no
custom n8n node, no plugin system.

### Repo layout

Src-layout, so tests run against the *installed* package and packaging mistakes
surface in CI rather than after publishing.

```
src/luckrate/
    __init__.py              # public API: Step, check, hard
    schema.py                # Step - the frozen contract
    check.py                 # check(), _repeats(), _ungrounded(), hard()
    adapters/                # created in P2, one module per framework
        n8n.py
        langgraph.py
    runner.py                # P3: evaluate(), report(), n8n_runner()
tests/
    test_check.py
    fixtures/
        n8n_good.json        # correct run
        n8n_skips.json       # skips the policy check
        n8n_loops.json       # loops on a failing tool
        n8n_fabricates.json  # invents an order id
examples/
    n8n_workflow.json        # the sample agent workflow
    refund_suite.py          # example spec + cases
pyproject.toml               # hatchling, requires-python >=3.9, no runtime deps
README.md  CONTRIBUTING.md  LICENSE  .gitignore
.github/workflows/ci.yml     # pytest on 3.9 / 3.11 / 3.13
docker-compose.yml           # pinned n8n 2.38.1
```

`adapters/` and `runner.py` do not exist yet — P2 and P3 create them. Empty
scaffolding is not structure.

Pytest is the one concession to open source — `demo()` with asserts is lazier, but
contributors expect a standard runner. Zero **runtime** dependencies stays firm:
stdlib only, `urllib` rather than `requests` for the n8n calls.

**Tests and eval runs are different things.** `pytest` stays offline, free and
deterministic: fixtures only, no LLM, no n8n, no keys. Running real evals costs
money and needs a live agent, so it is a user-invoked command and never part of
`test.yml`. Say so in CONTRIBUTING, or someone will wire live evals into CI.

**Scrub every recorded fixture.** They are real execution payloads going into a
public repo — tool arguments, tool results, credential blocks. Write the scrubber
during P1 capture, not as cleanup after the first leak.

## 6. Adapters

| Framework | Source | Tool call | Result | Ordering |
|---|---|---|---|---|
| n8n | `GET /api/v1/executions/:id?includeData=true` | `runData[node][]` | node `data` / `error` | sort by `startTime` |
| LangGraph | message list | `AIMessage.tool_calls` | `ToolMessage.content` / `.status` | by call, keyed on `tool_call_id` |
| CrewAI | OTel spans or callbacks | tool span | span output | span start |

### The adapter contract

This is the whole extension API. It goes in CONTRIBUTING verbatim:

> An adapter is a function `from_<framework>(raw, **opts) -> list[Step]`.
> It imports nothing from this library except `Step`, performs no I/O, and ships
> with one recorded fixture of that framework's output.

No abstract base class, no registry, no entry points, no plugin discovery. A
contributor adds one function and one fixture. If that ever stops being enough, a
`{name: callable}` dict is the next rung — not a framework.

### n8n specifics

Confirmed against a real 2.38.1 execution during P1:

- Walk `data.resultData.runData`. Every node, including `ai_tool` sub-nodes,
  appears with one entry **per invocation**.
- Args are at `inputOverride.ai_tool[0][0].json`; results at
  `data.ai_tool[0][0].json.response`; success at `executionStatus == "success"`.
- **Order by `executionIndex`, not `startTime`.** It is a monotonic integer n8n
  assigns across the whole execution, so it has no millisecond-collision risk.
  Fall back to `startTime` only if the field is absent on older versions.
- **Strip the tool-call `id` from args.** The tool-calling layer injects
  `{"id": "call_9xwq7yq..."}` alongside the real arguments. It is
  identifier-shaped and appears in no prior text, so every single tool call
  would raise a false `ungrounded` warning if it survived into `Step.args`.
  Framework plumbing gets removed in the adapter; the scorer stays generic.
- `lastNodeExecuted` is the *terminal* node — with a Respond to Webhook present
  that is the responder, not the agent. Its output holds the response body, which
  is where the agent answer and `$execution.id` are, so it still works; just do
  not assume it names the agent node.
- **Do not build on `returnIntermediateSteps`.** It returns empty when streaming is
  enabled and is sometimes missing entirely even when tools demonstrably fired.
  Enrichment only, never the primary source.
- **Tool name is node name, and node names get renamed.** A rename silently breaks
  every spec referencing it. Always set `spec["tools"]` so a rename surfaces as
  `unknown tool` rather than a mysterious `missing required`.
- **Sub-workflow tools are opaque.** The *Call n8n Workflow Tool* runs in a
  separate execution, so its internal steps never reach the parent's `runData` —
  a whole sub-agent collapses to one `Step`. Document it. Following `executionId`
  into child executions is post-v0.1 work.
- **Truncate `result` at 8k, not 2k.** Provenance searches prior results, so an id
  past the cut reads as fabricated. A rash of `ungrounded` warnings on large tool
  outputs is a truncation symptom before it is an agent one.

### LangGraph specifics

- Append steps at **call** time, not result time, so ordering survives and
  unanswered tool calls still appear.
- `graph.get_state_history()` is an alternative source when checkpointing is on;
  the message list is simpler and sufficient.

## 7. Phases — done

| Phase | Delivered | Verified by |
|---|---|---|
| P0 | `Step`, `check()`, `_ungrounded()`, severity tiers | 16 tests, no framework imported |
| P1 | n8n 2.38.1 + agent workflow, 4 fixtures from real runs | scrubbed, 0 secret hits |
| P2 | `from_n8n()` | good passes clean; each broken fixture trips only its own check |
| P3 | `evaluate()`, `report()`, `failed()`, `n8n_runner()` | live end-to-end, exit 0 |
| P4 | `from_langgraph()` | same spec scores both frameworks identically |
| P5 | packaging, CI, README | wheel installs in a clean venv; CI green on 3.9/3.11/3.13 |

33 tests. Repo public at `vidhyasagar-lab/agent-evaluator`, commit `d911249`.
Package name `luckrate` (repo name and package name differ deliberately —
`agent-evaluator` was taken on PyPI in spirit if not in fact, and `luckrate`
names the contribution).

## 8. Remaining work

Moved to **[ROADMAP.md](ROADMAP.md)**, which is the single source of truth for
forward work. This file stays the design record: what was built, and why.

Tracking the same items in two places was already drifting.

## 9. The demo

Run the **same spec** against an n8n agent and a LangGraph agent. Score both on
identical criteria: path validity, redundancy, recovery, steps, Luck Rate.

Nobody can do that today, because every eval tool is welded to one framework. One
table comparing two frameworks on one task, from one harness, explains the project
without a paragraph of setup. CrewAI makes it three — but do not put a
three-framework table in the README until the third adapter exists.

## 10. Skipped, and the trigger to add it

| Skipped | Add when |
|---|---|
| OTel collector | a 4th framework appears — 3 hand-written adapters is cheaper |
| Tree / delegation schema | you need delegation-depth metrics, not per-agent attribution |
| Custom n8n node | you want suites authored on-canvas |
| YAML specs | a non-engineer authors cases |
| Bootstrap confidence intervals | pass-rate over `k` proves too noisy in practice |
| Database | you want trends; until then append JSONL |
| Dashboard | someone other than you reads the results |
| LLM-judge output check | substring / callable checks stop being enough |
| Token and cost tracking | an adapter-uniform token source exists |
| Sub-workflow descent | one-`Step` sub-agents actually block a user |
| Adapter ABC / registry / entry points | a plain `{name: callable}` dict stops being enough |
| One package per adapter | an adapter needs a heavy dep the core must not carry |
| Docs site | the README no longer fits on one screen |
| Async / parallel k-runs | serial runs become the bottleneck, not the LLM |

The open-source temptation is to build the plugin system before the second plugin
exists. Two adapters do not justify an architecture.

## 11. Risks

- **`runData` is not a stable contract.** Confine all parsing to `from_n8n()` so an
  n8n upgrade breaks exactly one function. The image is pinned for this reason.
- **`Step` churn after v0.1 breaks every contributed adapter.** This is why
  LangGraph lands before release — a second framework is the only honest test that
  the schema is generic. Do not publish on one adapter.
- **Contributed adapters rot.** You cannot test frameworks you do not run. Require
  a recorded fixture with every adapter PR so CI catches drift.
- **Provenance false-positives** on known enums. Warn-only; tighten to id-shaped
  keys if noisy.
- **Spec authoring still costs something.** Cheaper than golden paths, not free.
  Vocabulary infers from the graph; ordering constraints are human work.
- **`EXECUTIONS_DATA_PRUNE=false` grows without bound.** Set deliberately, because
  pruning deletes the data this project reads — but hundreds of full-data runs will
  bloat SQLite and slow the n8n UI. Prune manually once fixtures are captured.
- **The failure mode is starting with adapters.** Five half-working integrations
  and no scoring logic. P0 first, always.

## 12. References

- [n8n — Test and improve AI workflows](https://docs.n8n.io/build/integrate-ai/test-and-improve-ai-workflows)
- [n8n — Tools Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent)
- [n8n issue #21998 — intermediate steps empty when streaming](https://github.com/n8n-io/n8n/issues/21998)
- [n8n issue #15234 — intermediate steps not returned](https://github.com/n8n-io/n8n/issues/15234)
- [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)
- [LangSmith trajectory evals](https://docs.langchain.com/langsmith/trajectory-evals)
