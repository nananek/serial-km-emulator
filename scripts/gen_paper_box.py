"""Generate an A4, 1:1 net for a folded paper case.

The case is a one-piece tuck box for the serial-km-emulator board.  The board
outline is read from serial-km-emulator.kicad_pcb, so the pocket follows the
real board size and corner cuts.  The sheet is drawn with the standard library
only: the PDF user space is in millimetres (1 mm = 72/25.4 pt), which keeps the
print size independent of the PDF viewer.

Usage:
    python3 scripts/gen_paper_box.py [output.pdf]
"""

import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gen_print_sheet import A4_H, A4_W, Sheet, outline_polygon, read_outline

ROOT = os.path.dirname(HERE)
PCB = os.path.join(ROOT, "serial-km-emulator.kicad_pcb")
DEFAULT_OUT = os.path.join(ROOT, "docs", "paper_case_a4.pdf")

# --- box dimensions (mm) ---------------------------------------------------
MARGIN = 0.5          # board to inner wall, left / right / front / back
PAPER_T = 0.3         # cardstock thickness used for the notes
HEIGHT = 8.0          # inner height
SLOT_LEN = 20.0       # USB-C opening along the left wall
SLOT_Z0 = 1.5         # bottom of the opening above the inner floor
SLOT_H = 4.5          # opening height
TAB_D = 7.0           # glue tab depth
TUCK_W = 43.0         # tuck flap width (clears the corner glue tabs)
TUCK_D = 6.0          # tuck flap depth
LID_OVERHANG = 0.5    # lid overlap over the left / right walls
LED_HOLE_D = 3.0      # LED window diameter


def read_footprint_at(path, ref):
    """Return the footprint origin (x, y) for a reference designator."""
    src = open(path, encoding="utf-8").read()
    key = '(property "Reference" "%s"' % ref
    i = src.index(key)
    ats = list(re.finditer(r"\(at\s+([-\d.]+)\s+([-\d.]+)", src[:i]))
    if not ats:
        raise SystemExit("no (at ...) before Reference %s" % ref)
    return float(ats[-1].group(1)), float(ats[-1].group(2))


