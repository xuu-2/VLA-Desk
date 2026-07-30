"""
YOLOv8 Object Detector for VLA-Desk Project

This module provides object detection capabilities using YOLOv8.
Returns detected objects with their labels and center coordinates.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import cv2
import numpy as np


@dataclass
class Detection:
    """Detected object with label, confidence, bounding box and center point."""
    label: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    center: List[float]  # [x_center, y_center]


class YOLODetector:
    """YOLO-based object detector for desktop manipulation tasks."""
    
    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5) -> None:
        """Initialize YOLO detector.
        
        Args:
            model_path: Path to YOLO model weights (default: yolov8n.pt)
            confidence_threshold: Minimum confidence for detections (default: 0.5)
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.model: Optional[Any] = None
        
    def load_model(self) -> None:
        """Load YOLO model. Downloads automatically if not present."""
        try:
            from ultralytics import YOLO
            print(f"Loading YOLO model: {self.model_path}")
            self.model = YOLO(self.model_path)
            print("Model loaded successfully!")
        except ImportError:
            raise ImportError(
                "ultralytics not installed. Run: pip install ultralytics"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load YOLO model: {e}")
    
    def detect(self, image_source: str) -> List[Detection]:
        """Run object detection on an image.
        
        Args:
            image_source: Path to image file
            
        Returns:
            List of Detection objects with label, confidence, bbox, and center
        """
        if self.model is None:
            self.load_model()
        
        if not Path(image_source).exists():
            raise FileNotFoundError(f"Image not found: {image_source}")
        
        # Run YOLO inference
        results = self.model(image_source, conf=self.confidence_threshold, verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Extract box data
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls = int(box.cls[0].cpu().numpy())
                label = result.names[cls]
                
                # Calculate center point
                x_center = float((x1 + x2) / 2)
                y_center = float((y1 + y2) / 2)
                
                detection = Detection(
                    label=label,
                    confidence=conf,
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    center=[x_center, y_center]
                )
                detections.append(detection)
        
        return detections
    
    def detect_and_visualize(self, image_source: str, save_path: Optional[str] = None) -> List[Detection]:
        """Run detection and optionally save annotated image.
        
        Args:
            image_source: Path to input image
            save_path: Optional path to save annotated image
            
        Returns:
            List of Detection objects
        """
        detections = self.detect(image_source)
        
        if save_path:
            img = cv2.imread(image_source)
            for det in detections:
                x1, y1, x2, y2 = map(int, det.bbox)
                cx, cy = map(int, det.center)
                
                # Draw bounding box
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw center point
                cv2.circle(img, (cx, cy), 5, (0, 0, 255), -1)
                
                # Add label
                label_text = f"{det.label} {det.confidence:.2f}"
                cv2.putText(img, label_text, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            cv2.imwrite(save_path, img)
            print(f"Annotated image saved to: {save_path}")
        
        return detections
    
    def to_serializable(self, detections: List[Detection]) -> List[Dict[str, Any]]:
        """Convert Detection objects to JSON-serializable dictionaries.
        
        Args:
            detections: List of Detection objects
            
        Returns:
            List of dictionaries
        """
        return [
            {
                "label": det.label,
                "confidence": det.confidence,
                "bbox": det.bbox,
                "center": det.center,
            }
            for det in detections
        ]


def main():
    """Test YOLODetector with a sample image."""
    print("=== YOLOv8 Detector Test ===\n")
    
    # Initialize detector
    detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    
    # Test image path (replace with your actual image)
    test_image = "test_image.jpg"
    
    # Check if test image exists
    if not Path(test_image).exists():
        print(f"⚠️  Test image not found: {test_image}")
        print("Please provide an image file named 'test_image.jpg' in the current directory.")
        print("\nCreating a sample detection output for demonstration:")
        
        # Mock detection for demo
        mock_detections = [
            Detection(label="cup", confidence=0.92, bbox=[100, 150, 200, 300], center=[150, 225]),
            Detection(label="bottle", confidence=0.87, bbox=[300, 100, 380, 280], center=[340, 190]),
            Detection(label="keyboard", confidence=0.95, bbox=[50, 350, 450, 450], center=[250, 400]),
        ]
        
        print("\n📦 Mock Detections:")
        for i, det in enumerate(mock_detections, 1):
            print(f"{i}. {det.label} (conf: {det.confidence:.2f}) - Center: ({det.center[0]:.0f}, {det.center[1]:.0f})")
        
        return
    
    try:
        # Run detection
        print(f"🔍 Running detection on: {test_image}\n")
        detections = detector.detect_and_visualize(
            image_source=test_image,
            save_path="output_annotated.jpg"
        )
        
        # Print results
        print(f"\n✅ Found {len(detections)} objects:\n")
        for i, det in enumerate(detections, 1):
            print(f"{i}. {det.label}")
            print(f"   Confidence: {det.confidence:.2f}")
            print(f"   Center: (x={det.center[0]:.1f}, y={det.center[1]:.1f})")
            print(f"   BBox: {[f'{x:.1f}' for x in det.bbox]}\n")
        
        # Show serialized format
        print("\n📋 Serialized output:")
        import json
        print(json.dumps(detector.to_serializable(detections), indent=2))
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
