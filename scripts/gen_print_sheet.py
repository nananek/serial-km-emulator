"""Shared 1:1 PDF helpers for the paper case.

The printable net itself lives in ``gen_paper_box.py``.  This module only
keeps the small PDF writer and the board-outline readers that both scripts
use, so the PDF user space is in millimetres (1 mm = 72/25.4 pt) and the
print size does not depend on the PDF viewer.
"""

import re

ROOT = None  # retained for callers that import this module as a script

MM = 72.0 / 25.4
A4_W, A4_H = 297.0, 210.0


def read_outline(path):
    """Return the Edge.Cuts segments as ((x1, y1), (x2, y2)) tuples."""
    src = open(path, encoding="utf-8").read()
    segs = []
    for m in re.finditer(
        r"\(gr_line\s*\(start\s+([-\d.]+)\s+([-\d.]+)\)\s*"
        r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s*\(stroke.*?\(layer\s+\"([^\"]+)\"\)",
        src,
        re.S,
    ):
        if m.group(5) != "Edge.Cuts":
            continue
        segs.append(((float(m.group(1)), float(m.group(2))),
                     (float(m.group(3)), float(m.group(4)))))
    if not segs:
        raise SystemExit("no Edge.Cuts segments found in " + path)
    return segs


def outline_polygon(segs, tol=1e-3):
    """Chain Edge.Cuts segments into one closed polygon."""
    remaining = list(segs)
    start, end = remaining.pop(0)
    pts = [start, end]
    while remaining:
        last = pts[-1]
        for i, (a, b) in enumerate(remaining):
            if abs(last[0] - a[0]) < tol and abs(last[1] - a[1]) < tol:
                pts.append(b)
                remaining.pop(i)
                break
            if abs(last[0] - b[0]) < tol and abs(last[1] - b[1]) < tol:
                pts.append(a)
                remaining.pop(i)
                break
        else:
            raise SystemExit("Edge.Cuts is not a single closed loop")
    if abs(pts[0][0] - pts[-1][0]) < tol and abs(pts[0][1] - pts[-1][1]) < tol:
        pts.pop()
    return pts


class Sheet:
    """Minimal PDF writer; coordinates are millimetres with y pointing up."""

    def __init__(self, width, height):
        self.w, self.h = width, height
        self.ops = []

    def _num(self, v):
        return ("%.3f" % v).rstrip("0").rstrip(".")

    def line(self, x1, y1, x2, y2, width=0.2, dash=None):
        d = "[%s %s] 0 d" % tuple(self._num(v) for v in dash) if dash else "[] 0 d"
        self.ops.append("%s %s w %s %s m %s %s l S" % (
            d, self._num(width), self._num(x1), self._num(y1),
            self._num(x2), self._num(y2)))

    def rect(self, x, y, w, h, width=0.2, dash=None):
        self.line(x, y, x + w, y, width, dash)
        self.line(x + w, y, x + w, y + h, width, dash)
        self.line(x + w, y + h, x, y + h, width, dash)
        self.line(x, y + h, x, y, width, dash)

    def polyline(self, pts, width=0.2, dash=None):
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], width, dash)

    def _path(self, pts):
        out = ["%s %s m" % (self._num(pts[0][0]), self._num(pts[0][1]))]
        for x, y in pts[1:]:
            out.append("%s %s l" % (self._num(x), self._num(y)))
        out.append("h")
        return " ".join(out)

    def fill(self, pts, gray=0.7):
        self.ops.append("%s g %s f 0 g" % (self._num(gray), self._path(pts)))

    def stroke_polygon(self, pts, width=1.0, gray=0.85):
        self.ops.append("%s G %s w %s S 0 G" % (
            self._num(gray), self._num(width), self._path(pts)))

    def text(self, s, x, y, size=3.0, angle=0.0):
        s = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if angle:
            import math
            c, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            tm = "%s %s %s %s %s %s Tm" % (
                self._num(c * size), self._num(sn * size),
                self._num(-sn * size), self._num(c * size),
                self._num(x), self._num(y))
        else:
            tm = "%s 0 0 %s %s %s Tm" % (
                self._num(size), self._num(size), self._num(x), self._num(y))
        self.ops.append("BT /F1 1 Tf %s (%s) Tj ET" % (tm, s))

    def save(self, path):
        content = ("q\n%s 0 0 %s 0 0 cm\n1 J 1 j 0 G 0 g\n" % (
            self._num(MM), self._num(MM))) + "\n".join(self.ops) + "\nQ\n"
        stream = content.encode("latin-1")
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
             "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>" % (
                 self._num(self.w * MM), self._num(self.h * MM))).encode("ascii"),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>",
        ]
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, xref))
        with open(path, "wb") as f:
            f.write(bytes(out))
