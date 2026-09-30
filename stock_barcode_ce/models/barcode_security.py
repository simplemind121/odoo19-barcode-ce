from odoo import _
from odoo.exceptions import AccessError


def bc_is_supervisor(env):
    return env.user.has_group("stock_barcode_ce.group_barcode_supervisor")


def bc_guard(records):
    """Entry check of every scanner API method.

    Inventory users keep their normal rights. Scanner-only operators have read
    access to the stock models: once the records passed the read check (ACL +
    record rules, so multi-company is respected) the scan engine runs in sudo
    mode. `sudo()` keeps the real user id, so create_uid/write_uid, chatter and
    the scan log still show who did it.
    """
    env = records.env
    if env.su or env.user.has_group("stock.group_stock_user"):
        return records
    if env.user.has_group("stock_barcode_ce.group_barcode_operator"):
        if records:
            records.check_access("read")
        return records.sudo()
    raise AccessError(_("You are not allowed to use the barcode scanner."))


def bc_require_supervisor(env, what):
    if not bc_is_supervisor(env):
        raise AccessError(_("Only a barcode supervisor can %s.", what))
