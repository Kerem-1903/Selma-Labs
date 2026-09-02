import logging
from typing import Optional, Tuple
from pathlib import Path

# Try importing ultralytics. If not available, fail gracefully.
try:
    from ultralytics import YOLO
    import cv2
    HAS_ULTRALYTICS = True
except ImportError:
    HAS_ULTRALYTICS = False

logger = logging.getLogger(__name__)

class SmartCroppingService:
    def __init__(self, model_name: str = "yolov8n.pt", target_ratio: float = 9/16):
        self.target_ratio = target_ratio
        if HAS_ULTRALYTICS:
            # Load the YOLOv8 nano model. It will auto-download if not present.
            self.model = YOLO(model_name)
        else:
            self.model = None
            logger.warning("ultralytics or cv2 not installed. Smart cropping will gracefully fall back to center crop.")

    def get_crop_filter(self, video_path: str, output_width: int, output_height: int) -> str:
        """
        Analyzes the video to find the primary subject (usually a person)
        and computes the FFmpeg crop filter parameters.
        Returns the crop filter string, e.g., 'crop=1080:1920:420:0'.
        """
        if not self.model:
            return f"crop={output_width}:{output_height}:(in_w-{output_width})/2:(in_h-{output_height})/2"

        try:
            # We sample a few frames to find the bounding box of the main subject
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logger.error(f"Cannot open video for smart cropping: {video_path}")
                return f"crop={output_width}:{output_height}:(in_w-{output_width})/2:(in_h-{output_height})/2"

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # If the video is already the target ratio or narrower, no horizontal crop needed.
            if in_w / in_h <= self.target_ratio + 0.01: # minor tolerance
                cap.release()
                return f"crop={output_width}:{output_height}:(in_w-{output_width})/2:(in_h-{output_height})/2"

            # Sample frames at 20%, 50%, and 80% to find a reliable center
            target_frames = [
                int(frame_count * 0.2),
                int(frame_count * 0.5),
                int(frame_count * 0.8)
            ]

            centers = []

            for frame_idx in target_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Run YOLO prediction (detects all objects, not just people)
                results = self.model.predict(frame, verbose=False)
                if results and len(results[0].boxes) > 0:
                    # Find the largest bounding box in this frame
                    boxes = results[0].boxes
                    largest_box = max(boxes, key=lambda b: (b.xyxy[0][2] - b.xyxy[0][0]) * (b.xyxy[0][3] - b.xyxy[0][1]))
                    x1, y1, x2, y2 = largest_box.xyxy[0].tolist()
                    centers.append((x1 + x2) / 2)

            cap.release()

            # Calculate the scale factor that FFmpeg uses: max(output_width/in_w, output_height/in_h)
            scale_factor = max(output_width / in_w, output_height / in_h)
            scaled_w = int(in_w * scale_factor)
            scaled_h = int(in_h * scale_factor)

            # The y-coordinate crop is always centered for vertical reframing
            crop_y = (scaled_h - output_height) // 2

            if centers:
                # Average the centers from sampled frames to avoid jitter
                orig_center_x = sum(centers) / len(centers)

                # Scale the center to match the pre-crop scaled frame
                scaled_center_x = orig_center_x * scale_factor

                # Calculate the desired crop top-left x coordinate
                crop_x = int(scaled_center_x - (output_width / 2))

                # Boundary checks on the scaled frame
                if crop_x < 0:
                    crop_x = 0
                elif crop_x + output_width > scaled_w:
                    crop_x = scaled_w - output_width
            else:
                crop_x = (scaled_w - output_width) // 2

            return f"crop={output_width}:{output_height}:{crop_x}:{crop_y}"


        except Exception as e:
            logger.error(f"Error during smart cropping analysis: {e}")
            return f"crop={output_width}:{output_height}:(in_w-{output_width})/2:(in_h-{output_height})/2"
