# Mission 06 — engineering and interface review

## Fresh baseline (2026-11-07)

Authenticated connector access and a fresh clone confirmed public repository
`AlirezaBelal/web-monitor`, default branch `master`, head
`d32ca64d772210833e16a191fc4a3699024aad37`, no open PRs, and successful CI run
[42108328854](https://github.com/AlirezaBelal/web-monitor/actions/runs/42108328854).
The latest Pages run was [42098035389](https://github.com/AlirezaBelal/web-monitor/actions/runs/42098035389).
The active master ruleset requires a PR, all five Python jobs, static analysis and
coverage, dependency audit, and Docker build/runtime. It permits no bypass.

Inspected main.py, web_monitor.py, notifications.py, health.py, configuration,
requirements, Dockerfile, deploy assets, SECURITY.md, workflows, Dependabot, all
Python tests, browser tests, website assets, pinned design skills, and recent
commit history (especially response cleanup #3, input/notification hardening #4,
and simulator #5). Existing protections were retained rather than rewritten.

The real application is a sequential multi-target requests/Beautiful Soup service:
fetch → retry/backoff → select → extract → SHA-256 → compare → notify → commit.
Baseline and changed-definition rebasing are silent. Alert delivery is at least
once. Failed targets do not prevent later checks. State stores identifiers, not
scraped content; health excludes URLs and secrets. Docker uses a non-root user,
and systemd uses a dedicated account, restrictive umask and sandboxing. The
browser was a deterministic three-target simulator with no network access.

## Confirmed defects and bounded fixes

- Original docs/app.js:37 classified request recovery as `change`. Recovery now
  has its own event and the first successful response establishes a baseline.
- Original docs/app.js:49 queued a callback which Reset at :51 did not cancel or
  invalidate. The simulation controller now cancels and uses a generation token.
  Repeated clicks cannot advance twice; filters do not mutate simulation state.
- notifications.py buffered arbitrary notification response bodies and did not
  explicitly close them. Webhook now streams status-only responses; Telegram
  reads at most 16 KiB decompressed acknowledgement data, requires an object with
  ok=true, and closes on success, rejection, malformed data and body-read failure.
- main.py did not close owned sessions on normal exit, Ctrl+C or partial setup
  failure. Ownership-aware cleanup preserves caller ownership of injected clients.
- web_monitor.py path checks caught identical paths but allowed one output file
  to be another output's parent directory, causing guaranteed write failures.
  Ancestor/descendant conflicts now fail configuration validation.
- Numeric overflow, very long integer strings, and deeply nested JSON could
  escape the controlled error boundary. They now produce safe configuration or
  state errors without echoing the input.

Regression evidence: tests/test_mission_hardening.py, tests/test_notifications.py,
tests/browser_demo.test.cjs and scripts/qa-browser.mjs. No change to the monitoring
comparison algorithm, no redirects, legacy format, target limits, response limits,
notification-before-state semantics, or legitimate loopback monitoring.

## Design skill evidence

skills-lock.json retains yikZero/skills at
5e85045d96662605f33e12150cdc6d00cb04dc0a. Ran the prescribed context loader (no
PRODUCT.md or DESIGN.md present), read brand/product, critique, heuristics,
personas, polish and web-interface-guidelines references. Product register governs
the workbench; the landing page preserves Signal Ledger's established identity.
Voice: careful, mechanical, calm. Existing system typography is retained; no font
or third-party asset is added. This is identity preservation, not a new font choice.

### Independent design review and detector synthesis

The original restrained navy/teal palette and honest synthetic labels worked.
The oversized hero, repeated small cards, and simulator-only opening made the
Python product hard to evaluate. The biggest opportunity was a useful comparison
experience with an explicit connection to the real installation workflow.

The prescribed `npx impeccable detect --json docs/index.html` initially reported
8 findings: 5 low-contrast findings (including duplicates), hero eyebrow, 10.4px
functional branding, and tiny 11.2px body copy. Source review independently found
the recovery and reset confusion. Final scan: no findings after removing numbered
section labels and rounding from the accented workbench. No detector overlays
were injected into the production CSP.

| Nielsen heuristic | Before / 4 | After / 4 | Reason |
|---|---:|---:|---|
| Status visibility | 2 | 3 | Explicit committed state, eligibility and progress |
| Real-world match | 3 | 4 | Python product and browser computation clearly separated |
| User control | 1 | 3 | Reliable Reset, clear inputs, sample restoration |
| Consistency | 2 | 4 | Recovery, failure and content changes use distinct terms |
| Error prevention | 3 | 3 | Bounded input, literal text rendering, disabled busy action |
| Recognition | 3 | 4 | Samples and contextual algorithm explanation |
| Efficiency | 2 | 3 | Direct comparison, native keyboard controls |
| Minimalism | 2 | 3 | Compact hero; instrument workflow replaces marketing cards |
| Error recovery | 2 | 3 | Actionable validation, preserved inputs, error focus |
| Help | 3 | 3 | Algorithm details, semantics and installation guide |
| Total | 23/40 | 33/40 | Subjective review, not an automated accessibility score |

Cognitive-load review: two initial action paths (compare or install); simulator
instructions reveal the next scenario. Low load (one concern: technical semantics
still require careful reading). Jordan can now find the actual Python product;
Riley can test arbitrary bounded text and reset pending work; Sam has native
controls, live announcements, visible focus, a working skip link and keyboard
access to the scrollable ledger. No hidden onboarding or time-limited controls.

Priority fixes applied: P1 reset reliability and recovery classification; P1
legible type and contrast; P2 compact hero and immediate real interaction; P2
installation/algorithm boundaries. Optional backend expansion, HTML comparison in
the browser, and exact Python parity were rejected as unnecessary scope.

### web-ui-audit — initial file:line findings

- docs/style.css:1 — 74px hero maximum; 10–11px functional text, muted contrast
  below AA in several actual text/background combinations.
- docs/style.css:1 — no scroll-margin on heading anchors; native select touch
  height below 44px in the compact controls.
- docs/app.js:37 — recovery presented as content change.
- docs/app.js:49,51 — Reset fails to interrupt pending action.

### web-ui-audit — final

- docs/index.html — pass: labeled native controls, skip link, live results,
  details disclosure, descriptive navigation, no inline scripts.
- docs/style.css — pass: visible focus, reduced motion, anchor margin, explicit
  select colors, ≥44px controls, responsive grids and wrap rules.
- docs/app.js — pass: user text uses textContent; limits checked before processing;
  bounded ledger, deterministic reset, no networking/storage/HTML injection sinks.

## Local release evidence

- Python 3.15.2 available locally: 56 tests pass (including localhost subprocess
  CLI and real loopback Webhook), coverage 91% (605 statements, 56 missing).
  Supported 3.10–3.14 remains verified by the existing CI matrix.
- Ruff correctness checks, pip check and three tracked configuration validations pass.
- Node: 10 deterministic tests pass.
- Real Chromium with axe: 320×700, 375×812, 390×844, 768×1024, 1024×768,
  1440×1000 and 1920×1080. Zero WCAG A/AA axe violations at each width;
  no overflow, control overlap, external requests, console errors or broken assets.
- Browser checks exercise keyboard comparison, skip link, focus, validation and
  size errors, literal markup, sample restore, baselines, retries, recovery,
  delivery failure/retry, filtering, reset mid-cycle and repeated clicks.
- Real browser screenshots captured and visually inspected; no generated mockups.
  The ultra-wide header alignment found in visual review was corrected.
- Lighthouse local mobile: performance 100, accessibility 100, best practices 100,
  SEO 92. Desktop: 97/100/100/92. SEO deduction: local test server has no root
  robots.txt; the project cannot control the root domain robots.txt. No artificial
  score-only production change was made. Small unminified assets remain readable.
- Docker daemon unavailable locally; required Linux CI builds the image, verifies
  non-root execution, and validates container configuration before merge.

The new browser job is a prerequisite of the existing Pages deployment and keeps
browser tools isolated from production Python dependencies. Screenshots and axe
JSON are retained as workflow artifacts for 14 days. Human visual review remains
necessary; a green job alone does not establish visual quality.
