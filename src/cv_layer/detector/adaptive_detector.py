import cv2
import supervision as sv
from src.cv_layer.detector.yolo_detector import YOLODetector

class AdaptiveDetector:
    def __init__(self, model_path, inference_interval=3, motion_ratio_threshold=0.0015, motion_target_width=480, device="cuda"):
        self.detector = YOLODetector(model_path, device=device)
        self.tracker = sv.ByteTrack()
        self.inference_interval = inference_interval            # base cadence
        self.motion_ratio_threshold = motion_ratio_threshold    # fraction of frame area, resolution-independent
        self.motion_target_width = motion_target_width          # downscale toward this width
        self.frame_count = 0
        self.last_detections = sv.Detections.empty()
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=False
        )

    def has_motion(self, frame):
        """Returns True if significant motion is detected in the frame.
           Frame is downscaled to avoid CPU bottleneck at higher resolutions.
        """
        h, w = frame.shape[:2]
        scale = min(1.0, self.motion_target_width / w)
        if scale < 1.0:
            small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        else:
            small = frame
        fg_mask = self.bg_subtractor.apply(small)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_area = sum(cv2.contourArea(c) for c in contours)
        frame_area = fg_mask.shape[0] * fg_mask.shape[1]
        motion_ratio = motion_area / frame_area
        return motion_ratio > self.motion_ratio_threshold

    def process_frame(self, frame, fps=None):
        """
        Runs inference adaptively:
        - Always runs on motion
        - Falls back to fixed interval when scene is static
        """
        self.frame_count += 1
        motion_detected = self.has_motion(frame)

        # Run inference if: motion detected or at the base interval cadence
        should_run_inference = motion_detected or (self.frame_count % self.inference_interval == 0)

        if should_run_inference:
            raw_detections = self.detector.detect(frame)
            self.last_detections = self.tracker.update_with_detections(raw_detections)

        # Always visualize using the most recent detections
        annotated = self.detector.visualize(frame.copy(), self.last_detections, fps)
        return annotated, self.last_detections