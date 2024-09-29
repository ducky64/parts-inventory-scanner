# Implementation of the ISO/IEC 15434 / EIGP144 coding standard for barcodes for labeling electronic parts
# https://www.ecianow.org/assets/docs/GIPC/EIGP-114.2018%20ECIA%20Labeling%20Specification%20for%20Product%20and%20Shipment%20Identification%20in%20the%20Electronics%20Industry%20-%202D%20Barcode.pdf
from typing import Dict, Union, Optional, Type


class Iso15434Record:
  """Abstract base class for records"""
  def __init__(self, identifier: str, raw: str):
    self.identifier = identifier
    self.raw = raw

  def __repr__(self):
    return f"{self.identifier}={self.raw}"


class Iso15434Field:
  """Abstract base class for fields definitions"""
  def __init__(self, name: str, identifier: str, ctor: Type[Iso15434Record] = Iso15434Record):
    self.name = name
    self.identifier = identifier
    self.ctor = ctor

  def __repr__(self):
    return f"{self.identifier} ({self.name})"


FieldPo = Iso15434Field('Customer PO', 'K')
FieldPackingListNumber = Iso15434Field('Packing List Number', '11K')
FieldShipDate = Iso15434Field('Ship Date', '6D')
FieldCustomerPartNumber = Iso15434Field('Customer Part Number', 'P')
FieldSupplierPartNumber = Iso15434Field('Supplier Part Number', '1P')
FieldCustomerPoLine = Iso15434Field('Customer PO Line', '4K')
FieldQuantity = Iso15434Field('Quantity', 'Q')
FieldDateCode0 = Iso15434Field('Date Code', '9D')
FieldDateCode1 = Iso15434Field('Date Code', '10D')
FieldLotCode = Iso15434Field('Lot Code', '1T')
FieldCountryOfOrigin = Iso15434Field('Country of Origin', '4L')
FieldBinCode = Iso15434Field('BIN Code', '33P')
FieldPackageCount = Iso15434Field('Package Count', '13Q')
FieldWeight = Iso15434Field('Weight', '7Q')
FieldManufacturer = Iso15434Field('Manufacturer', '1V')
FieldRohsCc = Iso15434Field('RoHS/CC', 'E')


class Iso15434:
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
  def from_data(cls, data: str) -> Optional['Iso15434']:
    if not data.startswith(cls.kHeader):
      return None
    data = data[len(cls.kHeader):]
    if data.endswith(cls.kTrailer):  # digikey doesn't have this, so this is optional even if nonstandard
      data = data[:-len(cls.kTrailer)]

    data_elements = {}
    for data_element in data.split(Iso15434.kGroupSeparator):
      identifier = ''
      while data_element and data_element[0].isnumeric():
        identifier += data_element[0]
        data_element = data_element[1:]
      identifier += data_element[0]
      data_element = data_element[1:]

      if identifier in Iso15434.kFieldsByIdentifier:
        field = Iso15434.kFieldsByIdentifier[identifier]
        ctor = field.ctor
      else:
        field = identifier
        ctor = Iso15434Record
      assert field not in data_elements, f"duplicate field {field}"
      parsed = ctor(identifier, data_element)
      data_elements[field] = parsed

    return Iso15434(data_elements)

  def __init__(self, data: Dict[Union[Iso15434Field, str], Iso15434Record]):
    self.data = data

  def __repr__(self):
    return f"{self.__class__.__name__}({self.data})"
