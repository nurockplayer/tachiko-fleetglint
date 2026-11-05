# Fleetglint

A local, read-only board for people who run many AI agents and models at once
(a lead session, its workers, detached jobs, reviews). It answers three
questions: what is running, why it is waiting, and who must act.

Fleetglint only observes. It never schedules, dispatches, merges or reviews.
Any workflow can feed it by writing records in an open, vendor-neutral NDJSON
format; read-only adapters cover existing tools.

> Status: pre-release. Nothing to install yet; v0.1 is being built (see [docs/architecture.md](docs/architecture.md)).

The record format is specified in [docs/spec.md](docs/spec.md), with a JSON
Schema in [schema/v1/](schema/v1/) and examples in [examples/v1/](examples/v1/).

## Planned for v0.1

- v1 record spec (`run`, `job`, `inbox_item`) with JSON Schema and a validator
- Durable NDJSON ingestion into a rebuildable local SQLite read model
- First adapter: tachiko-harness
- Local web UI on 127.0.0.1 (GET-only): Overview, Run detail, Needs attention
- Install with Homebrew or pipx; no Node at runtime

## License

MIT
