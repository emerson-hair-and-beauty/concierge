"""
Merge a refreshed Product Matrix (from Shopify) with the previous one.

The refreshed file has the current product list, names, prices, sizes, links,
images and shop status. It also replaces Emerson's hand-written assessment with
blanks or values inferred from the ingredient list. This script keeps Emerson's
values wherever the previous file had them, and uses the refreshed values only
where the previous file had nothing (mostly new products). Draft products are
left out, because guests cannot buy them.

Run from the project root:
    python scripts/merge_product_matrix.py <previous.xlsx> <refreshed.xlsx> <merged.xlsx>
"""
import sys

import openpyxl

FIRST_ROW = 8                     # product rows start under the headers in row 7
SKU, STATUS = 2, 34               # 1-based columns: B = SKU, AH = Shopify Status
# Emerson's own columns: E (Product Category) and H..AC (Primary Focus .. Best Seller).
KEEP_FROM_PREVIOUS = [5] + list(range(8, 30))


def main(previous_path: str, refreshed_path: str, merged_path: str) -> None:
    previous = openpyxl.load_workbook(previous_path, data_only=True)["Summary"]
    by_sku = {}
    for row in previous.iter_rows(min_row=FIRST_ROW):
        sku = row[SKU - 1].value
        if sku and not str(sku).startswith("="):
            by_sku.setdefault(str(sku).strip(), row)

    wb = openpyxl.load_workbook(refreshed_path)
    ws = wb["Summary"]
    # Some cells (for example Product Name) are formulas that look up the Shopify
    # Catalog tab. openpyxl cannot calculate formulas, and a saved file loses their
    # last values. So store each formula's last value instead of the formula.
    values = openpyxl.load_workbook(refreshed_path, data_only=True)["Summary"]
    for row in ws.iter_rows(min_row=FIRST_ROW):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.value = values.cell(cell.row, cell.column).value

    kept = filled = drafts = 0
    for r in range(ws.max_row, FIRST_ROW - 1, -1):          # bottom up, so deletes do not shift unread rows
        sku = ws.cell(r, SKU).value
        if not sku:
            continue
        if ws.cell(r, STATUS).value != "Active":
            ws.delete_rows(r)
            drafts += 1
            continue
        old = by_sku.get(str(sku).strip())
        if old is None:
            continue
        kept += 1
        for col in KEEP_FROM_PREVIOUS:
            value = old[col - 1].value
            if value not in (None, ""):
                ws.cell(r, col).value = value
                filled += 1

    wb.save(merged_path)
    print(f"Kept Emerson's values for {kept} products ({filled} cells). Left out {drafts} draft rows.")
    print(f"Saved: {merged_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
