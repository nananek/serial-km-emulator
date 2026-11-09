"""Generate the serial-km-emulator PCB with pcbnew (KiCad 10 python API).

Layout summary
--------------
Board 57.6 x 31.4 mm.  All four corners are 2 mm 45 degree punch cuts; a
punch cut is cheaper than routing a radius and leaves no sharp corner to
catch the paper case.
J1 = serial (CH340N) sits on the top long edge and J2 = HID (CH9329) on the
bottom long edge, so the two plugs leave in opposite directions and their
cables cannot foul each other.  Both mouths overhang the board edge by
1.5 mm.  J1 is placed next to the serial front end and J2 next to the HID
front end to keep the fan-out short.
Both connectors are sinks (5.1k CC pulldowns).
+5V is diode-OR'ed from both VBUS pins and distributed on the top layer.
GND is a copper pour on both layers.
"""

import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import PROJECT, PARTS, GND, P5V  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FP_DIR = os.path.join(ROOT, "lib", "KVM.pretty")

W, H = 57.6, 31.4
# Corner punch cuts: 2 mm along each edge (a 45 degree chamfer), on all four
# corners.  A punch cut is cheaper than routing an arc.
CHAMFER = 2.0
THICKNESS = 1.6

# reference -> (footprint name, x, y, rotation)
# J1 is on the top long edge (mouth up) and J2 on the bottom long edge
# (mouth down).  Each mouth overhangs the edge by 1.5 mm.  The rotations
# put the SMT pad row on the inside of the board.
PLACE = {
    "J1": ("USB_C_Receptacle_HRO_TYPE-C-31-M-12", 13.0, 2.4, 180),
    "J2": ("USB_C_Receptacle_HRO_TYPE-C-31-M-12", 25.0, 29.0, 0),
    "U2": ("SO-8_3.9x4.9mm_P1.27mm", 21.0, 14.0, 0),
    "U1": ("SO-16_3.9x9.9mm_P1.27mm", 36.5, 14.0, 0),
    "D1": ("D_SOD-323", 20.5, 4.5, 180),
    "D2": ("D_SOD-323", 31.5, 21.0, 180),
    "D3": ("SOT-23-6", 13.0, 13.5, 180),
    "D4": ("SOT-23-6", 22.0, 22.0, 180),
    "R1": ("R_0603_1608Metric", 23.5, 9.0, 0),
    "R2": ("R_0603_1608Metric", 15.8, 10.5, 0),
    "R3": ("R_0603_1608Metric", 16.0, 20.5, 0),
    "R4": ("R_0603_1608Metric", 35.5, 22.5, 0),
    "R5": ("R_0603_1608Metric", 31.0, 4.0, 0),
    "LED1": ("LED_0603_1608Metric", 35.0, 4.0, 180),
    "C1": ("C_0603_1608Metric", 43.675, 9.0, 180),
    "C2": ("C_0603_1608Metric", 22.0, 19.0, 180),
    "C3": ("C_0603_1608Metric", 27.0, 11.0, 0),
    "C4": ("C_0603_1608Metric", 41.5, 7.0, 0),
    "C5": ("C_0805_2012Metric", 29.0, 8.0, 0),
    "C6": ("C_0603_1608Metric", 12.0, 16.2, 0),
    "C7": ("C_0603_1608Metric", 25.0, 19.0, 0),
    "TP1": ("TestPoint_1P", 44.0, 17.0, 0),
    "TP2": ("TestPoint_1P", 46.54, 17.0, 0),
}

SIG_W = 0.2
PWR_W = 0.3
VIA_D = 0.5
VIA_DRILL = 0.3
# Keep every via at these standard sizes.  JLCPCB treats a 0.15 mm drill as
# an advanced process and adds several thousand yen in options (minimum via
# size, plugged via covering, 4-wire Kelvin test) even for a 5-piece order.


