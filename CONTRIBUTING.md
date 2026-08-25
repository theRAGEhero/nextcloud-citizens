# Contributing

Thanks for considering a contribution. This app records people's voices, so
correctness and privacy come before features.

## Priorities

When two goals conflict, resolve them in this order:

1. **Preserve recordings** — never risk captured audio.
2. **Privacy and security** — no verbatim speech or API key where it does not belong.
3. **Failure recovery** — a crash, a dead network or a reload must be survivable.
4. **Auditability** — every AI claim links to the evidence behind it.
5. **Usability**, then everything else.

## Development

See [docs/development-environment.md](docs/development-environment.md). In short:

```sh
make up          # run the app container with the source bind-mounted
make register    # register it with AppAPI
make test        # Python suite inside the image
make lint        # ruff
```

Frontend changes need `npm run build` in `frontend/`; the bundles in `js/`,
`css/` and `recorder_static/` are committed because the runtime image ships
them, and CI fails if they are stale.

## Pull requests

* Add or update tests — integration tests for API behaviour, Playwright specs in
  `tests/browser/` for anything the phone does offline.
* Keep comments about *why*, not *what*.
* Run `make lint && make test` before pushing.
* Database changes need an Alembic migration in
  `citizens/db/migrations/versions/`; migrations run automatically at startup.
* Never commit secrets, database files, or recordings. `.gitignore` covers the
  usual suspects — check `git status` before committing anyway.

## Releases

`make version VERSION=x.y.z` sets the version everywhere it is declared (a test
enforces they agree), then tag `vx.y.z`. CI builds the multi-arch image, packages
the App Store archive, signs it and publishes it.

## Reporting security issues

Please do not open a public issue — see [SECURITY.md](SECURITY.md).
