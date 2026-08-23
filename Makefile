.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "Nextcloud Citizens — development targets"
	@echo ""
	@echo "  make up          build dev image and (re)start the dev container (auto-reload)"
	@echo "  make register    register the manual-install daemon + Citizens ExApp in AppAPI"
	@echo "  make unregister  remove the Citizens ExApp registration"
	@echo "  make logs        tail the dev container logs (pretty structlog output)"
	@echo "  make test        run the Python test suite"
	@echo "  make lint        run ruff"
	@echo "  make dev-reset   wipe ONLY Citizens app data (asks for confirmation)"

.PHONY: up
up:
	sh scripts/dev-up.sh

.PHONY: register
register:
	sh scripts/register.sh

.PHONY: unregister
unregister:
	sh scripts/unregister.sh

.PHONY: logs
logs:
	docker logs -f --tail 200 nc_app_citizens

# Tests run inside the app container image: the runtime is Python 3.12 there,
# and this host is too memory-constrained for a native venv.
.PHONY: test
test:
	docker build -q -t citizens-dev . >/dev/null
	docker run --rm -v "$(CURDIR)":/app -w /app --entrypoint sh citizens-dev \
		-c "pip install -q pytest ruff && python -m pytest -q"

.PHONY: lint
lint:
	docker run --rm -v "$(CURDIR)":/app -w /app --entrypoint sh citizens-dev \
		-c "pip install -q ruff && python -m ruff check citizens tests"

.PHONY: dev-reset
dev-reset:
	sh scripts/dev-reset.sh
