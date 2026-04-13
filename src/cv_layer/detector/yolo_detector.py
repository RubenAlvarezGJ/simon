from ultralytics import YOLO
import cv2

class YOLODetector:
    def __init__(self, model_path="models/yolov8n.pt", confidence_threshold=0.5, device="cuda"):
        """
        Initializes the YOLO object detector.

        Parameters:
            model_path (str): Path to the YOLO model weights.
            confidence_threshold (float): Minimum confidence score to accept a detection.
            device (str): Inference device — 'cuda' for GPU, 'cpu' for CPU.
        """
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.model.to(device) # move model to gpu
    
    def detect(self, frame):
        """  
        Runs object detection on a single frame.

        Parameters:
            frame: OpenCV frame (numpy array in BGR format).

        Returns:
            List of dicts, each containing:
                - class_id (int): Numeric class index.
                - class_name (str): Human-readable class label.
                - bbox (list): Bounding box as [x1, y1, x2, y2].
                - confidence (float): Detection confidence score.
        """
        result = self.model(frame, device=self.device)[0]
        detections = []

        for box in result.boxes:
            confidence = float(box.conf)

            if confidence < self.confidence_threshold:
                continue

            class_id = int(box.cls)
            detections.append({
                "class_id": class_id,
                "class_name": self.model.names[class_id],
                "bbox": box.xyxy[0].tolist(),
                "confidence": confidence
            })
        return detections

    def visualize(self, frame, detections, fps=None):
        """
        Draws bounding boxes and labels onto a frame.

        Parameters:
            frame: OpenCV frame to draw on.
            detections (list): Output from detect().

        Returns:
            Annotated frame (numpy array).
        """
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            label = f'{det["class_name"]} {det["confidence"]:.2f}'

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
        if fps is not None:
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return frame
