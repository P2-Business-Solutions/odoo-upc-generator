from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestUpcGenerationWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Prefix = self.env['upc.prefix']
        self.Wizard = self.env['upc.generation.wizard']
        self.Template = self.env['product.template']
        self.Product = self.env['product.product']
        self.prefix = self.Prefix.create({
            'name': 'Test Prefix',
            'prefix': '840012',
            'is_active': True,
        })

    def _make_template(self, name, variant_barcodes=None):
        template = self.Template.create({'name': name, 'type': 'consu'})
        if variant_barcodes:
            variants = list(template.product_variant_ids)
            for i, bc in enumerate(variant_barcodes):
                if i >= len(variants):
                    break
                if bc:
                    variants[i].barcode = bc
        return template

    def _open_wizard_for_templates(self, templates):
        return self.Wizard.with_context(
            active_model='product.template',
            active_ids=templates.ids,
        ).action_open_wizard()

    def test_preview_and_generate_three_variants(self):
        t = self._make_template('T1')
        self.Product.create({
            'product_tmpl_id': t.id,
            'default_code': 'V2',
        })
        self.Product.create({
            'product_tmpl_id': t.id,
            'default_code': 'V3',
        })
        variants = t.product_variant_ids
        self.assertEqual(len(variants), 3)

        action = self._open_wizard_for_templates(t)
        wizard = self.Wizard.browse(action['res_id'])
        self.assertEqual(wizard.eligible_count, 3)
        self.assertEqual(wizard.remaining_before, 100000)

        wizard.action_generate()
        self.prefix.invalidate_recordset()
        self.assertEqual(self.prefix.next_ref, 3)
        self.assertEqual(self.prefix.remaining_count, 99997)

        barcodes = sorted(v.barcode for v in variants)
        self.assertEqual(
            barcodes,
            ['840012000007', '840012000014', '840012000021'],
        )
        for v in variants:
            self.assertTrue(v.upc_generated)
            self.assertEqual(v.barcode_source, 'generated_upc')
            self.assertEqual(v.upc_prefix_id, self.prefix)

    def test_skip_existing_barcode(self):
        t = self.Template.create({'name': 'T2', 'type': 'consu'})
        t.product_variant_ids.barcode = 'MANUAL123'
        action = self._open_wizard_for_templates(t)
        wizard = self.Wizard.browse(action['res_id'])
        self.assertEqual(wizard.eligible_count, 0)
        self.assertEqual(wizard.skip_existing_count, 1)
        statuses = wizard.line_ids.mapped('status')
        self.assertIn('SKIP_EXISTING_BARCODE', statuses)

    def test_skip_already_generated(self):
        t = self.Template.create({'name': 'T3', 'type': 'consu'})
        self._open_wizard_for_templates(t)
        # First generation
        action = self._open_wizard_for_templates(t)
        wizard = self.Wizard.browse(action['res_id'])
        wizard.action_generate()
        # Second preview should skip as UPC exists
        action2 = self._open_wizard_for_templates(t)
        wizard2 = self.Wizard.browse(action2['res_id'])
        self.assertEqual(wizard2.eligible_count, 0)
        self.assertEqual(wizard2.skip_existing_count + wizard2.skip_generated_count, 1)

    def test_immutable_generated_barcode(self):
        t = self.Template.create({'name': 'T4', 'type': 'consu'})
        action = self._open_wizard_for_templates(t)
        wizard = self.Wizard.browse(action['res_id'])
        wizard.action_generate()
        variant = t.product_variant_ids
        with self.assertRaises(UserError):
            variant.write({'barcode': 'SOMETHING_ELSE'})

    def test_no_active_prefix_errors(self):
        self.prefix.is_active = False
        t = self.Template.create({'name': 'T5', 'type': 'consu'})
        action = self._open_wizard_for_templates(t)
        wizard = self.Wizard.browse(action['res_id'])
        self.assertEqual(wizard.eligible_count, 0)
        statuses = wizard.line_ids.mapped('status')
        self.assertIn('SKIP_NO_ACTIVE_PREFIX', statuses)
        with self.assertRaises(UserError):
            wizard.action_generate()

    def test_contiguous_block_over_multiple_runs(self):
        t1 = self.Template.create({'name': 'T6a', 'type': 'consu'})
        t2 = self.Template.create({'name': 'T6b', 'type': 'consu'})
        action = self._open_wizard_for_templates(t1)
        self.Wizard.browse(action['res_id']).action_generate()
        self.prefix.invalidate_recordset()
        self.assertEqual(self.prefix.next_ref, 1)
        action = self._open_wizard_for_templates(t2)
        self.Wizard.browse(action['res_id']).action_generate()
        self.prefix.invalidate_recordset()
        self.assertEqual(self.prefix.next_ref, 2)
        self.assertEqual(t1.product_variant_ids.barcode, '840012000007')
        self.assertEqual(t2.product_variant_ids.barcode, '840012000014')
