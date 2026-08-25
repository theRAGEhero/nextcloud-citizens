# Development environment

Citizens is a Nextcloud **ExApp**: a container that Nextcloud talks to through
the AppAPI proxy. For development you run that container yourself and register
it with a `manual-install` daemon, so you can edit code and reload instantly.

## Requirements

* A Nextcloud instance (32 or newer) with the **AppAPI** app enabled
* Docker, on the same host, able to join the Nextcloud container's network
* Node 22+ for the frontend build

## One-time setup

1. Copy the settings you need into `scripts/dev-env.sh` — the Nextcloud
   container name, the Docker network it is on, and the public URL of the
   instance. Everything else has sane defaults.
2. Start the app container and register it:

   ```sh
   make up        # builds the image, runs it with the source bind-mounted
   make register  # registers the manual-install daemon + the ExApp in AppAPI
   ```

3. Open Nextcloud; "Citizens" appears in the top menu.

`make up` mounts the repository over `/app` and runs uvicorn with `--reload`,
so Python changes apply immediately. Frontend changes need `npm run build` in
`frontend/` (the bundles in `js/`, `css/` and `recorder_static/` are committed
because the runtime image ships them).

## Everyday commands

| Command | What it does |
|---|---|
| `make up` | rebuild + restart the dev container |
| `make logs` | tail the container logs (pretty structlog output) |
| `make test` | run the Python suite inside the image |
| `make lint` | ruff |
| `make appstore-check` | validate `appinfo/info.xml` the way the App Store does |
| `make dev-reset` | wipe **only** Citizens data (asks first) |

## Testing the phone recorder

`sh scripts/browser-test-env.sh start` launches a throwaway instance on
`127.0.0.1:23100` with authentication disabled (only honoured against a local
Nextcloud) and a seeded assembly, which the Playwright specs in
`tests/browser/` drive with a fake microphone. Stop it with
`sh scripts/browser-test-env.sh stop`.

## Notes that save time

* Route regexes in `appinfo/info.xml` are matched **without** a leading slash on
  AppAPI ≤33 and **with** one on 34+; the escaped form (`^api\/v1\/.*`) works on
  both. Order matters — narrow routes before catch-alls.
* The AppAPI proxy sends `default-src 'none'` as CSP for proxied responses, so
  the recorder page ships its own CSP header, and its path must end in `.html`
  for the proxy to inject a script nonce.
* Assets are cached by the proxy for an hour; the recorder busts this with the
  app version in its URLs, which is why the version must be bumped for a UI
  change to reach phones immediately.
