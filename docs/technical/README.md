# Technical reference

For framework developers, plugin authors, and operators who need to understand internals.

| File | Purpose |
| --- | --- |
| [`architecture.md`](./architecture.md) | Pipeline stages, queues, manager, what runs where. |
| [`data-model.md`](./data-model.md) | `Indicator`, `Observation`, canonicalization, dedup keys, schema versioning. |
| [`plugin-sdk.md`](./plugin-sdk.md) | The four ABCs, sync-bridge bases, entry-point registration. |
| [`observability.md`](./observability.md) | Metrics, traces, structured logs, queue-depth gauges. |
| [`security.md`](./security.md) | SSRF egress guard, TLP propagation, secrets, plugin sandboxing roadmap. |
| [`replay.md`](./replay.md) | Raw payload archive, durability fence, `cti replay` semantics. |
| [`design-decisions.md`](./design-decisions.md) | Trade-off log: why arq, why Postgres-only, why APScheduler, etc. |
