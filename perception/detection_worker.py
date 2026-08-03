"""
Background YOLO detection worker.
Runs detection on the latest frame from CameraStream without blocking the UI.
"""
import threading
import time
from typing import Optional, List, Dict, Any

import numpy as np


class DetectionWorker:
    def __init__(self, yolo_detector, min_interval: float = 0.15) -> None:
        self.yolo = yolo_detector
        self.min_interval = min_interval
        self._latest_detections: List[Dict[str, Any]] = []
        self._latest_frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_provider = None

    def start(self, frame_provider) -> None:
        self._frame_provider = frame_provider
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            frame = self._frame_provider.read() if self._frame_provider else None
            if frame is None:
                time.sleep(self.min_interval)
                continue

            try:
                # 直接把 numpy frame 交给 YOLO，避免磁盘 I/O 和 JPEG 编解码
                dets = self.yolo.detect(frame)
                serialized = self.yolo.to_serializable(dets)
                with self._lock:
                    self._latest_detections = serialized
                    self._latest_frame = frame.copy()
            except Exception as e:
                # 不阻塞主线程，错误只记录，不中断流
                with self._lock:
                    self._latest_detections = []
                print(f"[DetectionWorker] {e}")
            time.sleep(self.min_interval)

    def get_detections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._latest_detections)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
