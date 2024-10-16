from typing import Optional, Dict

import argparse
import os
import csv
import cv2
import zxingcpp
import numpy as np
import datetime
import sys
import beepy
import serial

from queue import Queue
from threading import Thread

from digikey_api import DigiKeyApi, DigiKeyApiConfig
from iso15434 import Iso15434, FieldSupplierPartNumber, FieldQuantity


# Scanner / OpenCV configurations
kWindowName = "PartsScanner"
kFrameWidth = 1920
kFrameHeight = 1080
kRoiWidth = 280  # center-aligned region-of-interest - speeds up scanning
kRoiHeight = kRoiWidth

kFontScale = 0.5

kBarcodeTimeoutThreshold = datetime.timedelta(seconds=4)  # after not seeing a barcode for this long, count as a new one


# CSV header definition
kCsvColBarcode = 'barcode'  # entire barcode, unique, used as a key
kCsvSymbology = 'symbology'  # barcode symbology identifier from zxing
kCsvColCategory = 'category'  # part category
kCsvColSupplierPart = 'supplier_part'  # manufacturer part number
kCsvColCurrQty = 'curr_qty'  # current quantity
kCsvColDesc = 'supplier_desc'  # catalog description
kCsvColPackQty = 'pack_qty'  # quantity as packed
kCsvColDistBarcodeData = 'dist_barcode_data'  # entire distributor barcode data response, optional
kCsvColDistProdData = 'dist_prod_data'  # entire distributor product data response
kCsvColScanTime = 'scan_time'  # initial scan time
kCsvColUpdateTime = 'update_time'  # last row updated time
kCsvHeaders = [kCsvColBarcode, kCsvSymbology, kCsvColCategory, kCsvColSupplierPart, kCsvColCurrQty, kCsvColDesc,
               kCsvColPackQty, kCsvColDistBarcodeData, kCsvColDistProdData, kCsvColScanTime, kCsvColUpdateTime]


# Cross-thread queues
data_queue = Queue()
beep_queue = Queue()


