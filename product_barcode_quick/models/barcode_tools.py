from odoo.tools.barcode import get_barcode_check_digit

#: Lengths that are treated as GTIN family codes (EAN-8, UPC-A, EAN-13, GTIN-14)
GTIN_LENGTHS = (8, 12, 13, 14)
#: Prefixes of the default Odoo nomenclature that encode something else than a
#: plain product (weight / discount / price) or that are GS1-reserved.
RESERVED_INSTORE_PREFIXES = ("21", "22", "23")
ALLOWED_INSTORE_PREFIXES = ("20", "24", "25", "26", "27", "28", "29")


def is_gtin_like(code):
    return bool(code) and code.isdigit() and len(code) in GTIN_LENGTHS


def gtin_is_valid(code):
    """Check digit validation for EAN-8 / UPC-A / EAN-13 / GTIN-14."""
    if not is_gtin_like(code):
        return False
    return int(code[-1]) == get_barcode_check_digit(code)


def make_ean13(body12):
    """Return a full EAN-13 from its first 12 digits."""
    assert len(body12) == 12 and body12.isdigit()
    return body12 + str(get_barcode_check_digit(body12 + "0"))


def gtin_candidates(code):
    """All stored forms a scanned GTIN may match (EAN-13 <-> UPC-A <-> GTIN-14)."""
    if not code or not code.isdigit():
        return [code] if code else []
    stripped = code.lstrip("0")
    cands = {code}
    for length in GTIN_LENGTHS:
        if len(stripped) <= length:
            cands.add(stripped.rjust(length, "0"))
    return list(cands)
