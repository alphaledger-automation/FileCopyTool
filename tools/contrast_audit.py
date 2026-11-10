"""
Contrast audit for the File Copy Tool palette
=============================================
Measures the exact foreground / background pairs the GUI actually draws,
in BOTH modes, against WCAG 2.1 AA:

    body text                                  >= 4.5:1
    large / bold button text, and boundaries   >= 3.0:1
      that identify a control (input border,
      progress fill, nav indicator)

Run it after changing any colour in constants.py:

    python tools\\contrast_audit.py

Card outlines ("div") and the scrollbar are reported as notes, not
failures: they separate two surfaces that serve the same purpose and
carry no information of their own, so forcing them to 3:1 would turn
every hairline into a hard outline.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from constants import C, HDR            # noqa: E402


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")

    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# (description, foreground key, background key, required ratio)
PAIRS = [
    ("body text on window",        "white",    "bg800",   4.5),
    ("body text on card",          "white",    "bg700",   4.5),
    ("body text on input / table", "white",    "bg900",   4.5),
    ("body text on sidebar",       "white",    "side",    4.5),
    ("secondary text on card",     "sl200",    "bg700",   4.5),
    ("secondary text on sidebar",  "sl200",    "side",    4.5),
    ("brand / version text",       "sl300",    "side",    4.5),
    ("section heading on card",    "a300",     "bg700",   4.5),
    ("section heading on sidebar", "a300",     "side",    4.5),
    ("table heading text",         "a200",     "bg600",   4.5),
    ("success text on card",       "ok",       "bg700",   4.5),
    ("warning text on card",       "warn",     "bg700",   4.5),
    ("error text on card",         "err",      "bg700",   4.5),
    ("log - info",                 "log_info", "bg900",   4.5),
    ("log - copied",               "log_ok",   "bg900",   4.5),
    ("log - warning",              "log_warn", "bg900",   4.5),
    ("log - error",                "log_err",  "bg900",   4.5),
    ("selected table row text",    "sel_fg",   "a600",    4.5),
    ("theme switch - selected",    "white",    "seg_sel", 4.5),
    ("primary button text",        "on_acc",   "a500",    3.0),
    ("progress fill on its track", "a500",     "bg900",   3.0),
    ("input border on card",       "sl600",    "bg700",   3.0),
    ("input border on input",      "sl600",    "bg900",   3.0),
    ("disabled button text",       "sl400",    "bg700",   3.0),
    ("nav indicator on sidebar",   "acc",      "side",    3.0),
]

NOTES = [
    ("card outline (decorative)",  "div",      "bg700"),
    ("card outline on window",     "div",      "bg800"),
]

HEADER_PAIRS = [
    ("header title",    "title", 4.5),
    ("header subtitle", "sub",   4.5),
    ("header counter",  "count", 4.5),
]


def main() -> int:
    failures = []
    print("File Copy Tool - palette contrast audit")
    print("=" * 62)

    for mode_index, mode in enumerate(("Light", "Dark")):
        print(f"\n{mode} mode")
        print("-" * 62)
        for label, fg, bg, need in PAIRS:
            value = ratio(C[fg][mode_index], C[bg][mode_index])
            ok = value >= need
            if not ok:
                failures.append((mode, label, value, need))
            print(f"  {'PASS' if ok else 'FAIL'}  {label:<28} "
                  f"{value:5.2f}  (need {need})")
        for label, fg, bg in NOTES:
            value = ratio(C[fg][mode_index], C[bg][mode_index])
            print(f"  note  {label:<28} {value:5.2f}  (decorative)")

    print("\nHeader bar (one colour in both modes)")
    print("-" * 62)
    for label, key, need in HEADER_PAIRS:
        value = ratio(HDR[key], HDR["bg"])
        ok = value >= need
        if not ok:
            failures.append(("Header", label, value, need))
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<28} "
              f"{value:5.2f}  (need {need})")

    print("\n" + "=" * 62)
    if failures:
        print(f"{len(failures)} pair(s) below the target:")
        for mode, label, value, need in failures:
            print(f"  {mode:<6} {label:<28} {value:5.2f} < {need}")
        return 1
    print("All measured pairs meet WCAG 2.1 AA in both modes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
