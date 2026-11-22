"""Read the shipper RFP and the client's transit table from Excel."""

from io import BytesIO

from openpyxl import load_workbook


def read_sheet(source, sheet_name, column_count):
    """Return the data rows of a sheet (header skipped) as tuples of the first N columns."""
    if isinstance(source, bytes):
        source = BytesIO(source)
    workbook = load_workbook(source, read_only=True, data_only=True)
    # An uploaded RFP may be a single-sheet workbook with a different sheet name.
    sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.worksheets[0]
    rows = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if row[0] is not None:
            rows.append(row[:column_count])
    return rows


def read_rfp(source):
    lanes = []
    for origin, destination, tons, max_days, email in read_sheet(source, "Shipper RFP", 5):
        lanes.append({
            "origin": str(origin).strip().upper(),
            "destination": str(destination).strip().upper(),
            "tons": float(tons),
            "max_days": float(max_days),
            "email": str(email or ""),
        })
    return lanes


def read_transit_table(source):
    legs = []
    for origin, destination, days, services in read_sheet(source, "Transit Table", 4):
        legs.append({
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "days": float(days),
            "services": [s.strip() for s in (services or "").split(";") if s.strip()],
        })
    return legs
