import pymupdf
import pytest

from mining_rights_agent.pdf.parser import extract_resource_records


def test_extracts_resource_rows_with_page_provenance() -> None:
    document = pymupdf.open()
    page = document.new_page()
    text = (
        "NI 43-101 Mineral Resource Estimate\n"
        "Classification Tonnes (Mt) Grade (g/t Au) Contained Gold (oz)\n"
        "Indicated 12.5 1.20 480000\n"
        "Inferred 4.2 0.95 128000"
    )
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 300), text, fontsize=10)
    records = extract_resource_records(document.tobytes(), "https://example.com/report.pdf")

    assert len(records) == 2
    assert records[0].classification == "Indicated"
    assert records[0].tonnage_mt == pytest.approx(12.5)
    assert records[0].grade_unit == "g/t Au"
    assert records[0].source_page == 1
    assert records[0].reporting_code == "NI 43-101"
