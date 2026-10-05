#!/usr/bin/env python3
"""
Elements by Remedy - Photo Resizer
----------------------------------
Crops and resizes product photos to a chosen size (default 1087 x 1087 px)
with automatic subject centering and manual arrow-key adjustment.

Requires:  pip install pillow numpy
Run:       python -m pip install pillow numpy   (then)   python photo_resizer.py
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageTk

# ----------------------------------------------------------------- settings
BRAND = "ELEMENTS BY REMEDY"
APP_NAME = "Photo Resizer"
DEFAULT_SIZE = (1087, 1087)
MIN_DIM, MAX_DIM = 16, 20000
EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
DEFAULT_THRESHOLD = 30      # how different from the background a pixel must be
CENTER_MODE = "bbox"        # "bbox" = bounding box, "mass" = center of mass
MAX_ZOOM = 4.0
PREVIEW_BOX = 520           # preview area (px); image is fitted inside it
RESAMPLE = Image.Resampling.LANCZOS

# ------------------------------------------------------------------ palette
WHITE = "#FFFFFF"
INK = "#111111"
GRAY = "#6B665F"
MUTED = "#A29C93"
LINE = "#E7E2DA"
STAGE = "#F3EFE9"           # warm linen behind the photo
TRACK = "#EAE5DD"
ACCENT = "#8C6B4A"
WARN = "#B4690E"
OK = "#2F7D4F"


# ------------------------------------------------------------ UI scaling
SCALE = 1.0     # UI scale factor: 1.0 = 96 dpi, 1.5 = 150% display scaling, ...


def px(n):
    """Scale a pixel measurement for the current display."""
    return max(1, round(n * SCALE))


def init_scaling(root):
    """Work out the display scale. (macOS handles scaling itself.)"""
    global SCALE
    if sys.platform == "darwin":
        SCALE = 1.0
    else:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96)


def enable_hidpi():
    """Tell Windows this app draws itself at full resolution, so it isn't
    blown up as a blurry bitmap. Must run before the Tk window is created."""
    if sys.platform.startswith("win"):
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# ------------------------------------------------------------- core logic
def load_image(path):
    """Open an image upright, as RGB, and return (image, icc_profile)."""
    im = Image.open(path)
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    else:
        im = im.convert("RGB")
    return im, icc


def make_small(im):
    """Small int16 array used for fast subject detection."""
    s = im.copy()
    s.thumbnail((400, 400))
    return np.asarray(s).astype(np.int16)


class Detection(NamedTuple):
    cx: float            # subject center, full-resolution pixels
    cy: float
    mask: np.ndarray     # pixels counted as product (thumbnail resolution)
    shadow: np.ndarray   # pixels ignored as shadow
    found: bool


def _despeckle(mask):
    """Drop isolated noise pixels (keep pixels with >= 3 set neighbours)."""
    h, w = mask.shape
    p = np.pad(mask, 1).astype(np.uint8)
    n = sum(p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))
    return mask & (n >= 3)


def detect_subject(small, full_w, full_h, thresh=DEFAULT_THRESHOLD,
                   ignore_shadows=True, mode=CENTER_MODE):
    """Find the product by how much it differs from the background.

    Background colour is sampled from the image border. With ignore_shadows,
    pixels that are just a darker, same-coloured version of a light backdrop
    (what a soft shadow looks like) are not counted.
    """
    h, w = small.shape[:2]
    border = np.concatenate([small[0], small[-1], small[:, 0], small[:, -1]])
    bg = np.median(border, axis=0)
    fg = np.abs(small - bg).max(axis=2) > thresh

    shadow = np.zeros_like(fg)
    bg_lum = float(bg.mean())
    if ignore_shadows and bg_lum > 100:            # only for light backdrops
        lum = np.maximum(small.mean(axis=2), 1.0)
        k = lum / bg_lum
        chroma_dev = np.abs(small / lum[..., None] - bg / bg_lum).max(axis=2)
        shadow = fg & (k > 0.5) & (k < 1.0) & (chroma_dev < 0.06)

    mask = _despeckle(fg & ~shadow)
    cols = np.where(mask.sum(axis=0) >= 2)[0]
    rows = np.where(mask.sum(axis=1) >= 2)[0]
    if len(cols) == 0 or len(rows) == 0 or not (0.005 < mask.mean() < 0.95):
        return Detection(full_w / 2, full_h / 2, mask, shadow, False)

    if mode == "mass":
        ys, xs = np.nonzero(mask)
        cx, cy = xs.mean() + 0.5, ys.mean() + 0.5
    else:
        cx, cy = (cols[0] + cols[-1] + 1) / 2, (rows[0] + rows[-1] + 1) / 2
    return Detection(cx * full_w / w, cy * full_h / h, mask, shadow, True)


def find_subject_center(im, ignore_shadows=True):
    d = detect_subject(make_small(im), im.width, im.height,
                       ignore_shadows=ignore_shadows)
    return d.cx, d.cy


def crop_box(img_w, img_h, cx, cy, zoom, tw, th):
    """Return ((l, t, r, b), clamped_cx, clamped_cy) for the target aspect."""
    ar = tw / th
    if img_w / img_h > ar:
        base_h, base_w = img_h, img_h * ar
    else:
        base_w, base_h = img_w, img_w / ar
    cw, ch = base_w / zoom, base_h / zoom
    cx = min(max(cx, cw / 2), img_w - cw / 2)
    cy = min(max(cy, ch / 2), img_h - ch / 2)
    return (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2), cx, cy


def export_image(im, icc, st, dest, fmt, tw, th):
    box, _, _ = crop_box(im.width, im.height, st["cx"], st["cy"], st["zoom"], tw, th)
    out = im.resize((tw, th), RESAMPLE, box=box)
    dest = Path(dest)
    if fmt == "PNG":
        out.save(dest.with_suffix(".png"), "PNG", icc_profile=icc)
    else:
        out.save(dest.with_suffix(".jpg"), "JPEG", quality=95,
                 subsampling=0, optimize=True, icc_profile=icc)


# ------------------------------------------------------- custom UI widgets
# Native Tk buttons look different on every OS (and ignore colours on macOS),
# so the controls below are drawn by hand with anti-aliased rounded shapes.
_cache = {}


def rr_photo(w, h, fill, outline=None, radius=10):
    """Anti-aliased rounded rectangle as a Tk image (supersampled via PIL)."""
    w, h = max(int(w), 4), max(int(h), 4)
    key = ("rr", w, h, fill, outline, radius)
    if key not in _cache:
        s = 4
        big = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        r = min(px(radius), h // 2) * s
        b = max(1, round(SCALE)) * s
        if outline:
            d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], r, fill=outline)
            d.rounded_rectangle([b, b, w * s - 1 - b, h * s - 1 - b],
                                max(r - b, 0), fill=fill)
        else:
            d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], r, fill=fill)
        _cache[key] = ImageTk.PhotoImage(big.resize((w, h), RESAMPLE))
    return _cache[key]


def switch_photo(on):
    key = ("sw", on)
    if key not in _cache:
        s, w, h = 4, px(42), px(26)
        big = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], h * s // 2,
                            fill=INK if on else "#D6D0C7")
        pad = px(3) * s
        kd = h * s - 2 * pad
        x0 = (w * s - pad - kd) if on else pad
        d.ellipse([x0, pad, x0 + kd, pad + kd], fill=WHITE)
        _cache[key] = ImageTk.PhotoImage(big.resize((w, h), RESAMPLE))
    return _cache[key]


class Btn(tk.Canvas):
    STYLES = {
        "primary":   dict(fill=INK, hover="#333333", fg=WHITE, outline=None),
        "secondary": dict(fill=WHITE, hover="#F5F2EC", fg=INK, outline="#CFC9C0"),
        "quiet":     dict(fill=TRACK, hover="#E0DAD0", fg=INK, outline=None),
    }

    def __init__(self, parent, text, command, style="secondary", height=40,
                 width=10, font=None, bg=WHITE):
        super().__init__(parent, width=px(width), height=px(height), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.font = text, command, font
        self.style = self.STYLES[style]
        self.hover = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _set_hover(self, v):
        self.hover = v
        self._draw()

    def _release(self, e):
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.command()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8:
            return
        st = self.style
        self.delete("all")
        self._img = rr_photo(w, h, st["hover"] if self.hover else st["fill"],
                             st["outline"], radius=10)
        self.create_image(0, 0, anchor="nw", image=self._img)
        self.create_text(w / 2, h / 2, text=self.text, fill=st["fg"], font=self.font)


class Toggle(tk.Canvas):
    """Label on the left, iOS-style switch on the right."""

    def __init__(self, parent, text, var, command=None, font=None, bg=WHITE):
        super().__init__(parent, width=10, height=px(31), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.var, self.command, self.font = text, var, command, font
        var.trace_add("write", lambda *a: self._draw())
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, e):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _draw(self):
        w = self.winfo_width()
        if w < 8:
            return
        self.delete("all")
        mid = self.winfo_height() / 2
        self.create_text(0, mid, text=self.text, anchor="w", font=self.font, fill=INK)
        self._img = switch_photo(bool(self.var.get()))
        self.create_image(w, mid, anchor="e", image=self._img)


class Segmented(tk.Canvas):
    """Pill-shaped segmented control bound to a StringVar."""

    def __init__(self, parent, options, var, font=None, height=38, bg=WHITE):
        super().__init__(parent, width=10, height=px(height), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.pad = px(4)
        self.options, self.var, self.font = options, var, font
        var.trace_add("write", lambda *a: self._draw())
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonRelease-1>", self._click)

    def _seg_w(self):
        return (self.winfo_width() - 2 * self.pad) / len(self.options)

    def _click(self, e):
        i = int((e.x - self.pad) // max(self._seg_w(), 1))
        self.var.set(self.options[min(max(i, 0), len(self.options) - 1)])

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20:
            return
        self.delete("all")
        self._track = rr_photo(w, h, TRACK, radius=11)
        self.create_image(0, 0, anchor="nw", image=self._track)
        sw = self._seg_w()
        self._pills = []
        for i, opt in enumerate(self.options):
            x = self.pad + i * sw
            sel = opt == self.var.get()
            if sel:
                pill = rr_photo(sw, h - 2 * self.pad, INK, radius=8)
                self._pills.append(pill)
                self.create_image(x, self.pad, anchor="nw", image=pill)
            self.create_text(x + sw / 2, h / 2, text=opt, font=self.font,
                             fill=WHITE if sel else GRAY)


class Progress(tk.Canvas):
    def __init__(self, parent, bg):
        super().__init__(parent, width=10, height=px(3), bg=bg, highlightthickness=0, bd=0)
        self.frac = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, frac):
        self.frac = frac
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        self.create_rectangle(0, 0, w, h, fill="#DDD6CC", width=0)
        self.create_rectangle(0, 0, w * self.frac, h, fill=INK, width=0)


def short_path(p):
    parts = Path(p).parts
    s = ("…/" + "/".join(parts[-2:])) if len(parts) > 2 else str(p)
    return s if len(s) <= 28 else "…" + s[-27:]


# --------------------------------------------------------------------- GUI
class App:
    def __init__(self, root):
        self.root = root
        init_scaling(root)
        logical_h = root.winfo_screenheight() / SCALE
        self.box = px(min(PREVIEW_BOX, max(340, int(logical_h - 90 - 200))))
        root.title(f"{APP_NAME} — Elements by Remedy")
        root.configure(bg=WHITE)
        root.resizable(False, False)
        self._init_fonts()

        self.files, self.idx = [], 0
        self.states, self.saved = {}, set()
        self.img = self.icc = self.photo = self.small = self.det = None
        self.tw, self.th = DEFAULT_SIZE
        self.in_dir = self.out_dir = None

        self.fmt = tk.StringVar(value="JPEG")
        self.w_var = tk.StringVar(value=str(self.tw))
        self.h_var = tk.StringVar(value=str(self.th))
        self.auto_on_load = tk.BooleanVar(value=True)
        self.ignore_shadows = tk.BooleanVar(value=True)
        self.guides = tk.BooleanVar(value=True)
        self.show_mask = tk.BooleanVar(value=False)

        self._build_ui()
        self._bind_keys()
        root.update_idletasks()
        avail = root.winfo_screenheight() - px(70)       # title bar + taskbar
        for hint in (self.hint_keys, self.hint_overlay):
            if root.winfo_reqheight() > avail:
                hint.pack_forget()
                root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
        y = max((root.winfo_screenheight() - root.winfo_reqheight()) // 3, 0)
        root.geometry(f"+{x}+{y}")

    def _init_fonts(self):
        fams = set(tkfont.families())
        fam = next((f for f in ("SF Pro Text", "Helvetica Neue", "Segoe UI",
                                "Inter", "Helvetica", "Arial") if f in fams), "Arial")
        k = 1.3 if sys.platform == "darwin" else 1.0   # Tk sizes run small on macOS

        def mk(size, weight="normal"):
            return tkfont.Font(family=fam, size=round(size * k), weight=weight)

        self.f_body, self.f_small = mk(10), mk(9)
        self.f_label, self.f_head = mk(8, "bold"), mk(13, "bold")
        self.f_title, self.f_btn = mk(20, "bold"), mk(10, "bold")

    # ---- layout
    def _label(self, parent, text, font, fg=INK, bg=WHITE, **kw):
        return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)

    def _section(self, parent, text):
        self._label(parent, text.upper(), self.f_label, MUTED,
                    anchor="w").pack(fill="x", pady=(px(15), px(6)))

    def _build_ui(self):
        r = self.root

        # ---------- left: photo stage
        left = tk.Frame(r, bg=STAGE)
        left.pack(side="left", fill="both")

        top = tk.Frame(left, bg=STAGE)
        top.pack(fill="x", padx=px(28), pady=(px(22), px(0)))
        self.title_lbl = self._label(top, "No image loaded", self.f_head, INK, STAGE,
                                     anchor="w")
        self.title_lbl.pack(fill="x")
        self.meta = tk.Frame(top, bg=STAGE)
        self.meta.pack(fill="x", pady=(px(2), px(10)))
        self.progress = Progress(top, STAGE)
        self.progress.pack(fill="x")

        bottom = tk.Frame(left, bg=STAGE)
        bottom.pack(side="bottom", fill="x", padx=px(28), pady=(px(0), px(22)))

        self.canvas = tk.Canvas(left, width=self.box, height=self.box,
                                bg=STAGE, highlightthickness=0, bd=0)
        self.canvas.pack(padx=px(28), pady=px(14), expand=True)
        self.canvas_text = self.canvas.create_text(
            self.box / 2, self.box / 2, fill=MUTED, font=self.f_body,
            text="Choose an input folder to begin")
        self.canvas_img = self.canvas.create_image(
            self.box / 2, self.box / 2, anchor="center")

        Btn(bottom, "‹   Back", self.prev, "secondary", 38, 104,
            self.f_btn, STAGE).pack(side="left")
        Btn(bottom, "Skip   ›", self.next, "secondary", 38, 104,
            self.f_btn, STAGE).pack(side="right")
        self.status = self._label(bottom, "", self.f_small, GRAY, STAGE)
        self.status.pack(side="left", expand=True)

        # ---------- divider
        tk.Frame(r, width=1, bg=LINE).pack(side="left", fill="y")

        # ---------- right: controls
        side = tk.Frame(r, bg=WHITE)
        side.pack(side="left", fill="both")
        inner = tk.Frame(side, bg=WHITE)
        inner.pack(fill="both", expand=True, padx=px(26), pady=(px(18), px(16)))
        tk.Frame(inner, width=px(290), height=1, bg=WHITE).pack()

        self._label(inner, BRAND, self.f_label, ACCENT, anchor="w").pack(fill="x")
        self._label(inner, APP_NAME, self.f_title, INK, anchor="w").pack(fill="x")

        # folders
        self._section(inner, "Folders")
        self.in_lbl = self._folder_row(inner, "Input", self.pick_input)
        self.out_lbl = self._folder_row(inner, "Output", self.pick_output)

        # output size + format
        self._section(inner, "Output")
        row = tk.Frame(inner, bg=WHITE)
        row.pack(fill="x")
        vcmd = (self.root.register(lambda s: s.isdigit() or s == ""), "%P")
        self.w_entry = self._size_entry(row, self.w_var, vcmd)
        self._label(row, "×", self.f_body, GRAY).pack(side="left", padx=px(8))
        self.h_entry = self._size_entry(row, self.h_var, vcmd)
        self._label(row, "px", self.f_small, MUTED).pack(side="left", padx=(px(8), px(0)))
        Segmented(inner, ["JPEG", "PNG"], self.fmt, self.f_btn).pack(fill="x", pady=(px(10), px(0)))

        # options
        self._section(inner, "Options")
        Toggle(inner, "Auto-center when opening", self.auto_on_load,
               font=self.f_body).pack(fill="x")
        Toggle(inner, "Ignore shadows", self.ignore_shadows,
               self.on_detection_change, self.f_body).pack(fill="x")
        Toggle(inner, "Show center guides", self.guides, self.render,
               self.f_body).pack(fill="x")
        Toggle(inner, "Show subject overlay", self.show_mask, self.render,
               self.f_body).pack(fill="x")
        self.hint_overlay = self._label(
            inner, "Overlay: red = subject, blue = ignored shadow",
            self.f_small, MUTED, anchor="w")
        self.hint_overlay.pack(fill="x", pady=(px(2), px(0)))

        # actions
        tk.Frame(inner, height=px(14), bg=WHITE).pack()
        ar = tk.Frame(inner, bg=WHITE)
        ar.pack(fill="x")
        Btn(ar, "Auto-center", self.auto_center, "quiet", 38, 10,
            self.f_btn).pack(side="left", expand=True, fill="x", padx=(px(0), px(5)))
        Btn(ar, "Reset", self.reset, "quiet", 38, 10,
            self.f_btn).pack(side="left", expand=True, fill="x", padx=(px(5), px(0)))
        Btn(inner, "Save & Next", self.save_and_next, "primary", 46, 10,
            self.f_btn).pack(fill="x", pady=(px(10), px(0)))
        Btn(inner, "Save all remaining", self.save_all, "secondary", 38, 10,
            self.f_btn).pack(fill="x", pady=(px(8), px(0)))

        self.hint_keys = self._label(
            inner,
            "← ↑ ↓ →  move     ⇧  faster     + −  zoom\n"
            "A  auto-center     R  reset     ⏎  save & next\n"
            "Space  skip     ⌫  back",
            self.f_small, MUTED, justify="left", anchor="w")
        self.hint_keys.pack(fill="x", pady=(px(12), px(0)))

    def _folder_row(self, parent, name, cmd):
        row = tk.Frame(parent, bg=WHITE)
        row.pack(fill="x", pady=px(3))
        self._label(row, name, self.f_small, GRAY, width=6, anchor="w").pack(side="left")
        lbl = self._label(row, "Not selected", self.f_body, MUTED, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        Btn(row, "Choose", cmd, "quiet", 30, 76, self.f_small).pack(side="right")
        return lbl

    def _size_entry(self, parent, var, vcmd):
        e = tk.Entry(parent, textvariable=var, width=6, justify="center",
                     font=self.f_body, relief="flat", bg=WHITE, fg=INK,
                     insertbackground=INK, highlightthickness=px(1),
                     highlightbackground="#CFC9C0", highlightcolor=INK,
                     validate="key", validatecommand=vcmd)
        e.pack(side="left", ipady=px(7))
        e.bind("<Return>", lambda ev: (self.apply_size(), self.root.focus_set(), "break")[-1])
        e.bind("<FocusOut>", lambda ev: self.apply_size(), add="+")
        return e

    def _bind_keys(self):
        r = self.root

        def guard(fn):
            def handler(e):
                try:
                    if isinstance(r.focus_get(), tk.Entry):
                        return           # typing in a size box: ignore shortcuts
                except KeyError:
                    pass
                fn()
            return handler

        for key, dx, dy in [("Up", 0, -1), ("Down", 0, 1),
                            ("Left", -1, 0), ("Right", 1, 0)]:
            r.bind(f"<{key}>", guard(lambda dx=dx, dy=dy: self.nudge(dx, dy, 10)))
            r.bind(f"<Shift-{key}>", guard(lambda dx=dx, dy=dy: self.nudge(dx, dy, 50)))
        for k in ("plus", "equal", "KP_Add"):
            r.bind(f"<{k}>", guard(lambda: self.zoom(1.05)))
        for k in ("minus", "KP_Subtract"):
            r.bind(f"<{k}>", guard(lambda: self.zoom(1 / 1.05)))
        r.bind("<a>", guard(self.auto_center))
        r.bind("<r>", guard(self.reset))
        r.bind("<Return>", guard(self.save_and_next))
        r.bind("<space>", guard(self.next))
        r.bind("<BackSpace>", guard(self.prev))
        # Clicking elsewhere drops focus from the size boxes.
        r.bind_all("<ButtonRelease-1>",
                   lambda e: None if isinstance(e.widget, tk.Entry) else r.focus_set(),
                   add="+")

    # ---- size
    def apply_size(self):
        try:
            w, h = int(self.w_var.get()), int(self.h_var.get())
            if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM):
                raise ValueError
        except ValueError:                       # invalid: put the old values back
            self.w_var.set(str(self.tw))
            self.h_var.set(str(self.th))
            return
        if (w, h) != (self.tw, self.th):
            self.tw, self.th = w, h
            self.saved.clear()                   # earlier saves used the old size
            self.status.config(text=f"Output size set to {w} × {h} px")
            self.render()

    # ---- folders
    def _set_folder(self, lbl, path):
        lbl.config(text=short_path(path), fg=INK)

    def pick_input(self):
        d = filedialog.askdirectory(title="Select folder with photos")
        if not d:
            return
        files = sorted(p for p in Path(d).iterdir()
                       if p.suffix.lower() in EXTS and not p.name.startswith("."))
        if not files:
            messagebox.showinfo("No images", "No supported images in that folder.")
            return
        self.in_dir = Path(d)
        self._set_folder(self.in_lbl, d)
        if self.out_dir is None:
            self.out_dir = self.in_dir / "resized"
            self._set_folder(self.out_lbl, self.out_dir)
        self.files, self.idx = files, 0
        self.states.clear()
        self.saved.clear()
        self.canvas.itemconfig(self.canvas_text, text="")
        self.load_current()

    def pick_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self.out_dir = Path(d)
            self._set_folder(self.out_lbl, d)

    # ---- navigation
    def detect(self):
        w, h = self.img.size
        self.det = detect_subject(self.small, w, h,
                                  ignore_shadows=self.ignore_shadows.get())

    def load_current(self):
        path = self.files[self.idx]
        try:
            self.img, self.icc = load_image(path)
        except Exception as e:  # corrupt / unsupported file
            messagebox.showerror("Could not open image", f"{path.name}\n\n{e}")
            self.img = None
            return
        self.small = make_small(self.img)
        self.detect()
        if path not in self.states:
            w, h = self.img.size
            cx, cy = ((self.det.cx, self.det.cy) if self.auto_on_load.get()
                      else (w / 2, h / 2))
            self.states[path] = {"cx": cx, "cy": cy, "zoom": 1.0}
        self.render()

    def next(self):
        if self.files and self.idx < len(self.files) - 1:
            self.idx += 1
            self.load_current()

    def prev(self):
        if self.files and self.idx > 0:
            self.idx -= 1
            self.load_current()

    # ---- adjustments
    @property
    def st(self):
        return self.states[self.files[self.idx]]

    def on_detection_change(self):
        if self.img is None:
            return
        self.detect()
        self.st["cx"], self.st["cy"] = self.det.cx, self.det.cy
        self.render()

    def nudge(self, dx, dy, out_px):
        """Move the IMAGE by out_px output pixels (the crop window moves the
        opposite way)."""
        if self.img is None:
            return
        box, _, _ = crop_box(*self.img.size, self.st["cx"], self.st["cy"],
                             self.st["zoom"], self.tw, self.th)
        scale = (box[2] - box[0]) / self.tw          # source px per output px
        self.st["cx"] -= dx * out_px * scale
        self.st["cy"] -= dy * out_px * scale
        self.render()

    def zoom(self, factor):
        if self.img is None:
            return
        self.st["zoom"] = min(max(self.st["zoom"] * factor, 1.0), MAX_ZOOM)
        self.render()

    def auto_center(self):
        if self.img is None:
            return
        self.st["cx"], self.st["cy"] = self.det.cx, self.det.cy
        self.render()

    def reset(self):
        if self.img is None:
            return
        w, h = self.img.size
        self.states[self.files[self.idx]] = {"cx": w / 2, "cy": h / 2, "zoom": 1.0}
        self.render()

    # ---- drawing
    def _overlay(self, prev, arr, box, color):
        """Tint the pixels where boolean array `arr` (thumbnail res) is set."""
        w, h = self.img.size
        m = Image.fromarray((arr * 255).astype(np.uint8))
        sx, sy = m.width / w, m.height / h
        mbox = (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy)
        mp = m.resize(prev.size, Image.Resampling.BILINEAR, box=mbox)
        tint = Image.new("RGB", prev.size, color)
        return Image.composite(tint, prev, mp.point(lambda v: int(v * 0.5)))

    def _set_meta(self, text, flags):
        for c in self.meta.winfo_children():
            c.destroy()
        self._label(self.meta, text, self.f_small, GRAY, STAGE).pack(side="left")
        for t, color in flags:
            self._label(self.meta, "   ·   " + t, self.f_small, color, STAGE).pack(side="left")

    def render(self):
        if self.img is None:
            return
        st = self.st
        w, h = self.img.size
        tw, th = self.tw, self.th
        box, st["cx"], st["cy"] = crop_box(w, h, st["cx"], st["cy"], st["zoom"], tw, th)

        fit = min(self.box / tw, self.box / th)
        pw, ph = max(1, round(tw * fit)), max(1, round(th * fit))
        prev = self.img.resize((pw, ph), Image.Resampling.LANCZOS,
                               box=box, reducing_gap=2.0)

        d = self.det
        if self.show_mask.get():
            prev = self._overlay(prev, d.mask, box, (230, 57, 70))
            prev = self._overlay(prev, d.shadow, box, (0, 120, 255))
            if d.found:  # mark where detection thinks the subject center is
                mx = (d.cx - box[0]) / (box[2] - box[0]) * pw
                my = (d.cy - box[1]) / (box[3] - box[1]) * ph
                dr = ImageDraw.Draw(prev)
                r1, r2, ln, wd = px(9), px(8), px(13), px(2)
                dr.ellipse([mx - r1, my - r1, mx + r1, my + r1], outline=(0, 0, 0), width=1)
                dr.ellipse([mx - r2, my - r2, mx + r2, my + r2],
                           outline=(255, 255, 255), width=wd)
                dr.line([mx - ln, my, mx + ln, my], fill=(255, 255, 255), width=wd)
                dr.line([mx, my - ln, mx, my + ln], fill=(255, 255, 255), width=wd)

        if self.guides.get():
            ov = Image.new("RGBA", prev.size, (0, 0, 0, 0))
            dr = ImageDraw.Draw(ov)
            cx, cy = pw // 2, ph // 2
            dr.line([(cx, 0), (cx, ph)], fill=(255, 255, 255, 210), width=1)
            dr.line([(cx + 1, 0), (cx + 1, ph)], fill=(0, 0, 0, 80), width=1)
            dr.line([(0, cy), (pw, cy)], fill=(255, 255, 255, 210), width=1)
            dr.line([(0, cy + 1), (pw, cy + 1)], fill=(0, 0, 0, 80), width=1)
            prev = Image.alpha_composite(prev.convert("RGBA"), ov).convert("RGB")

        self.photo = ImageTk.PhotoImage(prev)
        self.canvas.itemconfig(self.canvas_img, image=self.photo)

        scale = tw / (box[2] - box[0])
        path = self.files[self.idx]
        flags = []
        if scale > 1.0:
            flags.append((f"Upscaled {scale:.2f}×", WARN))
        if not d.found:
            flags.append(("Subject not detected", WARN))
        if path in self.saved:
            flags.append(("Saved", OK))
        self.title_lbl.config(text=path.name)
        zoom = f"   ·   Zoom {st['zoom']:.2f}×" if st["zoom"] > 1.005 else ""
        self._set_meta(f"{self.idx + 1} of {len(self.files)}   ·   {w} × {h} px{zoom}",
                       flags)
        self.progress.set((self.idx + 1) / len(self.files))

    # ---- saving
    def _dest(self, path):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir / path.stem

    def save_and_next(self):
        if self.img is None:
            return
        self.apply_size()
        path = self.files[self.idx]
        try:
            export_image(self.img, self.icc, self.st, self._dest(path),
                         self.fmt.get(), self.tw, self.th)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return
        self.saved.add(path)
        self.status.config(text=f"Saved {path.stem}")
        if self.idx < len(self.files) - 1:
            self.next()
        else:
            self.render()
            messagebox.showinfo("Done", "That was the last image.")

    def save_all(self):
        if not self.files:
            return
        self.apply_size()
        todo = [p for p in self.files if p not in self.saved]
        if not todo or not messagebox.askyesno(
                "Save all", f"Save {len(todo)} image(s) at {self.tw} × {self.th} px, "
                            f"using auto-centering (or your adjustments where you "
                            f"made them)?"):
            return
        errors = []
        for i, path in enumerate(todo, 1):
            self.status.config(text=f"Processing {i} of {len(todo)}…")
            self.root.update()
            try:
                im, icc = load_image(path)
                st = self.states.get(path)
                if st is None:
                    cx, cy = find_subject_center(im, self.ignore_shadows.get())
                    st = {"cx": cx, "cy": cy, "zoom": 1.0}
                export_image(im, icc, st, self._dest(path), self.fmt.get(),
                             self.tw, self.th)
                self.saved.add(path)
            except Exception as e:
                errors.append(f"{path.name}: {e}")
        self.render()
        msg = f"Finished. Saved to:\n{self.out_dir}"
        if errors:
            msg += "\n\nProblems:\n" + "\n".join(errors[:10])
        messagebox.showinfo("Done", msg)
        self.status.config(text="")


if __name__ == "__main__":
    enable_hidpi()
    root = tk.Tk()
    App(root)
    root.mainloop()
