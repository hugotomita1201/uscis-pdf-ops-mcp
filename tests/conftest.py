from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def build_fixture_pdf(path: Path) -> None:
    canv = canvas.Canvas(str(path), pagesize=letter)
    form = canv.acroForm

    canv.drawString(72, 740, "Full Name")
    form.textfield(
        name="full_name",
        tooltip="Full Name",
        x=160,
        y=730,
        width=180,
        height=20,
        value="",
        forceBorder=True,
    )

    canv.drawString(72, 700, "Notes")
    form.textfield(
        name="notes",
        tooltip="Notes",
        x=160,
        y=650,
        width=220,
        height=50,
        value="",
        forceBorder=True,
        fieldFlags="multiline",
        maxlen=100,
    )

    canv.drawString(72, 620, "Consent")
    form.checkbox(
        name="consent_box",
        tooltip="Consent",
        x=160,
        y=612,
        buttonStyle="check",
        checked=False,
        forceBorder=True,
    )

    canv.drawString(72, 580, "Color")
    form.radio(name="color_group", tooltip="Red", value="Red", selected=False, x=160, y=572, buttonStyle="circle")
    canv.drawString(182, 580, "Red")
    form.radio(name="color_group", tooltip="Blue", value="Blue", selected=False, x=220, y=572, buttonStyle="circle")
    canv.drawString(242, 580, "Blue")

    canv.drawString(72, 540, "Status")
    form.choice(
        name="status_choice",
        tooltip="Status",
        x=160,
        y=530,
        width=120,
        height=20,
        options=[("Initial", "Initial"), ("Renewal", "Renewal"), ("Approved", "Approved")],
        value="Initial",
        fieldFlags="combo",
        forceBorder=True,
    )

    canv.save()


@pytest.fixture
def fillable_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "fillable-form.pdf"
    build_fixture_pdf(pdf)
    return pdf

