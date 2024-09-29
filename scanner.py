import cv2
from PIL import Image
from pylibdmtx.pylibdmtx import decode

kWindowName = "PartsScanner"
kFrameWidth = 1280
kFrameHeight = 720

kFontScale = 0.5

kRoiWidth = 240  # center-aligned region-of-interest
kRoiHeight = 240


# data matrix code based on https://github.com/llpassarelli/dmtxscann/blob/master/dmtxscann.py
if __name__ == '__main__':
  cap = cv2.VideoCapture(0)  # TODO configurable
  assert cap.isOpened, "failed to open camera"
  cap.set(cv2.CAP_PROP_FRAME_WIDTH, kFrameWidth)  # TODO configurable
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT, kFrameHeight)

  while True:
    ticks = cv2.getTickCount()
    ret, frame = cap.read()
    assert ret, "failed to get frame"
    h, w = frame.shape[:2]

    # only scan a small RoI since decode is extremely slow
    roi = frame[h//2 - kRoiHeight//2 : h//2 + kRoiHeight//2,
          w//2 - kRoiWidth//2 : w//2 + kRoiWidth//2]
    roi = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    decodeds = decode(roi, max_count=1, timeout=250)

    # display for user
    # analysis ROI display
    cv2.rectangle(frame, (w//2 - kRoiWidth//2, h//2 - kRoiHeight//2),
                  (w//2 + kRoiWidth//2, h//2 + kRoiHeight//2),
                  (255, 0, 0), 1)
    # reticule
    cv2.putText(frame, f"{w}x{h} {ticks}", (0, 32), cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 0, 255), 1)
    cv2.line(frame, (w//2, h//2 - kRoiHeight//2), (w//2, h//2 + kRoiHeight//2), (0, 0, 255), 1)
    cv2.line(frame, (w//2 - kRoiWidth//2, h//2), (w//2 + kRoiWidth//2, h//2), (0, 0, 255), 1)

    woff = w//2 - kRoiWidth//2  # correct for RoI
    hoff = h//2 + kRoiHeight//2

    for decoded in decodeds:
      rect = decoded.rect
      cv2.rectangle(frame, (woff + rect.left, hoff - rect.top - rect.height),
                    (woff + rect.left + rect.width, hoff - rect.top),
                    (0, 255, 0), 1)
      cv2.putText(frame, f"{decoded.data}", (woff + rect.left, hoff + rect.top),
                  cv2.FONT_HERSHEY_SIMPLEX, kFontScale, (0, 255, 0), 1)

    cv2.imshow(kWindowName, frame)
    cv2.waitKey(1)  # delay
