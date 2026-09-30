def migrate(cr, version):
    """1.x stored the scanned quantity on stock.move.line.bc_qty; 2.0 computes it from events.
    Keep the old column aside so post-migrate can turn it into events."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stock_move_line' AND column_name = 'bc_qty'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE stock_move_line RENAME COLUMN bc_qty TO bc_qty_v1")
