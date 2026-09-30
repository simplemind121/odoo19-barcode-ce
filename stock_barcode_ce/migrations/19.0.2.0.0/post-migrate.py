import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stock_move_line' AND column_name = 'bc_qty_v1'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        INSERT INTO stock_barcode_scan_event
            (move_line_id, picking_id, product_id, qty, kind, user_id, company_id,
             create_uid, create_date, write_uid, write_date)
        SELECT ml.id, ml.picking_id, ml.product_id, ml.bc_qty_v1, 'migrated',
               COALESCE(ml.write_uid, 1), ml.company_id,
               COALESCE(ml.write_uid, 1), NOW() AT TIME ZONE 'UTC', COALESCE(ml.write_uid, 1), NOW() AT TIME ZONE 'UTC'
        FROM stock_move_line ml
        WHERE ml.bc_qty_v1 IS NOT NULL AND ml.bc_qty_v1 <> 0 AND ml.state NOT IN ('done', 'cancel')
    """)
    _logger.info("stock_barcode_ce: %s in-progress scanned quantities migrated to scan events", cr.rowcount)
    cr.execute("ALTER TABLE stock_move_line DROP COLUMN bc_qty_v1")
