# File Copy Tool

Copy a named list of files out of a folder tree — give it a source, a destination and a list of file names, and it fetches each one and tells you exactly what happened to it.

Built for the case where someone hands you a list of a few hundred file names and the files are scattered across sub-folders: you should not have to search for each one by hand.

Nothing is ever moved, renamed or deleted. It is a copy, always.

---

## Requirements

- Windows 10/11
- Python 3.10+

Only two packages, installed on first run. `run.bat` installs Python itself via `winget` if it is missing.

## Install and run

```bash
git clone https://github.com/alphaledger-automation/FileCopyTool.git
cd FileCopyTool
pip install -r requirements.txt
python main.py
```

Or double-click **`run.bat`** on Windows — `main.py` installs `customtkinter` and `pillow` itself if they are missing. There is no executable to build.

Prepare dependencies without opening the window:

```bash
python main.py --setup-only
```

## Giving it the list

Two ways, and you can switch between them freely:

- **From a `.txt` file** — one name per line. A `file_list.txt` sitting next to `run.bat` is picked up automatically at start-up.
- **Typed straight in** — paste the names into the box, one per line.

Either way, blank lines are ignored, lines beginning with `#` are comments, and stray quotes and trailing commas are stripped — so a list pasted out of Excel or a chat message works as-is.

## Name matching

| Mode | Behaviour |
|---|---|
| **Find by name** (default) | The extension is optional and sub-folders are searched. A line reading `[File Name]` finds `[File Name].pdf` three folders down. |
| **Exact name only** | The line must match the path under the source folder exactly. Faster, and the right choice when two files share a name. |

**Search sub-folders** is on by default; turn it off to look only in the source folder itself.

## When the file is already there

| Option | Behaviour |
|---|---|
| **Overwrite it** (default) | Replace the copy in the destination |
| **Skip it** | Leave the existing file alone, count it as `SKIPPED` |
| **Keep both** | Write `name (2).pdf` alongside it |

**Copy everything flat** ignores any sub-folder in the list lines and puts every copy directly in the destination.

## Running it

**Load List** reads the list and fills the File Queue table so you can check the matches *before* copying anything. **Start Copy** runs it; Pause/Resume work mid-run and Cancel stops after the file in flight.

Six summary tiles track the run — `LISTED`, `COPIED`, `SKIPPED`, `MISSING`, `FAILED`, `PENDING` — plus total bytes copied. The activity log carries one timestamped, colour-coded line per file.

**Save Report …** writes a CSV of the whole run: every name, what it matched, the size, the result and where it landed. Useful as a file note when you need to show which documents were handed over.

The **File Queue** page shows a live table — row number, the name as written in your list, what it actually matched when the two differ, size, result and full destination path. The row being copied scrolls itself into view.

## Command line

```bash
python main.py --cli "C:\source" "D:\dest" "C:\list.txt"
```

| Flag | Effect |
|---|---|
| `--skip-existing` | Leave files already in the destination alone |
| `--keep-both` | Append ` (2)` instead of overwriting |
| `--exact` | Match list lines exactly |
| `--no-recursive` | Do not search sub-folders |
| `--flatten` | Ignore sub-folders in list lines, copy flat |
| `--setup-only` | Install/verify packages, then exit |

## Appearance

Light / Dark at the bottom of the sidebar, remembered between launches in `%LocalAppData%\AlphaLedgerAutomation\filecopy_ui.json`.

The two schemes were built as a pair rather than one tinted from the other: in Light the red accent is a deep brick so it reads on pale surfaces, in Dark a bright coral so it reads on charcoal. Body text clears 4.5:1 contrast in both, checked by `tools/contrast_audit.py`:

```bash
python tools/contrast_audit.py .
```

## Project layout

| File | Purpose |
|---|---|
| `run.bat` | Windows launcher (finds or installs Python) |
| `main.py` | Entry point; window or `--cli` |
| `bootstrap.py` | First-run dependency check and installer |
| `gui.py` | Dashboard / File Queue window |
| `copy_engine.py` | List parsing, name matching, the copy itself |
| `constants.py` | Names, options, colour palette |
| `tools/contrast_audit.py` | WCAG contrast check |
| `Assets/` | Icon and logo |

`USER_GUIDE.txt` holds the end-user walkthrough and troubleshooting notes.

## Notes

- Source files are only ever read. The tool refuses to run when source and destination are the same folder.
- Your file lists and run reports are gitignored, so a working list never ends up in a commit.
- Setup log: `%LocalAppData%\AlphaLedgerAutomation\filecopy_setup.log`

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Alpha Edge Advisory.
