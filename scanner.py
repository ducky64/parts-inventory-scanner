from typing import Optional

import cv2
import zxingcpp
import numpy as np
import datetime

from iso15434 import Iso15434

kWindowName = "PartsScanner"
kFrameWidth = 1920
kFrameHeight = 1080

kFontScale = 0.5

kRoiWidth = 280  # center-aligned region-of-interest
kRoiHeight = 280

kBarcodeTimeoutThreshold = datetime.timedelta(seconds=2)  # after not seeing a barcode for this long, count as a new one

last_seen_times = {}  # text -> time


def guess_distributor(barcode, decoded: Iso15434) -> Optional[str]:
  """Guesses the distributor from barcode metadata and decoded data"""
  if barcode.format == zxingcpp.BarcodeFormat.DataMatrix:
    if '20Z' in decoded.data:
      return 'Digikey'
    else:
      return 'Mouser'
  else:
    return None


# data matrix code based on https://github.com/llpassarelli/dmtxscann/blob/master/dmtxscann.py
if __name__ == '__main__':
  cap = cv2.VideoCapture(0)  # TODO configurable
  assert cap.isOpened, "failed to open camera"
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
        decoded = Iso15434.from_data(barcode.text)
        dist = guess_distributor(barcode, decoded)
        print(f"{dist}: {decoded}")

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
      break
