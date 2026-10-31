"""Generate the Word report from the existing simulation outputs."""

import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
ASSETS = ROOT / "assets"


def add_table(doc, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = Inches(width)
    for cell, width, label in zip(table.rows[0].cells, widths, headers):
        cell.width = Inches(width)
        cell.text = label
    for row in rows:
        for cell, width, value in zip(table.add_row().cells, widths, row):
            cell.width = Inches(width)
            cell.text = str(value)
    for index, row in enumerate(table.rows):
        # Keep each record together and repeat the header if Word repaginates.
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if index == 0:
            trpr.append(OxmlElement("w:tblHeader"))
        for column, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "E8EEF3" if index == 0 else ("F6F8FA" if index % 2 == 0 else "FFFFFF"))
            tcpr.append(shade)
            borders = OxmlElement("w:tcBorders")
            for side in ["top", "left", "bottom", "right"]:
                edge = OxmlElement(f"w:{side}")
                edge.set(qn("w:val"), "single")
                edge.set(qn("w:sz"), "5")
                edge.set(qn("w:color"), "D9D9D9")
                borders.append(edge)
            tcpr.append(borders)
            margins = OxmlElement("w:tcMar")
            for side in ["top", "left", "bottom", "right"]:
                margin = OxmlElement(f"w:{side}")
                margin.set(qn("w:w"), "80")
                margin.set(qn("w:type"), "dxa")
                margins.append(margin)
            tcpr.append(margins)
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT if column == 0 else WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    run.font.size = Pt(10.5)
                    run.bold = index == 0
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def add_picture(doc, filename, width=6.4, caption=None, alt=None):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_with_next = caption is not None
    shape = paragraph.add_run().add_picture(str((RESULTS / filename) if (RESULTS / filename).exists() else (ASSETS / filename)), width=Inches(width))
    shape._inline.docPr.set("descr", alt or caption or filename)
    if caption:
        paragraph = doc.add_paragraph(caption, style="Caption")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def code_line(doc, text):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(text)
    run.font.name = "DejaVu Sans Mono"
    run.font.size = Pt(9.5)


def code_block(doc, text):
    """Editable code in the plain monospaced style used by the sample."""
    lines = text.strip("\n").splitlines()
    for index, line in enumerate(lines):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(7 if index == len(lines) - 1 else 0)
        p.paragraph_format.line_spacing = Pt(11)
        p.paragraph_format.keep_with_next = index < len(lines) - 1
        r = p.add_run(line or " ")
        r.font.name = "DejaVu Sans Mono"
        r.font.size = Pt(9)


def cover_artwork(section):
    """Anchor the unchanged artwork from the supplied cover to the page."""
    p = section.header.paragraphs[0]
    p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
    shape = p.add_run().add_picture(str(ASSETS / "cover_artwork.png"),
                                    width=Pt(208), height=Pt(793))
    shape._inline.docPr.set("descr", "University cover artwork from the supplied report template")
    inline = shape._inline
    anchor = OxmlElement("wp:anchor")
    for key, value in {"distT":"0", "distB":"0", "distL":"0", "distR":"0",
                       "simplePos":"0", "relativeHeight":"0", "behindDoc":"1",
                       "locked":"0", "layoutInCell":"1", "allowOverlap":"1"}.items():
        anchor.set(key, value)
    simple = OxmlElement("wp:simplePos")
    simple.set("x", "0")
    simple.set("y", "0")
    anchor.append(simple)
    for axis in ["H", "V"]:
        position = OxmlElement("wp:position" + axis)
        position.set("relativeFrom", "page")
        offset = OxmlElement("wp:posOffset")
        offset.text = str(26 * 12700)
        position.append(offset)
        anchor.append(position)
    for tag in ["wp:extent", "wp:effectExtent"]:
        child = inline.find(qn(tag))
        if child is not None:
            anchor.append(child)
    anchor.append(OxmlElement("wp:wrapNone"))
    for tag in ["wp:docPr", "wp:cNvGraphicFramePr", "a:graphic"]:
        child = inline.find(qn(tag))
        if child is not None:
            anchor.append(child)
    inline.getparent().replace(inline, anchor)