class Canvas:
    """Draw in net coordinates; the origin is the bottom-left of the floor."""

    def __init__(self, sheet, ox, oy):
        self.s = sheet
        self.ox = ox
        self.oy = oy

    def _num(self, v):
        return ("%.3f" % v).rstrip("0").rstrip(".")

    def line(self, x1, y1, x2, y2, width=0.25, dash=None, gray=None):
        x1, y1 = self.ox + x1, self.oy + y1
        x2, y2 = self.ox + x2, self.oy + y2
        if gray is None:
            self.s.line(x1, y1, x2, y2, width, dash)
            return
        d = "[%s %s] 0 d" % tuple(self._num(v) for v in dash) if dash else "[] 0 d"
        self.s.ops.append("%s %s G %s w %s %s m %s %s l S 0 G" % (
            d, self._num(gray), self._num(width), self._num(x1),
            self._num(y1), self._num(x2), self._num(y2)))

    def rect(self, x, y, w, h, width=0.25, dash=None, gray=None):
        self.line(x, y, x + w, y, width, dash, gray)
        self.line(x + w, y, x + w, y + h, width, dash, gray)
        self.line(x + w, y + h, x, y + h, width, dash, gray)
        self.line(x, y + h, x, y, width, dash, gray)

    def polyline(self, pts, width=0.25, dash=None, gray=None):
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], width, dash, gray)

    def polygon(self, pts, width=0.25, gray=None):
        self.polyline(pts + [pts[0]], width, gray=gray)

    def circle(self, cx, cy, r, width=0.25, n=48):
        pts = [(cx + r * math.cos(2 * math.pi * i / n),
                cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        self.polygon(pts, width)

    def fill(self, pts, gray=0.9):
        self.s.fill([(self.ox + x, self.oy + y) for x, y in pts], gray)

    def text(self, s, x, y, size=3.0, angle=0.0):
        self.s.text(s, self.ox + x, self.oy + y, size, angle)

    def ctext(self, s, x, y, size=3.0, angle=0.0):
        """Approximately centre a short Helvetica label."""
        width = 0.56 * len(s) * size
        if angle:
            # For 90 degree text the string runs up the page.
            self.text(s, x, y - width / 2.0, size, angle)
        else:
            self.text(s, x - width / 2.0, y - 0.35 * size, size)


def dim_h(c, x1, x2, y, label, size=2.6):
    c.line(x1, y, x2, y, 0.15)
    for x in (x1, x2):
        c.line(x, y - 1.2, x, y + 1.2, 0.15)
    c.ctext(label, (x1 + x2) / 2.0, y + 1.8, size)


def dim_v(c, x, y1, y2, label, size=2.6):
    c.line(x, y1, x, y2, 0.15)
    for y in (y1, y2):
        c.line(x - 1.2, y, x + 1.2, y, 0.15)
    c.ctext(label, x - 1.0, (y1 + y2) / 2.0, size, angle=90)


def box_layout(board_w, board_h):
    w = board_w + 2.0 * MARGIN
    d = board_h + 2.0 * MARGIN
    return dict(w=w, d=d, h=HEIGHT)


def draw_net(c, box, board_poly, board_min, j1, j2, led):
    W, D, H = box["w"], box["d"], box["h"]
    tx = (W - TUCK_W) / 2.0
    lid_x0 = -LID_OVERHANG
    lid_w = W + 2.0 * LID_OVERHANG

    # --- all panel outlines (cut edges) ---------------------------------
    c.rect(0, 0, W, D)                    # floor
    c.rect(0, -H, W, H)                   # front wall
    c.rect(0, D, W, H)                    # back wall
    c.rect(-H, 0, H, D)                   # left wall (USB-C side)
    c.rect(W, 0, H, D)                    # right wall
    c.rect(lid_x0, D + H, lid_w, D)       # lid
    c.rect(-H, -TAB_D, H, TAB_D)          # left front glue tab
    c.rect(-H, D, H, TAB_D)               # left back glue tab
    c.rect(W, -TAB_D, H, TAB_D)           # right front glue tab
    c.rect(W, D, H, TAB_D)                # right back glue tab

    # --- tuck flap (2 mm corner cuts) -----------------------------------
    y0 = D + H + D
    c.polyline([(tx, y0), (tx, y0 + TUCK_D - 2.0),
                (tx + 2.0, y0 + TUCK_D), (tx + TUCK_W - 2.0, y0 + TUCK_D),
                (tx + TUCK_W, y0 + TUCK_D - 2.0), (tx + TUCK_W, y0)])

    # --- fold lines: knock out the cut line, then draw the dashes --------
    folds = [
        ((-H, 0), (W + H, 0)),
        ((-H, D), (W + H, D)),
        ((0, 0), (0, D)),
        ((W, 0), (W, D)),
        ((0, D + H), (W, D + H)),
        ((tx, y0), (tx + TUCK_W, y0)),
    ]
    for (x1, y1), (x2, y2) in folds:
        c.line(x1, y1, x2, y2, 1.0, gray=1.0)
    for (x1, y1), (x2, y2) in folds:
        c.line(x1, y1, x2, y2, 0.25, dash=(2.2, 1.4))

    # --- USB-C opening in the left wall ---------------------------------
    # Centre the opening between the two connector centres, not just on the
    # wall, so a future board revision with a different pitch still lines up.
    slot_cy = D - MARGIN - ((j1[1] + j2[1]) / 2.0 - board_min[1])
    slot_y0 = slot_cy - SLOT_LEN / 2.0
    c.rect(-SLOT_Z0 - SLOT_H, slot_y0, SLOT_H, SLOT_LEN, 0.3)

    # --- board outline on the floor, for placement -----------------------
    bpts = [(MARGIN + (x - board_min[0]), D - MARGIN - (y - board_min[1]))
            for x, y in board_poly]
    c.fill(bpts, 0.93)
    c.polyline(bpts + [bpts[0]], 0.18, dash=(1.3, 1.1), gray=0.45)

    # Connector centre lines on the floor.
    for ref, at in (("J1", j1), ("J2", j2)):
        y = D - MARGIN - (at[1] - board_min[1])
        c.line(MARGIN, y, MARGIN + 6.0, y, 0.15, dash=(1.0, 1.0), gray=0.45)
        c.text(ref, MARGIN + 6.4, y - 1.0, 2.3)

    # --- LED window in the lid ------------------------------------------
    led_x = MARGIN + (led[0] - board_min[0])
    led_y = D + H + MARGIN + (led[1] - board_min[1]) + PAPER_T / 2.0
    c.circle(led_x, led_y, LED_HOLE_D / 2.0, 0.3)
    c.text("LED %g" % LED_HOLE_D, led_x + 2.6, led_y - 1.0, 2.3)

    # --- panel labels ----------------------------------------------------
    c.ctext("FRONT", W / 2.0, -H / 2.0 - 1.2, 4.0)
    c.ctext("BACK", W / 2.0, D + H / 2.0 - 1.2, 4.0)
    c.ctext("LID", W / 2.0, D + H + D / 2.0 - 1.5, 5.0)
    c.ctext("TUCK", W / 2.0, y0 + TUCK_D / 2.0 - 0.8, 3.0)
    c.ctext("LEFT", -H / 2.0, D - 3.0, 2.4)
    c.ctext("RIGHT", W + H / 2.0, D - 3.0, 2.4)
    c.ctext("BOARD", W / 2.0, D / 2.0 + 1.0, 4.0)
    c.ctext("%.1f x %.1f" % (W - 2 * MARGIN, D - 2 * MARGIN),
            W / 2.0, D / 2.0 - 4.5, 2.4)
    for x in (-H / 2.0, W + H / 2.0):
        c.ctext("G", x, -TAB_D / 2.0 - 1.0, 3.0)
        c.ctext("G", x, D + TAB_D / 2.0 - 1.0, 3.0)

    # Dimensions outside the net.
    dim_h(c, 0, W, -H - 7.0, "%.1f inner" % W)
    dim_v(c, W + H + 7.0, 0, D, "%.1f inner" % D)
    dim_v(c, -H - 7.0, 0, H, "%.1f" % H)


def draw_notes(sheet, box, led, board_min):
    W, D, H = box["w"], box["d"], box["h"]
    x, y = 125.0, 176.0

    sheet.text("ASSEMBLY", x, y, 4.2)
    lines = [
        "1. Print on A4 at 100% / 'Actual size'. Check the",
        "   100 mm bar at the bottom of this page.",
        "2. The printed side becomes the inside of the box.",
        "   Solid lines = cut. Black dashed lines = score and",
        "   valley fold (fold toward the printed side).",
        "3. Cut the outside, the 20 x 4.5 mm USB-C slot and",
        "   the 3 mm LED hole.",
        "4. Fold up the four walls. Put glue on the inside of",
        "   the front and back walls, then press the tabs (G).",
        "5. Fold the lid over and tuck the 43 mm flap",
        "   inside the front wall.",
        "6. Put the board on the floor, against the LEFT",
        "   wall. J1/J2 go through the slot, LED under",
        "   the 3 mm hole.",
        "7. No screws. Use tape or a foam pad if the board",
        "   rattles. A spacer up to 0.5 mm is OK.",
        "8. Chamfer the outside of the slot lightly if a",
        "   plug overmould catches on the paper.",
    ]
    for i, line in enumerate(lines):
        sheet.text(line, x, y - 7.0 - i * 4.0, 2.9)

    y2 = 93.0
    sheet.text("DIMENSIONS (mm)", x, y2, 3.4)
    for i, line in enumerate([
        "inner        %5.1f x %4.1f x %3.1f" % (W, D, H),
        "board        %5.1f x %4.1f x 1.6" % (W - 2 * MARGIN, D - 2 * MARGIN),
        "wall         0.3 cardstock (recommended)",
        "USB-C slot   %.1f x %.1f, %.1f above floor" % (
            SLOT_LEN, SLOT_H, SLOT_Z0),
        "LED hole     3.0 dia, %.1f / %.1f from hinge" % (
            MARGIN + (led[0] - board_min[0]),
            MARGIN + (led[1] - board_min[1]) + PAPER_T / 2.0),
        "glue tab     %.0f mm, four corners" % TAB_D,
        "tuck flap    %.0f x %.0f mm" % (TUCK_W, TUCK_D),
    ]):
        sheet.text(line, x, y2 - 5.5 - i * 4.0, 2.9)

    y3 = 57.0
    sheet.text("LINE TYPES", x, y3, 3.4)
    sheet.line(x, y3 - 5.0, x + 14, y3 - 5.0, 0.3)
    sheet.text("cut", x + 17, y3 - 6.0, 2.9)
    sheet.line(x, y3 - 10.0, x + 14, y3 - 10.0, 0.3, dash=(2.2, 1.4))
    sheet.text("fold (valley)", x + 17, y3 - 11.0, 2.9)
    sheet.text("grey dashed = board outline (reference)", x, y3 - 16.0, 2.7)

    sheet.text("The QR code on the board back is hidden while the board is",
               x, y3 - 24.0, 2.7)
    sheet.text("in the box. Take the board out to scan it.", x, y3 - 28.2, 2.7)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT

    segs = read_outline(PCB)
    poly = outline_polygon(segs)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    board_min = (min(xs), min(ys))
    board_w = max(xs) - min(xs)
    board_h = max(ys) - min(ys)

    j1 = read_footprint_at(PCB, "J1")
    j2 = read_footprint_at(PCB, "J2")
    led = read_footprint_at(PCB, "LED1")
    box = box_layout(board_w, board_h)

    sheet = Sheet(A4_W, A4_H)
    NX, NY = 30.0, 62.0
    c = Canvas(sheet, NX, NY)

    sheet.text("SERIAL-KM-EMULATOR  /  PAPER CASE", 15, 198, 6.5)
    sheet.text("A4 landscape, 1:1 net for 0.3 mm cardstock.",
               15, 191, 3.4)
    sheet.text("Print at 100% / 'Actual size'. Do not use 'fit to page'.",
               15, 186.5, 3.4)
    sheet.text("Printed side = inside. Solid = cut, black dashed = valley fold.",
               15, 181.5, 3.0)

    draw_net(c, box, poly, board_min, j1, j2, led)
    draw_notes(sheet, box, led, board_min)

    # 100 mm print-scale check.
    sx, sy, slen = 15.0, 18.0, 100.0
    sheet.line(sx, sy, sx + slen, sy, 0.3)
    for i in range(int(slen) + 1):
        if i % 10 == 0:
            tick, w = 3.2, 0.3
        elif i % 5 == 0:
            tick, w = 2.0, 0.2
        else:
            tick, w = 1.0, 0.15
        sheet.line(sx + i, sy, sx + i, sy + tick, w)
    for i in range(0, int(slen) + 1, 50):
        sheet.text("%d" % i, sx + i - (3 if i == 100 else 0), sy - 4.5, 3.0)
    sheet.text("100 mm scale check (mm)", sx, sy + 7.0, 3.2)

    sheet.text("Generated by scripts/gen_paper_box.py from serial-km-emulator.kicad_pcb",
               15, 10, 2.3)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    print("wrote %s (A4 landscape, 1:1)" % os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
