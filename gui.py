"""
File Copy Tool — GUI
====================
Charcoal & red interface built with customtkinter, with a real Light and
Dark mode (the choice is remembered). Two pages, switched from the left
sidebar:

  Dashboard    — pick the source folder, the destination and the list of
                 names, set the options, Start / Pause / Cancel, see the
                 summary tiles and the activity log.
  File Queue   — Copied / Total counter and a live table of every listed
                 file with what it matched, its size and its result.
"""

import datetime
import json
import os
import pathlib
import platform
import queue
import subprocess
import threading
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

import customtkinter as ctk

from constants import (
    APP_BRAND, APP_NAME, APP_SUBTITLE, APP_VERSION, C, FONT_MONO, FONT_UI, HDR,
    DONE_RESULTS, IF_EXISTS_MODES, IF_EXISTS_OVERWRITE,
    MATCH_MODES, MATCH_SMART, RES_CANCELLED, RES_COPIED, RES_COPYING,
    RES_MISSING, RES_PENDING, RES_SKIPPED,
    SRC_MODES, SRC_TXT, SRC_TYPED,
    default_dest_dir, default_list_file, settings_file,
)
from copy_engine import CopyWorker, Record, build_records, human_size, read_list_file


# ── Appearance ────────────────────────────────────────────────────────────────
ctk.set_default_color_theme("blue")

THEMES = ("Light", "Dark")
_SETTINGS_FILE = settings_file()


def load_mode() -> str:
    """Last-used appearance mode (Dark by default)."""
    try:
        mode = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("mode")
        return mode if mode in THEMES else "Dark"
    except Exception:
        return "Dark"


def save_mode(mode: str):
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps({"mode": mode}), encoding="utf-8")
    except Exception:
        pass


def pick(key: str) -> str:
    """Palette colour for the current mode — for plain tk / ttk widgets,
    which (unlike customtkinter ones) do not switch by themselves."""
    return C[key][1 if ctk.get_appearance_mode() == "Dark" else 0]


ctk.set_appearance_mode(load_mode())

PAGE_DASHBOARD = "Dashboard"
PAGE_QUEUE     = "File Queue"


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _open_path(path: str):
    if platform.system() == "Windows":
        os.startfile(path)                                   # noqa: S606
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _shorten(text: str, limit: int = 62) -> str:
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


# ── Small widget factories (keep the palette in one place) ───────────────────

def _font(size: int = 13, bold: bool = False, mono: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_MONO if mono else FONT_UI, size=size,
                       weight="bold" if bold else "normal")


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C["bg700"], border_width=1,
                        border_color=C["div"], corner_radius=8, **kw)


def _label(parent, text="", size=13, bold=False, color=None, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=_font(size, bold),
                        text_color=color or C["white"], **kw)


def _btn_primary(parent, text, command, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, font=_font(14, True),
        fg_color=C["a500"], hover_color=C["a400"], text_color=C["on_acc"],
        text_color_disabled=C["sl400"], corner_radius=7, **kw)


def _btn_outline(parent, text, command, color, hover, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, font=_font(13, True),
        fg_color="transparent", hover_color=hover, text_color=color,
        text_color_disabled=C["sl400"], border_width=1, border_color=color,
        corner_radius=7, **kw)


def _entry(parent, **kw) -> ctk.CTkEntry:
    return ctk.CTkEntry(parent, font=_font(13), fg_color=C["bg900"],
                        text_color=C["white"], border_color=C["sl600"],
                        border_width=1, placeholder_text_color=C["sl400"], **kw)


def _combo(parent, values, width=250) -> ctk.CTkComboBox:
    return ctk.CTkComboBox(
        parent, values=list(values), width=width, state="readonly",
        font=_font(13), dropdown_font=_font(13), fg_color=C["bg900"],
        text_color=C["white"], border_color=C["sl600"],
        button_color=C["sl600"], button_hover_color=C["a500"],
        dropdown_fg_color=C["bg800"], dropdown_text_color=C["white"],
        dropdown_hover_color=C["a600"])


class FileCopyToolApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__(fg_color=C["bg800"])

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self._fit_to_screen(1240, 760)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            icon = pathlib.Path(__file__).resolve().parent / "Assets" / "icon.ico"
            if icon.exists():
                self.iconbitmap(str(icon))
        except Exception:
            pass

        # ── Internal state ────────────────────────────────────────────────
        self._records: List[Record] = []
        self._worker: Optional[CopyWorker] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()       # SET = paused
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._is_running = False
        self._pages = {}
        self._nav = {}
        self._scale = 1.0

        self._build_ui()
        self._apply_native_theme()
        self._show_page(PAGE_DASHBOARD)

        start_list = default_list_file()
        if start_list:
            self._list_entry.insert(0, start_list)
            self._log(f"Found a list next to the app: {start_list}")
            self._load_list(auto=True)
        else:
            self._log("Pick a source folder, a destination and a list of names.")

        self._refresh_counts()
        self._poll_queue()

    # ==================================================================
    #  UI BUILD
    # ==================================================================

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header bar ───────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=HDR["bg"], corner_radius=0, height=62)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        _label(header, APP_NAME, size=19, bold=True, color=HDR["title"]).grid(
            row=0, column=0, sticky="w", padx=(22, 12), pady=(16, 16))
        _label(header, APP_SUBTITLE, size=13, color=HDR["sub"]).grid(
            row=0, column=1, sticky="w", pady=(19, 16))
        self._lbl_header_count = _label(header, "", size=14, bold=True,
                                        color=HDR["count"])
        self._lbl_header_count.grid(row=0, column=2, sticky="e", padx=22)

        ctk.CTkFrame(self, fg_color=C["a500"], corner_radius=0, height=2).grid(
            row=1, column=0, columnspan=2, sticky="ew")

        # ── Sidebar ──────────────────────────────────────────────────────
        side = ctk.CTkFrame(self, fg_color=C["side"], corner_radius=0, width=208)
        side.grid(row=2, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(1, weight=1)
        side.grid_rowconfigure(10, weight=1)

        _label(side, "NAVIGATION", size=11, bold=True, color=C["a300"]).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 8))

        for i, name in enumerate((PAGE_DASHBOARD, PAGE_QUEUE), start=1):
            bar = ctk.CTkFrame(side, fg_color="transparent", corner_radius=0,
                               width=3, height=40)
            bar.grid(row=i, column=0, sticky="ns")
            btn = ctk.CTkButton(
                side, text="   " + name, anchor="w", height=40, corner_radius=0,
                font=_font(13), fg_color="transparent",
                hover_color=C["sl700"], text_color=C["sl200"],
                command=lambda n=name: self._show_page(n))
            btn.grid(row=i, column=1, sticky="ew")
            self._nav[name] = (bar, btn)

        _label(side, "SHORTCUTS", size=11, bold=True, color=C["a300"]).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 6))
        for i, (text, fn) in enumerate((
                ("Open source folder", self._open_source),
                ("Open destination", self._open_dest),
                ("Clear everything", self._clear_all)), start=5):
            ctk.CTkButton(
                side, text="   " + text, anchor="w", height=34, corner_radius=0,
                font=_font(12), fg_color="transparent",
                hover_color=C["sl700"], text_color=C["sl200"], command=fn).grid(
                row=i, column=0, columnspan=2, sticky="ew", padx=(3, 0))

        _label(side, "APPEARANCE", size=11, bold=True, color=C["a300"]).grid(
            row=11, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 6))
        self._mode_switch = ctk.CTkSegmentedButton(
            side, values=list(THEMES), font=_font(12, True), height=30,
            fg_color=C["bg900"], unselected_color=C["bg900"],
            unselected_hover_color=C["sl700"], selected_color=C["seg_sel"],
            selected_hover_color=C["seg_hover"], text_color=C["white"],
            command=self._set_mode)
        self._mode_switch.set(ctk.get_appearance_mode())
        self._mode_switch.grid(row=12, column=0, columnspan=2, sticky="ew",
                               padx=16, pady=(0, 10))

        _label(side, APP_BRAND, size=11, color=C["sl300"]).grid(
            row=13, column=0, columnspan=2, sticky="w", padx=18)
        _label(side, f"Version {APP_VERSION}", size=12, color=C["sl300"]).grid(
            row=14, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))

        # ── Pages ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        body.grid(row=2, column=1, sticky="nsew", padx=16, pady=14)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # The dashboard is taller than a 768-high laptop screen once Windows
        # scaling is on, so it scrolls. The queue page is a plain frame — its
        # table does its own scrolling.
        for name, builder in ((PAGE_DASHBOARD, self._build_dashboard),
                              (PAGE_QUEUE, self._build_queue)):
            if name == PAGE_DASHBOARD:
                page = ctk.CTkScrollableFrame(
                    body, fg_color="transparent", corner_radius=0,
                    scrollbar_button_color=C["sl600"],
                    scrollbar_button_hover_color=C["a500"])
            else:
                page = ctk.CTkFrame(body, fg_color="transparent",
                                    corner_radius=0)
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self._pages[name] = page

    def _fit_to_screen(self, width: int, height: int):
        """Open centred, and never larger than the screen (small laptops)."""
        try:
            scale = float(self._get_window_scaling())
        except Exception:
            scale = 1.0
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width  = int(min(width,  screen_w / scale - 40))
        height = int(min(height, screen_h / scale - 100))    # taskbar + title bar
        x = max(0, int((screen_w - width * scale) / 2))
        y = max(0, int((screen_h - height * scale) / 2 - 30 * scale))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1040, width), min(620, height))

    def _show_page(self, name: str):
        for page_name, page in self._pages.items():
            bar, btn = self._nav[page_name]
            if page_name == name:
                page.grid()            # grid/grid_remove, not tkraise: a
                bar.configure(fg_color=C["acc"])   # scrollable frame ignores
                btn.configure(fg_color=C["sl700"], text_color=C["a200"],
                              font=_font(13, True))
            else:
                page.grid_remove()                 # a raise of its own
                bar.configure(fg_color="transparent")
                btn.configure(fg_color="transparent", text_color=C["sl200"],
                              font=_font(13))

    # ── Dashboard page ───────────────────────────────────────────────────

    def _build_dashboard(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        # 1. Paths + list source
        inp = _card(tab)
        inp.grid(row=0, column=0, sticky="ew")
        inp.grid_columnconfigure(1, weight=1)

        _label(inp, "Source Folder", bold=True).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self._src_entry = _entry(inp, placeholder_text="Folder the files are in now")
        self._src_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(12, 4))
        self._btn_src = _btn_outline(inp, "Browse ...", self._browse_source,
                                     C["a300"], C["sl700"], width=112)
        self._btn_src.grid(row=0, column=2, padx=16, pady=(12, 4))

        _label(inp, "Destination Folder", bold=True).grid(
            row=1, column=0, sticky="w", padx=16, pady=4)
        self._dst_entry = _entry(inp, placeholder_text="Folder to copy them into")
        self._dst_entry.insert(0, str(default_dest_dir()))
        self._dst_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        self._btn_dst = _btn_outline(inp, "Browse ...", self._browse_dest,
                                     C["a300"], C["sl700"], width=112)
        self._btn_dst.grid(row=1, column=2, padx=16, pady=4)

        _label(inp, "File Names", bold=True).grid(
            row=2, column=0, sticky="w", padx=16, pady=(10, 4))
        self._src_mode = ctk.CTkSegmentedButton(
            inp, values=list(SRC_MODES), font=_font(12, True), height=30,
            fg_color=C["bg900"], unselected_color=C["bg900"],
            unselected_hover_color=C["sl700"], selected_color=C["seg_sel"],
            selected_hover_color=C["seg_hover"], text_color=C["white"],
            command=self._switch_src_mode)
        self._src_mode.set(SRC_TXT)
        self._src_mode.grid(row=2, column=1, columnspan=2, sticky="w", padx=8,
                            pady=(10, 4))

        # Stacked input: a .txt path, or a typed list
        stack = ctk.CTkFrame(inp, fg_color="transparent")
        stack.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16,
                   pady=(2, 12))
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)

        self._page_txt = ctk.CTkFrame(stack, fg_color="transparent")
        self._page_txt.grid(row=0, column=0, sticky="ew")
        self._page_txt.grid_columnconfigure(0, weight=1)
        self._list_entry = _entry(self._page_txt,
                                  placeholder_text="Path to a .txt list of file names")
        self._list_entry.grid(row=0, column=0, sticky="ew")
        self._btn_list = _btn_outline(self._page_txt, "Browse ...",
                                      self._browse_list, C["a300"], C["sl700"],
                                      width=112)
        self._btn_list.grid(row=0, column=1, padx=(8, 0))

        self._page_typed = ctk.CTkFrame(stack, fg_color="transparent")
        self._page_typed.grid(row=0, column=0, sticky="nsew")
        self._page_typed.grid_columnconfigure(0, weight=1)
        self._typed_box = ctk.CTkTextbox(
            self._page_typed, height=84, font=_font(12, mono=True), wrap="none",
            fg_color=C["bg900"], text_color=C["white"], border_width=1,
            border_color=C["sl600"], corner_radius=7,
            scrollbar_button_color=C["sl600"],
            scrollbar_button_hover_color=C["a500"])
        self._typed_box.grid(row=0, column=0, sticky="ew")
        _label(self._page_typed, "one name per line", size=11,
               color=C["sl300"]).grid(row=1, column=0, sticky="w", pady=(3, 0))
        # The two inputs are different heights, so swap them in and out of the
        # grid rather than stacking them — a raised frame would not cover the
        # taller one.
        self._page_typed.grid_remove()

        # 2. Options
        opt = _card(tab)
        opt.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        opt.grid_columnconfigure(3, weight=1)

        _label(opt, "If it already exists", bold=True).grid(
            row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 10))
        self._combo_exists = _combo(opt, IF_EXISTS_MODES, width=210)
        self._combo_exists.set(IF_EXISTS_OVERWRITE)
        self._combo_exists.grid(row=0, column=1, sticky="w", pady=(12, 10))

        _label(opt, "Name matching", bold=True).grid(
            row=0, column=2, sticky="w", padx=(22, 8), pady=(12, 10))
        self._combo_match = _combo(opt, MATCH_MODES, width=300)
        self._combo_match.set(MATCH_SMART)
        self._combo_match.grid(row=0, column=3, sticky="w", pady=(12, 10))

        chk = dict(font=_font(13), text_color=C["sl100"], fg_color=C["a500"],
                   hover_color=C["a400"], border_color=C["sl400"],
                   checkmark_color=C["on_acc"], border_width=2,
                   checkbox_width=20, checkbox_height=20)
        self._chk_recursive = ctk.CTkCheckBox(
            opt, text="Search the source's sub-folders", **chk)
        self._chk_recursive.select()
        self._chk_recursive.grid(row=1, column=0, columnspan=2, sticky="w",
                                 padx=16, pady=(0, 12))
        self._chk_flatten = ctk.CTkCheckBox(
            opt, text="Copy everything flat into one folder", **chk)
        self._chk_flatten.grid(row=1, column=2, columnspan=2, sticky="w",
                               padx=(22, 0), pady=(0, 12))
        self._chk_open = ctk.CTkCheckBox(
            opt, text="Open the destination when finished", **chk)
        self._chk_open.grid(row=2, column=0, columnspan=4, sticky="w", padx=16,
                            pady=(0, 12))

        # 3. Action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(12, 6))

        self._btn_load = _btn_outline(
            btn_frame, "Load List", self._load_list, C["a300"], C["sl700"],
            width=130, height=38)
        self._btn_load.pack(side="left", padx=(0, 8))
        self._btn_start = _btn_primary(btn_frame, "Start Copy", self._start,
                                       width=150, height=38, state="disabled")
        self._btn_start.pack(side="left", padx=(0, 8))
        self._btn_pause = _btn_outline(
            btn_frame, "Pause", self._toggle_pause, C["warn"], C["warn_hover"],
            width=110, height=38, state="disabled")
        self._btn_pause.pack(side="left", padx=(0, 8))
        self._btn_cancel = _btn_outline(
            btn_frame, "Cancel", self._cancel, C["err"], C["err_hover"],
            width=110, height=38, state="disabled")
        self._btn_cancel.pack(side="left")

        # 4. Summary tiles
        tiles = ctk.CTkFrame(tab, fg_color="transparent")
        tiles.grid(row=3, column=0, sticky="ew", pady=6)
        self._tiles = {}
        for i, (key, title, colour) in enumerate([
            ("total",   "LISTED",  C["white"]),
            ("copied",  "COPIED",  C["ok"]),
            ("skipped", "SKIPPED", C["sl200"]),
            ("missing", "MISSING", C["warn"]),
            ("failed",  "FAILED",  C["err"]),
            ("pending", "PENDING", C["a300"]),
            ("size",    "DATA",    C["a300"]),
        ]):
            tiles.grid_columnconfigure(i, weight=1, uniform="tile")
            box = _card(tiles)
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            value = _label(box, "0", size=24, bold=True, color=colour)
            value.pack(pady=(6, 0))
            _label(box, title, size=11, bold=True, color=C["sl200"]).pack(
                pady=(0, 7))
            self._tiles[key] = value

        # 5. Progress bar
        prog = _card(tab)
        prog.grid(row=4, column=0, sticky="ew", pady=6)
        prog.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(prog, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        top.grid_columnconfigure(0, weight=1)
        self._lbl_progress = _label(top, "Copied 0 / 0", bold=True)
        self._lbl_progress.grid(row=0, column=0, sticky="w")
        self._lbl_current = _label(top, "", color=C["sl200"])
        self._lbl_current.grid(row=0, column=1, sticky="e")
        self._progress_bar = ctk.CTkProgressBar(
            prog, height=12, fg_color=C["bg900"], progress_color=C["a500"],
            border_width=1, border_color=C["sl700"])
        self._progress_bar.grid(row=1, column=0, sticky="ew", padx=16,
                                pady=(0, 14))
        self._progress_bar.set(0)

        # 6. Activity log
        log_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        log_hdr.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        _label(log_hdr, "ACTIVITY LOG", size=11, bold=True,
               color=C["a300"]).pack(side="left", padx=2)
        _btn_outline(log_hdr, "Clear", self._clear_log, C["sl200"], C["sl700"],
                     width=70, height=26).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            tab, font=_font(12, mono=True), state="disabled", wrap="word",
            height=132, fg_color=C["bg900"], text_color=C["log_info"],
            border_width=1, border_color=C["div"], corner_radius=7,
            scrollbar_button_color=C["sl600"],
            scrollbar_button_hover_color=C["a500"])
        self._log_box.grid(row=6, column=0, sticky="nsew", pady=(6, 8))

        # 7. Footer buttons
        foot = ctk.CTkFrame(tab, fg_color="transparent")
        foot.grid(row=7, column=0, sticky="ew")
        _btn_outline(foot, "Open Source Folder", self._open_source,
                     C["a300"], C["sl700"], width=170, height=32).pack(
                         side="left", padx=(0, 8))
        _btn_outline(foot, "Open Destination", self._open_dest,
                     C["a300"], C["sl700"], width=170, height=32).pack(
                         side="left", padx=(0, 8))
        _btn_outline(foot, "Save Report ...", self._save_report,
                     C["a300"], C["sl700"], width=150, height=32).pack(
                         side="left")

    # ── File Queue page ──────────────────────────────────────────────────

    def _build_queue(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top = _card(tab)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        self._lbl_big = _label(top, "0 / 0", size=36, bold=True, color=C["a300"])
        self._lbl_big.grid(row=0, column=0, rowspan=2, padx=(20, 10), pady=12)
        _label(top, "COPIED / LISTED", size=11, bold=True,
               color=C["sl200"]).grid(row=0, column=1, sticky="sw", padx=8,
                                      pady=(16, 0))
        self._lbl_queue_detail = _label(top, "", color=C["sl100"], anchor="w")
        self._lbl_queue_detail.grid(row=1, column=1, sticky="nw", padx=8,
                                    pady=(0, 12))
        self._queue_bar = ctk.CTkProgressBar(
            top, height=12, fg_color=C["bg900"], progress_color=C["a500"],
            border_width=1, border_color=C["sl700"])
        self._queue_bar.grid(row=2, column=0, columnspan=2, sticky="ew",
                             padx=20, pady=(0, 16))
        self._queue_bar.set(0)

        table = _card(tab)
        table.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)

        # ttk widgets are not scaled by customtkinter, so do it here — this
        # keeps the table text the same crisp size as the rest of the UI.
        try:
            scale = float(self._get_window_scaling())
        except Exception:
            scale = 1.0
        self._scale = scale

        ttk.Style(self).theme_use("clam")       # the only theme that takes colours

        cols = [("no", "#", 40, "center"),
                ("name", "Name in the list", 230, "w"),
                ("found", "Matched as", 140, "w"),
                ("size", "Size", 80, "e"),
                ("result", "Result", 170, "w"),
                ("dest", "Copied to", 200, "w")]
        self._tree = ttk.Treeview(table, columns=[c[0] for c in cols],
                                  show="headings", style="FC.Treeview")
        for key, title, width, anchor in cols:
            self._tree.heading(key, text=title, anchor=anchor)
            self._tree.column(key, width=int(width * scale), anchor=anchor,
                              stretch=(key in ("name", "dest")))

        scroll = ctk.CTkScrollbar(
            table, command=self._tree.yview, fg_color="transparent",
            button_color=C["sl600"], button_hover_color=C["a500"])
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scroll.grid(row=0, column=1, sticky="ns", padx=(2, 6), pady=10)

    # ── Light / Dark ─────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        ctk.set_appearance_mode(mode)       # recolours every customtkinter widget
        self._apply_native_theme()
        save_mode(mode)

    def _apply_native_theme(self):
        """Colour the plain tk / ttk parts (table, log tags) for the current mode."""
        scale = self._scale
        px = lambda n: -max(1, int(round(n * scale)))   # negative = pixels

        style = ttk.Style(self)
        style.configure(
            "FC.Treeview", rowheight=int(round(30 * scale)),
            font=(FONT_UI, px(13)), background=pick("bg900"),
            fieldbackground=pick("bg900"), foreground=pick("white"),
            borderwidth=0, relief="flat")
        style.configure(
            "FC.Treeview.Heading", font=(FONT_UI, px(13), "bold"),
            background=pick("bg600"), foreground=pick("a200"), relief="flat",
            borderwidth=0, padding=(6, int(round(7 * scale))))
        style.map("FC.Treeview",
                  background=[("selected", pick("a600"))],
                  foreground=[("selected", pick("sel_fg"))])
        style.map("FC.Treeview.Heading",
                  background=[("active", pick("bg500"))])
        style.layout("FC.Treeview",
                     [("Treeview.treearea", {"sticky": "nswe"})])   # no border

        self._tree.tag_configure("done",    foreground=pick("ok"))
        self._tree.tag_configure("skipped", foreground=pick("sl200"))
        self._tree.tag_configure("missing", foreground=pick("warn"))
        self._tree.tag_configure("failed",  foreground=pick("err"))
        self._tree.tag_configure("working", foreground=pick("warn"))
        self._tree.tag_configure("pending", foreground=pick("sl200"))

        text = self._log_box._textbox
        text.tag_configure("ok",   foreground=pick("log_ok"))
        text.tag_configure("err",  foreground=pick("log_err"))
        text.tag_configure("warn", foreground=pick("log_warn"))
        text.tag_configure("info", foreground=pick("log_info"))

    # ==================================================================
    #  TABLE + COUNTERS
    # ==================================================================

    @staticmethod
    def _row_tag(rec: Record) -> str:
        if rec.result == RES_COPIED:
            return "done"
        if rec.result == RES_SKIPPED:
            return "skipped"
        if rec.result == RES_MISSING:
            return "missing"
        if rec.result == RES_COPYING:
            return "working"
        if rec.result in (RES_PENDING, RES_CANCELLED):
            return "pending"
        return "failed"

    @staticmethod
    def _row_values(rec: Record):
        return (rec.idx, rec.name, rec.found_as, rec.size_text, rec.result,
                rec.dest_path)

    def _fill_table(self):
        self._tree.delete(*self._tree.get_children())
        for rec in self._records:
            self._tree.insert("", "end", iid=str(rec.idx),
                              values=self._row_values(rec),
                              tags=(self._row_tag(rec),))

    def _update_row(self, rec: Record):
        iid = str(rec.idx)
        if self._tree.exists(iid):
            self._tree.item(iid, values=self._row_values(rec),
                            tags=(self._row_tag(rec),))
            if rec.result == RES_COPYING:
                self._tree.see(iid)

    def _refresh_counts(self):
        total = len(self._records)
        copied = skipped = missing = failed = 0
        size = 0
        for rec in self._records:
            if rec.result == RES_COPIED:
                copied += 1
                size += rec.size
            elif rec.result == RES_SKIPPED:
                skipped += 1
            elif rec.result == RES_MISSING:
                missing += 1
            elif rec.result not in (RES_PENDING, RES_COPYING, RES_CANCELLED):
                failed += 1
        handled = copied + skipped + missing + failed
        pending = total - handled

        for key, value in (("total", f"{total:,}"), ("copied", f"{copied:,}"),
                           ("skipped", f"{skipped:,}"), ("missing", f"{missing:,}"),
                           ("failed", f"{failed:,}"), ("pending", f"{pending:,}"),
                           ("size", human_size(size) if size else "0 B")):
            self._tiles[key].configure(text=value)

        fraction = handled / total if total else 0
        self._progress_bar.set(fraction)
        self._queue_bar.set(fraction)
        self._lbl_progress.configure(text=f"Copied {copied:,} / {total:,}")
        self._lbl_big.configure(text=f"{copied:,} / {total:,}")
        self._lbl_header_count.configure(
            text=f"Copied {copied:,} / {total:,}" if total else "")

        bits = []
        if skipped:
            bits.append(f"{skipped:,} already there")
        if missing:
            bits.append(f"{missing:,} not found in the source")
        if failed:
            bits.append(f"{failed:,} failed")
        if size:
            bits.append(human_size(size) + " copied")
        self._lbl_queue_detail.configure(
            text="   ".join(bits) if bits else
            ("nothing loaded yet" if not total else "ready"))

    # ==================================================================
    #  INPUT
    # ==================================================================

    def _switch_src_mode(self, mode: str):
        if mode == SRC_TYPED:
            self._page_txt.grid_remove()
            self._page_typed.grid()
        else:
            self._page_typed.grid_remove()
            self._page_txt.grid()

    def _browse_source(self):
        folder = filedialog.askdirectory(title="Select the source folder")
        if folder:
            self._src_entry.delete(0, "end")
            self._src_entry.insert(0, os.path.normpath(folder))

    def _browse_dest(self):
        folder = filedialog.askdirectory(title="Select the destination folder")
        if folder:
            self._dst_entry.delete(0, "end")
            self._dst_entry.insert(0, os.path.normpath(folder))

    def _browse_list(self):
        path = filedialog.askopenfilename(
            title="Select the list of file names",
            filetypes=[("Text files", "*.txt *.csv *.log"), ("All files", "*.*")])
        if path:
            self._list_entry.delete(0, "end")
            self._list_entry.insert(0, os.path.normpath(path))
            self._load_list()

    def _names_from_input(self) -> Optional[List[str]]:
        """Read the list from whichever input the user is using."""
        if self._src_mode.get() == SRC_TYPED:
            from copy_engine import parse_lines
            names = parse_lines(self._typed_box.get("1.0", "end"))
            if not names:
                self._log("Type at least one file name, one per line.", "warn")
                return None
            return names

        path = self._list_entry.get().strip().strip('"')
        if not path:
            self._log("Pick a .txt list, or switch to \"Type the names\".", "warn")
            return None
        if not os.path.isfile(path):
            self._log(f"List file not found: {path}", "err")
            return None
        try:
            names = read_list_file(path)
        except Exception as exc:                        # noqa: BLE001
            self._log(f"Could not read the list: {exc}", "err")
            return None
        if not names:
            self._log(f"The list has no file names in it: {path}", "warn")
            return None
        return names

    def _load_list(self, auto: bool = False):
        source = self._src_entry.get().strip().strip('"')
        if source and not os.path.isdir(source):
            self._log(f"Source folder not found: {source}", "warn")

        names = self._names_from_input()
        if names is None:
            return

        self._records = build_records(names)
        self._fill_table()
        self._refresh_counts()
        self._btn_start.configure(
            state="normal" if not self._is_running else "disabled")
        self._log(f"Loaded {len(names):,} file name(s).", "ok")
        if not auto:
            self._show_page(PAGE_QUEUE)

    # ==================================================================
    #  RUN
    # ==================================================================

    def _start(self):
        if self._is_running:
            return

        source = self._src_entry.get().strip().strip('"')
        dest   = self._dst_entry.get().strip().strip('"')

        if not source or not os.path.isdir(source):
            messagebox.showwarning(APP_NAME, "Pick a source folder that exists.")
            return
        if not dest:
            messagebox.showwarning(APP_NAME, "Pick a destination folder.")
            return
        if os.path.normcase(os.path.abspath(source)) == \
                os.path.normcase(os.path.abspath(dest)):
            messagebox.showwarning(
                APP_NAME,
                "The source and the destination are the same folder.\n"
                "Pick a different destination.")
            return

        # Re-read the list, so edits since the last Load are picked up.
        names = self._names_from_input()
        if names is None:
            return
        self._records = build_records(names)      # fresh rows for every run
        self._fill_table()
        self._refresh_counts()

        self._stop_event.clear()
        self._pause_event.clear()
        self._is_running = True
        self._set_running_ui(True)
        self._log("")
        self._log(f"Starting - {len(self._records):,} file(s) to copy.", "ok")

        self._worker = CopyWorker(
            records=self._records,
            source_dir=pathlib.Path(source),
            dest_dir=pathlib.Path(dest),
            out_q=self._q,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            if_exists=self._combo_exists.get(),
            match_mode=self._combo_match.get(),
            recursive=bool(self._chk_recursive.get()),
            flatten=bool(self._chk_flatten.get()),
        )
        self._worker_thread = threading.Thread(target=self._worker.run,
                                               daemon=True)
        self._worker_thread.start()
        self._show_page(PAGE_QUEUE)

    def _toggle_pause(self):
        if not self._is_running:
            return
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._btn_pause.configure(text="Pause")
            self._log("Resumed.", "info")
        else:
            self._pause_event.set()
            self._btn_pause.configure(text="Resume")
            self._log("Paused.", "warn")

    def _cancel(self):
        if not self._is_running:
            return
        self._stop_event.set()
        self._pause_event.clear()
        self._btn_pause.configure(text="Pause")
        self._log("Cancelling after the current file ...", "warn")

    def _set_running_ui(self, running: bool):
        state = "disabled" if running else "normal"
        for widget in (self._btn_start, self._btn_load, self._btn_src,
                       self._btn_dst, self._btn_list):
            widget.configure(state=state)
        self._btn_pause.configure(state="normal" if running else "disabled",
                                  text="Pause")
        self._btn_cancel.configure(state="normal" if running else "disabled")

    def _on_done(self):
        self._is_running = False
        self._set_running_ui(False)
        self._refresh_counts()
        copied = sum(1 for r in self._records if r.result == RES_COPIED)
        self._lbl_current.configure(text="")
        if self._stop_event.is_set():
            self._log(f"Cancelled - {copied:,} file(s) had already been copied.",
                      "warn")
        else:
            self._log(f"Finished - {copied:,} file(s) copied.", "ok")
        if copied and self._chk_open.get():
            self._open_dest()

    # ==================================================================
    #  FOLDERS, REPORT, LOG
    # ==================================================================

    def _open_source(self):
        self._open_folder(self._src_entry.get().strip().strip('"'), create=False)

    def _open_dest(self):
        self._open_folder(self._dst_entry.get().strip().strip('"'), create=True)

    def _open_folder(self, folder: str, create: bool):
        if not folder:
            self._log("No folder set yet.", "warn")
            return
        if not os.path.isdir(folder):
            if not create:
                self._log(f"Folder not found: {folder}", "warn")
                return
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as exc:                    # noqa: BLE001
                self._log(f"Could not create {folder}: {exc}", "err")
                return
        try:
            _open_path(folder)
        except Exception as exc:                        # noqa: BLE001
            self._log(f"Could not open the folder: {exc}", "err")

    def _save_report(self):
        if not self._records:
            self._log("Nothing to report yet - load a list first.", "warn")
            return
        default = f"FileCopy_Report_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.csv"
        path = filedialog.asksaveasfilename(
            title="Save the run report", defaultextension=".csv",
            initialfile=default, filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["#", "Name in list", "Matched as", "Bytes",
                                 "Result", "Source path", "Copied to", "Note"])
                for rec in self._records:
                    writer.writerow([rec.idx, rec.name, rec.found_as, rec.size,
                                     rec.result, rec.source_path, rec.dest_path,
                                     rec.note])
            self._log(f"Report saved: {path}", "ok")
        except Exception as exc:                        # noqa: BLE001
            self._log(f"Could not save the report: {exc}", "err")

    def _log(self, text: str, level: str = "info"):
        self._append_log(text, level)

    def _append_log(self, text: str, level: str = "info"):
        self._log_box.configure(state="normal")
        line = f"[{_now()}]  {text}\n" if text else "\n"
        self._log_box.insert("end", line, level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _clear_all(self):
        if self._is_running:
            self._log("A run is in progress - cancel it first.", "warn")
            return
        self._records = []
        self._tree.delete(*self._tree.get_children())
        self._src_entry.delete(0, "end")
        self._list_entry.delete(0, "end")
        self._typed_box.delete("1.0", "end")
        self._dst_entry.delete(0, "end")
        self._dst_entry.insert(0, str(default_dest_dir()))
        self._btn_start.configure(state="disabled")
        self._lbl_current.configure(text="")
        self._refresh_counts()
        self._clear_log()
        self._log("Cleared.", "info")

    def _on_close(self):
        if self._is_running:
            if not messagebox.askyesno(APP_NAME,
                                       "A copy is in progress. Stop and quit?"):
                return
            self._stop_event.set()
            self._pause_event.clear()
        self.destroy()

    # ==================================================================
    #  QUEUE POLLING  (runs on the GUI / main thread every 120 ms)
    # ==================================================================

    def _poll_queue(self):
        changed = False
        for _ in range(500):
            try:
                msg = self._q.get_nowait()
            except queue.Empty:
                break
            kind = msg[0]
            if kind == "log":
                self._append_log(msg[2], msg[1])
            elif kind == "record":
                self._update_row(msg[1])
                changed = True
            elif kind == "current":
                self._lbl_current.configure(text=_shorten(msg[1], 52))
            elif kind == "done":
                self._on_done()
                changed = False          # _on_done refreshes already
        if changed:
            self._refresh_counts()
        self.after(120, self._poll_queue)
