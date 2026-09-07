# Processing boundaries

These are input, operating-system, and trust boundaries for version 0.2.0. They are not a list of hidden placeholder features.

| Area | Boundary |
| :--- | :--- |
| Workflow graph | 1 to 40 nodes, at most 120 edges, and no cycles. |
| Records | At most 500 records per run. |
| Regex | Bounded pattern and text lengths with a separate deadline-controlled worker. |
| Desktop actions | At most 50 actions per step and a 120 second execution window. Primary-screen coordinates and ASCII text input. |
| Desktop trust | Input affects the focused application. It can change files or issue commands there. It is not a sandbox. |
| Trigger intervals | 15 seconds to 24 hours. Enabled settings resume only after the vault unlocks. |
| Interrupted runs | Marked interrupted at restart. A half-written run is not silently continued. |

## Shared safeguards

The normal input limit is 25 MiB per file. Text extraction is bounded to 250,000 characters. XML parts are bounded and reject document-type and entity declarations. Archive paths cannot escape into parent folders. Scans exclude common private and generated folders and do not follow ordinary symlinks.

The advanced document worker has a 90 second overall deadline, at most 50 pages, and at most 20 million rendered pixels per page. Tesseract has a per-page timeout. Resource limits reduce excessive work; they do not make native parsers an operating-system sandbox.

The semantic backend fits a local latent semantic analysis model. Very small corpora use an explicit TF-IDF fallback. Similarity is not a calibrated probability. Optional neural models require trusted, already-downloaded safetensors and an allowed model layout. That optional backend is separate from the tested built-in model.

## Encryption and operating systems

The vault protects database bytes and database backups at rest. It does not protect an unlocked process from same-user malware. Original files, exports, and parser temporary files need OS-level disk protection.

The worker must run on an awake computer. Login services depend on the OS credential store and user-session permissions. Desktop input and title capture depend on an unlocked supported graphical session. No CPU, memory, or full-drive throughput benchmark is claimed.

Read [Verification](VERIFICATION.md) for actual test environments and skipped checks.
