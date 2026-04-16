import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_DIGIT_RE = re.compile(r'^[0-9]+$')


def compute_upc_check_digit(first_11):
    """Compute the UPC-A check digit for an 11-digit string.

    UPC-A uses 1-indexed positions:
    - Odd positions (1, 3, 5, 7, 9, 11): sum * 3
    - Even positions (2, 4, 6, 8, 10): sum * 1
    - Check digit = (10 - (total % 10)) % 10
    """
    if not (isinstance(first_11, str) and len(first_11) == 11 and first_11.isdigit()):
        raise ValueError("first_11 must be an 11-digit string")
    odd_sum = sum(int(first_11[i]) for i in range(0, 11, 2))
    even_sum = sum(int(first_11[i]) for i in range(1, 11, 2))
    total = odd_sum * 3 + even_sum
    return (10 - (total % 10)) % 10


def generate_upc_a(prefix, item_ref):
    """Generate a full 12-digit UPC-A barcode from prefix and 0-based item_ref."""
    if not (isinstance(prefix, str) and _DIGIT_RE.match(prefix)):
        raise ValueError("prefix must be a digit string")
    if not (1 <= len(prefix) <= 10):
        raise ValueError("prefix length must be between 1 and 10")
    if item_ref < 0:
        raise ValueError("item_ref must be non-negative")
    ref_length = 11 - len(prefix)
    ref_str = str(item_ref).zfill(ref_length)
    if len(ref_str) > ref_length:
        raise ValueError("item_ref exceeds prefix capacity")
    first_11 = prefix + ref_str
    assert len(first_11) == 11
    return first_11 + str(compute_upc_check_digit(first_11))


class UpcPrefix(models.Model):
    _name = 'upc.prefix'
    _description = 'UPC Prefix'
    _order = 'is_active desc, name'

    name = fields.Char(string='Name', required=True)
    prefix = fields.Char(string='Prefix', required=True)
    is_active = fields.Boolean(string='Active', default=False)
    next_ref = fields.Integer(string='Next Reference', default=0, required=True)
    capacity = fields.Integer(
        string='Capacity',
        compute='_compute_capacity',
        store=True,
    )
    remaining_count = fields.Integer(
        string='Remaining',
        compute='_compute_remaining_count',
        store=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    @api.depends('prefix')
    def _compute_capacity(self):
        for rec in self:
            if rec.prefix and _DIGIT_RE.match(rec.prefix) and 1 <= len(rec.prefix) <= 10:
                rec.capacity = 10 ** (11 - len(rec.prefix))
            else:
                rec.capacity = 0

    @api.depends('capacity', 'next_ref')
    def _compute_remaining_count(self):
        for rec in self:
            rec.remaining_count = rec.capacity - rec.next_ref

    @api.constrains('prefix')
    def _check_prefix_format(self):
        for rec in self:
            if not rec.prefix or not _DIGIT_RE.match(rec.prefix):
                raise ValidationError(_("Prefix must contain only digits."))
            if not (1 <= len(rec.prefix) <= 10):
                raise ValidationError(
                    _("Prefix length must be between 1 and 10 digits.")
                )

    @api.constrains('next_ref', 'capacity')
    def _check_next_ref_bounds(self):
        for rec in self:
            if rec.next_ref < 0:
                raise ValidationError(_("Next reference cannot be negative."))
            if rec.next_ref > rec.capacity:
                raise ValidationError(
                    _("Next reference (%s) cannot exceed capacity (%s).")
                    % (rec.next_ref, rec.capacity)
                )

    @api.constrains('is_active', 'company_id')
    def _check_single_active(self):
        for rec in self:
            if not rec.is_active:
                continue
            domain = [('is_active', '=', True), ('id', '!=', rec.id)]
            if rec.company_id:
                domain.append(('company_id', '=', rec.company_id.id))
            else:
                domain.append(('company_id', '=', False))
            if self.search_count(domain):
                raise ValidationError(
                    _("Only one UPC prefix may be active at a time per company.")
                )

    def write(self, vals):
        if 'next_ref' in vals:
            new_value = vals['next_ref']
            for rec in self:
                if new_value < rec.next_ref:
                    raise UserError(
                        _("next_ref must never decrease. "
                          "Consumed references cannot be reclaimed.")
                    )
        return super().write(vals)

    def generate_upc(self, item_ref):
        """Return a 12-digit UPC-A barcode for this prefix and item_ref."""
        self.ensure_one()
        return generate_upc_a(self.prefix, item_ref)

    @api.model
    def get_active_prefix(self, company=None):
        """Return the active prefix for the given company (or current), or empty."""
        domain = [('is_active', '=', True)]
        if company is None:
            company = self.env.company
        if company:
            domain += ['|', ('company_id', '=', company.id), ('company_id', '=', False)]
        return self.search(domain, limit=1)
