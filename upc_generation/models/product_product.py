from odoo import _, fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    upc_generated = fields.Boolean(string='UPC Generated', default=False, readonly=True)
    barcode_source = fields.Selection(
        [
            ('manual', 'Manual'),
            ('generated_upc', 'Generated UPC'),
            ('imported', 'Imported'),
        ],
        string='Barcode Source',
        readonly=True,
    )
    upc_prefix_id = fields.Many2one(
        'upc.prefix',
        string='UPC Prefix',
        readonly=True,
        ondelete='restrict',
    )
    upc_ref = fields.Integer(string='UPC Reference', readonly=True)
    upc_assigned_on = fields.Datetime(string='UPC Assigned On', readonly=True)

    def write(self, vals):
        if 'barcode' in vals:
            for rec in self:
                if rec.upc_generated:
                    raise UserError(_(
                        "Cannot modify barcode on products with generated UPCs. "
                        "Generated UPCs are immutable."
                    ))
        return super().write(vals)
