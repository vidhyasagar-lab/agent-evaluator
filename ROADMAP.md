# Roadmap

What to build, in order, with enough detail to pick any item up cold.

[PLAN.md](PLAN.md) is the design record for what already exists and why. This file
is only forward-looking. Each item states what it touches, roughly how big it is,
and what "done" means — so nothing here needs the conversation that produced it.

**Ordering principle:** finish v0.1 (A), then the security wedge (B), because B is
the only differentiated space. C and D are catch-up work with the field and should
not jump the queue.

---

## A — Finish v0.1

Release blockers and hygiene. Detail lives in [PLAN.md](PLAN.md) §8.

### A1 — Record a real LangGraph fixture
**Build:** replace `tests/fixtures/langgraph_good.json`, currently hand-authored to
the LangChain message schema, with a real `graph.invoke(...)["messages"]` dump.
**Why:** v0.1 freezes `Step` as a public contract. Half the evidence that it is
framework-generic is synthetic. After release, a schema change breaks every
contributed adapter.
**Touches:** `tests/fixtures/`
**Size:** 15 minutes, needs a live LangGraph agent with tools named
`lookup_order`, `check_policy`, `escalate_to_human`, `issue_refund`.
**Done when:** `test_same_spec_scores_both_frameworks_identically` passes against a
recorded trajectory.
**Blocks:** A2.

### A2 — Publish v0.1 to PyPI
**Build:** bump `0.1.0.dev0` → `0.1.0`, rebuild, `twine upload`, tag `v0.1.0`.
**Size:** 20 minutes. Needs a PyPI token.
**Done when:** `pip install luckrate` works in a clean venv elsewhere.
**Depends on:** A1.

### A3 — Trim the GitHub PAT
**Build:** reduce to **Contents: Read and write** + **Metadata: Read-only**.
**Why:** it currently carries 36 repository permissions and can read every private
repo on the account, from a `.env` on disk.
**Size:** 2 minutes.

### A4 — Correct the over-claim in the README
**Build:** the "One spec, any framework" section says *"No eval tool does this today
because each is welded to one framework."* That is false — DeepEval, MLflow and
Arize Phoenix are all framework-agnostic. Narrow it to the defensible version: the
same spec scores an n8n agent and a code-framework agent **without instrumenting
either one**.
**Why:** a reader who finds DeepEval and sees this line concludes we did not look.
**Touches:** `README.md`
**Size:** 10 minutes.

---

## B — The security wedge

**The differentiated work.** `_ungrounded()` already performs data-flow analysis —
it asks where an argument value came from, and currently only reports "nowhere."
The same pass can report *which source*, and that distinction is most of agent
security.

Eval tools score quality. None of them enforce policy. Constraint specs are good at
exactly that: deterministic rules, not judgment.

### B0 — Verify the prior art before building any of B
**Build:** research Invariant Labs (trace analysis with a policy language), NVIDIA
NeMo Guardrails, Lakera, LlamaFirewall, and anything newer. Establish what overlaps
B2–B4 and what does not.
**Why:** the novelty question in this project has been wrong twice — once on
trajectory evaluation generally, once on n8n coverage. Both times the claim was
made before checking. Do not repeat it a third time.
**Expected finding:** runtime guardrails are an occupied space. The likely gap is
the *insertion point* — policy checks running **in CI against recorded
trajectories** rather than as a runtime firewall. Guardrails block at execution;
this fails a build before deploy. Different buyer, different failure mode.
**Size:** 20 minutes.
**Blocks:** B1–B4. Do not skip.

### B1 — Provenance tagging
**Build:** extend the `_ungrounded` pass so each argument value is attributed to a
source: `user` (the task input), `tool:<name>` (an earlier tool result), or
`invented` (untraceable). Return the map rather than only the warnings.
**Why:** the foundation for B2, B3 and B4. On its own it also upgrades the existing
warning from "this is invented" to "this came from the web page you fetched."
**Touches:** `src/luckrate/check.py`
**Size:** ~30 lines. **No schema change** — provenance is computed, not stored, so
this is additive and does not touch the frozen `Step` contract.
**Done when:** a test asserts an argument sourced from a tool result is labelled
`tool:<name>`, not `user`, and not `invented`.

### B2 — `grounded_in`: indirect prompt injection
**Build:** a spec key asserting where an argument must originate.

```python
"grounded_in": {
    "issue_refund.amount":   "user",
    "issue_refund.order_id": "user",
}
```

If `issue_refund.amount` traces to `fetch_webpage`'s output instead of the user's
message, that is the canonical indirect-injection signature: content the agent
*read* caused a privileged action.
**Why:** detected structurally, with no LLM judge and no model of what injection
"looks like." Deterministic, free, reproducible.
**Touches:** `check.py`, README, CONTRIBUTING
**Size:** ~20 lines on top of B1.
**Severity:** hard. This is correctness, not variance.
**Done when:** a fixture where a tool result supplies a privileged argument fails,
and the same trajectory with a user-supplied argument passes.

### B3 — Taint rules across a trust boundary
**Build:** classify tools, then enforce one rule.

```python
"untrusted":  ["fetch_webpage", "read_email", "read_file"],
"privileged": ["issue_refund", "send_email", "delete_record"],
# no privileged call may consume untrusted-tainted data
```

