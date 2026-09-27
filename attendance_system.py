"""Headless CCTV face recognition and attendance recording.

This module deliberately depends only on OpenCV and the Python standard library.
It is a useful baseline for a controlled classroom, but the recognizer can later
be replaced by a modern embedding model without changing the attendance store.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


FACE_SIZE = (112, 112)
FEATURE_SIZE = 20


@dataclass(frozen=True)
class Attendance:
    person_id: str
    recorded_at: str
    confidence: float
    source: str


class FaceRecognizer:
    """Small dependency-free recognizer trained from folders of face images."""

    def __init__(self, people_dir: Path, threshold: float = 0.82):
        self.people_dir = people_dir
        self.threshold = threshold
        cascade = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(cascade)
        if self.detector.empty():
            raise RuntimeError(f"Could not load face detector: {cascade}")
        self.references = self._load_references()

    @staticmethod
    def _feature(face: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY) if face.ndim == 3 else face
        gray = cv2.resize(gray, FACE_SIZE)
        gray = cv2.equalizeHist(gray).astype(np.float32) / 255.0
        # Low-frequency DCT coefficients retain facial structure while reducing
        # sensitivity to camera noise and minor resizing artifacts.
        vector = cv2.dct(gray)[:FEATURE_SIZE, :FEATURE_SIZE].flatten()[1:]
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )
        return [tuple(map(int, face)) for face in faces]

    def _largest_face(self, image: np.ndarray) -> np.ndarray:
        faces = self.detect(image)
        if not faces:
            # Enrollment photos may already be tightly cropped.
            return image
        x, y, width, height = max(faces, key=lambda box: box[2] * box[3])
        return image[y : y + height, x : x + width]

    def _load_references(self) -> dict[str, list[np.ndarray]]:
        references: dict[str, list[np.ndarray]] = defaultdict(list)
        if not self.people_dir.exists():
            return references
        for path in sorted(self.people_dir.glob("*/*")):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            image = cv2.imread(str(path))
            if image is not None:
                references[path.parent.name].append(
                    self._feature(self._largest_face(image))
                )
        return dict(references)

    def identify(self, face: np.ndarray) -> tuple[str | None, float]:
        candidate = self._feature(face)
        best_person, best_score = None, -1.0
        for person_id, samples in self.references.items():
            # Use the best enrollment image to tolerate pose variation.
            score = max(float(np.dot(candidate, sample)) for sample in samples)
            if score > best_score:
                best_person, best_score = person_id, score
        if best_score < self.threshold:
            return None, max(0.0, best_score)
        return best_person, best_score


class AttendanceStore:
    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY,
                person_id TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(person_id, attendance_date)
            )"""
        )

    def record(self, person_id: str, confidence: float, source: str) -> Attendance | None:
        now = datetime.now(timezone.utc)
        attendance = Attendance(person_id, now.isoformat(), confidence, source)
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO attendance
               (person_id, attendance_date, recorded_at, confidence, source)
               VALUES (?, ?, ?, ?, ?)""",
            (person_id, now.date().isoformat(), attendance.recorded_at, confidence, source),
        )
        self.connection.commit()
        return attendance if cursor.rowcount else None

    def close(self) -> None:
        self.connection.close()

    def list_for_date(self, attendance_date: str) -> list[Attendance]:
        rows = self.connection.execute(
            """SELECT person_id, recorded_at, confidence, source
               FROM attendance WHERE attendance_date = ? ORDER BY recorded_at""",
            (attendance_date,),
        ).fetchall()
        return [Attendance(*row) for row in rows]


def process_video(
    video_path: Path,
    people_dir: Path,
    database: Path,
    *,
    threshold: float = 0.82,
    confirmations: int = 3,
    sample_every: int = 5,
) -> list[Attendance]:
    if confirmations < 1 or sample_every < 1:
        raise ValueError("confirmations and sample_every must be at least 1")
    recognizer = FaceRecognizer(people_dir, threshold)
    if not recognizer.references:
        raise RuntimeError(
            f"No enrollment images found. Add images under {people_dir}/<person-id>/"
        )
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    store = AttendanceStore(database)
    sightings: dict[str, int] = defaultdict(int)
    recorded: list[Attendance] = []
    frame_number = 0
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            frame_number += 1
            if frame_number % sample_every:
                continue
            seen_this_frame: dict[str, float] = {}
            for x, y, width, height in recognizer.detect(frame):
                person_id, score = recognizer.identify(
                    frame[y : y + height, x : x + width]
                )
                if person_id:
                    seen_this_frame[person_id] = max(score, seen_this_frame.get(person_id, 0))
            for person_id, score in seen_this_frame.items():
                sightings[person_id] += 1
                if sightings[person_id] == confirmations:
                    item = store.record(person_id, score, video_path.name)
                    if item:
                        recorded.append(item)
    finally:
        capture.release()
        store.close()
    return recorded


def main() -> None:
    parser = argparse.ArgumentParser(description="Take attendance from CCTV video")
    parser.add_argument(
        "video",
        type=Path,
        nargs="?",
        default=Path(__file__).parent.parent / "sample-videos" / "c1.mp4",
        help="uploaded CCTV video path (default: ../sample-videos/c1.mp4)",
    )
    parser.add_argument("--people", type=Path, default=Path("people"))
    parser.add_argument("--database", type=Path, default=Path("data/attendance.db"))
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--confirmations", type=int, default=3)
    parser.add_argument("--sample-every", type=int, default=5)
    parser.add_argument(
        "--list",
        action="store_true",
        help="list today's recorded attendance instead of processing a video",
    )
    args = parser.parse_args()
    if args.list:
        store = AttendanceStore(args.database)
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            results = store.list_for_date(today)
        finally:
            store.close()
        print(json.dumps([asdict(item) for item in results], indent=2))
        return
    try:
        results = process_video(
            args.video,
            args.people,
            args.database,
            threshold=args.threshold,
            confirmations=args.confirmations,
            sample_every=args.sample_every,
        )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps([asdict(item) for item in results], indent=2))


if __name__ == "__main__":
    main()
