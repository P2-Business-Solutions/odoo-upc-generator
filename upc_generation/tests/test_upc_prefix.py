from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestUpcPrefix(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Prefix = self.env['upc.prefix']

    def test_capacity_computed(self):
        p = self.Prefix.create({'name': 'Six', 'prefix': '840012'})
        self.assertEqual(p.capacity, 100000)
        self.assertEqual(p.remaining_count, 100000)

    def test_capacity_updates_on_prefix_change(self):
        p = self.Prefix.create({'name': 'Six', 'prefix': '840012'})
        p.prefix = '12'
        self.assertEqual(p.capacity, 10 ** 9)

    def test_only_one_active(self):
        self.Prefix.create({'name': 'A', 'prefix': '840012', 'is_active': True})
        with self.assertRaises(ValidationError):
            self.Prefix.create({'name': 'B', 'prefix': '840013', 'is_active': True})

    def test_digits_only(self):
        with self.assertRaises(ValidationError):
            self.Prefix.create({'name': 'Bad', 'prefix': '84A012'})

    def test_prefix_length_bounds(self):
        with self.assertRaises(ValidationError):
            self.Prefix.create({'name': 'Too long', 'prefix': '12345678901'})
        with self.assertRaises(ValidationError):
            self.Prefix.create({'name': 'Empty', 'prefix': ''})

    def test_next_ref_cannot_decrease(self):
        p = self.Prefix.create({'name': 'N', 'prefix': '840012', 'next_ref': 5})
        with self.assertRaises(UserError):
            p.write({'next_ref': 4})

    def test_next_ref_cannot_exceed_capacity(self):
        p = self.Prefix.create({'name': 'N', 'prefix': '840012'})
        with self.assertRaises(ValidationError):
            p.write({'next_ref': p.capacity + 1})
