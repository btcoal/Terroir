# Terroir

Point-in-time U.S. fundamentals from SEC filings. Release 1 scope, backlog,
and ticket specifications live in
[us_fundamentals/execution_tickets.md](us_fundamentals/execution_tickets.md).

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and, for migration tests,
a reachable PostgreSQL (peer auth or `TERROIR_PG_TEST_DSN`).

```bash
cd us_fundamentals
make sync        # install locked dependencies into .venv
make check       # lint + typecheck + tests + minimal pipeline
```

Individual commands: `make lint`, `make typecheck`, `make test`,
`make pipeline`, `make fmt`.

## Configuration

Typed profiles (`development`, `test`, `backfill`, `production`) load from
`TERROIR_*` environment variables — see
[us_fundamentals/src/us_fundamentals/config.py](us_fundamentals/src/us_fundamentals/config.py).
Development runs with safe defaults; `backfill` and `production` refuse to
start without an explicit `TERROIR_SEC_USER_AGENT` (with contact email) and
`TERROIR_PG_DSN`. No secrets are committed.
