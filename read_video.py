from pathlib import Path
import cv2

video_path = (
    Path(__file__).parent.parent
    / "sample-videos"
    / "c1.mp4"
)

video = cv2.VideoCapture(str(video_path))

if not video.isOpened():
    raise RuntimeError(f"Could not open video: {video_path}")

while True:
    success, frame = video.read()

    if not success:
        break

    frame = cv2.resize(frame, (960, 540))
    cv2.imshow("Classroom CCTV", frame)

    # Press Q to close the video
    if cv2.waitKey(25) & 0xFF == ord("q"):
        break

video.release()
cv2.destroyAllWindows()