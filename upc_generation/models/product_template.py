from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    generate_upc = fields.Boolean(
        string='Generate UPC',
        default=False,
        help="Flag set during import so a later batch action can find and "
             "process these products. Does not trigger any automatic generation.",
    )
