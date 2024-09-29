# Implementation of the EIGP144 coding standard for barcodes for labeling electronic parts
# https://www.ecianow.org/assets/docs/GIPC/EIGP-114.2018%20ECIA%20Labeling%20Specification%20for%20Product%20and%20Shipment%20Identification%20in%20the%20Electronics%20Industry%20-%202D%20Barcode.pdf
from typing import Dict, Union, Optional, Type


class Eigp144Record:
  """Abstract base class for records"""
  def __init__(self, identifier: str, raw: str):
    self.identifier = identifier
    self.raw = raw

  def __repr__(self):
    return f"{self.identifier}={self.raw}"


class Eigp144Field:
  """Abstract base class for fields definitions"""
  def __init__(self, name: str, identifier: str, ctor: Type[Eigp144Record] = Eigp144Record):
    self.name = name
    self.identifier = identifier
    self.ctor = ctor

  def __repr__(self):
    return f"{self.identifier} ({self.name})"


FieldPo = Eigp144Field('Customer PO', 'K')
FieldPackingListNumber = Eigp144Field('Packing List Number', '11K')
FieldShipDate = Eigp144Field('Ship Date', '6D')
FieldCustomerPartNumber = Eigp144Field('Customer Part Number', 'P')
FieldSupplierPartNumber = Eigp144Field('Supplier Part Number', '1P')
FieldCustomerPoLine = Eigp144Field('Customer PO Line', '4K')
FieldQuantity = Eigp144Field('Quantity', 'Q')
FieldDateCode0 = Eigp144Field('Date Code', '9D')
FieldDateCode1 = Eigp144Field('Date Code', '10D')
FieldLotCode = Eigp144Field('Lot Code', '1T')
FieldCountryOfOrigin = Eigp144Field('Country of Origin', '4L')
FieldBinCode = Eigp144Field('BIN Code', '33P')
FieldPackageCount = Eigp144Field('Package Count', '13Q')
FieldWeight = Eigp144Field('Weight', '7Q')
FieldManufacturer = Eigp144Field('Manufacturer', '1V')
FieldRohsCc = Eigp144Field('RoHS/CC', 'E')


class Eigp144:
  kAllFields = [
    FieldPo,
    FieldPackingListNumber,
    FieldShipDate,
    FieldCustomerPartNumber,
    FieldSupplierPartNumber,
    FieldCustomerPoLine,
    FieldQuantity,
    FieldDateCode0,
    FieldDateCode1,
    FieldLotCode,
    FieldCountryOfOrigin,
    FieldBinCode,
    FieldPackageCount,
    FieldWeight,
    FieldManufacturer,
    FieldRohsCc,
  ]
  kFieldsByIdentifier = {field.identifier: field for field in kAllFields}
  kComplianceIndicator = '[)>'
  kRecordSeparator = '\u241e'
  kGroupSeparator = '\u241d'
  kEndOfTransmission = '\u2404'
  kHeader = kComplianceIndicator + kRecordSeparator + '06' + kGroupSeparator
  kTrailer = kRecordSeparator + kEndOfTransmission

  @classmethod
  def from_data(cls, data: str) -> Optional['Eigp144']:
    if not data.startswith(cls.kHeader):
      return None
    data = data[len(cls.kHeader):]
    if data.endswith(cls.kTrailer):  # digikey doesn't have this, so this is optional even if nonstandard
      data = data[:-len(cls.kTrailer)]

    data_elements = {}
    for data_element in data.split(Eigp144.kGroupSeparator):
      identifier = ''
      while data_element and data_element[0].isnumeric():
        identifier += data_element[0]
        data_element = data_element[1:]
      identifier += data_element[0]
      data_element = data_element[1:]

      if identifier in Eigp144.kFieldsByIdentifier:
        field = Eigp144.kFieldsByIdentifier[identifier]
        ctor = field.ctor
      else:
        field = identifier
        ctor = Eigp144Record
      assert field not in data_elements, f"duplicate field {field}"
      parsed = ctor(identifier, data_element)
      data_elements[field] = parsed

    return Eigp144(data_elements)

  def __init__(self, data: Dict[Union[Eigp144Field, str], Eigp144Record]):
    self.data = data

  def __repr__(self):
    return f"Eigp144({self.data})"