def make_cover(doc):
    section = doc.sections[0]
    section.page_width, section.page_height = Pt(595.32), Pt(841.92)
    section.top_margin, section.bottom_margin = Pt(72), Pt(40)
    section.left_margin, section.right_margin = Pt(245), Pt(69)
    section.header_distance = Pt(0)
    cover_artwork(section)
    cursor = 72.0
    def line(text, y, size=12, title=False):
        nonlocal cursor
        p = doc.add_paragraph(style="Title" if title else "Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(max(0, y - cursor))
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(size + 5)
        p.paragraph_format.keep_with_next = False
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.bold = True
        r.font.color.rgb = RGBColor(0, 0, 0)
        cursor = y + len(text.split("\n")) * (size + 5)
    line("A", 72)
    line("EXAM PRACTICAL REPORT", 121)
    line("ON", 194)
    line("Model Predictive Control\nof a Double Integrator\nin Python", 244, size=16, title=True)
    line("WRITTEN BY", 324)
    line("MOHAMMAD AZIMI", 372, size=16)
    line("Group No. 5140201/50302", 400, size=16)
    line("ON", 470)
    line("INTELLIGENT SYSTEMS", 495, size=14)
    line("October 31, 2026", 746)


def start_body(doc):
    section = doc.add_section(WD_SECTION_START.NEW_PAGE)
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    section.top_margin = section.bottom_margin = Pt(72)
    section.left_margin = section.right_margin = Pt(72)
    section.header_distance = Pt(36)
    section.footer_distance = Pt(31)
    page_number = OxmlElement("w:pgNumType")
    page_number.set(qn("w:start"), "1")
    section._sectPr.append(page_number)
    p = section.footer.paragraphs[0]
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(0)
    borders = OxmlElement("w:pBdr")
    border = OxmlElement("w:top")
    for key, value in {"val":"single", "sz":"4", "color":"D9D9D9", "space":"3"}.items():
        border.set(qn("w:" + key), value)
    borders.append(border)
    p._p.get_or_add_pPr().append(borders)
    run = p.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t")
    value.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for item in [begin, instruction, separate, value, end]:
        run._r.append(item)
    p.add_run(" | ").bold = True
    p.add_run("Page").font.color.rgb = RGBColor.from_string("777777")
    for run in p.runs:
        run.font.size = Pt(11)


def heading(doc, text, centered=False):
    p = doc.add_heading(text, level=1)
    if centered:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def main():
    data = json.loads((RESULTS / "metrics.json").read_text(encoding="utf-8"))
    verification = json.loads((RESULTS / "verification.json").read_text(encoding="utf-8"))
    if verification["status"] != "PASS":
        raise RuntimeError("Run verify_mpc.py successfully before creating the report.")
    baseline, tighter, longer = data["metrics"]
    doc = Document()
    for style in ["Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Caption"]:
        doc.styles[style].font.name = "Calibri"
        doc.styles[style].font.color.rgb = RGBColor(0, 0, 0)
        for border in list(doc.styles[style].element.xpath("./w:pPr/w:pBdr")):
            border.getparent().remove(border)
    doc.styles["Normal"].font.size = Pt(12)
    doc.styles["Normal"].paragraph_format.line_spacing = Pt(17)
    doc.styles["Normal"].paragraph_format.space_after = Pt(8)
    doc.styles["Heading 1"].font.size = Pt(15)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(10)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(8)
    doc.styles["Heading 1"].paragraph_format.keep_with_next = True
    doc.styles["Caption"].font.size = Pt(10)
    doc.styles["Caption"].font.bold = False
    doc.styles["Caption"].paragraph_format.space_after = Pt(7)
    doc.core_properties.title = "Model Predictive Control of a Double Integrator in Python"
    doc.core_properties.subject = "Intelligent Systems practical task 04"
    doc.core_properties.author = "Mohammad Azimi"
    make_cover(doc)
    start_body(doc)

    # Printed page 1: introduction, plant and graphical model.
    intro = heading(doc, "INTRODUCTION", centered=True)
    for run in intro.runs:
        run.font.size = Pt(18)
    doc.add_paragraph(
        "Model predictive control uses a mathematical model to predict a system's "
        "future response and select suitable control inputs. At each sample, the "
        "controller solves a constrained optimization problem, applies its first "
        "planned input, and repeats the calculation using the updated state.")
    doc.add_paragraph(
        "This practical implements the plant and baseline tuning of the MathWorks "
        "single-input, single-output example [1] in Python. The objective is to move "
        "the output from zero to a unit reference while respecting input limits. "
        "The experiment compares the baseline with a tighter input limit and a "
        "longer prediction horizon.")
    heading(doc, "Define the Plant Model", centered=True)
    doc.add_paragraph(
        "The plant is a double integrator. Its input u represents acceleration, "
        "its output y represents position, and v is velocity. A unit mass moving "
        "without friction provides a physical interpretation.")
    add_picture(doc, "plant_equations.png", width=6.1,
                alt="Double integrator and exact discrete position and velocity equations")
    code_block(doc, """ts = sample_time
A = np.array([[1.0, ts], [0.0, 1.0]])
B = np.array([0.5 * ts**2, ts])
C = np.array([1.0, 0.0])""")
    doc.add_paragraph(
        "These discrete equations are exact for an input held constant during "
        "each interval. The sampling time is 0.1 s and the initial position and "
        "velocity are both zero.")
    heading(doc, "Control Structure")
    add_picture(doc, "control_structure.png", width=6.0,
                caption="Figure 1  Simulation structure with exact state feedback")

    # Printed page 2: controller design and optimization.
    doc.add_page_break()
    heading(doc, "Design the MPC Controller")
    doc.add_paragraph(
        "The controller predicts Np future outputs and optimizes Nc control inputs. "
        "The final planned input is held constant after the control horizon. The "
        "cost penalizes position error and changes in the input.")
    add_picture(doc, "cost_equations.png", width=6.1,
                alt="Quadratic MPC objective and symmetric input constraints")
    doc.add_paragraph(
        "The tracking weight q is 1 and the input-change weight rho is 0.1. The "
        "first input change is measured relative to the previously applied input. "
        "Both acceleration and braking are limited by the symmetric bounds.")
    add_table(doc, ["Scenario", "Np", "Nc", "Input bounds"], [
        ["Baseline", "10", "3", "-1 to 1"],
        ["Tighter input limit", "10", "3", "-0.4 to 0.4"],
        ["Longer prediction horizon", "20", "3", "-1 to 1"],
    ], [2.75, 0.6, 0.6, 2.25])
    heading(doc, "Specify the Cost and Input Constraints")
    doc.add_paragraph(
        "The linear model gives predictions of the form Y = F x + G U. Expanding "
        "the tracking and input-change penalties produces a convex quadratic "
        "program. The Hessian H is positive definite, so the optimal planned "
        "sequence is unique. The relevant solver call is:")
    code_block(doc, """result = minimize(
    lambda u: 0.5 * u @ self.H @ u + f @ u,
    self.guess,
    jac=lambda u: self.H @ u + f,
    method="SLSQP",
    bounds=[(-s.input_limit, s.input_limit)]
           * s.control_horizon,
    options={"ftol": 1e-12, "maxiter": 150},
)""")
    doc.add_paragraph(
        "SciPy SLSQP [2] receives the analytic gradient and the input bounds. "
        "A shifted previous solution initializes the next solve. Only the first "
        "element of each optimized sequence is applied to the plant.")

    # Printed page 3: execution and baseline figure.
    doc.add_page_break()
    heading(doc, "Run the Simulation")
    doc.add_paragraph(
        "Each simulation lasts 10 s, giving 100 optimization steps and 101 "
        "recorded states. The reference remains at 1. The position and velocity "
        "are updated using the exact discrete plant equations.")
    code_block(doc, """for k in range(n):
    inputs[k], residuals[k], iterations[k] = (
        controller.control(state[k], previous_input)
    )
    state[k + 1] = (
        controller.A @ state[k]
        + controller.B * inputs[k]
    )
    previous_input = inputs[k]""")
    heading(doc, "Evaluate the Baseline Response")
    add_picture(doc, "baseline_response.png", width=6.1,
                caption="Figure 2  Baseline position and control input")
    doc.add_paragraph(
        f"The baseline reaches a 2% settling band in {baseline['settling_time_2pct_s']:.1f} s "
        f"with {baseline['overshoot_pct']:.2f}% overshoot. Positive input initially "
        "accelerates the system toward the reference. Negative input then slows "
        "the motion. The input stays between -1 and 1 throughout the run.")

    # Printed page 4: comparison figure and measured results.
    doc.add_page_break()
    heading(doc, "Compare Different Controller Settings")
    doc.add_paragraph(
        "Only one parameter changes in each comparison with the baseline. "
        "Prediction horizons of 10 and 20 samples correspond to 1 s and 2 s. "
        "The control horizon remains three samples.")
    add_picture(doc, "response_comparison.png", width=6.1,
                caption="Figure 3  Output tracking and inputs for all three settings")
    add_table(doc, ["Scenario", "RMSE", "Settling s", "Overshoot %"], [
        [row["scenario"], f"{row['rmse']:.4f}",
         f"{row['settling_time_2pct_s']:.1f}", f"{row['overshoot_pct']:.2f}"]
        for row in data["metrics"]
    ], [2.75, 0.95, 1.15, 1.35])
    doc.add_paragraph(
        "RMSE uses all 101 sampled positions. Settling time is the first sample "
        "after the last exit from the 0.98 to 1.02 band, with no later exit during "
        "the simulation. Overshoot measures the maximum position above the unit "
        "reference. The CSV files contain the full trajectories and additional metrics.")

    # Printed page 5: discussion and numerical verification.
    doc.add_page_break()
    heading(doc, "Discuss the Results")
    doc.add_paragraph(
        f"Reducing the input limit from 1 to 0.4 increases settling time from "
        f"{baseline['settling_time_2pct_s']:.1f} s to {tighter['settling_time_2pct_s']:.1f} s "
        f"and overshoot from {baseline['overshoot_pct']:.2f}% to {tighter['overshoot_pct']:.2f}%. "
        "The limit restricts both acceleration and braking. With the same short "
        "prediction horizon, the restricted controller overshoots more. This "
        "observation applies to these settings and is not a general rule for "
        "every MPC design.")
    doc.add_paragraph(
        f"Increasing the prediction horizon from 10 to 20 samples reduces "
        f"overshoot to {longer['overshoot_pct']:.2f}% and settling time to "
        f"{longer['settling_time_2pct_s']:.1f} s. RMSE changes only slightly. "
        "The position curves are similar during their initial acceleration, "
        "when both designs use the same maximum available input.")
    heading(doc, "Verify the Numerical Results")
    doc.add_paragraph(
        "All 300 optimization solves completed successfully and respected their "
        "input bounds. A projected-gradient residual checks whether each "
        "solution satisfies the optimality conditions for the bounded problem. "
        "Every recorded residual is below the tolerance of 0.00002.")
    code_block(doc, """gradient = self.H @ result.x + f
projected = np.clip(
    result.x - gradient,
    -s.input_limit, s.input_limit
)
residual = np.max(np.abs(result.x - projected))""")
    doc.add_paragraph(
        "Independent checks compare the plant with the constant-acceleration "
        "solution, the prediction matrices with direct simulation, and the "
        "analytic gradient with central differences. An enumeration of active "
        "constraints verifies nine representative QP solutions. The saved "
        "trajectories satisfy the model equations, and all final position "
        "errors are below 0.0001.")
    heading(doc, "Implementation Assumptions")
    doc.add_paragraph(
        "The controller receives exact simulated position and velocity. "
        "Measurement noise, a Kalman filter, output-disturbance estimation and "
        "model mismatch are not included. These plots are independent Python "
        "simulation results. The problem has no terminal cost or terminal "
        "constraint, and the finite runs do not establish asymptotic stability.")

    # Printed page 6: conclusion, run instructions and sources.
    doc.add_page_break()
    heading(doc, "Conclusion")
    doc.add_paragraph(
        "The Python implementation tracks the unit reference while enforcing "
        "the input bounds in every control step. The experiments demonstrate "
        "that actuator limits and prediction horizon affect the transient "
        "response. For this plant and tuning, extending the prediction horizon "
        "reduces overshoot and settling time. Tightening the actuator limit "
        "while retaining the shorter horizon produces a slower response and "
        "greater overshoot.")
    heading(doc, "Run the Project")
    doc.add_paragraph(
        "Open a terminal in the project folder and execute the following "
        "commands. Python 3.10 or newer is required.")
    code_block(doc, """python -m pip install -r requirements.txt
python mpc_simulation.py
python verify_mpc.py
python make_report.py""")
    doc.add_paragraph(
        "NumPy performs the matrix calculations, SciPy solves the optimization "
        "problems, Matplotlib creates the figures, and python-docx generates "
        "the Word report. Plots and numeric data are saved in the results "
        "folder. The supplied report includes actual simulation results.")
    doc.add_paragraph(
        "The delivered run used Python 3.12, NumPy 2.3.5, SciPy 1.17.0, "
        "Matplotlib 3.10.8 and python-docx 1.2.0.")
    heading(doc, "References")
    for text in [
        "[1] MathWorks. Model Predictive Control of a Single-Input-Single-Output Plant. "
        "https://www.mathworks.com/help/mpc/gs/control-of-a-single-input-single-output-plant.html",
        "[2] SciPy. scipy.optimize.minimize with method SLSQP. "
        "https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html",
    ]:
        p = doc.add_paragraph(text)
        p.paragraph_format.line_spacing = Pt(14)
        for run in p.runs:
            run.font.size = Pt(10)
    destination = ROOT / "MPC_Python_Report.docx"
    doc.save(destination)
    print(destination)


if __name__ == "__main__":
    main()
