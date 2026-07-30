import cv2
import os
from perception.yolo_detector import YOLODetector

def main():
    # 检查图片
    if not os.path.exists("desk.jpg"):
        print("❌ 请把 desk.jpg 放在项目根目录")
        return

    # 初始化检测器
    print("⏳ 加载 YOLO 模型...")
    detector = YOLODetector()

    # 读取图片（用于显示）
    image = cv2.imread("desk.jpg")
    if image is None:
        print("❌ 无法读取图片")
        return
    print(f"📷 图片尺寸: {image.shape}")

    # 检测（传入图片路径）
    print("🔍 开始检测...")
    detections = detector.detect("desk.jpg")

    # 打印结果（对象属性访问方式）
    print(f"\n✅ 检测到 {len(detections)} 个物体:")
    for d in detections:
        print(f"  - {d.label}: {d.confidence:.2f} @ ({d.center[0]:.0f}, {d.center[1]:.0f})")

    # 手动绘制检测框
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        label = f"{d.label} {d.confidence:.2f}"
        cv2.putText(image, label, (int(x1), int(y1)-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # 显示结果
    cv2.imshow("Detection Result", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print("✅ 视觉模块测试完成！")

if __name__ == "__main__":
    main()