import unittest

from eigp144 import Eigp144, FieldCustomerPartNumber, FieldSupplierPartNumber, FieldQuantity, FieldDateCode1, FieldLotCode, FieldCountryOfOrigin, FieldManufacturer


class Eigp144TestCase(unittest.TestCase):
  def test_speccase(self):
    input = "[)>\u241e06\u241dP596-777A1-ND\u241d1PXAF4444\u241dQ3\u241d10D1452\u241d1TBF1103\u241d4LUS\u241e\u2404"
    parsed = Eigp144.from_data(input)
    self.assertNotEqual(parsed, None)
    self.assertEqual(parsed.data[FieldCustomerPartNumber].raw, "596-777A1-ND")
    self.assertEqual(parsed.data[FieldSupplierPartNumber].raw, "XAF4444")
    self.assertEqual(parsed.data[FieldQuantity].raw, "3")
    self.assertEqual(parsed.data[FieldDateCode1].raw, "1452")
    self.assertEqual(parsed.data[FieldLotCode].raw, "BF1103")
    self.assertEqual(parsed.data[FieldCountryOfOrigin].raw, "US")

  def test_digikey(self):
    input = "[)>␞06␝PRMCF0603FT5K10CT-ND␝1PRMCF0603FT5K10␝K␝1K58732613␝10K67192477␝11K1␝4LCN␝Q100␝11ZPICK␝12Z1943037␝13Z803900␝20Z00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    parsed = Eigp144.from_data(input)
    self.assertNotEqual(parsed, None)
    self.assertEqual(parsed.data[FieldCustomerPartNumber].raw, "RMCF0603FT5K10CT-ND")
    self.assertEqual(parsed.data[FieldSupplierPartNumber].raw, "RMCF0603FT5K10")
    self.assertEqual(parsed.data[FieldQuantity].raw, "100")

  def test_mouser(self):
    input = "[)>␞06␝K0160NLA52600␝14K002␝1PFH12-15S-0.5SH(55)␝Q2␝11K069808311␝4LJP␝1VHirose␞␄"
    parsed = Eigp144.from_data(input)
    self.assertNotEqual(parsed, None)
    self.assertEqual(parsed.data[FieldSupplierPartNumber].raw, "FH12-15S-0.5SH(55)")
    self.assertEqual(parsed.data[FieldManufacturer].raw, "Hirose")
    self.assertEqual(parsed.data[FieldQuantity].raw, "2")
