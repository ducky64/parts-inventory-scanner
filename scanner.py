from typing import Optional, TextIO, Dict

import os
import csv
import cv2
import zxingcpp
import numpy as np
import datetime
import sys
import beepy

from queue import Queue
from threading import Thread

from digikey_api import DigiKeyApi, DigiKeyApiConfig
from iso15434 import Iso15434, FieldSupplierPartNumber, FieldQuantity


# Scanner / OpenCV configurations
kWindowName = "PartsScanner"
kFrameWidth = 1920
kFrameHeight = 1080
kRoiWidth = 280  # center-aligned region-of-interest - speeds up scanning
kRoiHeight = 280

kFontScale = 0.5

kBarcodeTimeoutThreshold = datetime.timedelta(seconds=4)  # after not seeing a barcode for this long, count as a new one


# CSV header definition
kCsvFilename = 'parts.csv'

kCsvColBarcode = 'barcode'  # entire barcode, unique, used as a key
kCsvSymbology = 'symbology'  # barcode symbology identifier from zxing
kCsvColSupplierPart = 'supplier_part'  # manufacturer part number
kCsvColCurrQty = 'curr_qty'  # current quantity
kCsvColDesc = 'desc'  # catalog description
kCsvColPackQty = 'pack_qty'  # quantity as packed
kCsvColDistBarcodeData = 'dist_barcode_data'  # entire distributor barcode data response, optional
kCsvColDistProdData = 'dist_prod_data'  # entire distributor product data response
kCsvColScanTime = 'scan_time'  # initial scan time
kCsvColUpdateTime = 'update_time'  # last row updated time
kCsvHeaders = [kCsvColBarcode, kCsvSymbology, kCsvColSupplierPart, kCsvColCurrQty, kCsvColDesc,
               kCsvColPackQty, kCsvColDistBarcodeData, kCsvColDistProdData, kCsvColScanTime, kCsvColUpdateTime]


# Cross-thread queues
data_queue = Queue()
beep_queue = Queue()


def scan_fn(cap: cv2.VideoCapture):
  """Thread for scanning barcodes, enqueueing scanned barcodes
  Handles de-duplication using a timeout between scans of the same barcode"""
  last_seen_times = {}  # text -> time, used for scan antiduplication

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
    roi = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    # roi = cv2.multiply(roi, roi_msk)
    results = zxingcpp.read_barcodes(roi, formats=zxingcpp.BarcodeFormat.DataMatrix)

    # display for user
    # analysis ROI display
    cv2.rectangle(frame, (w//2 - kRoiWidth//2, h//2 - kRoiHeight//2),
                  (w//2 + kRoiWidth//2, h//2 + kRoiHeight//2),
                  (255, 0, 0), 1)
    # reticule
    cv2.putText(frame, f"{w}x{h} {ticks}", (0, 32), cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 0, 255), 1)
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


def console_fn():
  """Thread that handles user input, enueueing each user-inputted line"""
  while True:
    userline = input()
    data_queue.put(userline)


def guess_distributor(barcode, decoded: Iso15434) -> Optional[str]:
  """Guesses the distributor from barcode metadata and decoded data"""
  if barcode.format == zxingcpp.BarcodeFormat.DataMatrix:
    if '20Z' in decoded.data:
      return 'DigiKey2d'
    else:
      return 'Mouser2d'
  else:
    return None


def csv_fn():
  """Data handling thread that mixes scanned barcodes and user input, writing data to a CSV file"""
  with open(kCsvFilename, 'r', newline='') as csvfile:
    csvr = csv.DictReader(csvfile)
    records = {row[kCsvColBarcode]: row for row in csvr}
    fieldnames = csvr.fieldnames
    print(f"loaded {len(records)} rows, fieldnames {fieldnames} from existing CSV")

  with open(kCsvFilename, 'a', newline='') as csvfile:
    csvw = csv.DictWriter(csvfile, fieldnames=kCsvHeaders)
    curr_dict: Optional[Dict[str, str]] = None  # none if no part active

    while True:
      data = data_queue.get()

      if isinstance(data, str):
        if not data and curr_dict is not None:  # return to commit line
          csvw.writerow(curr_dict)
          csvfile.flush()
          records[curr_dict[kCsvColBarcode]] = curr_dict
          curr_dict = None
          print(f"line saved")
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
        else:
          print(f"unknown command {data}")
      elif isinstance(data, zxingcpp.Result):
        barcode_raw = data.text
        barcode_key = str(barcode_raw.encode('utf-8'))
        if curr_dict is not None:  # commit prev line
          csvw.writerow(curr_dict)
          csvfile.flush()
          records[curr_dict[kCsvColBarcode]] = curr_dict

        if barcode_key in records:
          print("WARNING: duplicate row")

        curr_dict = {kCsvColBarcode: barcode_key,
                     kCsvSymbology: data.symbology_identifier}
        if data.symbology_identifier.startswith(']d'):
          decoded = Iso15434.from_data(data.text)
          distributor = guess_distributor(data, decoded)

          curr_dict[kCsvColSupplierPart] = decoded.data[FieldSupplierPartNumber].raw
          curr_dict[kCsvColPackQty] = decoded.data[FieldQuantity].raw

          print(f"{distributor} {curr_dict[kCsvColSupplierPart]} x {curr_dict[kCsvColPackQty]}")
          if distributor == 'DigiKey2d':
            dk_barcode = digikey_api.barcode2d(barcode_raw)
            dk_pn = dk_barcode.DigiKeyPartNumber
            curr_dict[kCsvColDistBarcodeData] = dk_barcode.model_dump_json()
            dk_product = digikey_api.product_details(dk_pn)
            curr_dict[kCsvColDistProdData] = dk_product.model_dump_json()

            curr_dict[kCsvColDesc] = dk_product.Product.Description.ProductDescription
            print(dk_product)
          elif distributor == 'Mouser2d':
            pass
        else:
          print(f"unknown symbology {data.symbology_identifier} {data.text}")


def beep_fn():
  while True:
    beepy.beep(sound=beep_queue.get())  # beep seems to be blocking, so it gets its own thread


# data matrix code based on https://github.com/llpassarelli/dmtxscann/blob/master/dmtxscann.py
if __name__ == '__main__':
  # initialize Digikey API
  with open('digikey_api_config.json') as f:
    # IMPORTANT! You will need to set up your DigiKey API access and API keys.
    # Copy the digikey_api_config_sample.json to digikey_api_config.json and fill in the values.
    digikey_api_config = DigiKeyApiConfig.model_validate_json(f.read())

  digikey_api = DigiKeyApi(digikey_api_config, token_filename='digikey_api_token.json')

  # initialize output file
  # TODO: validate fieldnames
  if not os.path.exists(kCsvFilename):
    print(f"creating new csv {kCsvFilename}")
    with open(kCsvFilename, 'w', newline='') as csvfile:
      csvw = csv.DictWriter(csvfile, fieldnames=kCsvHeaders)
      csvw.writeheader()

  # initialize OpenCV
  cap = cv2.VideoCapture(0)  # TODO configurable
  assert cap.isOpened, "failed to open camera"

  console_thread = Thread(target=console_fn)
  csv_thread = Thread(target=csv_fn)
  beep_thread = Thread(target=beep_fn)

  console_thread.start()
  csv_thread.daemon = True
  csv_thread.start()
  beep_thread.daemon = True
  beep_thread.start()

  scan_fn(cap)  # becomes the main thread for user input because it handles the exit function
