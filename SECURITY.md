# Security Policy

## Supported version

Security fixes are applied to the current `master` branch.

## Reporting a vulnerability

Please report security issues privately through GitHub's security reporting features when available. Do not open public issues containing credentials, authenticated target URLs, session cookies, authorization headers, Webhook URLs, Telegram bot tokens/chat IDs, or other sensitive runtime configuration.

## Configuration and secret safety

`config.json` is intentionally ignored by Git. Tracked example configurations contain only public placeholders and environment-variable names.

Webhook destinations and Telegram credentials are resolved from environment variables at runtime. Do not hard-code secret-bearing Webhook URLs or bot credentials in tracked JSON, unit files, Dockerfiles, source code, issue reports, CI logs, or screenshots.

For systemd deployments, keep the real environment file outside the repository and restrict its filesystem permissions. For containers, use your runtime's environment/secret mechanism rather than baking secrets into the image.

## State and health privacy

Target state files store only SHA-256 identifiers. Scraped webpage content is not written to state.

Optional health output contains target names, statuses, matched-element counts, and controlled error messages. It intentionally excludes target URLs, CSS selectors, scraped content, Webhook destinations, and notification credentials.

The `.webmonitor/` directory and local environment files are ignored by Git. The configuration reader enforces a 1 MiB size limit, persisted state readers a 16 KiB limit, and multi-target suites accept at most 64 targets. These limits prevent accidental unbounded reads, but they do not make hostile HTML safe to parse or restrict which networks an authorized operator can reach.

## Notification reliability

On a detected change, notification delivery occurs before the changed digest is committed. HTTP redirects are not followed when delivering Webhook/Telegram alerts, and a redirect or other non-2xx status is not treated as delivery. Telegram additionally must acknowledge the call with `"ok": true`. If delivery fails, the old digest remains active so the change can be attempted again during the next check.

Notification delivery errors are intentionally generic. In particular, Telegram failures do not print the request URL because the bot token is embedded in that URL.

## Network behavior

Configured monitoring targets and Webhook destinations must be absolute HTTP(S) URLs. Operators should prefer HTTPS Webhooks outside local development.

Monitoring requests use explicit timeouts and bounded retry/backoff. Operators are responsible for monitoring only pages they are authorized to access and for selecting intervals consistent with target-site terms and acceptable-use policies.

## Deployment hardening

The tracked Docker image runs as a non-root user. The example systemd unit uses a dedicated service account, restrictive umask, a managed state directory, restart behavior, and systemd sandboxing controls.

Review deployment examples for your environment before production use. Protect configuration/state directories according to the sensitivity of monitored targets and notification routing.

## Dependency and CI security

GitHub Actions uses read-only repository contents permission and does not persist checkout credentials. Core and optional desktop dependencies are checked with `pip-audit`, Dependabot is configured for Python and GitHub Actions updates, and CI builds/verifies the non-root Docker image.
