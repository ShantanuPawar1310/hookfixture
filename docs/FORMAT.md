# Fixture format v1

## Logical events

The source is a non-empty JSON array. Each event has:

| Field | Requirement |
| --- | --- |
| `type` | Required string, 1–512 characters, not whitespace-only |
| `data` | Required JSON object; nested JSON values are allowed |
| `id` | Optional string with the same bounds as `type`; must be unique in the source |
| `created_at` | Optional ISO 8601 timestamp with an explicit timezone |

Unknown envelope fields, repeated JSON keys, NaN and Infinity are rejected. Move
provider fields inside `data`. Source files and individual fixtures are limited to
8 MiB. A scenario has at most 10,000 deliveries and at most 100 copies per event.

Generated IDs use UUID5 over a versioned namespace, source position and SHA-256 of
the consistently serialized source event. Keep explicit IDs if identity must
survive editing or reordering the source. These IDs are test identifiers, not
cryptographic secrets. The shuffle seed does not affect identity.

Generated times are one second apart from `--start`, which defaults to
`2000-01-01T00:00:00Z`. Explicit times are preserved as instants and normalized to
UTC. Delivery order never rewrites event time. No real clock is consulted.

## Delivery records

Files are numbered `000001.json`, `000002.json`, and so on, with one normalized
event per file. Copies of a logical event have identical content and ID. Their
copy numbers, starting at 1 without gaps, are stored in the manifest.

The manifest is named `manifest.json` and contains:

- `format_version`: integer `1`.
- `seed`: the integer shuffle seed.
- `order`: `original`, `reverse`, or `shuffle`.
- `summary`: integer `deliveries`, `unique_events`, and `duplicates` counts.
- `deliveries`: ordered records with `file`, `event_id`, `copy`, and `sha256`.

The manifest's record order is delivery order. `sha256` covers the exact file
bytes. Verification checks consistency, not whether record order was generated
by a particular seed. A user can deliberately construct another valid order.

JSON output uses UTF-8, sorted object keys, two-space indentation and a final
newline. Reproducible output is tested for the supported Python versions in CI;
cross-version shuffle sequences are not a compatibility guarantee. Persist
generated scenarios or use a fixed Python version when exact ordering matters.

## Public Python API

- `load_events(path)` reads a source array.
- `create_scenario(events, copies=1, order="original", seed=0, start=...)` returns
  a `Scenario` with a tuple of `Delivery` objects (`event` and `copy`).
- `write_scenario(scenario, destination)` writes a new directory and returns its
  manifest `Path`. Parent directories must already exist.
- `verify_scenario(manifest_path)` returns `Summary(deliveries, unique_events,
  duplicates)` or raises a validation/filesystem error.

The scenario detaches source data, but event dictionaries remain mutable Python
objects. Treat them as read-only; copies of one event share the same dictionary.
Writing revalidates the scenario. No delivery timing or network replay is provided.
