"""Raw TSPL / ZPL generation for thermal label printers.

Text is rendered server side as a 1-bit bitmap (so Chinese and any other script
print the same on every printer, without printer fonts). Barcodes use the
printer's native barcode commands, which are sharper and always scannable.
"""
import io
import logging
import os

from odoo import api, models

from odoo.addons.product_barcode_quick.models.barcode_tools import gtin_is_valid

_logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size_px):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size_px)
            except OSError:
                continue
    return ImageFont.load_default()


def text_bitmap(lines, width_dots, max_lines_per_item=2):
    """lines: list of (text, size_px, align). Returns a PIL '1' image (black text on white),
    width rounded to a multiple of 8."""
    width = (width_dots // 8) * 8
    rendered = []
    for text, size, align in lines:
        if not text:
            continue
        font = _font(size)
        draw = ImageDraw.Draw(Image.new("1", (1, 1)))
        # greedy wrap on characters (works for CJK and latin)
        out, cur = [], ""
        for ch in str(text):
            trial = cur + ch
            if draw.textlength(trial, font=font) <= width or not cur:
                cur = trial
            else:
                out.append(cur)
                cur = ch
        if cur:
            out.append(cur)
        if len(out) > max_lines_per_item:
            out = out[:max_lines_per_item]
            out[-1] = out[-1][:-1] + "…"
        for line in out:
            rendered.append((line, font, align, size))
    height = sum(int(size * 1.2) for *_x, size in rendered) or 1
    img = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(img)
    y = 0
    for line, font, align, size in rendered:
        w = draw.textlength(line, font=font)
        x = {"left": 0, "center": (width - w) / 2, "right": width - w}[align]
        draw.text((x, y), line, font=font, fill=0)
        y += int(size * 1.2)
    return img


def bitmap_rows(img, black_bit):
    """Pack a '1' image into bytes rows. black_bit: value of a bit that prints black."""
    width, height = img.size
    px = img.load()
    rows = []
    for y in range(height):
        row = bytearray()
        for xb in range(0, width, 8):
            byte = 0
            for bit in range(8):
                is_black = px[xb + bit, y] == 0
                val = black_bit if is_black else 1 - black_bit
                byte = (byte << 1) | val
            row.append(byte)
        rows.append(bytes(row))
    return rows


class BarcodeLabelRender(models.AbstractModel):
    _name = "barcode.label.render"
    _description = "Thermal label raw command renderer"

    # --------------------------------------------------------------
    # label contents
    # --------------------------------------------------------------
    @api.model
    def _content_product(self, product, price=True):
        lines = [(product.display_name, "title")]
        sub = product.default_code or ""
        if price:
            symbol = product.currency_id.symbol or ""
            sub = ("%s  %s%.2f" % (sub, symbol, product.lst_price)).strip()
        if sub:
            lines.append((sub, "sub"))
        return {"lines": lines, "barcode": product.barcode or ""}

    @api.model
    def _content_lot(self, lot):
        lines = [(lot.product_id.display_name, "title"), (lot.name, "sub")]
        exp = getattr(lot, "expiration_date", False)
        if exp:
            lines.append(("EXP %s" % exp.strftime("%Y-%m-%d"), "sub"))
        return {"lines": lines, "barcode": lot.name}

    @api.model
    def _content_location(self, location):
        return {"lines": [(location.name, "title"), (location.location_id.complete_name or "", "sub")],
                "barcode": location.barcode or location.complete_name}

    @api.model
    def _content_package(self, package):
        return {"lines": [(package.name, "title"), (package.content_description or "", "sub")],
                "barcode": package.name}

    # --------------------------------------------------------------
    # raw commands
    # --------------------------------------------------------------
    @api.model
    def render(self, printer, contents):
        """contents: list of (content dict, copies). Returns bytes for the printer."""
        dots = 8 if printer.dpi == "203" else 12  # dots per mm
        w, h = int(printer.width_mm * dots), int(printer.height_mm * dots)
        margin = int(1.5 * dots)
        out = b""
        for content, copies in contents:
            if copies <= 0:
                continue
            out += self._render_one(printer, content, copies, w, h, dots, margin)
        return out

    @api.model
    def _layout(self, content, w, h, dots, margin):
        title_px = int(2.9 * dots) if h >= 35 * dots else int(2.5 * dots)
        sub_px = int(2.1 * dots)
        lines = [(txt, title_px if kind == "title" else sub_px, "left") for txt, kind in content["lines"]]
        bmp = text_bitmap(lines, w - 2 * margin)
        barcode_h = max(int(h * 0.32), 6 * dots)
        # keep the text above the barcode + its human readable line
        max_text_h = h - margin - barcode_h - int(3.5 * dots) - margin
        if bmp.size[1] > max_text_h:
            bmp = bmp.crop((0, 0, bmp.size[0], max(max_text_h, 1)))
        code = content["barcode"]
        symbology = "EAN13" if code.isdigit() and len(code) == 13 and gtin_is_valid(code) else "128"
        # narrow bar width in dots: as wide as the label allows
        modules = 95 if symbology == "EAN13" else 11 * len(code) + 35
        narrow = max(1, min(4, (w - 2 * margin) // max(modules, 1)))
        bar_w = modules * narrow
        bar_x = max(margin, (w - bar_w) // 2)
        bar_y = h - margin - barcode_h - int(3 * dots)
        return bmp, code, symbology, narrow, bar_x, bar_y, barcode_h

    @api.model
    def _render_one(self, printer, content, copies, w, h, dots, margin):
        bmp, code, symbology, narrow, bar_x, bar_y, bar_h = self._layout(content, w, h, dots, margin)
        if printer.language == "zpl":
            rows = bitmap_rows(bmp, black_bit=1)
            data_hex = b"".join(rows).hex().upper()
            bytes_per_row = len(rows[0]) if rows else 0
            total = bytes_per_row * len(rows)
            parts = [
                "^XA", "^CI28", "^PW%d" % w, "^LL%d" % h, "^LH0,0", "~SD%02d" % printer.darkness,
                "^FO%d,%d^GFA,%d,%d,%d,%s^FS" % (margin, margin, total, total, bytes_per_row, data_hex),
            ]
            if code:
                if symbology == "EAN13":
                    parts.append("^FO%d,%d^BY%d^BEN,%d,Y,N^FD%s^FS" % (bar_x, bar_y, narrow, bar_h, code[:12]))
                else:
                    parts.append("^FO%d,%d^BY%d^BCN,%d,Y,N,N^FD%s^FS" % (bar_x, bar_y, narrow, bar_h, code))
            parts += ["^PQ%d" % copies, "^XZ"]
            return ("\n".join(parts) + "\n").encode("utf-8")
        # TSPL
        rows = bitmap_rows(bmp, black_bit=1 if printer.tspl_invert else 0)
        bytes_per_row = len(rows[0]) if rows else 0
        head = [
            "SIZE %s mm,%s mm" % (printer.width_mm, printer.height_mm),
            "GAP %s mm,0 mm" % printer.gap_mm,
            "DIRECTION 1,0",
            "REFERENCE 0,0",
            "DENSITY %d" % min(15, printer.darkness // 2),
            "CLS",
        ]
        out = ("\r\n".join(head) + "\r\n").encode("ascii")
        out += ("BITMAP %d,%d,%d,%d,0," % (margin, margin, bytes_per_row, len(rows))).encode("ascii")
        out += b"".join(rows) + b"\r\n"
        if code:
            if symbology == "EAN13":
                out += ('BARCODE %d,%d,"EAN13",%d,1,0,%d,%d,"%s"\r\n' % (bar_x, bar_y, bar_h, narrow, narrow, code[:12])).encode("ascii")
            else:
                safe = code.replace('"', "'")
                out += ('BARCODE %d,%d,"128",%d,1,0,%d,%d,"%s"\r\n' % (bar_x, bar_y, bar_h, narrow, narrow, safe)).encode("utf-8")
        out += ("PRINT 1,%d\r\n" % copies).encode("ascii")
        return out