**Why:** the lethal-trifecta pattern — private data, untrusted content, an
exfiltration path — expressed as a constraint rather than a vibe.
**Touches:** `check.py`
**Size:** ~25 lines, reusing B1's taint map.
**Done when:** a trajectory where `fetch_webpage` output reaches `issue_refund`
arguments fails, and an intervening human-approval step clears it.

### B4 — Exfiltration checks
**Build:** B1 inverted. Flag when an argument to an outbound tool contains a value
that originated from a private-data tool — `send_email.body` carrying something
from `read_customer_record`.
**Touches:** `check.py`
**Size:** ~15 lines once B1 exists.
**Done when:** a fixture moving private data into an outbound argument fails.

### B5 — Secret leakage scan
**Build:** scan `Step.args` and `Step.result` for credential patterns — API keys,
bearer tokens, private key headers.
**Why:** cheap and useful, but commodity. Lowest priority in B; do it only if it
falls out of the other work.
**Size:** ~15 lines.
**Severity:** warn.

---

## C — Reach

### C1 — OpenTelemetry ingestion
**Build:** `from_otel(spans)` normalizing OTel GenAI / OpenInference spans into
`list[Step]`.
**Why:** one path reaches CrewAI, AutoGen, LlamaIndex, the OpenAI Agents SDK and
whatever ships next, instead of one adapter each. Phoenix is built on it.
**Caveat:** OTel GenAI semconv and OpenInference use different attribute names for
the same concepts. Normalizing across both is the actual work — and the moat.
**Touches:** `src/luckrate/adapters/otel.py`
**Size:** 1 day.
**Trigger:** [PLAN.md](PLAN.md) §10 says a 4th framework. Security-conscious users
will bring more than that, so this likely lands earlier than planned.

### C2 — CrewAI adapter
**Build:** `from_crewai()`. First multi-agent framework; the `agent` field on `Step`
either earns its keep here or should be deleted before v1.0.
**Status:** filed as [issue #1](https://github.com/vidhyasagar-lab/agent-evaluator/issues/1),
`help wanted`. One PR arrived and was closed by an unrelated force-push; the branch
still exists on the contributor's fork.
**Why leave it to a contributor:** it is the only real test of whether the adapter
contract works for someone who did not write it.

### C3 — Further adapters
AutoGen, OpenAI Agents SDK, LlamaIndex. Only build one if C1 does not already cover
it, or if someone asks.

---

## D — Catch-up with the field

Every item here exists in DeepEval, MLflow, Phoenix or Langfuse. None of it is
differentiating. Build only what a user actually asks for.

### D1 — Cost and token tracking
**Build:** token counts on `Step`, cost per successful trajectory in `report()`.
**Blocked by:** n8n's `runData` does not reliably carry per-node token counts, so no
adapter can fill it uniformly — which is why it was excluded from the schema. C1
may solve this: OTel GenAI spans carry token usage.
**Second reason to want it:** an agent looping on a poisoned instruction is also a
cost anomaly. One signal, two audiences.
**Note:** adding a field to `Step` post-v0.1 is a breaking change. If this is ever
wanted, it must land before v0.1 or wait for v1.0.

### D2 — Latency metrics
**Build:** report duration and time-to-recovery from `Step.t`.
**Note:** `t` is already in the schema and nothing reads it. n8n fills it;
LangGraph cannot (LangChain messages carry no timestamps), so any metric must
degrade gracefully.
**Size:** ~20 lines.

### D3 — Run history and experiment comparison
**Build:** append each run to JSONL, and a command to diff two runs — did v2 regress
against v1?
**Why:** currently there is no way to see whether a change made things worse, only
whether the current run passes.
**Size:** ~40 lines for JSONL plus a diff command. Resist a database until someone
wants queries.

### D4 — Tool vocabulary drift
**Build:** record the agent's tool vocabulary per run; flag when it changes.
**Why:** someone attaching a `delete_record` tool to a production n8n workflow is a
change worth failing on, and the vocabulary is already derivable from the graph.
Sits between C and B — arguably security.
**Size:** ~25 lines.

### D5 — Not building
LLM-judge output scoring. It is where the field is strongest and it forfeits the
determinism that makes this worth using. Users who want it can pass a judge as
their `expect` callable.

Everything else deliberately skipped, with triggers, is in [PLAN.md](PLAN.md) §10:
a custom n8n node, a dashboard, a database, parallel runs, an adapter registry.

---

## Sequencing

```
A1 ─► A2                     release
A3, A4                       independent, do anytime
B0 ─► B1 ─► B2 ─► B3 ─► B4   the wedge; B0 gates all of it
              └─► B5         optional
C1                           independent; unblocks D1
C2                           community
D1 ─── needs C1
D2, D3, D4                   independent
```

**If only one thing gets built: B1 + B2.** It is a day's work, it reuses machinery
that already exists, it needs no schema change, and it is the only item on this page
that the established tools do not already do better.

---

## Decisions that would change this document

- **B0 finds a tool already doing CI-time trajectory policy checks.** Then B is not
  differentiated either, and the honest move is to narrow to "deterministic,
  dependency-free path gating with a first-class n8n path" and stop expanding.
- **Nobody takes C2.** Then the adapter contract has not been validated externally,
  and `agent` should be deleted from `Step` before v1.0.
- **Someone asks for cost tracking.** D1 jumps the queue, because it needs a schema
  field and schema changes get harder every release.