def scan_fn(cap: cv2.VideoCapture):
  """Thread for scanning barcodes, enqueueing scanned barcodes
  Handles de-duplication using a timeout between scans of the same barcode"""
  last_seen_times = {}  # text -> time, used for scan antiduplication
  kFormats = [
    zxingcpp.BarcodeFormat.DataMatrix,
    zxingcpp.BarcodeFormat.Code128
  ]
  format = zxingcpp.BarcodeFormat.DataMatrix

  cap.set(cv2.CAP_PROP_FRAME_WIDTH, kFrameWidth)  # TODO configurable
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT, kFrameHeight)

  while True:
    frame_time = datetime.datetime.now()
    ticks = cv2.getTickCount()
    ret, frame = cap.read()
    assert ret, "failed to get frame"
    h, w = frame.shape[:2]

    # only scan a small RoI since decode is extremely slow
    roi = frame[h//2 - kRoiHeight//2 : h//2 + kRoiHeight//2,
          w//2 - kRoiWidth//2 : w//2 + kRoiWidth//2]
    roi = cv2.fastNlMeansDenoisingColored(roi, None, 10, 10, 7, 21)
    roi = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    roi = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    # roi = cv2.threshold(roi, 63, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # roi = cv2.multiply(roi, roi_msk)
    results = zxingcpp.read_barcodes(roi, formats=format)

    # display for user
    # analysis ROI display
    cv2.rectangle(frame, (w//2 - kRoiWidth//2, h//2 - kRoiHeight//2),
                  (w//2 + kRoiWidth//2, h//2 + kRoiHeight//2),
                  (255, 0, 0), 1)
    # reticule
    cv2.putText(frame, f"{w}x{h} {ticks}", (0, 16), cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 0, 255), 1)
    cv2.putText(frame, f"{format}", (0, 32), cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 0, 255), 1)
    cv2.line(frame, (w//2, h//2 - kRoiHeight//2), (w//2, h//2 + kRoiHeight//2), (0, 0, 255), 1)
    cv2.line(frame, (w//2 - kRoiWidth//2, h//2), (w//2 + kRoiWidth//2, h//2), (0, 0, 255), 1)

    cv2.putText(frame, f"{results}", (w//2 - kRoiWidth//2, h//2 + kRoiHeight//2),
                cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 0, 255), 1)

    woff = w//2 - kRoiWidth//2  # correct for RoI
    hoff = h//2 - kRoiHeight//2

    def zxing_pos_to_cv2(pos):
      return (woff + pos.x, hoff + pos.y)

    for barcode in results:
      last_seen = last_seen_times.get(barcode.text, datetime.datetime(1990, 1, 1))
      if frame_time - last_seen > kBarcodeTimeoutThreshold:
        print(f"{barcode.symbology_identifier}: {barcode.text}")
        beep_queue.put(1)
        data_queue.put(barcode)
        frame_thick = 4
      else:
        frame_thick = 1
      last_seen_times[barcode.text] = frame_time

      pos = barcode.position
      polypts = np.array([zxing_pos_to_cv2(xy)
                          for xy in [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]], np.int32)
      cv2.polylines(frame, [polypts], isClosed=True, color=(0, 255, 0), thickness=frame_thick)
      cv2.putText(frame, f"{barcode.text}", (woff + pos.top_left.x, hoff + pos.top_left.y),
                  cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 255, 0), 1)

    cv2.imshow(kWindowName, frame)
    cv2.imshow(kWindowName + "b", roi)
    key = cv2.waitKey(1)  # delay
    if key == ord('q'):
      sys.exit(0)
    elif key == ord('f'):
      format = kFormats[(kFormats.index(format) + 1) % len(kFormats)]


def console_fn():
  """Thread that handles user input, enueueing each user-inputted line"""
  while True:
    userline = input()
    data_queue.put(userline)


def csv_fn(csv_filename: str):
  """Data handling thread that mixes scanned barcodes and user input, writing data to a CSV file"""
  with open(csv_filename, 'r', newline='', encoding='utf-8') as csvfile:
    csvr = csv.DictReader(csvfile)
    records = {row[kCsvColBarcode]: row for row in csvr}
    fieldnames = csvr.fieldnames
    print(f"loaded {len(records)} rows, fieldnames {fieldnames} from existing CSV")

  with open(csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
    csvw = csv.DictWriter(csvfile, fieldnames=fieldnames)
    curr_dict: Optional[Dict[str, str]] = None  # none if no part active

    def write_line():
      if curr_dict is not None:  # commit prev line
        csvw.writerow(curr_dict)
        csvfile.flush()
        records[curr_dict[kCsvColBarcode]] = curr_dict

    def process_iso15434(barcode_raw: str, decoded: Iso15434, curr_dict: Dict[str, str]):
      if '20Z' in decoded.data:
        distributor = 'DigiKey2d'
      else:
        distributor = 'Mouser2d'

      curr_dict[kCsvColSupplierPart] = decoded.data[FieldSupplierPartNumber].raw
      curr_dict[kCsvColPackQty] = decoded.data[FieldQuantity].raw

      print(f"{distributor} {curr_dict[kCsvColSupplierPart]} x {curr_dict[kCsvColPackQty]}")
      if distributor == 'DigiKey2d':
        try:
          dk_barcode2d = digikey_api.barcode2d(barcode_raw)
          dk_searchterm = dk_barcode2d.DigiKeyPartNumber
          curr_dict[kCsvColDistBarcodeData] = dk_barcode2d.model_dump_json()
        except AssertionError as e:
          print(f"WARNING: barcode lookup failed: {e}")
          dk_searchterm = curr_dict[kCsvColSupplierPart]
      elif distributor == 'Mouser2d':
        dk_searchterm = curr_dict[kCsvColSupplierPart]

      try:
        dk_product = digikey_api.product_details(dk_searchterm)
        curr_dict[kCsvColDistProdData] = dk_product.model_dump_json()
        curr_dict[kCsvColDesc] = dk_product.Product.Description.ProductDescription
        curr_dict[kCsvColCategory] = dk_product.Product.Category.simple_str()
        print(f"{curr_dict[kCsvColDesc]}, {curr_dict[kCsvColCategory]}")
      except AssertionError as e:
        print(f"WARNING: product lookup failed, fields not populated: {e}")


    while True:
      data = data_queue.get()

      if isinstance(data, str):
        if not data and curr_dict is not None:  # return to commit line
          write_line()
          curr_dict = None
          print(f"line saved")
        elif data.startswith('d') and curr_dict is not None:
          curr_dict = None
          print(f"line deleted")
        elif data.startswith('+') or data.startswith('-') or data == '0':
          if data.startswith('+'):
            data = data[1:]
          try:
            qtymod = int(data)
            curr_qty = int(curr_dict.get(kCsvColCurrQty, curr_dict[kCsvColPackQty])) + qtymod
            curr_dict[kCsvColCurrQty] = str(curr_qty)
            print(f"Updated quantity to {curr_qty}")
          except ValueError:
            print(f"unknown quantity modifier {data}")
        elif data.startswith('p') and curr_dict is not None:
          data = data[1:]
          try:
            dk_product = digikey_api.product_details(data)
            curr_dict[kCsvColDistProdData] = dk_product.model_dump_json()
            curr_dict[kCsvColDesc] = dk_product.Product.Description.ProductDescription
            curr_dict[kCsvColCategory] = dk_product.Product.Category.simple_str()
            print(f"{[kCsvColDesc]}, {curr_dict[kCsvColCategory]}")
          except AssertionError as e:
            print(f"WARNING: product lookup failed, fields not modified: {e}")
        else:
          print(f"unknown command {data}")
      elif isinstance(data, bytes):  # from serial;
        if data.startswith(b'[)>'):
          write_line()
          curr_dict = None
          barcode_raw = data.decode('utf-8')
          barcode_key = str(barcode_raw.encode('unicode_escape').decode('ascii'))
          if barcode_key in records:
            print("WARNING: duplicate row")

          curr_dict = {kCsvColBarcode: barcode_key,
                       kCsvColScanTime: datetime.datetime.now().isoformat()}
          decoded = Iso15434.from_data(barcode_raw)
          if decoded is not None:
            process_iso15434(barcode_raw, decoded, curr_dict)
          else:
            print(f"failed to decode iso15434")
        else:
          print(f"unknown scanned data {data}")
      elif isinstance(data, zxingcpp.Result):
        write_line()
        curr_dict = None
        barcode_raw = data.text
        barcode_key = str(barcode_raw.encode('unicode_escape').decode('ascii'))
        if barcode_key in records:
          print("WARNING: duplicate row")

        curr_dict = {kCsvColBarcode: barcode_key,
                     kCsvSymbology: data.symbology_identifier,
                     kCsvColScanTime: datetime.datetime.now().isoformat()}
        if data.symbology_identifier.startswith(']d'):
          decoded = Iso15434.from_data(data.text)
          if decoded is not None:
            process_iso15434(barcode_raw, decoded, curr_dict)
          else:
            print(f"failed to decode iso15434")
        elif data.symbology_identifier.startswith(']C'):
          try:
            dk_barcode1d = digikey_api.barcode(barcode_raw)
            dk_searchterm = dk_barcode1d.DigiKeyPartNumber
            curr_dict[kCsvColDistBarcodeData] = dk_barcode1d.model_dump_json()
            curr_dict[kCsvColSupplierPart] = dk_barcode1d.ManufacturerPartNumber
            curr_dict[kCsvColPackQty] = dk_barcode1d.Quantity

            dk_product = digikey_api.product_details(dk_searchterm)
            curr_dict[kCsvColDistProdData] = dk_product.model_dump_json()
            curr_dict[kCsvColDesc] = dk_product.Product.Description.ProductDescription
            curr_dict[kCsvColCategory] = dk_product.Product.Category.simple_str()
            print(f"Digikey1d {curr_dict[kCsvColSupplierPart]} x {curr_dict[kCsvColPackQty]}")
            print(f"{curr_dict[kCsvColDesc]}, {curr_dict[kCsvColCategory]}")
          except AssertionError as e:
            print(f"WARNING: product lookup failed, fields not populated: {e}")

        else:
          print(f"unknown symbology {data.symbology_identifier} {data.text}")


def beep_fn():
  while True:
    beepy.beep(sound=beep_queue.get())  # beep seems to be blocking, so it gets its own thread


def serial_fn(port: serial.Serial):
  while True:
    s = port.readline()
    if s:
      data_queue.put(s)
      print(s)


# data matrix code based on https://github.com/llpassarelli/dmtxscann/blob/master/dmtxscann.py
if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Parts barcode / datamatrix scanner.')
  parser.add_argument('csv', type=str,
                      help='CSV filename to create / append.')
  parser.add_argument('--serial', type=str,
                      help='Optional serial port for a connected barcode scanner.')
  args = parser.parse_args()

  # initialize Digikey API
  with open('digikey_api_config.json') as f:
    # IMPORTANT! You will need to set up your DigiKey API access and API keys.
    # Copy the digikey_api_config_sample.json to digikey_api_config.json and fill in the values.
    digikey_api_config = DigiKeyApiConfig.model_validate_json(f.read())

  digikey_api = DigiKeyApi(digikey_api_config, token_filename='digikey_api_token.json')

  # initialize output file
  # TODO: validate fieldnames
  if not os.path.exists(args.csv):
    print(f"creating new csv {args.csv}")
    with open(args.csv, 'w', newline='') as csvfile:
      csvw = csv.DictWriter(csvfile, fieldnames=kCsvHeaders)
      csvw.writeheader()

  # initialize OpenCV
  cap = cv2.VideoCapture(0)  # TODO configurable
  assert cap.isOpened, "failed to open camera"

  if args.serial:
    port = serial.Serial(args.serial, timeout=0.05)
    serial_thread = Thread(target=serial_fn, args=(port, ))
    serial_thread.daemon = True
    serial_thread.start()

  console_thread = Thread(target=console_fn)
  console_thread.start()

  csv_thread = Thread(target=csv_fn, args=(args.csv, ))
  csv_thread.daemon = True
  csv_thread.start()

  beep_thread = Thread(target=beep_fn)
  beep_thread.daemon = True
  beep_thread.start()

  scan_fn(cap)  # becomes the main thread for user input because it handles the exit function
