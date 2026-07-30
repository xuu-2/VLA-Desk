"""
Real-time Object Detection using Webcam + YOLO
Press 'q' to quit
"""

import cv2
import time
from perception.yolo_detector import YOLODetector


def main():
    print("=" * 70)
    print("  🎥 Real-time Object Detection - Webcam + YOLO")
    print("=" * 70)
    print()
    
    # Initialize YOLO detector
    print("⏳ Loading YOLO model...")
    detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    detector.load_model()
    print("✅ YOLO model loaded\n")
    
    # Open webcam (0 = default camera)
    print("📷 Opening webcam...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Error: Cannot access webcam")
        print("💡 Tips:")
        print("   - Check if camera is connected")
        print("   - Close other apps using the camera")
        print("   - Try changing camera index (0, 1, 2...)")
        return
    
    # Set camera resolution (optional)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print("✅ Webcam opened successfully")
    print()
    print("🎮 Controls:")
    print("   - Press 'q' to quit")
    print("   - Press 's' to save current frame")
    print()
    
    # FPS calculation variables
    fps = 0
    frame_count = 0
    start_time = time.time()
    
    # Save frame counter
    save_count = 0
    
    print("🚀 Starting real-time detection...\n")
    
    try:
        while True:
            # Read frame from webcam
            ret, frame = cap.read()
            
            if not ret:
                print("❌ Failed to read frame from webcam")
                break
            
            # Save original frame for detection
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Save to temporary file for YOLO detection
            temp_img_path = "temp_frame.jpg"
            cv2.imwrite(temp_img_path, frame)
            
            # Run YOLO detection
            detections_raw = detector.detect(temp_img_path)
            detections = detector.to_serializable(detections_raw)
            
            # Draw detections on frame
            for det in detections:
                # Extract detection info
                label = det["label"]
                conf = det["confidence"]
                bbox = det["bbox"]
                center = det["center"]
                
                # Draw bounding box
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw center point
                cx, cy = map(int, center)
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                
                # Draw label with background
                label_text = f"{label} {conf:.2f}"
                (text_w, text_h), _ = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                cv2.rectangle(frame, (x1, y1 - text_h - 10), 
                            (x1 + text_w, y1), (0, 255, 0), -1)
                cv2.putText(frame, label_text, (x1, y1 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            
            # Calculate FPS
            frame_count += 1
            elapsed_time = time.time() - start_time
            if elapsed_time >= 1.0:
                fps = frame_count / elapsed_time
                frame_count = 0
                start_time = time.time()
            
            # Draw FPS and detection count
            info_y = 30
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, info_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.putText(frame, f"Objects: {len(detections)}", (10, info_y + 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Draw instructions
            cv2.putText(frame, "Press 'q' to quit | 's' to save", 
                       (10, frame.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Display frame
            cv2.imshow("Real-time Detection - VLA-Desk", frame)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n👋 Quitting...")
                break
            elif key == ord('s'):
                save_count += 1
                filename = f"captured_frame_{save_count}.jpg"
                cv2.imwrite(filename, frame)
                print(f"📸 Saved: {filename}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Error during detection: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        
        # Remove temporary file
        import os
        if os.path.exists("temp_frame.jpg"):
            os.remove("temp_frame.jpg")
        
        print("\n✅ Webcam released and windows closed")
        print(f"📊 Final FPS: {fps:.1f}")
        print(f"📸 Frames saved: {save_count}")
        print("\nThank you for using VLA-Desk! 🤖\n")


if __name__ == "__main__":
    main()
