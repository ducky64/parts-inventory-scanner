import cv2
import zxingcpp
import datetime

from iso15434 import Iso15434

kWindowName = "PartsScanner"
kFrameWidth = 1920
kFrameHeight = 1080

kFontScale = 0.5

kRoiWidth = 240  # center-aligned region-of-interest
kRoiHeight = 240

kBarcodeTimeoutThreshold = datetime.timedelta(seconds=2)  # after not seeing a barcode for this long, count as a new one

last_seen_times = {}  # text -> time

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

    for result in results:
      last_seen = last_seen_times.get(result.text, datetime.datetime(1990, 1, 1))
      if frame_time - last_seen > kBarcodeTimeoutThreshold:
        frame_thick = 4
        print(f"{result.text.encode('unicode-escape')}")
        print(Iso15434.from_data(result.text))
      else:
        frame_thick = 1
      last_seen_times[result.text] = frame_time

      pos = result.position
      cv2.line(frame, zxing_pos_to_cv2(pos.top_left), zxing_pos_to_cv2(pos.top_right), (0, 255, 0), frame_thick)
      cv2.line(frame, zxing_pos_to_cv2(pos.top_right), zxing_pos_to_cv2(pos.bottom_right), (0, 255, 0), frame_thick)
      cv2.line(frame, zxing_pos_to_cv2(pos.bottom_right), zxing_pos_to_cv2(pos.bottom_left), (0, 255, 0), frame_thick)
      cv2.line(frame, zxing_pos_to_cv2(pos.bottom_left), zxing_pos_to_cv2(pos.top_left), (0, 255, 0), frame_thick)

      cv2.putText(frame, f"{result.text}", (woff + pos.top_left.x, hoff + pos.top_left.y),
                  cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 255, 0), 1)

    cv2.imshow(kWindowName, frame)
    cv2.imshow(kWindowName + "b", roi)
    key = cv2.waitKey(1)  # delay
    if key == ord('q'):
      break
