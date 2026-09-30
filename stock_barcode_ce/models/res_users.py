from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _bc_set_scanner_home(self):
        action = self.env.ref("stock_barcode_ce.action_stock_barcode_ce_main", raise_if_not_found=False)
        if not action:
            return
        for user in self:
            if (not user.action_id and user.has_group("stock_barcode_ce.group_barcode_operator")
                    and not user.has_group("stock.group_stock_user")):
                user.sudo().action_id = action.id

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._bc_set_scanner_home()
        return users

    def write(self, vals):
        res = super().write(vals)
        if any(k.startswith("group") or k.startswith("sel_groups") or k.startswith("in_group") or k == "group_ids" for k in vals):
            self._bc_set_scanner_home()
        return res
