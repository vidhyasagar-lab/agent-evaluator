# Contributing

## The adapter contract

Adapters are the whole extension API. There is no base class, no registry, no
entry points, no plugin discovery.

> An adapter is a function `from_<framework>(raw, **opts) -> list[Step]`.
> It imports nothing from this library except `Step`, performs no I/O, and ships
> with one recorded fixture of that framework's output.

Adapters live in `src/luckrate/adapters/<framework>.py`. A pull request adding one
is three things:

1. the function
2. a recorded, scrubbed fixture in `tests/fixtures/`
3. a test asserting the `list[Step]` it produces from that fixture

No I/O in the adapter means it takes an already-fetched payload. Fetching is the
caller's problem, which is what keeps adapters testable offline.

## Tests must run offline and free

`pytest` never calls an LLM, never reaches a running agent, and needs no API keys.
It runs against recorded fixtures only, and CI runs it on every push.

**Running actual evals is a different thing.** It costs money and needs a live
agent, so it is a user-invoked command and is never wired into CI. Please do not
add live-agent calls to the test suite.

## Scrub every fixture

Fixtures are real execution payloads going into a public repository. They contain
tool arguments, tool results, and — for n8n — credential blocks. Scrub them before
committing:

- credentials, API keys, tokens, auth headers
- real customer data: names, emails, addresses, order ids tied to real accounts
- internal URLs and hostnames

Replace with plausible fakes rather than deleting the field, so the fixture still
exercises the adapter's parsing.

## Schema stability

`Step` is a public contract. Adapters depend on it, so fields are not added or
renamed without a major version bump. If your framework does not fit `Step`,
open an issue before writing the adapter — that is a design conversation, not a
pull request.
