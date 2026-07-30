# 添加项目截图指南

## 📸 你已经有的截图

根据你提供的图片，你有两张很棒的效果图：

1. **检测效果图** - 显示 teddy bear 被检测到（置信度 0.77）
2. **执行效果图** - 显示 "pick up cell phone" 指令的完整执行过程

## 📁 如何添加截图到项目

### 步骤 1: 保存截图文件

将你的两张截图保存到项目的 `docs/screenshots/` 目录：

```
VLA-Desk/
└── docs/
    └── screenshots/
        ├── detection.png          # 第一张图（teddy bear 检测）
        └── execution.png          # 第二张图（pick up cell phone）
```

### 步骤 2: 更新 README.md

在 README.md 的 "📸 效果预览" 部分，将注释替换为实际图片：

**当前内容（第 40-45 行）：**
```markdown
## 📸 效果预览

<!-- 添加你的截图或 GIF -->
<!-- ![主界面](docs/screenshots/main-ui.png) -->
<!-- ![检测效果](docs/screenshots/detection.gif) -->

> 💡 提示：运行 `python app.py` 后访问 http://127.0.0.1:7860 查看完整界面
```

**替换为：**
```markdown
## 📸 效果预览

### 视觉检测效果
![物体检测](docs/screenshots/detection.png)
*YOLO 实时检测 teddy bear，置信度 0.77，自动绘制检测框和中心点*

### 语言指令执行
![指令执行](docs/screenshots/execution.png)
*输入 "pick up cell phone"，系统解析指令并生成完整的 4 步动作序列*

**功能演示：**
- ✅ 实时物体检测和标注
- ✅ 自然语言指令理解
- ✅ 动作序列自动规划
- ✅ PyBullet 仿真执行
- ✅ 完整的系统日志记录

> 💡 提示：运行 `python app.py` 后访问 http://127.0.0.1:7860 查看完整界面
```

## 🎯 推荐的截图说明

根据你的两张图，我建议这样描述：

### 第一张图（detection.png）
- **展示内容**：YOLO 检测 teddy bear
- **关键特性**：黄色检测框、置信度 0.77、蓝色中心点
- **说明文字**：展示 VLA-Desk 的实时视觉检测能力

### 第二张图（execution.png）
- **展示内容**：完整的 pick-and-place 流程
- **关键特性**：
  - 指令：pick up cell phone
  - 解析结果：action=pick, target=phone
  - 生成 4 个动作：move_above → move_to → grasp → move_above
  - PyBullet 仿真执行成功
- **说明文字**：展示从语言理解到动作执行的完整流程

## 📝 可选：添加 GIF 动图

如果你想让展示更生动，可以：

1. **录制操作过程**：使用 ScreenToGif 或 Peek 等工具
2. **保存为 GIF**：`demo.gif`
3. **添加到 README**：
   ```markdown
   ### 完整操作演示
   ![完整演示](docs/screenshots/demo.gif)
   ```

## ✅ 完成后的效果

更新后，访问你的 GitHub 仓库，README 页面会直接展示：
- 🖼️ 视觉检测的实际效果
- 🖼️ 指令执行的完整流程
- 📝 清晰的功能说明

这样访问者一眼就能看懂你的项目能做什么！

## 🚀 快速命令

```bash
# 1. 确保截图目录存在
mkdir -p docs/screenshots

# 2. 将截图复制到目录（替换为你的实际路径）
# 第一张图（teddy bear）命名为 detection.png
# 第二张图（cell phone）命名为 execution.png

# 3. 提交到 Git
git add docs/screenshots/
git add README.md
git commit -m "docs: add project screenshots and demo"
git push
```

## 💡 提示

- 图片建议使用 PNG 格式（清晰度高）
- 单张图片大小建议不超过 2MB
- 如果图片太大，可以使用在线压缩工具：https://tinypng.com/

---

完成这些步骤后，你的项目就有了专业的效果展示！🎉
