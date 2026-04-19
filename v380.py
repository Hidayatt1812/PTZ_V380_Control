import cv2
import numpy as np
from config import RTSP_URL

cap = cv2.VideoCapture(RTSP_URL)


while True:
	_, frame = cap.read()
	 
	cv2.imshow("Frame",frame)
	key = cv2.waitKey(1)

	if  key == 27:
		break

cap.release()
cv2.destroAllWindows()
