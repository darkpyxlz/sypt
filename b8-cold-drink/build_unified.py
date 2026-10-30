"""Build B8-unified.pdf: cover + discrepancy report + the four B8 reports."""
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

D = Path(sys.argv[1])
OUT = D / "B8-unified.pdf"
FRONT = Path(sys.argv[2])

F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", F + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVI", F + "DejaVuSans.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DVI", boldItalic="DVB")

TEAL = colors.HexColor("#0f6e6e")
body = ParagraphStyle("b", fontName="DV", fontSize=9.2, leading=12.6, spaceAfter=5)
small = ParagraphStyle("s", parent=body, fontSize=7.8, leading=10, spaceAfter=0)
h1 = ParagraphStyle("h1", fontName="DVB", fontSize=15, leading=19, textColor=TEAL,
                    spaceBefore=8, spaceAfter=8)
h2 = ParagraphStyle("h2", fontName="DVB", fontSize=11, leading=14, textColor=TEAL,
                    spaceBefore=9, spaceAfter=4)
title = ParagraphStyle("t", fontName="DVB", fontSize=24, leading=30, spaceAfter=10)

# Source documents, in reading order.
DOCS = [
    ("B8-salted-ice-bath.pdf", "Part A — The salted ice bath (handover report)",
     "Main report: physics from first principles, equilibrium model b8_sim.py and "
     "time-dependent simulator b8_model.py, results, experimental programme."),
    ("B8-model-derivation.pdf", "Part B — The lumped model, derived step by step (25 Oct)",
     "The drink-and-bath lumped model with no stirrer, every step explained, "
     "ending in the closed equation set and closed-form special cases."),
    ("sypt_salt_ice_model.pdf", "Part C — Salt–ice–water model notes, 2nd edition",
     "Equation compendium: Steps 1–12, with the part-filled can, floating, and an "
     "ethanol model of the drink."),
    ("B8_strong_case.pdf", "Part D — The strong case (29 Oct)",
     "Closed-form model: salt + water + ethanol + ice, no stirrer, no convection, "
     "part-filled can, slush effusivity, cooling law."),
]

P = lambda t, s=body: Paragraph(t, s)


def table(rows, widths, head=True):
    data = [[P(c, small) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, 0), 0.6, TEAL),
          ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#cccccc")),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f2f2")))
    t.setStyle(TableStyle(st))
    return t


