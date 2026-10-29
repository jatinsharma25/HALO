"""
scripts/standalone_tracker.py

Phase 3: Standalone vision-based person tracking test script.

Runs independent of the FastAPI backend to verify the feedback loop:
  1. Captures frames from webcam (or video file).
  2. Runs YOLOv8n person detection and CentroidTracker.
  3. Displays bounding boxes, image center, dead zone, and error vectors.
  4. Calculates error, applies dead-zone and EMA smoothing.
  5. Computes proportional pan/tilt corrections and clamps angles.
  6. Sends SET,<pan>,<tilt> to Arduino via ArduinoController (or mock mode).
  7. Shows live HUD with state, angles, FPS, and error readouts.

Usage:
    python scripts/standalone_tracker.py --camera 0 --port COM3
    python scripts/standalone_tracker.py --camera 0 --no-arduino   # Test vision only
    python scripts/standalone_tracker.py --source media/test.mp4 --no-arduino

Controls:
    'q' or ESC: Quit
    'h': Home servos (90, 90)
    't': Toggle tracking on/off
    'r': Reset tracker
"""
import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np

from backend.hardware import tracking_config as cfg
from backend.hardware.arduino_controller import ArduinoController
from backend.modules.centroid_tracker import CentroidTracker


def parse_args():
    parser = argparse.ArgumentParser(description="EyeSpy Standalone Vision Tracker")
    parser.add_argument("--camera", type=int, default=0, help="Webcam device index (default: 0)")
    parser.add_argument("--source", type=str, default=None, help="Video file path override")
    parser.add_argument("--port", type=str, default=cfg.SERIAL_PORT, help=f"Serial port (default: {cfg.SERIAL_PORT})")
    parser.add_argument("--baud", type=int, default=cfg.BAUD_RATE, help=f"Baud rate (default: {cfg.BAUD_RATE})")
    parser.add_argument("--no-arduino", action="store_true", help="Run without connecting to Arduino")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="YOLO model path (default: yolov8n.pt)")
    parser.add_argument("--conf", type=float, default=cfg.CONF_THRESHOLD, help=f"Detection confidence (default: {cfg.CONF_THRESHOLD})")
    parser.add_argument("--pan-gain", type=float, default=cfg.PAN_GAIN, help=f"Pan gain (default: {cfg.PAN_GAIN})")
    parser.add_argument("--tilt-gain", type=float, default=cfg.TILT_GAIN, help=f"Tilt gain (default: {cfg.TILT_GAIN})")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 65)
    print(" EyeSpy Standalone Person Tracker (Phase 3)")
    print("=" * 65)

    # 1. Connect to Arduino (if enabled)
    arduino = None
    if not args.no_arduino:
        print(f"Connecting to Arduino on {args.port} @ {args.baud} baud...")
        arduino = ArduinoController(port=args.port, baud_rate=args.baud)
        if arduino.connect():
            print(" Arduino connected successfully!")
            arduino.send_angles(cfg.INITIAL_PAN, cfg.INITIAL_TILT)
        else:
            print(" Arduino connection failed. Running in simulation mode (no hardware output).")
            arduino = None
    else:
        print("Running in --no-arduino mode (visual simulation only).")

    # 2. Load YOLO model
    print(f"Loading YOLO model ({args.model})...")
    try:
        from ultralytics import YOLO
        import supervision as sv
        yolo = YOLO(args.model)
        print(" YOLO model loaded.")
    except Exception as exc:
        print(f" Error loading YOLO: {exc}")
        return

    # 3. Open Video Source
    source_uri = args.source if args.source else args.camera
    print(f"Opening video source: {source_uri}...")
    cap = cv2.VideoCapture(source_uri)
    if not cap.isOpened():
        print(f" Could not open video source: {source_uri}")
        return

    # Video properties
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    print(f"Video resolution: {frame_w}x{frame_h}")

    # Tracking parameters and state
    tracker = CentroidTracker(max_disappeared=30, max_distance=120)
    current_pan = cfg.INITIAL_PAN
    current_tilt = cfg.INITIAL_TILT
    filtered_error_x = 0.0
    filtered_error_y = 0.0
    target_track_id = None
    last_target_time = 0.0
    tracking_active = True
    last_command_time = 0.0
    command_interval = 1.0 / cfg.COMMAND_RATE_HZ

    fps_count = 0
    fps_start = time.time()
    fps_display = 0.0

    print("\nStarting video tracking loop. Press 'q' or ESC to quit.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                if args.source:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                print("End of video stream or camera read failure.")
                break

            h, w = frame.shape[:2]
            cx_frame = w // 2
            cy_frame = h // 2

            # YOLO Person Detection
            person_boxes = []
            try:
                results = yolo(frame, verbose=False)[0]
                detections = sv.Detections.from_ultralytics(results)
                mask = (detections.class_id == 0) & (detections.confidence > args.conf)
                person_detections = detections[mask]
                person_boxes = person_detections.xyxy.astype(int).tolist()
            except Exception as e:
                print(f"Inference error: {e}")

            # Tracker update
            objects_info = tracker.update(person_boxes)
            now = time.time()

            # Target Selection
            selected_target = None
            if objects_info:
                if target_track_id and target_track_id in objects_info:
                    selected_target = (target_track_id, objects_info[target_track_id])
                else:
                    # Fallback to largest bounding box
                    best_id = max(
                        objects_info,
                        key=lambda tid: (
                            (objects_info[tid]["bbox"][2] - objects_info[tid]["bbox"][0]) *
                            (objects_info[tid]["bbox"][3] - objects_info[tid]["bbox"][1])
                        )
                    )
                    selected_target = (best_id, objects_info[best_id])
                    target_track_id = best_id
                last_target_time = now
            else:
                if target_track_id and (now - last_target_time > cfg.TARGET_LOSS_TIMEOUT_S):
                    target_track_id = None

            # Calculate Error & Servos
            target_cx, target_cy = None, None
            raw_error_x, raw_error_y = 0.0, 0.0
            in_deadzone = False

            if selected_target:
                tid, info = selected_target
                bbox = info["bbox"]
                target_cx = int((bbox[0] + bbox[2]) / 2.0)
                target_cy = int((bbox[1] + bbox[3]) / 2.0)

                raw_error_x = target_cx - cx_frame
                raw_error_y = target_cy - cy_frame

                if abs(raw_error_x) < cfg.DEAD_ZONE_X_PX and abs(raw_error_y) < cfg.DEAD_ZONE_Y_PX:
                    in_deadzone = True
                else:
                    filtered_error_x = cfg.EMA_ALPHA * raw_error_x + (1.0 - cfg.EMA_ALPHA) * filtered_error_x
                    filtered_error_y = cfg.EMA_ALPHA * raw_error_y + (1.0 - cfg.EMA_ALPHA) * filtered_error_y

                    if tracking_active and (now - last_command_time >= command_interval):
                        pan_delta = args.pan_gain * filtered_error_x
                        tilt_delta = args.tilt_gain * filtered_error_y

                        # Clamp step
                        pan_delta = max(-cfg.MAX_PAN_STEP, min(cfg.MAX_PAN_STEP, pan_delta))
                        tilt_delta = max(-cfg.MAX_TILT_STEP, min(cfg.MAX_TILT_STEP, tilt_delta))

                        current_pan = max(cfg.MIN_PAN, min(cfg.MAX_PAN, current_pan + pan_delta))
                        current_tilt = max(cfg.MIN_TILT, min(cfg.MAX_TILT, current_tilt + tilt_delta))

                        if arduino and arduino.connected:
                            arduino.send_angles(current_pan, current_tilt)
                        last_command_time = now

            # ── Drawing & Visualization ───────────────────────────────────────
            # Draw center crosshair
            cv2.drawMarker(frame, (cx_frame, cy_frame), (255, 255, 255), cv2.MARKER_CROSS, 20, 1)

            # Draw dead zone box
            dz_x1 = cx_frame - cfg.DEAD_ZONE_X_PX
            dz_y1 = cy_frame - cfg.DEAD_ZONE_Y_PX
            dz_x2 = cx_frame + cfg.DEAD_ZONE_X_PX
            dz_y2 = cy_frame + cfg.DEAD_ZONE_Y_PX
            cv2.rectangle(frame, (dz_x1, dz_y1), (dz_x2, dz_y2), (255, 255, 0), 1, cv2.LINE_AA)

            # Draw detected people
            for tid, info in objects_info.items():
                bx1, by1, bx2, by2 = info["bbox"]
                is_selected = (target_track_id == tid)
                box_color = (0, 255, 0) if is_selected else (128, 128, 128)
                thickness = 2 if is_selected else 1

                cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, thickness)
                label = f"ID: {tid}" + (" [TARGET]" if is_selected else "")
                cv2.putText(frame, label, (bx1, max(20, by1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1)

            # Draw target vector
            if target_cx is not None:
                vec_color = (0, 255, 255) if in_deadzone else (0, 0, 255)
                cv2.line(frame, (cx_frame, cy_frame), (target_cx, target_cy), vec_color, 2)
                cv2.circle(frame, (target_cx, target_cy), 5, (0, 0, 255), -1)

            # Calculate FPS
            fps_count += 1
            if now - fps_start >= 1.0:
                fps_display = fps_count / (now - fps_start)
                fps_count = 0
                fps_start = now

            # Live HUD
            hud_y = 25
            state_str = "TRACKING" if (target_track_id and not in_deadzone) else ("DEADZONE" if in_deadzone else ("TARGET LOST" if tracking_active else "DISABLED"))
            state_color = (0, 255, 0) if state_str == "TRACKING" else ((255, 255, 0) if state_str == "DEADZONE" else (0, 0, 255))

            cv2.putText(frame, f"State: {state_str} (Mode: {'AUTO' if tracking_active else 'MANUAL'})", (15, hud_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, state_color, 2)
            hud_y += 25
            cv2.putText(frame, f"Servos: Pan={current_pan:.1f} deg  Tilt={current_tilt:.1f} deg", (15, hud_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            hud_y += 22
            cv2.putText(frame, f"Error: X={raw_error_x:+d}px  Y={raw_error_y:+d}px  (EMA X={filtered_error_x:+.1f}, Y={filtered_error_y:+.1f})", (15, hud_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            hud_y += 22
            cv2.putText(frame, f"FPS: {fps_display:.1f}  |  Arduino: {'Connected' if (arduino and arduino.connected) else 'None/Sim'}", (15, hud_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("EyeSpy Autonomous Tracker", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' or ESC
                break
            elif key == ord('t'):  # Toggle tracking
                tracking_active = not tracking_active
                print(f"Tracking {'ENABLED' if tracking_active else 'DISABLED'}")
            elif key == ord('h'):  # Home position
                current_pan = cfg.INITIAL_PAN
                current_tilt = cfg.INITIAL_TILT
                if arduino and arduino.connected:
                    arduino.send_angles(current_pan, current_tilt)
                print(f"Servos homed to ({current_pan}, {current_tilt})")
            elif key == ord('r'):  # Reset tracker
                tracker = CentroidTracker(max_disappeared=30, max_distance=120)
                target_track_id = None
                filtered_error_x = 0.0
                filtered_error_y = 0.0
                print("Tracker reset.")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        if arduino and arduino.connected:
            print("Disconnecting Arduino...")
            arduino.disconnect()
        print("Standalone tracker terminated.")


if __name__ == "__main__":
    main()
