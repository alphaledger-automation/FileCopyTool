"""
File Copy Tool — Entry Point
============================
Run this file:  python main.py     (or just double-click run.bat)

On start-up the app checks for everything it needs and installs whatever
is missing by itself (customtkinter, pillow). Nothing needs to be
installed manually except Python — and run.bat installs that too.

Options:
    python main.py --setup-only
        install / verify the dependencies, then exit.

    python main.py --cli "<source folder>" "<destination folder>" "<list.txt>"
        copy without opening the window. Extra switches:
            --skip-existing     leave files already in the destination alone
            --keep-both         add " (2)" instead of overwriting
            --exact             match the list lines exactly (no name search)
            --no-recursive      do not look in the source's sub-folders
            --flatten           ignore sub-folders in the list, copy flat
"""

import sys


def _enable_hidpi():
    """
    Tell Windows this app draws at the screen's real resolution. Without it
    Windows stretches the window on 125% / 150% displays and all text looks
    blurry. Must run before the first window (incl. the setup splash) opens.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _run_cli(argv):
    """Copy a list of files and print the result — no window, no prompts."""
    import pathlib
    import queue
    import threading

    from constants import (
        DONE_RESULTS, IF_EXISTS_OVERWRITE, IF_EXISTS_RENAME, IF_EXISTS_SKIP,
        MATCH_EXACT, MATCH_SMART, RES_COPIED,
    )
    from copy_engine import CopyWorker, build_records, read_list_file

    positional = [a for a in argv if not a.startswith("--")]
    if len(positional) < 3:
        print("Usage: python main.py --cli "
              '"<source folder>" "<destination folder>" "<list.txt>"')
        return 2

    source = pathlib.Path(positional[0]).resolve()
    dest   = pathlib.Path(positional[1]).resolve()
    listf  = pathlib.Path(positional[2]).resolve()

    if not source.is_dir():
        print(f"Source folder not found: {source}")
        return 1
    if not listf.is_file():
        print(f"File list not found: {listf}")
        return 1

    names = read_list_file(str(listf))
    if not names:
        print(f"The list is empty: {listf}")
        return 1

    if_exists = IF_EXISTS_OVERWRITE
    if "--skip-existing" in argv:
        if_exists = IF_EXISTS_SKIP
    elif "--keep-both" in argv:
        if_exists = IF_EXISTS_RENAME

    records = build_records(names)
    q: "queue.Queue[tuple]" = queue.Queue()
    worker = CopyWorker(
        records=records, source_dir=source, dest_dir=dest, out_q=q,
        stop_event=threading.Event(), pause_event=threading.Event(),
        if_exists=if_exists,
        match_mode=MATCH_EXACT if "--exact" in argv else MATCH_SMART,
        recursive="--no-recursive" not in argv,
        flatten="--flatten" in argv,
    )
    worker.run()

    while True:                                   # drain the queue to stdout
        try:
            msg = q.get_nowait()
        except queue.Empty:
            break
        if msg[0] == "log" and msg[2]:
            print(msg[2])

    done = sum(1 for r in records if r.result in DONE_RESULTS)
    print(f"\n{done} / {len(records)} file(s) handled  "
          f"({worker.copied} copied, {worker.skipped} skipped, "
          f"{worker.missing} missing, {worker.failed} failed)")
    print(f"Destination: {dest}")
    return 0 if worker.copied or worker.skipped else 1


def main():
    setup_only = "--setup-only" in sys.argv
    cli        = "--cli" in sys.argv

    if not cli:
        _enable_hidpi()

    # bootstrap uses only the standard library, so it can run before any
    # third-party package has been installed.
    from bootstrap import ensure_ready
    ensure_ready(show_gui=not (setup_only or cli))

    if setup_only:
        print("Setup complete. All dependencies are installed.")
        return

    if cli:
        rest = sys.argv[sys.argv.index("--cli") + 1:]
        sys.exit(_run_cli(rest))

    from gui import FileCopyToolApp
    app = FileCopyToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
