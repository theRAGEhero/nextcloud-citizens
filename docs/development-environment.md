# Development environment

Inventory of the existing server, taken 2026-08-23 before any Citizens work
(brief §3.1). This is a shared production-ish host: **downtime is acceptable,
data loss is not.** Citizens must never touch Nextcloud user files.

## Nextcloud

| Item | Value |
|---|---|
| Version | **34.0.3.2** (`nextcloud:34-apache`; upgraded 32→33→34 on 2026-08-23, backups + rollback in `/root/backups/nextcloud-upgrade-20260823/`) |
| Container | `nextcloud`, published on `127.0.0.1`-reachable `0.0.0.0:8081->80` |
| Database | `nextcloud-db` (postgres:15), db `nextcloud`, user `oc_admin` |
| Cache | `nextcloud-redis` (redis:7-alpine) |
| Docker network | `nextcloud_nextcloud-network` |
| Compose file | `/root/nextcloud/docker-compose.yml` |
| Volumes | `nextcloud_nextcloud_data` → `/var/www/html` (data dir **119 GB**), `..._config` → `/var/www/html/config`, `..._apps` → `/var/www/html/custom_apps` |
| Public URL | `https://cloud.democracyinnovators.com` (trusted domains: `localhost`, `cloud.democracyinnovators.com`; `overwritehost`/`overwriteprotocol` set) |
| Maintenance | off; no pending DB upgrade |

## AppAPI

- `app_api` v34.0.0 installed and enabled (auto-updated with the server upgrade).
- `manual_install` deploy daemon registered (host = `nc_app_citizens`); the
  Citizens ExApp is registered and enabled, its container joins
  `nextcloud_nextcloud-network`, and Nextcloud PHP-proxies
  `/index.php/apps/app_api/proxy/citizens/*` to it.

## HTTPS / reverse proxy

- Host `nginx` (systemd service) terminates TLS. Port 443 is owned by an SNI
  **stream demux**; the Nextcloud vhost listens on `127.0.0.1:8443 ssl proxy_protocol`
  and proxies `/` → `http://127.0.0.1:8081`.
- Vhost: `/etc/nginx/sites-available/cloud.democracyinnovators.com` (symlinked in
  `sites-enabled`). `client_max_body_size 16G`, proxy timeouts 300 s.
- Certificates: Let's Encrypt via certbot cron. `status.php` returns HTTP 200.
- **Constraint:** the vhost sets no `Upgrade`/`Connection` headers →
  **WebSockets will not traverse this proxy.** Citizens V1 therefore uses HTTP
  polling / short posts for live features. Enabling WebSockets later requires a
  careful vhost edit (stop-and-ask change, see plan safety rules).

## Host resources

| Item | Value |
|---|---|
| OS | Debian, kernel 6.1.0-38-amd64 |
| CPU | 4 cores |
| RAM | 5.8 GiB total; ~1.3 GiB available at inspection, **swap already in use (7.2 GiB)** |
| Disk | `/dev/sda3` 391 GB, **91 GB free** (76 % used) |
| Docker | ~30 containers (Democracy Routes stack, Jitsi/LiveKit, blogs, an Ollama app, …) share this host |

Consequences for Citizens:

- Container must be lean; run with a memory limit (≤ 512 MB).
- ffmpeg / analysis jobs run strictly sequentially (single job worker).
- **No local LLM inference on this host** — analysis goes to remote
  OpenAI-compatible endpoints (Mistral default; Ollama Cloud etc. via base URL).
- Audio storage must be size-conscious; retention cleanup matters.

## Backup

- No pre-existing Nextcloud backup mechanism was found on the host.
- Pre-Citizens backup created and restore-tested on 2026-08-23:
  `/root/backups/nextcloud-pre-citizens-20260823/` — DB (`pg_dump -Fc`,
  verified with `pg_restore --list`), config + custom_apps volume tars
  (verified with `tar -t`), compose file, container inspects, app list, and
  `RESTORE.md` with the full restore procedure.
- The 119 GB data volume is **not** duplicated (exceeds free disk). Accepted
  risk: Citizens never touches user files; AppAPI registration writes only DB
  and config, both covered.

## Test identity

- Dedicated Nextcloud user `citizens-test` for all UI testing.
- The admin account is used only for installation, AppAPI configuration and
  Citizens admin settings.
