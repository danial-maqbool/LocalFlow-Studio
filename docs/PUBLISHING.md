# Publishing a release

Run setup and the test suite. Run browser checks and review the actual generated media.
Confirm the database migration, source-preservation rules, dependency audit, and processing boundaries.
Publish only the source, tests, synthetic examples, and documentation.
Never commit .venv, app data, credentials, vaults, user documents, or downloaded model weights.
Use a version tag only after checking CI. Do not force-push over unrelated history.

The `release/v0.2.0` preparation workflow verifies source hashes before formatting. When a shared-source manifest is present, it copies only named files from an immutable reviewed LocalFlow commit. The prepared repository contains those files directly. This copy step is a release operation, not a runtime dependency.

A six-job OS and Python matrix must finish before the evidence job runs. The evidence job audits runtime packages, runs native Linux tests, records the real interface, and commits the reports on the release branch. The maintainer checks those results before promoting the release branch to main.
