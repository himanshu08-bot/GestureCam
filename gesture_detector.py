from __future__ import annotations

import time
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def ensure_model(model_path: str):
    from pathlib import Path
    from urllib.request import urlretrieve

    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print("Downloading the MediaPipe hand model (first launch only)...")
        urlretrieve(MODEL_URL, path)
    return str(path)


class GestureDetector:
    """
    Recognizes:
      - WAVE: open hand moving side-to-side -> SHOW
      - OPEN_PALM: held steady -> HIDE
      - PEACE: held two-finger sign -> TOGGLE

    The wave detector is evaluated before the open-palm hold so waving
    does not immediately trigger the hide gesture.
    """

    def __init__(self, model_path="assets/hand_landmarker.task",
                 hold_seconds=0.9, wave_window=1.3,
                 wave_min_direction_changes=2):
        model_path = ensure_model(model_path)
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)
        self.hold_seconds = float(hold_seconds)
        self.wave_window = float(wave_window)
        self.wave_min_direction_changes = int(wave_min_direction_changes)
        self.pose_since = {}
        self.wave_positions = deque()
        self.last_video_ms = 0
        self.snap_pinched_at = None
        self.snap_armed = True
        self.snap_cooldown_until = 0.0

    @staticmethod
    def _finger_states(lm):
        # For a roughly upright hand, finger tips above their PIP joints
        # indicate extension. Thumb uses horizontal displacement.
        index = lm[8].y < lm[6].y
        middle = lm[12].y < lm[10].y
        ring = lm[16].y < lm[14].y
        pinky = lm[20].y < lm[18].y
        thumb = abs(lm[4].x - lm[2].x) > 0.045
        return thumb, index, middle, ring, pinky

    @staticmethod
    def _wave_detected(points, min_changes):
        if len(points) < 5:
            return False
        xs = [p[1] for p in points]
        span = max(xs) - min(xs)
        if span < 0.18:
            return False
        diffs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        signs = [1 if d > 0.012 else -1 if d < -0.012 else 0 for d in diffs]
        signs = [s for s in signs if s]
        changes = sum(signs[i] != signs[i - 1] for i in range(1, len(signs)))
        return changes >= min_changes

    def process(self, frame):
        now = time.monotonic()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int(now * 1000)
        timestamp_ms = max(timestamp_ms, self.last_video_ms + 1)
        self.last_video_ms = timestamp_ms
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.hand_landmarks:
            self.pose_since.clear()
            self.wave_positions.clear()
            return "NO HAND", None

        lm = result.hand_landmarks[0]
        thumb, index, middle, ring, pinky = self._finger_states(lm)
        fingers = (index, middle, ring, pinky)

        # Approximate finger snap: thumb and middle fingertips touch,
        # then separate quickly. Distances are normalized to hand size.
        # This is a visual approximation; webcam frame rate and angle matter.
        def distance(a, b):
            dx = lm[a].x - lm[b].x
            dy = lm[a].y - lm[b].y
            return (dx * dx + dy * dy) ** 0.5

        hand_scale = max(distance(0, 9), 0.001)  # wrist to middle MCP
        pinch_ratio = distance(4, 12) / hand_scale
        if pinch_ratio < 0.24 and self.snap_armed and now >= self.snap_cooldown_until:
            self.snap_pinched_at = now
            self.snap_armed = False
        elif self.snap_pinched_at is not None:
            pinch_age = now - self.snap_pinched_at
            if pinch_ratio > 0.43 and pinch_age <= 0.38:
                self.snap_pinched_at = None
                self.snap_armed = True
                self.snap_cooldown_until = now + 1.0
                self.pose_since.clear()
                return "SNAP", lm
            if pinch_age > 0.38:
                self.snap_pinched_at = None
                self.snap_armed = True
        elif pinch_ratio > 0.43:
            self.snap_armed = True

        # Keep wrist x history only while the palm is open.
        is_open = all(fingers)
        if is_open:
            self.wave_positions.append((now, float(lm[0].x)))
        else:
            self.wave_positions.clear()

        while self.wave_positions and now - self.wave_positions[0][0] > self.wave_window:
            self.wave_positions.popleft()

        if is_open and self._wave_detected(
            self.wave_positions, self.wave_min_direction_changes
        ):
            self.pose_since.clear()
            return "WAVE", lm

        if is_open:
            pose = "OPEN PALM"
        elif index and middle and not ring and not pinky:
            pose = "PEACE"
        elif not any(fingers):
            pose = "FIST"
        else:
            pose = "OTHER"

        if pose != "OTHER":
            self.pose_since.setdefault(pose, now)
            held = now - self.pose_since[pose]
            if held >= self.hold_seconds:
                return pose, lm
            # Distinguish a pose being observed from a gesture that is
            # fully held long enough to trigger an action.
            return f"{pose} (HOLD)", lm
        self.pose_since = {pose: self.pose_since.get(pose, now)}
        return pose, lm

    def close(self):
        self.landmarker.close()
