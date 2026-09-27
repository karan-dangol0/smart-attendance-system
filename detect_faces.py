from pathlib import Path
import cv2

video_path = (
    Path(__file__).parent.parent
    / "sample-videos"
    / "c1.mp4"
)

# OpenCV includes this pretrained face detector
model_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_detector = cv2.CascadeClassifier(model_path)

video = cv2.VideoCapture(str(video_path))

if not video.isOpened():
    raise RuntimeError(f"Could not open video: {video_path}")

while True:
    success, frame = video.read()

    if not success:
        break

    frame = cv2.resize(frame, (960, 540))

    # Face detector works with grayscale images
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_detector.detectMultiScale(
        gray_frame,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(40, 40),
    )

    # Draw a rectangle around every detected face
    for x, y, width, height in faces:
        cv2.rectangle(
            frame,
            (x, y),
            (x + width, y + height),
            (0, 255, 0),
            2,
        )

    cv2.putText(
        frame,
        f"Faces detected: {len(faces)}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2,
    )

    cv2.imshow("Face Detection", frame)

    if cv2.waitKey(25) & 0xFF == ord("q"):
        break

video.release()
cv2.destroyAllWindows()