def P(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def board_points(inset=0.0):
    """Return the board outline as a closed polygon.

    All four corners are 2 mm 45 degree punch cuts.  A punch cut is cheaper
    than routing a rounded corner.  ``inset`` shrinks every edge for the GND
    zone.
    """
    left = inset
    right = W - inset
    top = inset
    bottom = H - inset
    # An inward offset shifts a 45 degree chamfer by inset * sqrt(2), so its
    # legs measured from the inset edges lose inset * (2 - sqrt(2)).
    leg = CHAMFER - inset * (2.0 - math.sqrt(2.0))

    return [
        (right, top + leg),
        (right, bottom - leg),
        (right - leg, bottom),        # bottom-right punch cut
        (left + leg, bottom),
        (left, bottom - leg),         # bottom-left punch cut
        (left, top + leg),
        (left + leg, top),            # top-left punch cut
        (right - leg, top),           # top-right punch cut
    ]



class Builder:
    def __init__(self):
        self.board = pcbnew.BOARD()
        self.board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(THICKNESS))
        self.board.GetDesignSettings().m_CopperEdgeClearance = pcbnew.FromMM(0.2)
        # drill/place origin at the bottom-left corner, so the gerbers and the
        # JLCPCB CPL share the same coordinate system
        self.board.GetDesignSettings().SetAuxOrigin(P(0, H))
        self.nets = {}
        self.pads = {}
        self._add_nets()
        self._place()

    # -- setup ---------------------------------------------------------
    def _add_nets(self):
        names = sorted({n for p in PARTS for n in p["pins"].values() if n})
        for name in names:
            ni = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(ni)
            self.nets[name] = ni
        self.nets[GND] = self.board.FindNet(GND)
        self.nets[P5V] = self.board.FindNet(P5V)

    def _place(self):
        for part in PARTS:
            fpname, x, y, rot = PLACE[part["ref"]]
            fp = pcbnew.FootprintLoad(FP_DIR, fpname)
            if fp is None:
                raise RuntimeError("footprint not found: " + fpname)
            fp.SetPosition(P(x, y))
            fp.SetOrientationDegrees(rot)
            self.board.Add(fp)
            fp.SetReference(part["ref"])
            fp.SetValue(part["value"])
            if part["ref"] not in ("U1", "U2"):
                fp.Reference().SetVisible(False)
                fp.Value().SetVisible(False)
            if part["ref"] in ("J1", "J2"):
                for g in fp.GraphicalItems():
                    if g.GetLayer() == pcbnew.F_SilkS:
                        g.SetLayer(pcbnew.F_Fab)
            for pad in fp.Pads():
                num = pad.GetNumber()
                pad.SetLocalSolderMaskMargin(0)
                net = part["pins"].get(num)
                if net:
                    pad.SetNet(self.nets[net])
                if net == GND:
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
                self.pads[(part["ref"], num)] = pad

    # -- geometry helpers ---------------------------------------------
    def pad(self, ref, num):
        p = self.pads[(ref, num)].GetPosition()
        return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

    def track(self, net, pts, layer=pcbnew.F_Cu, width=SIG_W):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(P(*a))
            t.SetEnd(P(*b))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(layer)
            t.SetNet(self.nets[net])
            self.board.Add(t)

    def via(self, net, x, y, size=VIA_D, drill=VIA_DRILL):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(P(x, y))
        v.SetWidth(pcbnew.FromMM(size))
        v.SetDrill(pcbnew.FromMM(drill))
        try:
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
        except AttributeError:
            # KiCad 9 removed the VIATYPE_* constants; a new PCB_VIA is through.
            pass
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(self.nets[net])
        self.board.Add(v)

    # -- construction --------------------------------------------------
    def outline(self):
        pts = board_points()
        for a, b in zip(pts, pts[1:] + pts[:1]):
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue
            seg = pcbnew.PCB_SHAPE(self.board)
            seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
            seg.SetLayer(pcbnew.Edge_Cuts)
            seg.SetStart(P(*a))
            seg.SetEnd(P(*b))
            seg.SetWidth(pcbnew.FromMM(0.1))
            self.board.Add(seg)

    def zones(self):
        # Stay 0.3 mm inside every edge.  The corners are cut a little
        # deeper than the board chamfer so the pour never pinhces on it.
        m, leg = 0.3, CHAMFER + 1.0
        # Start and close on a straight edge, not on a chamfer vertex:
        # KiCad's connectivity check otherwise splits the pour at that point.
        outline = [(m, H / 2.0), (m, H - m - leg), (m + leg, H - m),
                   (W - m - leg, H - m), (W - m, H - m - leg),
                   (W - m, m + leg), (W - m - leg, m),
                   (m + leg, m), (m, m + leg)]
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            z = pcbnew.ZONE(self.board)
            z.SetLayer(layer)
            z.SetNet(self.nets[GND])
            z.SetLocalClearance(pcbnew.FromMM(0.2))
            z.SetMinThickness(pcbnew.FromMM(0.2))
            z.SetThermalReliefGap(pcbnew.FromMM(0.25))
            z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            o = z.Outline()
            o.NewOutline()
            for x, y in outline:
                o.Append(P(x, y))
            self.board.Add(z)

    def texts(self):
        def text(s, x, y, size=1.0, w=0.15, layer=pcbnew.F_SilkS):
            t = pcbnew.PCB_TEXT(self.board)
            t.SetText(s)
            t.SetPosition(P(x, y))
            t.SetLayer(layer)
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
            t.SetTextThickness(pcbnew.FromMM(w))
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            self.board.Add(t)

        text("SERIAL / CH340", 6.0, 20.0, 0.8)
        text("HID / CH9329", 33.0, 28.0, 1.0)
        # 0.85 mm at x = 29.3 keeps the longer name clear of R1 at the left.
        text("SERIAL-KM-EMULATOR  CH9329EMU-USB replacement", 39.0, 2.5, 0.8, 0.12)
        # pin-1 / polarity marks for datasheet comparison
        text("1", 32.2, 8.2, 0.8)
        text("1", 17.4, 11.2, 0.8)
        text("1", 15.6, 14.8, 0.8)
        text("K", 22.6, 4.5, 0.8)
        text("K", 34.3, 20.0, 0.8)
        text("K", 37.0, 5.2, 0.8)
        # A1 marks: J1 is rotated 180 deg, J2 is not rotated.
        text("A1", 18.2, 7.5, 0.8)
        text("A1", 18.5, 24.2, 0.8)
        text("U1 CH9329", 46.0, 11.5, 0.8, 0.1)
        text("U2 CH340N", 46.0, 12.6, 0.8, 0.1)
        text("D1,D2 BAT54WS", 46.0, 23.5, 0.8, 0.1)
        text("D3,D4 USBLC6-2SC6", 46.0, 24.6, 0.8, 0.1)
        # SET / GND test pads to the right of U1 (TP1 / TP2)
        text("SET", 44.0, 15.35, 0.8, 0.1)
        text("GND", 46.54, 15.35, 0.8, 0.1)
        text("SHORT TO CONFIGURE", 45.0, 20.5, 0.8, 0.1)

    def qr_code(self):
        """Draw the repository QR code on the bottom silkscreen.

        The text file holds the QR as seen from the bottom (1 = dark module).
        Board coordinates are mirrored horizontally so the code reads the right
        way round when the finished board is turned over.
        """
        path = os.path.join(ROOT, "scripts", "repo_qr.txt")
        rows = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                rows.append(line)
        n = len(rows)
        if n == 0 or any(len(row) != n for row in rows):
            raise RuntimeError("repo_qr.txt is not a square matrix")

        cell = 0.5
        x0 = 31.0
        # 41x41 modules at 0.5 mm.  Keep the code's centre at y = 21.0 (as in
        # the previous 37x37 code); the bottom edge is 0.15 mm inside the board.
        y0 = 10.75
        for r, row in enumerate(rows):
            c = 0
            while c < n:
                if row[c] != "0":
                    c += 1
                    continue
                c_end = c
                while c_end < n and row[c_end] == "0":
                    c_end += 1
                # mirror the run: bottom-view column c maps to board column n-1-c
                xa = x0 + (n - c_end) * cell
                xb = x0 + (n - c) * cell
                ya = y0 + r * cell
                yb = y0 + (r + 1) * cell
                rect = pcbnew.PCB_SHAPE(self.board)
                rect.SetShape(pcbnew.SHAPE_T_RECT)
                rect.SetStart(P(xa, ya))
                rect.SetEnd(P(xb, yb))
                rect.SetLayer(pcbnew.B_SilkS)
                rect.SetWidth(pcbnew.FromMM(0.05))
                rect.SetFilled(True)
                self.board.Add(rect)
                c = c_end

    # -- routing -------------------------------------------------------
    def route(self):
        T = self.track
        V = self.via

        # ---------------- +5V (diode OR of both VBUS) ----------------
        # One rail runs along the top edge.  D1 feeds it at the left, D2 is
        # placed on the right and feeds the same rail from below.
        T(P5V, [(21.55, 4.5), (21.55, 6.0), (44.5, 6.0)], width=PWR_W)
        T(P5V, [self.pad("D2", "1"), (35.0, 21.0), (35.0, 19.5)],
          width=PWR_W)
        V(P5V, 35.0, 19.5)
        T(P5V, [(35.0, 19.5), (35.0, 6.5)], layer=pcbnew.B_Cu, width=PWR_W)
        V(P5V, 35.0, 6.5)
        T(P5V, [(35.0, 6.5), (35.0, 6.0)], width=PWR_W)

        # serial VBUS: both J1 VBUS pads -> B.Cu trunk -> D1, C6, D3
        T("VBUS_SER", [self.pad("J1", "A4"), (15.45, 7.8)], width=SIG_W)
        V("VBUS_SER", 15.45, 7.8)
        T("VBUS_SER", [self.pad("J1", "A9"), (10.55, 7.6)], width=SIG_W)
        V("VBUS_SER", 10.55, 7.6)
        T("VBUS_SER", [(15.45, 7.8), (19.45, 7.8)],
          layer=pcbnew.B_Cu, width=PWR_W)
        V("VBUS_SER", 19.45, 7.8)
        T("VBUS_SER", [(19.45, 7.8), self.pad("D1", "2")], width=SIG_W)
        T("VBUS_SER", [(15.45, 7.8), (17.5, 7.8), (17.5, 18.0),
                       (10.55, 18.0), (10.55, 7.6)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("VBUS_SER", 10.55, 13.5)
        T("VBUS_SER", [(10.55, 13.5), self.pad("D3", "5")], width=SIG_W)
        V("VBUS_SER", 11.225, 18.0)
        T("VBUS_SER", [(11.225, 18.0), self.pad("C6", "1")], width=SIG_W)

        # HID VBUS: both J2 VBUS pads run above the connector, then around
        # the west side of D4 to pin 5.  D4 is rotated 180 deg, so pin 5 is
        # on its left and the data fan-out stays on the right.
        T("VBUS_HID", [self.pad("J2", "A4"), (22.55, 23.8), (19.5, 23.8),
                       (19.5, 22.0), self.pad("D4", "5")], width=SIG_W)
        T("VBUS_HID", [self.pad("J2", "A9"), (27.45, 20.0)], width=PWR_W)
        T("VBUS_HID", [(19.5, 22.0), (19.5, 20.0), (30.45, 20.0),
                       (30.45, 21.0), self.pad("D2", "2")], width=PWR_W)
        T("VBUS_HID", [(24.225, 20.0), self.pad("C7", "1")], width=SIG_W)

        # U2 (CH340N) VCC: drop under the data signals on the back layer
        V(P5V, 23.0, 6.0)
        T(P5V, [(23.0, 6.0), (23.0, 18.5)], layer=pcbnew.B_Cu, width=PWR_W)
        V(P5V, 23.0, 18.5)
        T(P5V, [(23.0, 18.5), (23.0, 15.905), (23.575, 15.905)], width=PWR_W)
        T(P5V, [self.pad("C2", "1"), (22.775, 18.5), (23.0, 18.5)],
          width=SIG_W)
        # U1 (CH9329) VCC
        T(P5V, [(44.5, 6.0), (44.5, 10.825)], width=PWR_W)
        T(P5V, [(44.5, 10.825), self.pad("U1", "15")], width=PWR_W)
        # decoupling caps + LED
        T(P5V, [(self.pad("C5", "1")[0], 6.0), self.pad("C5", "1")],
          width=SIG_W)
        T(P5V, [self.pad("R5", "1"), (30.175, 6.0)], width=SIG_W)

        T("VBUS_HID", [(27.45, 20.0), (29.95, 20.0)], width=PWR_W)

        # ---------------- serial port USB ----------------
        # D3 is rotated 180 deg: DP is pins 1/6 on the bottom, DM is 3/4 on
        # the top, VBUS is pin 5 on the left.  DP lanes drop past the package
        # and meet on one bridge below it; DM lanes cross on B.Cu.
        T("USB_SER_DP", [self.pad("J1", "B6"), (12.25, 8.2), (10.0, 8.2),
                         (10.0, 15.2), (11.863, 15.2),
                         self.pad("D3", "6")], width=SIG_W)
        T("USB_SER_DP", [self.pad("J1", "A6"), (13.25, 10.5), (13.1, 10.5),
                         (13.1, 15.2), (14.137, 15.2),
                         self.pad("D3", "1")], width=SIG_W)
        T("USB_SER_DP", [(11.863, 15.2), (14.5, 15.2)], width=SIG_W)
        T("USB_SER_DP", [self.pad("D3", "1"), (14.137, 15.2)], width=SIG_W)
        V("USB_SER_DP", 14.5, 15.2)
        T("USB_SER_DP", [(14.5, 15.2), (17.0, 15.2), (17.0, 12.095)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_SER_DP", 17.0, 12.095)
        T("USB_SER_DP", [(17.0, 12.095), self.pad("U2", "1")], width=SIG_W)
        T("USB_SER_DM", [self.pad("J1", "A7"), (12.75, 9.5)], width=SIG_W)
        V("USB_SER_DM", 12.75, 9.5)
        T("USB_SER_DM", [self.pad("J1", "B7"), (13.75, 9.5)], width=SIG_W)
        V("USB_SER_DM", 13.75, 9.5)
        T("USB_SER_DM", [(12.75, 9.5), (13.75, 9.5)], layer=pcbnew.B_Cu,
          width=SIG_W)
        T("USB_SER_DM", [(12.75, 9.5), (12.75, 11.2), (11.863, 11.2)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_SER_DM", 11.863, 11.2)
        T("USB_SER_DM", [(11.863, 11.2), self.pad("D3", "4")], width=SIG_W)
        T("USB_SER_DM", [(13.75, 9.5), (13.75, 11.2), (14.137, 11.2)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_SER_DM", 14.137, 11.2)
        T("USB_SER_DM", [(14.137, 11.2), self.pad("D3", "3")], width=SIG_W)
        T("USB_SER_DM", [self.pad("D3", "3"), (15.1, 12.55), (15.1, 15.5),
                         (17.2, 15.5), (17.2, 13.365),
                         self.pad("U2", "2")], width=SIG_W)

        # ---------------- HID port USB ----------------
        # D4 is rotated 180 deg: DP is pins 3/4 and DM is pins 1/6.  The two
        # J2 DP pads meet on F.Cu; the DM pad pair joins on B.Cu.
        T("USB_HID_DP", [self.pad("J2", "A6"), (24.75, 21.05),
                         self.pad("D4", "3")], width=SIG_W)
        T("USB_HID_DP", [self.pad("J2", "B6"), (25.75, 23.7)], width=SIG_W)
        V("USB_HID_DP", 25.75, 23.7)
        T("USB_HID_DP", [(25.75, 23.7), (24.75, 23.7)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_HID_DP", 24.75, 23.7)
        T("USB_HID_DM", [self.pad("J2", "B7"), (24.25, 22.95),
                         self.pad("D4", "1")], width=SIG_W)
        T("USB_HID_DM", [self.pad("J2", "A7"), (25.25, 22.3)], width=SIG_W)
        V("USB_HID_DM", 25.25, 22.3)
        T("USB_HID_DM", [(25.25, 22.3), (25.25, 22.95)],
          layer=pcbnew.B_Cu, width=SIG_W)

        # CC pulldowns
        T("CC1_SER", [self.pad("J1", "A5"), (14.25, 9.5), (22.675, 9.5),
                      self.pad("R1", "1")], width=SIG_W)
        T("CC2_SER", [self.pad("J1", "B5"), (11.25, 7.5)], width=SIG_W)
        V("CC2_SER", 11.25, 7.5)
        T("CC2_SER", [(11.25, 7.5), (14.6, 7.5), (14.6, 10.5)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("CC2_SER", 14.6, 10.5)
        T("CC2_SER", [(14.6, 10.5), self.pad("R2", "1")], width=SIG_W)

        # CC1_HID crosses the data fan-out on B.Cu, west of the data trunk.
        T("CC1_HID", [self.pad("J2", "A5"), (23.75, 23.7)], width=SIG_W)
        V("CC1_HID", 23.75, 23.7)
        T("CC1_HID", [(23.75, 23.7), (15.175, 23.7), (15.175, 21.2)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("CC1_HID", 15.175, 21.2)
        T("CC1_HID", [(15.175, 21.2), self.pad("R3", "1")], width=SIG_W)
        # CC2_HID jogs onto B.Cu between the two data trunks to pass the
        # VBUS column, then returns to F.Cu east of it.
        T("CC2_HID", [self.pad("J2", "B5"), (26.75, 21.7)], width=SIG_W)
        V("CC2_HID", 26.75, 21.7)
        T("CC2_HID", [(26.75, 21.7), (28.2, 21.7)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("CC2_HID", 28.2, 21.7)
        T("CC2_HID", [(28.2, 21.7), (34.675, 22.5),
                      self.pad("R4", "1")], width=SIG_W)

        # D4 -> U1.  DM is I/O1 (pins 1/6), DP is I/O2 (pins 3/4).  The long
        # runs are on B.Cu; the left-hand pads connect to the same trunks.
        T("USB_HID_DM", [(20.2, 22.95), (41.8, 22.95), (41.8, 14.2)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_HID_DM", 41.8, 14.2)
        T("USB_HID_DM", [(41.8, 14.2), (41.8, 13.365),
                         self.pad("U1", "13")], width=SIG_W)
        T("USB_HID_DM", [self.pad("D4", "6"), (20.2, 22.95)], width=SIG_W)
        V("USB_HID_DM", 20.2, 22.95)
        V("USB_HID_DM", 24.25, 22.95)

        T("USB_HID_DP", [(20.2, 21.05), (41.2, 21.05), (41.2, 15.2)],
          layer=pcbnew.B_Cu, width=SIG_W)
        V("USB_HID_DP", 41.2, 15.2)
        T("USB_HID_DP", [(41.2, 15.2), (41.2, 14.635),
                         self.pad("U1", "12")], width=SIG_W)
        T("USB_HID_DP", [self.pad("D4", "4"), (20.2, 21.05)], width=SIG_W)
        V("USB_HID_DP", 20.2, 21.05)
        V("USB_HID_DP", 24.5, 21.05)

        # ---------------- UART between CH340N and CH9329 ----------------
        # U1 TXD (7) -> U2 RXD (7), U2 TXD (6) -> U1 RXD (8).
        T("UART_9329_TX", [self.pad("U1", "7"), (31.0, 17.175), (31.0, 13.365),
                           self.pad("U2", "7")], width=SIG_W)
        T("UART_9329_RX", [self.pad("U2", "6"), (24.9, 14.635), (24.9, 17.8),
                           (32.0, 17.8), (32.0, 18.445),
                           self.pad("U1", "8")], width=SIG_W)

        # ---------------- LED (cathode crosses the +5V rail on B.Cu) --------
        T("LED_A", [self.pad("R5", "2"), self.pad("LED1", "2")], width=SIG_W)
        led_x = self.pad("LED1", "1")[0]
        T("LED_ACT", [self.pad("LED1", "1"), (led_x, 5.0)], width=SIG_W)
        V("LED_ACT", led_x, 5.0)
        T("LED_ACT", [(led_x, 5.0), (led_x, 8.0)], layer=pcbnew.B_Cu, width=SIG_W)
        V("LED_ACT", led_x, 8.0)
        T("LED_ACT", [(led_x, 8.0), (33.425, 8.0), (33.425, 9.555),
                      self.pad("U1", "1")], width=SIG_W)

        # ---------------- V33 / V3 ----------------
        T("V33", [self.pad("C4", "1"), (40.3, 7.0), (40.3, 9.555),
                  self.pad("U1", "16")], width=SIG_W)
        T("V3_340", [self.pad("C3", "1"), (24.0, 11.0), (24.0, 12.095),
                     self.pad("U2", "8")], width=SIG_W)

        # ---------------- SET test pad (TP1) ----------------
        T("SET", [self.pad("U1", "11"), (44.0, 15.905),
                  self.pad("TP1", "1")], width=SIG_W)

        # ---------------- ground ----------------
        for x, y in ((42.85, 9.0), (42.325, 7.0), (29.825, 8.0),
                     (3.0, 12.0), (53.0, 12.0), (3.0, 17.0), (53.0, 17.0),
                     (2.0, 2.0), (53.0, 2.0), (2.0, 25.5), (54.0, 25.5),
                     (16.0, 25.5), (28.0, 2.0), (10.0, 25.0), (42.0, 25.0),
                     (50.0, 25.0), (32.0, 10.0), (45.0, 25.0),
                     (13.7, 13.7), (22.0, 22.3), (56.0, 3.0),
                     (11.8, 17.4)):
            V(GND, x, y)
        T(GND, [self.pad("U1", "14"), (40.0, 12.095)], width=SIG_W)
        V(GND, 40.0, 12.095)
        # connector and ESD grounds are handled by the GND pour

    def finish(self):
        path = os.path.join(ROOT, f"{PROJECT}.kicad_pcb")

        def drop_zero_length_edges(board):
            for item in list(board.GetDrawings()):
                if item.GetLayer() != pcbnew.Edge_Cuts:
                    continue
                if item.GetShape() != pcbnew.SHAPE_T_SEGMENT:
                    continue
                s = item.GetStart()
                e = item.GetEnd()
                if s.x == e.x and s.y == e.y:
                    board.Remove(item)

        # KiCad 10 crashes when the zone filler runs on a board that only exists
        # in memory, so write it out and fill the reloaded copy.
        drop_zero_length_edges(self.board)
        pcbnew.SaveBoard(path, self.board)
        board = pcbnew.LoadBoard(path)
        drop_zero_length_edges(board)
        board.BuildConnectivity()
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        pcbnew.SaveBoard(path, board)


def main():
    b = Builder()
    b.outline()
    b.zones()
    b.texts()
    b.qr_code()
    b.route()
    b.finish()
    print("wrote", os.path.join(ROOT, f"{PROJECT}.kicad_pcb"))


if __name__ == "__main__":
    main()
