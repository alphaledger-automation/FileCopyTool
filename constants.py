"""
File Copy Tool — Constants & Configuration
==========================================
Everything the shell (gui / copy_engine) needs: result states, input
modes and the colour palette.

The palette has one entry per colour KEY, and every entry is a
(light, dark) pair. customtkinter picks the right half automatically for
its own widgets; `gui.pick()` does it for the plain tk / ttk parts
(the file table and the log tags).
"""

import pathlib

# ── Application identity ────────────────────────────────────────────────────
APP_NAME     = "File Copy Tool"
APP_VERSION  = "2.0"
APP_SUBTITLE = "Copy a named list of files  →  anywhere"
APP_BRAND    = "Alpha Ledger Automation"

APP_DIR_NAME = "AlphaLedgerAutomation"       # per-user settings folder


def settings_file() -> pathlib.Path:
    import os
    base = pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home())))
    return base / APP_DIR_NAME / "filecopy_ui.json"


# ── Where the file list comes from ──────────────────────────────────────────
SRC_TXT    = "From a .txt list"
SRC_TYPED  = "Type the names"
SRC_MODES  = (SRC_TXT, SRC_TYPED)

DEFAULT_LIST_NAME = "file_list.txt"          # looked for next to the app


def default_list_file() -> str:
    """A file_list.txt sitting next to the app, if there is one."""
    here = pathlib.Path(__file__).resolve().parent
    for base in (here, here.parent):
        candidate = base / DEFAULT_LIST_NAME
        if candidate.is_file():
            return str(candidate)
    return ""


def default_dest_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Downloads"


# ── What to do when the destination already has the file ────────────────────
IF_EXISTS_OVERWRITE = "Overwrite it"
IF_EXISTS_SKIP      = "Skip it"
IF_EXISTS_RENAME    = "Keep both (add a number)"
IF_EXISTS_MODES     = (IF_EXISTS_OVERWRITE, IF_EXISTS_SKIP, IF_EXISTS_RENAME)

# ── Per-file result values ──────────────────────────────────────────────────
RES_PENDING    = "Pending"
RES_COPYING    = "Copying"
RES_COPIED     = "Copied"
RES_SKIPPED    = "Skipped - already there"
RES_MISSING    = "Missing in source"
RES_CANCELLED  = "Cancelled"
RES_FAILED     = "Failed"           # always followed by " - <reason>"

DONE_RESULTS = (RES_COPIED, RES_SKIPPED)

# ── Matching ────────────────────────────────────────────────────────────────
# A list line can be an exact relative path, or just a file name. When the
# name has no extension, or is not found as written, the tool can search the
# source folder (and its sub-folders) for a file with that stem.
MATCH_EXACT = "Exact name only"
MATCH_SMART = "Find by name (any extension / sub-folder)"
MATCH_MODES = (MATCH_EXACT, MATCH_SMART)

# ── Colour palette — CHARCOAL & RED scheme ──────────────────────────────────
# Every entry is (light, dark).
#
#   body text                     >= 4.5:1 against its surface
#   large / bold button text      >= 3.0:1
#   control boundaries            >= 3.0:1   (input border, progress fill,
#                                             nav indicator)
#
# Light column: the accent is a DEEP red so it reads on pale surfaces.
# Dark column: the accent is a BRIGHT coral so it reads on charcoal.
# The same key therefore flips lightness between modes — that is what keeps
# every label legible in both.
#
# Card outlines ("div") and the scrollbar sit below 3:1 on purpose: they
# separate two surfaces that serve the same purpose and carry no information
# of their own.
C = {
    # surfaces — charcoal in dark mode, warm paper-white in light
    "bg800": ("#F4F5F3", "#1A1E21"),      # window
    "side":  ("#E7E9E4", "#141719"),      # sidebar
    "bg700": ("#FFFFFF", "#22282C"),      # cards
    "bg900": ("#FAFAF8", "#15191C"),      # inputs, log, table
    "bg600": ("#DFE1DB", "#2A3035"),      # table heading
    "bg500": ("#CBCEC5", "#343C42"),
    "div":   ("#D2D5CC", "#333A40"),      # card outlines (decorative)
    # red accent
    "a600": ("#FBD5CE", "#7A1E10"),       # selection background
    "a500": ("#A62718", "#E94F37"),       # header rule
    "a400": ("#B32D1C", "#EF6F5A"),       # progress bar, checkbox
    "a300": ("#99220F", "#F08A74"),       # accent text / primary button
    "a200": ("#73180A", "#FAC0B5"),
    "acc":  ("#A62718", "#E94F37"),
    "on_acc": ("#FFFFFF", "#1A0A06"),     # text on an accent-filled button
    "sel_fg": ("#1A0A06", "#FFFFFF"),     # text on a selected table row
    "seg_sel": ("#F3B9AE", "#8C2414"),    # selected Light/Dark switch segment
    "seg_hover": ("#EFA294", "#A62E1B"),
    # neutral slate (warm grey)
    "sl700": ("#E2E4DE", "#2C3338"),      # hover background
    "sl600": ("#7D837A", "#717A82"),      # input borders, scrollbars (>=3:1)
    "sl500": ("#6E746B", "#656D74"),
    "sl400": ("#73796F", "#8A9199"),      # disabled text
    "sl300": ("#5B6158", "#A6ADB4"),
    "sl200": ("#474C44", "#C2C9CE"),      # secondary text
    "sl100": ("#2F342D", "#DEE3E7"),
    # text + status
    "white": ("#15191C", "#F6F7EB"),      # primary text
    "ok":    ("#1D7A46", "#5BBF7E"),
    "warn":  ("#8A5100", "#E8A838"),
    "err":   ("#B3261E", "#F2715C"),
    "warn_hover": ("#FAF1DE", "#332C18"),
    "err_hover":  ("#FCE9E7", "#3A1F1A"),
    "log_info": ("#3A4049", "#AEB8C2"), "log_ok": ("#1D7A46", "#5BBF7E"),
    "log_warn": ("#8A5100", "#E8A838"), "log_err": ("#B3261E", "#F2715C"),
}

# The header bar keeps one deep charcoal in both modes, so the product
# always looks like itself.
HDR = {"bg": "#14181B", "title": "#F6F7EB", "sub": "#B3BBC2",
       "count": "#EF6F5A"}

# Segoe UI / Consolas are hinted for Windows ClearType, so they stay sharp
# at small sizes (customtkinter's default Roboto does not).
FONT_UI   = "Segoe UI"
FONT_MONO = "Consolas"