def story(starts):
    s = [Spacer(1, 30 * mm),
         P("SYPT 2027 · Problem B8 “Cold drink”", h2),
         P("The B8 reports, unified", title),
         P("All four B8 reports in one volume, with a check of where they disagree. "
           "The reports are reproduced unchanged after the discrepancy review. "
           "Each keeps its own section, equation and page numbering; the page numbers "
           "below are pages of this combined PDF.", body),
         Spacer(1, 6 * mm), P("Contents", h2)]
    rows = [["Part", "What it is", "Page"],
            ["Discrepancy review", "Where the four reports disagree, why, and which value to use.", "2"]]
    for (f, name, what), p in zip(DOCS, starts):
        rows.append([name, what + f"  <i>(source: {f})</i>", str(p)])
    s.append(table(rows, [55 * mm, 100 * mm, 12 * mm]))
    s.append(Spacer(1, 8 * mm))
    s.append(P("The nine single figures in <i>figs/</i> are already embedded in Part A, so they "
               "are not repeated.", small))
    s.append(PageBreak())

    s.append(P("Discrepancy review", h1))
    s.append(P("The four reports were written days apart, for different models, and they say so: "
               "Part A is the 24 Oct equilibrium model plus the simulator, Part B derives that "
               "same model, Part C is the second edition of the compendium, and Part D (29 Oct) "
               "is a separate closed-form model with no convection. Most differences are "
               "therefore different <b>assumptions</b>, not errors. Below, each one is "
               "classified: <b>[Conflict]</b> the reports give different answers to the same "
               "question; <b>[Constant]</b> a handbook value differs; <b>[Setup]</b> the rig is "
               "described differently; <b>[Internal]</b> a report disagrees with itself."))

    s.append(P("1 · Results that conflict", h2))
    s.append(table([
        ["Item", "A · salted ice bath", "B · derivation", "C · compendium", "D · strong case", "Assessment"],
        ["[Conflict] Rig-note charge 3.0 kg ice / 2.6 kg water / 0.95 kg salt: where the bath settles",
         "−17.78 °C, all salt dissolved", "−17.8 °C (used for L<sub>eff</sub> = 411 500 J/kg)", "—",
         "B4: −14.7 °C, regime U (needs 1.409 kg salt for the eutectic)",
         "All agree it never reaches the eutectic. The 3 K gap comes mainly from the start temperatures: "
         "A puts the water in at 4 °C, D at room temperature 25 °C. The extra 2.6 kg × 4190 × 21 K ≈ 230 kJ "
         "melts about 0.7 kg more ice and dilutes the brine. Quote the temperature together with the water "
         "start temperature, and measure it (Part A, experiment E1)."],
        ["[Conflict] Buffered charge 4.0 ice / 1.6 water / 1.0 salt: salt left solid",
         "193 g at −21.2 °C", "—", "193 g (measured diagram)", "B1: 36 g at −21.2 °C",
         "Same cause: water at 4 °C (A, C) against 25 °C (D). With 25 °C water, 1.0 kg is only just "
         "enough (D: 0.963 kg needed). To keep a real buffer, chill the water or add salt."],
        ["[Conflict] Time for the drink to reach 5 °C, Can 2",
         "222 s simulator (can lying, 28→5 °C); 169 s equilibrium model (Newton); 184 s well-mixed",
         "closed forms only", "165–246 s depending on k<sub>m</sub>, orientation, floating",
         "151–223 s depending on where the ice sits (25→5 °C, upright, no convection); lower bound 813 s "
         "with no convection inside the can",
         "Not comparable as they stand: different start temperature (28 vs 25 °C), orientation (lying vs "
         "upright) and heat-transfer physics (fitted U vs pure conduction). The spread, ~150–250 s, is a "
         "fair model uncertainty until U is measured on the rig."],
    ], [30 * mm, 27 * mm, 22 * mm, 24 * mm, 30 * mm, 41 * mm]))

    s.append(P("2 · Rig and can described differently", h2))
    s.append(table([
        ["Item", "Values in the reports", "Assessment"],
        ["[Setup] Room and drink start temperature",
         "A, C: 28 °C. D: 25 °C (also water and salt at 25 °C). B: symbolic.",
         "Pick one for the presentation; 28 °C matches the rig note."],
        ["[Setup] Water start temperature", "A, C: 4 °C. D: room temperature.",
         "The largest single cause of the conflicts above."],
        ["[Setup] Can orientation", "A, C: lying (as in the rig). D: upright, base 1 cm off the floor, held by the lid board.",
         "Both are possible; state which one each number is for."],
        ["[Setup] Headspace in Can 2",
         "A, C: measured 1.2 cm upright (41 mL), drink 10.46 cm. D: 66.5 mL, 19.6 mm, drink 97.0 mm "
         "(ideal cylinder minus 330 mL).",
         "Use the measured 1.2 cm / 41 mL: D's ideal cylinder ignores the neck and domed base, as C notes."],
        ["[Setup] Drink mass and heat capacity",
         "A, C: 330 g, c = 4000 → C<sub>d</sub> = 1332 J/K, can + drink 343 g. "
         "D: 330 mL × 1040 kg/m³ = 343 g, c = 4050 → 1402 J/K, can + drink 356 g. "
         "B: water properties (ρ = 999.1, k = 0.589).",
         "Weigh the can full and empty. The 5 % difference in C<sub>d</sub> moves t<sub>5</sub> by about 5 %. "
         "The draft in eutectic brine (C: 8.48 cm, D: 8.85 cm) follows from the mass."],
        ["[Setup] Box conductance (UA)<sub>box</sub>",
         "0.46 W/K (foam alone, rig note) and 0.34 W/K (with films and lid gaps) both appear in A and C; "
         "the A table uses 0.46, the simulator 0.34.",
         "Not a contradiction, but say which. Measure it with the box test (box_test.toml)."],
    ], [38 * mm, 78 * mm, 58 * mm]))

    s.append(P("3 · Handbook constants that differ", h2))
    s.append(table([
        ["Constant", "A", "B", "C", "D", "Note"],
        ["L<sub>f</sub> (J/kg)", "333 550", "333 550", "333 500", "333 550", "333.55 kJ/kg is the standard value."],
        ["c<sub>w</sub> (J/kg K)", "4180", "4180", "4180", "4190", "Both within the 0–30 °C range."],
        ["c<sub>i</sub> (J/kg K)", "2000 (sim: IAPWS)", "2000", "2100", "2060",
         "Ice c falls from 2097 at 0 °C to 1950 at −20 °C; so c<sub>w</sub> − c<sub>i</sub> is 2180 (A, B), 2080 (C), 2130 (D)."],
        ["c<sub>s</sub> NaCl (J/kg K)", "864", "864", "864", "860", "Negligible."],
        ["Δh<sub>s</sub>", "3.88 kJ/mol = 66.4 kJ/kg", "66 400 J/kg", "3900 J/mol = 66 735 J/kg",
         "3.88 kJ/mol", "3.88 kJ/mol is the handbook value at 25 °C, infinite dilution."],
        ["k<sub>b</sub> brine (W/m K)", "0.54; sim 0.5725 − 0.149 w", "0.54", "—", "0.52", "Within the uncertainty."],
        ["ρ<sub>b</sub> eutectic (kg/m³)", "1180 table, 1182 text; sim 1000 + 786 w", "1182", "1182",
         "1000 + 765 w (≈1177)", "Within 0.5 %."],
        ["k of can aluminium (W/m K)", "—", "160", "160", "205", "The wall resistance is negligible either way."],
        ["Freezing curve", "Bodnar fit, eutectic −21.2 °C, w = 0.2318", "same", "dilute law 2K<sub>f</sub>b (floor −22.7 °C); "
         "measured diagram as a correction", "bound-water fit K<sub>s</sub> = 3.173, ω = 0.044",
         "C's dilute law is ~2 K too warm near the eutectic, which C states. Use Bodnar."],
    ], [30 * mm, 30 * mm, 20 * mm, 30 * mm, 26 * mm, 38 * mm]))

    s.append(P("4 · Inside one report", h2))
    s.append(P("[Internal] Part A gives the SINTEF can time constant as τ ≈ 265 s in Table 1 and "
               "τ = 268 s in §7 (U<sub>0</sub> = 160 W/m²K, A = 310 cm²). The difference is rounding and does "
               "not matter. No other internal inconsistency was found in the constants and headline numbers checked."))

    s.append(P("5 · What agrees", h2))
    s.append(P("The eutectic (−21.2 °C, 23.2 wt %, 5.163 mol/kg, 0.302 kg salt per kg water); K<sub>f</sub> = 1.86 K kg/mol; "
               "Kirchhoff's law for the latent heat below 0 °C; Can 2's size (66.0 × 116.6 mm, 13 g aluminium, "
               "wall area 310 cm²); the tank (14.2 × 29.0 cm floor, 412 cm²); the film coefficients "
               "h<sub>i</sub> ≈ 400 and h<sub>o</sub> ≈ 250–300 W/m²K where they are used; that a 330 mL can floats "
               "in brine and is unstable upright, so it must be held; and the main conclusion that "
               "<b>reaching the eutectic is an energy condition, not a mass condition</b>. A, C and D all show "
               "it, and all show that the rig-note charge has no thermostat."))

    s.append(P("6 · Recommendations", h2))
    for t in [
        "Fix one set of rig inputs (room, drink, water and salt start temperatures; can orientation; "
        "measured headspace; drink mass) and rerun every model on it. Then the headline tables can be compared.",
        "Use 333.55 kJ/kg, 3.88 kJ/mol and Bodnar's freezing curve everywhere. Choose one c<sub>i</sub>, or "
        "use the IAPWS curve.",
        "Run experiment E1 (Part A) first. It decides the rig-note bath temperature and shows directly "
        "whether the water start temperature explains the A–D gap.",
        "Measure U on the rig (cool a can in a bath held at a steady temperature). That shrinks the "
        "150–250 s spread in t<sub>5</sub> more than anything else.",
    ]:
        s.append(P("• " + t))
    s.append(P("Method: text extracted from all four PDFs. Constant tables, headline results and the "
               "rig/can descriptions were compared line by line. The causes given in section 1 are "
               "energy-balance estimates; they were not checked by rerunning the models.", small))
    return s


