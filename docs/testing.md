# Testing

Testing is part of implementation, not a final phase (brief §55).

## Layers

1. **Unit** (`tests/unit/`, pytest): pure logic — config, logging redaction,
   storage layout, migrations, and later token validation, state machines,
   chunk ordering/dedupe/checksums, provider normalization.
2. **Integration** (`tests/integration/`, from Milestone 1): API flows against
   a real app instance with a temp SQLite DB and mocked providers.
3. **Browser** (`tests/browser/`, Playwright, from Milestone 2): organizer and
   recorder UIs, including offline simulation via network emulation.
4. **Manual gates**: real-phone recording tests over HTTPS (Milestones 2–3,
   brief §66) and the physical multi-phone room test before release (§57).

## Running

```bash
make test     # pytest via the repo .venv
make lint     # ruff
```

Provider tests that hit real APIs are opt-in only, gated on
`MISTRAL_API_KEY` / `DEEPGRAM_API_KEY` environment variables (Milestone 4+).
CI must never depend on paid APIs.

## Conventions

- `settings_env` fixture (tests/conftest.py) points `APP_PERSISTENT_STORAGE`
  at a pytest tmp dir and clears the settings cache.
- App instances for tests are built with `create_app(with_auth=False)` to skip
  AppAPI signature validation; auth logic itself gets dedicated tests.
- Every reliability feature (retry, dedupe, recovery) lands together with a
  test that exercises its failure mode.
