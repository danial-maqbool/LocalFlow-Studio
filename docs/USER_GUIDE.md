# Daily use

Complete [Setup](SETUP.md) first. Start with `start.bat` on Windows or `sh start.sh` on Linux and macOS.
Unlock the vault with your passphrase. Use `--demo` for a temporary synthetic-data session.

## First run

1. Select **Invoice register** in the workflow list.
2. Keep the sample workspace. It contains three synthetic invoice files.
3. Select **Preview plan**. Check the extracted invoice IDs and planned file names.
4. Select **Create outputs**. Open the completed run.
5. Download the three invoice copies, the CSV register, and the run manifest.

### Edit a workflow

Select a node on the canvas. Edit its label and JSON settings in the right panel. Select its parent nodes to change the edges. Apply the settings, then save the workflow. A failed validation leaves the saved definition unchanged.

The `name` node changes the planned output name, not the source name. Use `${stem}`, `${ext}`, or an extracted field such as `${invoice_id}`. The `copy` node creates the file. A `condition` node filters records; it is not a general two-branch programming statement.

### Use a trigger

Open the trigger view. Select a saved definition, workspace, and interval. Start the trigger explicitly. Stop it before editing files that should not be processed. A running trigger keeps the selected definition snapshot. Restart the trigger to use a later revision.

### Inspect a failed run

Open Run history and read the failed step. Correct its input or settings. Preview again before creating outputs. Files from a failed run can remain in that run's output folder. They do not replace source files.


### OCR, tables, and semantic steps

Add `ocr` after a folder and filter step for image or PDF inputs. Add `tables` for PDF table records. For a scanned table, select the OCR strategy. Optional column boundaries use PDF page points, not rendered-image pixels. Install the corresponding Tesseract language data first.

Add `semantic` after text extraction. Enter a query and minimum cosine score. The model fits the current records. A score is similarity, not a probability. Add `summary` to select source sentences. These nodes do not contact an AI service.

### Confirm desktop input

Stop the normal worker. Start `run.py --allow-desktop` in the virtual environment. Add a `desktop` node and inspect every action. Preview the workflow first. Select the desktop confirmation control before creating outputs. The confirmation expires after 60 seconds and authorizes one exact workflow and workspace.

Move the pointer to a screen corner to stop PyAutoGUI input. Keep the intended application in focus. Desktop input can modify that application, including terminals and source documents. It is not a safe copy operation. Background services never enable this capability.

### Restart and background operation

An enabled trigger resumes after a normal password-unlocked start. A user service can unlock the vault through the OS credential store. Stop the trigger explicitly to prevent resumption. A powered-off or sleeping computer cannot process files. Read [Background operation](BACKGROUND.md).

## Back up your work

The Backup control creates an authenticated encrypted database copy. Keep the passphrase with your own password manager. A database backup does not include source inputs or exported files. Stop the app before copying its complete data directory. Protect that copy with OS disk encryption or a trusted encrypted backup tool.

## Troubleshooting

| Symptom | Action |
| :--- | :--- |
| Missing Python package | Run the setup command from this repository again. Start through its virtual environment. |
| Missing OCR | Install Tesseract and the required language data. Check `run.py doctor`. |
| Port in use | Close the older app process or use `--port 0`. Services need a fixed port. |
| Changed source | Scan or preview the source again. Do not reuse an old approval. |
| Expired session | Reload the browser after restarting the worker. |
| Failed job | Read the failed step and its coverage note. Do not treat partial outputs as complete. |

Do not put private files, vault passwords, tokens, or real window titles in public bug reports.
