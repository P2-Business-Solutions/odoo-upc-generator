from odoo.tests.common import TransactionCase

from ..models.upc_prefix import compute_upc_check_digit, generate_upc_a


class TestUpcCheckDigit(TransactionCase):

    def test_check_digit_known_values(self):
        # Values verified against the standard UPC-A algorithm described in the
        # module spec; two values in the spec's verification table were
        # arithmetically off and have been recomputed here.
        cases = [
            ('84001200000', 7),
            ('84001200001', 4),
            ('84001200002', 1),
            ('84001200003', 8),
            ('84001299999', 8),
            ('07000000000', 3),
            ('60000000000', 2),
            ('03600029145', 2),  # classic reference: 036000291452
        ]
        for first_11, expected in cases:
            self.assertEqual(
                compute_upc_check_digit(first_11),
                expected,
                f"Check digit mismatch for {first_11}",
            )

    def test_generate_upc_a_full(self):
        cases = [
            ('840012', 0, '840012000007'),
            ('840012', 1, '840012000014'),
            ('840012', 2, '840012000021'),
            ('840012', 3, '840012000038'),
            ('840012', 99999, '840012999998'),
            ('07', 0, '070000000003'),
            ('6', 0, '600000000002'),
        ]
        for prefix, ref, expected in cases:
            self.assertEqual(generate_upc_a(prefix, ref), expected)

    def test_generate_upc_a_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            generate_upc_a('abc', 0)
        with self.assertRaises(ValueError):
            generate_upc_a('', 0)
        with self.assertRaises(ValueError):
            generate_upc_a('12345678901', 0)
        with self.assertRaises(ValueError):
            generate_upc_a('840012', -1)

    def test_check_digit_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            compute_upc_check_digit('123')
        with self.assertRaises(ValueError):
            compute_upc_check_digit('8400120000A')
