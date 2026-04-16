import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.upc_prefix import generate_upc_a


_logger = logging.getLogger(__name__)


STATUS_SELECTION = [
    ('WILL_GENERATE', 'Will generate'),
    ('GENERATED', 'Generated'),
    ('SKIP_EXISTING_BARCODE', 'Skip: existing barcode'),
    ('SKIP_UPC_EXISTS', 'Skip: UPC already generated'),
    ('SKIP_NO_ACTIVE_PREFIX', 'Skip: no active prefix'),
    ('SKIP_PREFIX_EXHAUSTED', 'Skip: prefix exhausted'),
]


class UpcGenerationWizard(models.TransientModel):
    _name = 'upc.generation.wizard'
    _description = 'UPC Generation Wizard'

    prefix_id = fields.Many2one('upc.prefix', string='Active Prefix', readonly=True)
    prefix_display = fields.Char(
        string='Prefix',
        compute='_compute_prefix_display',
    )
    remaining_before = fields.Integer(string='Remaining Before', readonly=True)
    eligible_count = fields.Integer(string='Will Generate', readonly=True)
    skip_existing_count = fields.Integer(string='Skip: Existing Barcode', readonly=True)
    skip_generated_count = fields.Integer(string='Skip: Already Generated', readonly=True)
    skip_other_count = fields.Integer(string='Skip: Other', readonly=True)
    remaining_after = fields.Integer(string='Remaining After', readonly=True)
    state = fields.Selection(
        [('preview', 'Preview'), ('done', 'Done')],
        string='State',
        default='preview',
    )
    line_ids = fields.One2many(
        'upc.generation.wizard.line',
        'wizard_id',
        string='Lines',
    )
    product_template_ids = fields.Many2many(
        'product.template',
        'upc_wizard_template_rel',
        'wizard_id',
        'template_id',
        string='Source Templates',
    )
    product_ids = fields.Many2many(
        'product.product',
        'upc_wizard_product_rel',
        'wizard_id',
        'product_id',
        string='Source Variants',
    )

    @api.depends('prefix_id', 'prefix_id.prefix')
    def _compute_prefix_display(self):
        for wiz in self:
            if wiz.prefix_id:
                wiz.prefix_display = _(
                    "%(prefix)s (length %(len)s)",
                    prefix=wiz.prefix_id.prefix,
                    len=len(wiz.prefix_id.prefix or ''),
                )
            else:
                wiz.prefix_display = ''

    # ------------------------------------------------------------------
    # Candidate gathering & eligibility
    # ------------------------------------------------------------------
    def _gather_candidates(self):
        """Return the product.product recordset this wizard operates on."""
        self.ensure_one()
        if self.product_ids:
            return self.product_ids
        if self.product_template_ids:
            return self.product_template_ids.mapped('product_variant_ids')
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if active_model == 'product.template' and active_ids:
            templates = self.env['product.template'].browse(active_ids)
            return templates.mapped('product_variant_ids')
        if active_model == 'product.product' and active_ids:
            return self.env['product.product'].browse(active_ids)
        return self.env['product.product']

    @staticmethod
    def _classify(product, prefix, remaining):
        """Return a status code for a candidate given current prefix state."""
        if product.barcode:
            return 'SKIP_EXISTING_BARCODE'
        if product.upc_generated:
            return 'SKIP_UPC_EXISTS'
        if not prefix:
            return 'SKIP_NO_ACTIVE_PREFIX'
        if remaining <= 0:
            return 'SKIP_PREFIX_EXHAUSTED'
        return 'WILL_GENERATE'

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _compute_preview(self):
        self.ensure_one()
        prefix = self.env['upc.prefix'].get_active_prefix()
        candidates = self._gather_candidates()
        remaining = prefix.remaining_count if prefix else 0

        lines_vals = []
        eligible = skip_existing = skip_generated = skip_other = 0
        will_generate_seen = 0

        for product in candidates:
            available = remaining - will_generate_seen
            status = self._classify(product, prefix, available)
            if status == 'WILL_GENERATE':
                eligible += 1
                will_generate_seen += 1
            elif status == 'SKIP_EXISTING_BARCODE':
                skip_existing += 1
            elif status == 'SKIP_UPC_EXISTS':
                skip_generated += 1
            else:
                skip_other += 1
            lines_vals.append({
                'wizard_id': self.id,
                'product_id': product.id,
                'status': status,
            })

        self.line_ids.unlink()
        if lines_vals:
            self.env['upc.generation.wizard.line'].create(lines_vals)

        self.write({
            'prefix_id': prefix.id if prefix else False,
            'remaining_before': remaining,
            'eligible_count': eligible,
            'skip_existing_count': skip_existing,
            'skip_generated_count': skip_generated,
            'skip_other_count': skip_other,
            'remaining_after': remaining - eligible,
            'state': 'preview',
        })

    @api.model
    def action_open_wizard(self):
        """Create a wizard seeded from context and return its window action."""
        ctx = self.env.context
        vals = {}
        if ctx.get('active_model') == 'product.template':
            vals['product_template_ids'] = [(6, 0, ctx.get('active_ids') or [])]
        elif ctx.get('active_model') == 'product.product':
            vals['product_ids'] = [(6, 0, ctx.get('active_ids') or [])]
        wizard = self.create(vals)
        wizard._compute_preview()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preview UPC Generation'),
            'res_model': 'upc.generation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        prefix = self.env['upc.prefix'].get_active_prefix()
        if not prefix:
            raise UserError(_("No active UPC prefix is configured."))

        try:
            self.env.cr.execute(
                "SELECT id FROM upc_prefix WHERE id = %s FOR UPDATE NOWAIT",
                [prefix.id],
            )
        except Exception as exc:
            _logger.warning("UPC prefix lock failed: %s", exc)
            raise UserError(_(
                "Could not acquire lock on the active UPC prefix. "
                "Another generation may be in progress. Please retry."
            ))
        prefix.invalidate_recordset(['next_ref', 'remaining_count', 'capacity'])

        candidates = self._gather_candidates()
        eligible = candidates.filtered(
            lambda p: not p.barcode and not p.upc_generated
        )
        if not eligible:
            raise UserError(_("No eligible products to generate UPCs for."))

        count = len(eligible)
        start_ref = prefix.next_ref
        end_ref = start_ref + count
        if end_ref > prefix.capacity:
            raise UserError(_(
                "Not enough remaining UPCs in the active prefix. "
                "Needed %(need)s, available %(have)s."
            ) % {'need': count, 'have': prefix.capacity - start_ref})

        now = fields.Datetime.now()
        ref_by_product = {}
        for i, product in enumerate(eligible):
            ref = start_ref + i
            upc = generate_upc_a(prefix.prefix, ref)
            product.write({
                'barcode': upc,
                'upc_generated': True,
                'barcode_source': 'generated_upc',
                'upc_prefix_id': prefix.id,
                'upc_ref': ref,
                'upc_assigned_on': now,
            })
            ref_by_product[product.id] = upc

        prefix.write({'next_ref': end_ref})

        for line in self.line_ids:
            if line.product_id.id in ref_by_product:
                line.write({
                    'status': 'GENERATED',
                    'generated_upc': ref_by_product[line.product_id.id],
                })

        self.write({
            'state': 'done',
            'eligible_count': count,
            'remaining_before': prefix.capacity - start_ref,
            'remaining_after': prefix.capacity - end_ref,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('UPC Generation Result'),
            'res_model': 'upc.generation.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class UpcGenerationWizardLine(models.TransientModel):
    _name = 'upc.generation.wizard.line'
    _description = 'UPC Generation Wizard Line'
    _order = 'status, id'

    wizard_id = fields.Many2one(
        'upc.generation.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade',
    )
    default_code = fields.Char(related='product_id.default_code', string='Internal Ref.')
    current_barcode = fields.Char(related='product_id.barcode', string='Current Barcode')
    status = fields.Selection(STATUS_SELECTION, string='Status', required=True)
    generated_upc = fields.Char(string='Generated UPC')