def footer(c, d):
    c.saveState()
    c.setFont("DV", 7.5)
    c.setFillColor(colors.grey)
    c.drawString(20 * mm, 12 * mm, "B8 Cold drink · unified reports")
    c.drawRightString(190 * mm, 12 * mm, str(c.getPageNumber()))
    c.restoreState()


def build_front(starts):
    doc = SimpleDocTemplate(str(FRONT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=20 * mm, title="B8 reports, unified",
                            author="SYPT B8")
    doc.build(story(starts), onFirstPage=footer, onLaterPages=footer)
    return len(PdfReader(str(FRONT)).pages)


readers = [PdfReader(str(D / f)) for f, _, _ in DOCS]
n = build_front([0] * 4)
for _ in range(2):
    starts, p = [], n + 1
    for r in readers:
        starts.append(p)
        p += len(r.pages)
    n2 = build_front(starts)
    if n2 == n:
        break
    n = n2

w = PdfWriter()
w.append(str(FRONT), outline_item="Cover and discrepancy review", import_outline=False)
for (f, name, _), r in zip(DOCS, readers):
    w.append(r, outline_item=name, import_outline=True)
w.add_metadata({"/Title": "B8 Cold drink: the reports, unified"})
with open(OUT, "wb") as fh:
    w.write(fh)
print(OUT, len(PdfReader(str(OUT)).pages), "pages; front", n, "starts", starts)
