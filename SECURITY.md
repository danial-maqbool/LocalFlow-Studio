# Security

LocalFlow Studio is a local desktop tool. It is not a network service.

- The default server address is `127.0.0.1`.
- The core app sends no telemetry.
- The core app uses no API key.
- Workflow data cannot execute shell commands or Python code.
- Folder scans skip symbolic links.
- Source files are read only. Generated files use a separate output folder.
- The local SQLite database is not encrypted.

Do not run LocalFlow as an administrator. Do not expose port 8761 to another device. Review generated files before you use them in another system.

Report a security problem through a private GitHub security advisory when possible. Do not publish sensitive example data in an issue.
