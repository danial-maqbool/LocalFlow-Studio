# Local API

This API is for the running local app. It is not a hosted service or a stable public API contract.
The server listens on `127.0.0.1:8761` by default.

## Session checks

The index page supplies a random token for the current Python process.
The UI sends it in the `X-Local-Token` header. Every API request must use the current token.
POST requests must use `Content-Type: application/json`. The body limit is 36 MiB.
The server checks Host and Origin and does not enable cross-origin access.

Do not copy the token into a repository or enable network forwarding to the port.
Restarting the Python process changes the token.

## Common operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/info` | none | Name, version, paths, and local optional-tool availability. |
| GET | `/api/state` | none | Current application state and recent jobs. |
| GET | `/api/browse` | path, optional | Up to 1,500 visible folder entries. |
| GET | `/api/jobs/ID` | job ID in the path | Status, progress, result, or error. |
| POST | `/api/cancel` | id | Request cooperative job cancellation. |
| POST | `/api/upload` | name, base64 content | Save a new private inbox file. |
| POST | `/api/backup` | none | Write an encrypted database-only backup artifact. |

## Application operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/workflow` | id, optional | Return one saved workflow. |
| GET | `/api/versions` | id | List its saved revisions. |
| POST | `/api/save` | workflow | Validate and save a definition. |
| POST | `/api/run` | workspace; id or workflow; dry_run; stop_after, optional | Start a job. dry_run defaults to true. |
| POST | `/api/export` | id | Write a workflow JSON file. |
| POST | `/api/restore` | id, revision | Restore a saved revision as a new revision. |
| POST | `/api/delete` | id | Remove the current definition; it does not remove source files. |
| POST | `/api/trigger/start` | id, workspace, mode: watch or schedule, seconds | Start one explicit local trigger. |
| POST | `/api/trigger/stop` | none | Stop the trigger. |

### Example request body

Send this JSON to `POST /api/run` with the current session token:

```json
{
  "id": "invoice-register",
  "workspace": "C:/Users/You/Documents/invoices",
  "dry_run": true
}
```

Use paths from the computer running Python. Change the example path before sending the request.
A job-start response contains `job_id`. Read `/api/jobs/ID` until its status is terminal.
Read the error field when the job fails. Do not treat a queued response as a completed operation.

An artifact response contains its name, relative output path, and size. The browser download helper requests only paths under the app output directory.
Use `web/common.js` as the reference client for the exact response envelope and download route.

## Desktop confirmation

`POST /api/desktop/arm` takes the exact workflow, workspace, and `confirmed: true`. It requires a process started with `--allow-desktop`. Pass the returned one-use token to the corresponding run request as `desktop_token`. Preview does not arm input. Tokens expire and cannot authorize a modified workflow. See `app/service.py` for the request validation.
