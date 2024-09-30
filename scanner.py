import os
from typing import Optional

import cv2
import zxingcpp
import numpy as np
import datetime
import sys
import beepy

from queue import Queue
import json

from digikey_api import DigikeyApi, DigikeyApiConfig
from iso15434 import Iso15434

kWindowName = "PartsScanner"
kFrameWidth = 1920
kFrameHeight = 1080

kFontScale = 0.5

kRoiWidth = 280  # center-aligned region-of-interest - speeds up scanning
kRoiHeight = 280

kBarcodeTimeoutThreshold = datetime.timedelta(seconds=4)  # after not seeing a barcode for this long, count as a new one

kCsvHeaders = ['barcode',  # entire barcode, unique, used as a key
               'supplier_part',  # manufacturer part number
               'desc',  # catalog description
               'pack_qty',  # quantity as packed
               'mod_qty',  # quantity modifier from pack_qty, eg -20
               'dist_data',  # entire distributor data response
               'scan_time',  # initial scan time
               'update_time'  # last row updated time
               ]

last_seen_times = {}  # text -> time, used for scan antiduplication


data_queue = Queue()
beep_queue = Queue()


def guess_distributor(barcode, decoded: Iso15434) -> Optional[str]:
  """Guesses the distributor from barcode metadata and decoded data"""
  if barcode.format == zxingcpp.BarcodeFormat.DataMatrix:
    if '20Z' in decoded.data:
      return 'Digikey'
    else:
      return 'Mouser'
  else:
    return None


def scan_fn(cap: cv2.VideoCapture):
  """Thread for scanning barcodes, enqueueing scanned barcodes
  Handles de-duplication using a timeout between scans of the same barcode"""
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


def console_fn(csvfilename: str):
  """Thread that handles user input, enueueing each user-inputted line"""
  while True:
    userline = input()
    data_queue.put(userline)


def csv_fn():
  """'Primary' thread that mixes scanned barcodes and user input, writing data to a CSV file"""
  while True:
    data = data_queue.get()

    if isinstance(data, str):
      pass
    elif isinstance(data, zxingcpp.Result):
      decoded = Iso15434.from_data(data.text)
      distributor = guess_distributor(data, decoded)
      print(f"{distributor} {decoded}")


def beep_fn():
  while True:
    beepy.beep(sound=beep_queue.get())  # beep seems to be blocking, so it gets its own thread


# data matrix code based on https://github.com/llpassarelli/dmtxscann/blob/master/dmtxscann.py
if __name__ == '__main__':
  with open('digikey_api_sandbox_config.json') as f:
    digikey_api_config = DigikeyApiConfig.model_validate_json(f.read())
  if os.path.exists('digikey_api_token.json'):
    with open('digikey_api_token.json') as f:
      token = json.load(f)
      print("Loaded Digikey API token")
  else:
    token = None

  digikey_api = DigikeyApi(digikey_api_config, token=token, sandbox=True)

  with open('digikey_api_token.json', 'w') as f:
    json.dump(digikey_api.token(), f)
    print("Saved Digikey API token")

  print(digikey_api.product_details("ducks"))
  print(digikey_api.barcode("1234567"))
  digikey_api.barcode2d("[)>␞06␝PRMCF0603FT5K10CT-ND␝1PRMCF0603FT5K10␝K␝1K58732613␝10K67192477␝11K1␝4LCN␝Q100␝11ZPICK␝12Z1943037␝13Z803900␝20Z00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")

  sys.exit(0)

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
