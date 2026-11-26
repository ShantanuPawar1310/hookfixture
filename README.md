# HookFixture

Repeatable webhook test data for duplicate and out-of-order deliveries.

Webhook handlers can work for one event and still fail when a provider retries it,
or when a later event arrives first. HookFixture turns a small JSON event list into
a delivery scenario you can check into a test suite. The same input, options and
seed produce the same files.

**Status:** initial alpha, v0.1.0. This is a new independent project. No external
adoption or production reliability is claimed. Python 3.10+; no runtime dependencies.

## Install

From a checkout:

```sh
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
hookfixture --version
```

The source uses Python's standard library. Installation uses setuptools as the
build backend and may download it. There is no PyPI release at this stage.

## Make a scenario

The repository includes two synthetic invoice events:

```sh
hookfixture build examples/invoice-events.json --out fixtures-out --copies 3 --order shuffle --seed 42
hookfixture verify fixtures-out/manifest.json
```

The first command writes six numbered event files and a manifest. There are two
unique event IDs and four duplicate deliveries. The second command returns:

```json
{"deliveries": 6, "duplicates": 4, "unique_events": 2, "valid": true}
```

`--copies` is the **total** deliveries per event, including the original. Use
`--order reverse` for reverse source order, or `original` to preserve it. Changing
`--seed` changes shuffled delivery order without changing event IDs or timestamps.

The output directory must be new and its parent must exist. HookFixture refuses
to overwrite existing paths. Re-run with a different output directory.

## Input format

```json
[
  {"type": "invoice.paid", "data": {"invoice_id": "inv_example", "amount_minor": 1500}}
]
```

`type` and object-valued `data` are required. `id` and timezone-aware `created_at`
are optional. Missing IDs are derived deterministically from source content and
position. Missing timestamps start at `2000-01-01T00:00:00Z`, one second apart;
override this with `--start`. Explicit timestamps are normalized to UTC.

This is a provider-neutral envelope. It does not claim to reproduce Stripe,
Razorpay, GitHub or another provider's full request format or signature scheme.
Put provider-specific fields inside `data`, then adapt fixtures in your tests.
See [the format specification](docs/FORMAT.md).

## Use it in Python

```python
from hookfixture import create_scenario

scenario = create_scenario(
    [{"type": "invoice.paid", "data": {"amount_minor": 1500}}],
    copies=3, order="shuffle", seed=42,
)
seen = set()
processed = 0
for delivery in scenario.deliveries:
    event = delivery.event
    if event["id"] not in seen:
        seen.add(event["id"])
        processed += 1
assert processed == 1
```

[The runnable consumer example](examples/idempotent_consumer.py) demonstrates
duplicate suppression across a payment and refund. Its in-memory set is for the
example; production idempotency needs durable transactional storage.

## Verify fixtures in CI

`verify` checks file checksums, event envelopes, copy numbers, ID consistency and
summary counts. It rejects conflicting payloads for the same ID. Exit status is
`0` for success and `2` for invalid input or filesystem errors. Successful commands
print JSON on stdout; errors go to stderr.

Checksums detect accidental edits. They do not authenticate an untrusted manifest.
The tool makes no HTTP requests, starts no server and reads no service credentials.
Use synthetic data; fixture files are plain JSON.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/idempotent_consumer.py
```

Tests cover repeatable output, delivery identity, order, timestamps, invalid data,
manifest tampering and command-line round trips. GitHub Actions runs the suite and
the installed CLI on Python 3.10, 3.13 and 3.14. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the contribution workflow and [CHANGELOG.md](CHANGELOG.md) for releases.

## Feedback and roadmap

Useful feedback includes a reproducible handler-testing problem, the fixture
format your project needs, or a small failing test. Do not upload production
payloads or credentials. Planned work is driven by actual use cases: optional
provider adapters, selective retries, and timing schedules. These are not shipped
features.

Maintained by [Shantanu Pawar](https://github.com/ShantanuPawar1310). Licensed under
the [MIT License](LICENSE).
