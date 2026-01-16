# very simple initial object detector class using YOLOv8

class YOLODetector:
    """
        Default constructor.
        Parameters: Path to YOLO model
    """
    def __init__(self, model_path="models/yolov8n.pt"):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
    
    """
        Object detector function.
        Parameters: openCV frame
        Returns: array of objects detected (represented as a dictionary storing the class of the object, coordinates of        bounding box, and confidence score.
    """
    def detect(self, frame):
        result = self.model(frame)[0]
        detections = []

        for box in result.boxes:
            detections.append({
                "class": box.cls,
                "bbox": box.xyxy.tolist(),
                "confidence": float(box.conf)
            })
        return detections

    """
        Visualizes YOLO detection
        Parameters: openCV object
    """
    def show(self, cvObject):
        for result in self.model(source=0, stream=True):
    
            frame = result.plot()
            cvObject.imshow("Detection Window", frame)

            if cvObject.waitKey(1) & 0xFF == 27:
                break

        cvObject.destroyAllWindows()
