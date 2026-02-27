"""
### FILE: utils/pdf_generator.py
Utility to generate PDF reports using ReportLab and Plotly images.
Requires: reportlab and kaleido (for fig.write_image)
"""
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import os
from typing import List


def generate_pdf(report_title: str, image_paths: List[str], out_path: str = "report.pdf", notes: str = None):
    doc = SimpleDocTemplate(out_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(report_title, styles["Title"]))
    story.append(Spacer(1, 0.2 * cm))

    if notes:
        story.append(Paragraph(notes, styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

    for img in image_paths:
        if not os.path.exists(img):
            continue
        try:
            story.append(Image(img, width=17 * cm, height=9 * cm))
            story.append(Spacer(1, 0.2 * cm))
        except Exception:
            # skip bad images
            continue

    doc.build(story)
    return out_path