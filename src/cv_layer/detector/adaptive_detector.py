import cv2
from src.cv_layer.detector.yolo_detector import YOLODetector

class AdaptiveDetector:
    def __init__(self, model_path, inference_interval=3, motion_threshold=500, device="cuda"):
        self.detector = YOLODetector(model_path, device=device)
        self.inference_interval = inference_interval  # base cadence
        self.motion_threshold = motion_threshold      # pixel diff area to trigger fast inference
        self.frame_count = 0
        self.last_detections = []
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=False
        )

    def has_motion(self, frame):
        """Returns True if significant motion is detected in the frame."""
        fg_mask = self.bg_subtractor.apply(frame)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_area = sum(cv2.contourArea(c) for c in contours)
        return motion_area > self.motion_threshold

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
            # DEBUG logs ---------------------------------------------------
            if motion_detected:
                print("DEBUG: motion detected -> running inference")
            else:
                print("DEBUG: at base cadence -> running inference")
            # --------------------------------------------------------------

            self.last_detections = self.detector.detect(frame)

        # Always visualize using the most recent detections
        annotated = self.detector.visualize(frame.copy(), self.last_detections, fps)
        return annotated, self.last_detections