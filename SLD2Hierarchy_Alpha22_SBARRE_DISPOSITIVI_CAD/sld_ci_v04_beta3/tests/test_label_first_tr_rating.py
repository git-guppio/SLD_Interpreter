"""Etichette TR native: qualsiasi taglia plausibile, non solo 1.700 kVA (PV11)."""
import tempfile
import unittest
from pathlib import Path

import pymupdf

from sld_ci_v04_beta3.sap.label_first import _native_page


def tr_tags(label):
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / 'tr.pdf'
        doc = pymupdf.open()
        doc.new_page(width=650, height=500).insert_text((345, 175), label)
        doc.save(pdf)
        doc.close()
        with pymupdf.open(pdf) as d:
            return [t['tag'] for t in _native_page(d[0], 1)['transformers']]


class TransformerRatingTests(unittest.TestCase):
    def test_pv11_label_unchanged(self):
        self.assertEqual(tr_tags('TRANSFORMER 1.700 kVA'), ['TRANSFORMER 1.700 kVA'])

    def test_other_ratings_recognized(self):
        for label, tag in (('TRANSFORMER 2.500 kVA', 'TRANSFORMER 2.500 kVA'),
                           ('TRANSFORMER 1600 kVA', 'TRANSFORMER 1600 kVA'),
                           ('TRANSFORMER 800 kVA', 'TRANSFORMER 800 kVA'),
                           ('TRANSFORMER 2,000', 'TRANSFORMER 2,000 kVA'),
                           ('TRANSFORMER 3.150kVA', 'TRANSFORMER 3.150 kVA')):
            with self.subTest(label=label):
                self.assertEqual(tr_tags(label), [tag])

    def test_numbering_and_legends_not_transformers(self):
        for label in ('TRANSFORMER 1', 'TRANSFORMER 12', 'TRANSFORMER ROOM', 'TRANSFORMER 1.7'):
            with self.subTest(label=label):
                self.assertEqual(tr_tags(label), [])


if __name__ == '__main__':
    unittest.main()
