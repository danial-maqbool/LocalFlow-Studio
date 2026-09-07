# Verification

Run `python -m unittest discover -s tests -v` in the installed environment.
The suite covers app operations, loopback HTTP, input bounds, and encrypted storage.
Tesseract and FFmpeg checks skip only when the corresponding executable is absent.
The release CI must run the full dependency set on Linux. Core platform tests also run on Windows and macOS.

`docs/test-report.json` records the local test result and package versions.
`docs/browser-report.json` records browser actions and the navigation mode.
A real HTTP bridge is used only when the build environment blocks browser loopback navigation.
A bridge check does not test browser-origin enforcement. The HTTP suite tests server enforcement directly.
Normal CI browser checks use direct loopback navigation.

Native service definitions and credential-selection rules have configuration tests.
A successful configuration test is not a completed native service installation.
Optional neural model loading requires a trusted local model folder. The built-in LSA model is tested without a download.
No independent security audit, universal file-repair guarantee, or universal OCR accuracy is claimed.
