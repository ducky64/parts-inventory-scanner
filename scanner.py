import cv2

kWindowName = "PartsScanner"
kFrameWidth = 1280
kFrameHeight = 720

kRoiWidth = 320  # center-aligned region-of-interest
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

    roi = frame[h//2 - kRoiHeight//2 : h//2 + kRoiHeight//2,
          w//2 - kRoiWidth//2 : w//2 + kRoiWidth//2]

    # display for user
    # analysis ROI display
    cv2.rectangle(frame, (w//2 - kRoiWidth//2, h//2 - kRoiHeight//2),
                  (w//2 + kRoiWidth//2, h//2 + kRoiHeight//2),
                  (255, 0, 0), 1)
    # reticule
    cv2.line(frame, (w//2, h//2 - kRoiHeight//2), (w//2, h//2 + kRoiHeight//2), (0, 255, 0), 1)
    cv2.line(frame, (w//2 - kRoiWidth//2, h//2), (w//2 + kRoiWidth//2, h//2), (0, 255, 0), 1)

    # frame = cv2.resize(  # optional: downscaling
    #   frame,
    #   None,
    #   fx=0.5, fy=0.5,
    #   interpolation=cv2.INTER_CUBIC)

    cv2.imshow(kWindowName, frame)
    cv2.waitKey(1)  # delay
