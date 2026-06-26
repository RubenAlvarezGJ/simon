from ultralytics import YOLO
import cv2
import supervision as sv

class YOLODetector:
    def __init__(self, model_path="models/yolov8n.pt", confidence_threshold=0.7, device="cuda"):
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

        self.box_annotator = sv.BoxAnnotator(color=sv.Color.RED, thickness=1)
        self.label_annotator = sv.LabelAnnotator(color=sv.Color.RED, text_color=sv.Color.BLACK)
    
    def detect(self, frame):
        """  
        Runs object detection on a single frame.

        Parameters:
            frame: OpenCV frame (numpy array in BGR format).

        Returns:
            sv.Detections object containing all detections above the confidence
            threshold, with the following key attributes:
                - xyxy (np.ndarray): Bounding boxes as shape (N, 4) in [x1, y1, x2, y2] format.
                - class_id (np.ndarray): Numeric class indices, shape (N,).
                - confidence (np.ndarray): Detection confidence scores, shape (N,).
                - tracker_id (np.ndarray or None): Track IDs, shape (N,). None until
                  passed through a tracker such as sv.ByteTrack.

            Returns sv.Detections.empty() if no detections exceed the confidence
            threshold. Class names can be retrieved via self.model.names[class_id]
        """
        result = self.model(frame, device=self.device, verbose=False)[0]

        # Converts Ultralytics result to Supervision Detections
        detections = sv.Detections.from_ultralytics(result)

        # Filter confidence threshold
        detections = detections[detections.confidence >= self.confidence_threshold]
        
        return detections

    def visualize(self, frame, detections: sv.Detections, fps=None):
        """
        Draws bounding boxes and tracking labels.

        Parameters:
            frame: OpenCV frame to draw on.
            detections (sv.Detections): Output from the tracker/detector.

        Returns:
            Annotated frame (numpy array).
        """

        labels = []
        for class_id, confidence, tracker_id in zip(
            detections.class_id, 
            detections.confidence, 
            detections.tracker_id if detections.tracker_id is not None else [None] * len(detections)
        ):
            class_name = self.model.names[class_id]
            if tracker_id is not None:
                labels.append(f"#{tracker_id} {class_name} {confidence:.2f}")
            else:
                labels.append(f"{class_name} {confidence:.2f}")

        annotated_frame = self.box_annotator.annotate(
            scene=frame, detections=detections
        )

        annotated_frame = self.label_annotator.annotate(
            scene=annotated_frame, detections=detections, labels=labels
        )

        if fps is not None:
            cv2.putText(
                annotated_frame, 
                f"FPS: {fps:.1f}", 
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (0, 255, 0), 
                2
            )

        return annotated_frame
