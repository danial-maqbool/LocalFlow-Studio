# LocalFlow Studio: local testing handoff

Handoff revision: 1. Prepared on 2026-09-07. Application version: 0.2.0.

## Status

The application source is published. This handoff prepares a repeatable local acceptance pass.
It does not certify the user PC, native permissions, every input file, or optional neural weights.
Do not remove documented processing boundaries to change the completion status.

The prior release evidence was recorded at `a42262279fef3a69f031fecfcdd54cabc78c682b`.
It reports 125 passing full Linux test executions and 17 browser checks.
Those counts are historical. Shared tests occur in each repository. Native-tool and OS-specific skips are recorded separately.
Use current GitHub Actions and new local reports to verify the handoff commit. Do not present the prior counts as a new run.

## Changes in this handoff

`bootstrap.py --dev` installs test tools into this project .venv.
`scripts/preflight.py` checks Python, direct package pins, SQLite FTS5, and applicable native-tool availability.
`--report-dir` keeps local test reports and media separate from committed release evidence.
Browser reports now distinguish started, failed, and completed runs. An interrupted run cannot keep a stale pass report.
Ten handoff regression tests check setup, requirement handling, and report isolation.

## Read order

Read `AGENTS.md`, this file, `handoff.json`, and `docs/LOCAL_TESTING.md` first.
Then read `docs/SETUP.md`, `docs/LIMITS.md`, `SECURITY.md`, and `docs/VERIFICATION.md`.
The full agent brief is in `docs/LOCAL_AGENT_PROMPT.md`.
Use `docs/LOCAL_TEST_RESULTS.template.md` for the sanitized final report.

## Start and verify

Windows PowerShell, from this repository root:

```powershell
py -3 bootstrap.py
.\.venv\Scripts\python.exe scripts/preflight.py --report-dir artifacts/local-qa/runtime
.\start.bat --demo
```

Stop the demo. Then follow the full runtime-only and development-install checks in `docs/LOCAL_TESTING.md`.
The default local port is `8761`. Use `--port 0 --no-browser` for a temporary server on an available port.
Use a unique `--data-dir` for persistence tests. `--demo` uses temporary data and does not prove persistent vault behavior.
Normal startup needs a vault passphrase. Do not put a real passphrase in a command, script, commit, or report.

## Project acceptance scope

| ID | Area | Required evidence |
| :--- | :--- | :--- |
| LF-01 | Invoice workflow | Preview the included invoice workflow, then run it. Compare CSV values and copied-file bytes. Preview must not create export files. Hash each source before and after. |
| LF-02 | Graph and parser failures | Reject cycles, missing nodes, invalid edges, unsafe paths, long regex inputs, oversized records, and unsupported files. Cancellation and retries must not replace source files. |
| LF-03 | OCR and PDF tables | Use a synthetic image, scanned PDF, mixed native/scanned page, ruled table, and borderless table. Compare extracted values with fixture truth. Exercise configured OCR column boundaries and missing language data. |
| LF-04 | Local semantic processing | Run semantic filtering and source-sentence summaries offline. Test an empty corpus and an unknown query. Record whether LSA or TF-IDF ran. Do not label either backend as a neural model. |
| LF-05 | Persistent worker | Run scripts/worker_check.py. Verify an enabled trigger resumes after a process restart. Verify a disabled trigger stays disabled. Check interrupted-job records. |
| LF-06 | Native login service | In a disposable OS user profile, install this project service, close the terminal, log out and back in, and create a watched file. Check the output. Remove the service and confirm its saved credential is removed. |
| LF-07 | Desktop input | Use a disposable desktop and synthetic target window. Test preview, missing permission, explicit confirmation, expired confirmation, reused confirmation, focus changes, and fail-safe interruption. A worker must reject desktop execution. |
| LF-08 | Vault and migration | Use a synthetic passphrase and copied legacy database. Test persistence, wrong password, altered ciphertext, backup restore, failed write, and a second writer. Preserve the legacy database and all source files. |

## Work that requires the local machine

Run the separate worker and disposable-desktop checks. Native login service and OS keyring acceptance still need a real user session.
Install required native tools and language data. Check actual outputs with independent parsers or viewers.
Test a clean runtime-only environment, paths with spaces and Unicode, offline operation, and the existing app data migration path when applicable.
Measure local performance with synthetic fixtures. No universal hardware benchmark is claimed.
Use a disposable OS profile for service and credential-store checks. Do not alter the user active desktop without local consent.

## Evidence and Git rules

Keep raw logs, resolved dependency lists, screenshots, and temporary outputs under ignored `artifacts/`.
The committed `docs/test-report.json`, `docs/browser-report.json`, and `docs/platforms/` remain historical release evidence.
New local reports must identify their actual commit and environment. Review evidence before publishing it.
Never commit user documents, browser history, vaults, passwords, API tokens, model weights, or .venv.
Use a local-validation branch. Preserve existing changes. Never force-push or reset user work.

If a shared `localdesk/` defect is fixed, compare all five copies and apply only the relevant patch.
Run each affected repository suite. The apps must remain independently cloneable and runnable.
Do not run `scripts/prepare_release.py` as an installer. Use `bootstrap.py`.
Update source-manifest hashes only after reviewing changes. Preserve real tests and security controls.

## Acceptance decision

Local-machine acceptance: **NOT RUN HERE**.
Use PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE for each case.
Only state that local acceptance is complete when every applicable gate has evidence.
If a permission blocks one test, record that requirement and continue unrelated tests.
