from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import cv2
from PIL import Image, ImageTk

from gesture_detector import GestureDetector
from obs_controller import OBSController


BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class GestureCamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GestureCam")
        self.root.geometry("760x540")
        self.root.minsize(680, 480)
        self.root.configure(bg="#101318")

        self.config = load_config()
        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.worker = None
        self.detector = None
        self.obs = None
        self.scene_item_id = None
        self.camera_visible = True
        self.current_opacity = 1.0
        self.transition_after_id = None
        self.transition_started_at = 0.0
        self.transition_start_opacity = 1.0
        self.transition_target_opacity = 1.0
        self.transition_target_visible = True
        self.transition_duration = max(
            100, int(self.config.get("transition_duration_ms", 700))
        ) / 1000.0
        self.filter_name = self.config.get(
            "transition_filter_name", "GestureCam Fade"
        )
        self.last_action_at = 0.0
        self.last_triggered_pose = None
        self.photo = None

        self._style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(40, self._update_preview)

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=8, font=("Segoe UI", 10))
        style.configure("TLabel", background="#101318", foreground="#e8edf5",
                        font=("Segoe UI", 10))
        style.configure("TEntry", padding=6)

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#101318")
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(header, text="GestureCam", bg="#101318", fg="#f5f7fb",
                 font=("Segoe UI Semibold", 20)).pack(side="left")
        self.status = tk.Label(header, text="● Not connected", bg="#101318",
                               fg="#f0b45a", font=("Segoe UI", 10))
        self.status.pack(side="right", pady=8)

        body = tk.Frame(self.root, bg="#101318")
        body.pack(fill="both", expand=True, padx=18, pady=8)

        preview_frame = tk.Frame(body, bg="#191f28", highlightthickness=1,
                                 highlightbackground="#2c3542")
        preview_frame.pack(side="left", fill="both", expand=True, padx=(0, 12))
        tk.Label(preview_frame, text="CAMERA PREVIEW", bg="#191f28",
                 fg="#9eacbd", font=("Segoe UI Semibold", 9)).pack(
                     anchor="w", padx=12, pady=(10, 6))
        self.preview = tk.Label(preview_frame, text="Camera preview will appear here",
                                bg="#080a0e", fg="#7f8b9a",
                                font=("Segoe UI", 11))
        self.preview.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        side = tk.Frame(body, bg="#101318", width=220)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="CONTROL", bg="#101318", fg="#9eacbd",
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(2, 8))
        self.gesture_label = tk.Label(side, text="Waiting for hand",
                                      bg="#1b222c", fg="#f5f7fb",
                                      font=("Segoe UI Semibold", 13),
                                      padx=12, pady=16)
        self.gesture_label.pack(fill="x", pady=(0, 10))

        self.camera_label = tk.Label(side, text="Camera: UNKNOWN",
                                     bg="#1b222c", fg="#dbe4ef",
                                     font=("Segoe UI", 10), padx=10, pady=10)
        self.camera_label.pack(fill="x", pady=(0, 12))

        ttk.Button(side, text="Connect to OBS", command=self.connect_obs).pack(fill="x", pady=4)
        ttk.Button(side, text="Start gesture control", command=self.start).pack(fill="x", pady=4)
        ttk.Button(side, text="Stop gesture control", command=self.stop).pack(fill="x", pady=4)
        ttk.Button(side, text="Show camera", command=lambda: self.set_visible(True)).pack(fill="x", pady=4)
        ttk.Button(side, text="Hide camera", command=lambda: self.set_visible(False)).pack(fill="x", pady=4)

        self.log = tk.Text(side, height=8, bg="#080a0e", fg="#aebccc",
                           insertbackground="white", relief="flat",
                           font=("Consolas", 8), wrap="word")
        self.log.pack(fill="both", expand=True, pady=(12, 0))
        self._log("Ready. Connect OBS, then start gesture control.")

        footer = tk.Label(
            self.root,
            text="Peace = Fade In  •  Snap = Fade Out  •  Fade: 700 ms",
            bg="#101318", fg="#8391a2", font=("Segoe UI", 9)
        )
        footer.pack(fill="x", padx=18, pady=(2, 12))

    def _log(self, text):
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log.see("end")

    def connect_obs(self):
        try:
            if self.obs:
                self.obs.disconnect()
            self.obs = OBSController(
                self.config["obs_host"],
                self.config["obs_port"],
                self.config["obs_password"]
            )
            self.scene_item_id = self.obs.find_scene_item_id(
                self.config["scene_name"],
                self.config["camera_source_name"]
            )
            self.obs.ensure_opacity_filter(
                self.config["camera_source_name"],
                self.filter_name
            )
            self.camera_visible = self.obs.get_scene_item_enabled(
                self.config["scene_name"], self.scene_item_id
            )
            self.current_opacity = 1.0 if self.camera_visible else 0.0
            self.obs.set_opacity(
                self.config["camera_source_name"],
                self.filter_name,
                self.current_opacity
            )
            self.status.config(text="● OBS connected", fg="#68d391")
            self.camera_label.config(
                text=f"Camera: {'VISIBLE' if self.camera_visible else 'HIDDEN'}"
            )
            self._log("Connected to OBS; GestureCam Fade filter is ready.")
            messagebox.showinfo(
                "GestureCam",
                'Connected to OBS. The "GestureCam Fade" Color Correction '
                "filter is ready on your webcam source."
            )
        except Exception as exc:
            self.obs = None
            self.status.config(text="● OBS connection failed", fg="#f0b45a")
            self._log(f"OBS error: {exc}")
            messagebox.showerror("OBS connection failed", str(exc))

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.obs or self.scene_item_id is None:
            messagebox.showwarning("GestureCam", "Connect to OBS first.")
            return
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._camera_loop, daemon=True)
        self.worker.start()
        self._log("Gesture control started.")

    def stop(self):
        self.stop_event.set()
        self._log("Stopping gesture control...")

    def _camera_loop(self):
        backend_name = str(self.config.get("camera_backend", "MSMF")).upper()
        backend = {
            "MSMF": cv2.CAP_MSMF,
            "DSHOW": cv2.CAP_DSHOW,
            "ANY": cv2.CAP_ANY
        }.get(backend_name, cv2.CAP_MSMF)
        cap = cv2.VideoCapture(int(self.config["camera_index"]), backend)
        if not cap.isOpened():
            self.frames.put(("error", "Could not open webcam. Check camera_index."))
            return

        try:
            self.detector = GestureDetector(
                hold_seconds=self.config["gesture_hold_seconds"],
                wave_window=self.config["wave_window_seconds"],
                wave_min_direction_changes=self.config["wave_min_direction_changes"]
            )
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    continue

                if self.config.get("mirror_preview", True):
                    frame = cv2.flip(frame, 1)

                gesture, landmarks = self.detector.process(frame)
                self._handle_gesture(gesture)

                if landmarks:
                    h, w = frame.shape[:2]
                    for point in landmarks:
                        cv2.circle(frame, (int(point.x * w), int(point.y * h)),
                                   4, (80, 220, 150), -1)

                cv2.putText(frame, gesture, (18, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 220, 150), 2)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                try:
                    self.frames.put_nowait(("frame", rgb, gesture))
                except queue.Full:
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass
                    self.frames.put_nowait(("frame", rgb, gesture))
        except Exception as exc:
            self.frames.put(("error", str(exc)))
        finally:
            cap.release()
            if self.detector:
                self.detector.close()
                self.detector = None

    def _handle_gesture(self, gesture):
        now = time.monotonic()
        if now - self.last_action_at < self.config["cooldown_seconds"]:
            return

        action = None
        if gesture == "WAVE":
            action = self.config["wave_action"]
        elif gesture == "OPEN PALM":
            action = self.config["open_palm_action"]
        elif gesture == "PEACE":
            action = self.config["peace_action"]
        elif gesture == "SNAP":
            action = self.config.get("snap_action", "hide")

        # Only trigger once per continuous held gesture. Re-arm when pose changes.
        if gesture != self.last_triggered_pose:
            self.last_triggered_pose = gesture
            if action == "show":
                self.root.after(0, lambda: self.set_visible(True))
            elif action == "hide":
                self.root.after(0, lambda: self.set_visible(False))
            elif action == "toggle":
                next_state = not self.camera_visible
                self.root.after(0, lambda state=next_state: self.set_visible(state))
            if action:
                self.last_action_at = now

    def set_visible(self, visible):
        """Animate the OBS webcam source opacity to the requested state."""
        if not self.obs or self.scene_item_id is None:
            self._log("Not connected to OBS; visibility command ignored.")
            return

        visible = bool(visible)
        target = 1.0 if visible else 0.0

        # Cancel the previous scheduled frame. Start from the current opacity
        # so a gesture during a fade reverses smoothly rather than snapping.
        if self.transition_after_id is not None:
            try:
                self.root.after_cancel(self.transition_after_id)
            except Exception:
                pass
            self.transition_after_id = None

        try:
            if visible:
                # Set alpha to zero before enabling a previously hidden source,
                # preventing a one-frame flash at full opacity.
                if not self.camera_visible:
                    self.current_opacity = 0.0
                    self.obs.set_opacity(
                        self.config["camera_source_name"],
                        self.filter_name,
                        0.0
                    )
                    self.obs.set_camera_visible(
                        self.config["scene_name"], self.scene_item_id, True
                    )

            self.transition_start_opacity = self.current_opacity
            self.transition_target_opacity = target
            self.transition_target_visible = visible
            self.transition_started_at = time.monotonic()

            if abs(self.transition_start_opacity - target) < 0.001:
                self._finish_transition(visible)
                return

            self._log(
                f"Fading {'in' if visible else 'out'} "
                f"({self.config.get('transition_duration_ms', 700)} ms)."
            )
            self._animate_fade()
        except Exception as exc:
            self._log(f"Transition error: {exc}")
            messagebox.showerror("GestureCam transition error", str(exc))

    def _animate_fade(self):
        elapsed = time.monotonic() - self.transition_started_at
        duration = self.transition_duration
        progress = min(1.0, elapsed / duration) if duration > 0 else 1.0

        # Selected easing: linear.
        opacity = (
            self.transition_start_opacity
            + (self.transition_target_opacity - self.transition_start_opacity)
            * progress
        )
        opacity = max(0.0, min(1.0, opacity))

        try:
            self.obs.set_opacity(
                self.config["camera_source_name"],
                self.filter_name,
                opacity
            )
            self.current_opacity = opacity
        except Exception as exc:
            self.transition_after_id = None
            self._log(f"Could not update OBS opacity: {exc}")
            return

        if progress >= 1.0:
            self.transition_after_id = None
            self._finish_transition(self.transition_target_visible)
        else:
            self.transition_after_id = self.root.after(33, self._animate_fade)

    def _finish_transition(self, visible):
        self.current_opacity = 1.0 if visible else 0.0
        if not visible:
            # Only disable after opacity reaches zero.
            self.obs.set_camera_visible(
                self.config["scene_name"], self.scene_item_id, False
            )
        else:
            self.obs.set_camera_visible(
                self.config["scene_name"], self.scene_item_id, True
            )

        self.camera_visible = bool(visible)
        state = "VISIBLE" if visible else "HIDDEN"
        self.camera_label.config(text=f"Camera: {state}")
        self._log(f"Camera source {state.lower()}.")

    def _update_preview(self):
        try:
            while True:
                item = self.frames.get_nowait()
                if item[0] == "error":
                    self._log(item[1])
                    self.status.config(text="● Camera error", fg="#f0b45a")
                else:
                    _, frame, gesture = item
                    image = Image.fromarray(frame)
                    image.thumbnail((520, 420))
                    self.photo = ImageTk.PhotoImage(image)
                    self.preview.configure(image=self.photo, text="")
                    self.gesture_label.config(text=gesture)
                    self.status.config(text="● Gesture control running", fg="#68d391")
        except queue.Empty:
            pass
        self.root.after(40, self._update_preview)

    def close(self):
        self.stop_event.set()
        if self.transition_after_id is not None:
            try:
                self.root.after_cancel(self.transition_after_id)
            except Exception:
                pass
            self.transition_after_id = None
        if self.obs:
            self.obs.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    app = GestureCamApp(window)
    window.mainloop()
