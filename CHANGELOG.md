# Changelog

## 2026-09-07: local acceptance handoff

- Add project-specific acceptance cases, local requirements, and an agent brief.
- Add development setup and prerequisite checks.
- Keep local test reports and recorded media separate from release evidence.
- Record browser run state to prevent stale success reports after a failed run.


## 0.2.0

- Document OCR: Read images and scanned PDFs with local Tesseract. Keep word positions and recognition notes.
- PDF tables: Extract ruled or text-aligned tables. Use OCR with explicit column boundaries for scanned tables.
- Local semantic model: Rank workflow records with a model fitted on the current text. Filter by cosine similarity.
- Source summaries: Select representative source sentences. No cloud prompt or generated factual claims.
- Desktop actions: Preview and confirm mouse, keyboard, scroll, wait, and screenshot actions for one interactive run.
- Persistent triggers: Resume enabled folder watches and interval jobs after unlocking. Install a user worker for login startup.
- Encrypted history: Save workflow revisions and job history in an authenticated encrypted vault.
- File operations: Filter, extract fields, set output names, create copies, export CSV/JSON, and create ZIP files.

## 0.1.0

Initial local application. Version 0.2.0 changes the database format. Follow docs/UPGRADING.md.
