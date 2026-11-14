# GestureCam (Windows MVP)

A minimal desktop app that uses hand gestures to show/hide a camera source in OBS.
Use OBS Virtual Camera as the output device in Zoom, Meet, Discord, etc.

## Default gestures

- Wave: show camera
- Open palm held: hide camera
- Peace sign held: toggle camera

Gesture assignments and timing values are in `config.json`.

## Requirements

- Windows 10/11, 64-bit
- Python 3.11 (recommended for a predictable package environment)
- OBS Studio 28+ (WebSocket server is built in)
- A webcam

## 1. Install

Open PowerShell in this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 2. Configure OBS

1. Open OBS Studio.
2. Create or select a scene.
3. Add your webcam as a **Video Capture Device** source.
4. Open **Tools > WebSocket Server Settings**.
5. Enable the WebSocket server. Keep the default port `4455`.
6. Set a password.
7. Copy that password into `config.json`.
8. In `config.json`, set the exact scene and webcam source names.

Do not expose the WebSocket port to the public internet. Keep it bound to localhost.

## 3. Run

```powershell
python main.py
```

Click **Connect to OBS**, then **Start gesture control**.

The first launch downloads the official MediaPipe Hand Landmarker model into `assets/`.
An internet connection is required only for that first download.

## 4. Use it in other apps

1. In OBS, click **Start Virtual Camera**.
2. In Zoom/Meet/Discord, select **OBS Virtual Camera** as your camera.
3. GestureCam toggles the webcam source in the OBS scene. When hidden, OBS shows the remaining scene/background.

For a privacy-safe hidden state, add a solid-color background source to the scene and place it below the webcam source.

## 5. Customize gestures

Edit `config.json`:

- `wave_action`: `show`, `hide`, or `toggle`
- `open_palm_action`: `show`, `hide`, or `toggle`
- `peace_action`: `show`, `hide`, or `toggle`

You can adjust:

- `gesture_hold_seconds`
- `cooldown_seconds`
- `wave_window_seconds`
- `wave_min_direction_changes`

Restart GestureCam after editing the file.

## Troubleshooting

### OBS connection fails
- Confirm OBS is running.
- Confirm WebSocket is enabled and port/password match.
- Check scene and source names exactly, including spaces and capitalization.

### Camera source not found
- Confirm the selected source is in the configured scene.
- If the source is nested inside a group, move it into the scene directly for this MVP.

### Webcam does not open
- Close apps that may be using the webcam.
- Change `camera_index` in `config.json` (try 1 or 2).

### MediaPipe model download fails
- Check internet access and retry. The model is downloaded once and cached locally.

### Gestures are unreliable
- Keep the full hand in frame and use even lighting.
- Start with `gesture_hold_seconds` around 0.9.
- The current MVP assumes a mostly upright hand; rotation-invariant classification is a future improvement.

## Current limitations

- This is an MVP, not a signed installer or native OBS plugin.
- It controls one source in one scene.
- The hand detector is local; camera frames are not uploaded.
- Hiding the source affects OBS output, not the physical webcam device itself.
- A future native OBS plugin can move the controls into OBS and eliminate the separate desktop controller.


## Fade transitions (GestureCam 1.1)

When you click Connect to OBS, GestureCam creates (if missing) a Color Correction
filter named `GestureCam Fade` on the configured webcam source. It animates the
filter's opacity from 0 to 1 or 1 to 0 over 700 ms using linear easing.

- Show: set opacity to 0, enable the scene item, then fade to 1.
- Hide: fade to 0, then disable the scene item.
- Gesture detection remains connected to its own webcam capture.
- Sound effects are disabled.

OBS's built-in Color Correction filter supports source opacity. If you already
have a filter with the name `GestureCam Fade`, the app reuses it. Do not rename
or remove that filter while GestureCam is connected.

You can change the transition in `config.json`:
- `transition_duration_ms`: duration in milliseconds
- `transition_filter_name`: name of the OBS filter

The current implementation uses linear easing as requested.


## Webcam capture backend

`camera_backend` in `config.json` defaults to `MSMF` (Windows Media Foundation).
If GestureCam cannot open the webcam, try `DSHOW` or `ANY`. This setting affects
GestureCam's own hand-detection capture only; it does not change the OBS source.


## Updated gesture mapping

- Peace sign held: fade camera IN (show).
- Finger snap motion: fade camera OUT (hide).
- The snap detector approximates a snap by detecting thumb/middle fingertip
  contact followed by quick separation. It may need tuning for webcam angle,
  lighting, and frame rate; a real acoustic snap detector is not included.
- Wave remains configured as show; open palm remains configured as hide.
