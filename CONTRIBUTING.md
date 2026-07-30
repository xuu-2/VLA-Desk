# 贡献指南

感谢你对 VLA-Desk 项目的关注！我们欢迎任何形式的贡献。

## 🤝 如何贡献

### 报告 Bug

如果你发现了 bug，请：

1. 在 [Issues](https://github.com/xuu-2/VLA-Desk/issues) 中搜索是否已有相关问题
2. 如果没有，创建新 Issue，并包含：
   - 清晰的问题描述
   - 复现步骤
   - 预期行为 vs 实际行为
   - 系统环境（OS、Python 版本等）
   - 错误日志（如有）

### 提出新功能

如果你有好的想法：

1. 先在 Issues 中讨论你的想法
2. 等待反馈和讨论
3. 得到认可后再开始开发

### 提交代码

1. **Fork 项目**
   ```bash
   # 在 GitHub 上点击 Fork 按钮
   ```

2. **克隆到本地**
   ```bash
   git clone https://github.com/your-username/VLA-Desk.git
   cd VLA-Desk
   ```

3. **创建新分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

4. **进行修改**
   - 遵循现有代码风格
   - 添加必要的注释
   - 更新相关文档

5. **测试你的更改**
   ```bash
   python test_pipeline.py
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   # 或
   git commit -m "fix: fix your bug description"
   ```

7. **推送到你的 Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **创建 Pull Request**
   - 在 GitHub 上创建 PR
   - 填写 PR 模板
   - 等待代码审查

## 📝 Commit 消息规范

使用语义化提交消息：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建或辅助工具变动

示例：
```
feat: add voice input support
fix: resolve camera connection issue
docs: update installation guide
```

## 🎨 代码风格

- 遵循 PEP 8 规范
- 函数和变量使用描述性命名
- 添加类型提示（Type Hints）
- 保持代码简洁清晰

## ✅ Pull Request 检查清单

在提交 PR 前，确保：

- [ ] 代码通过所有测试
- [ ] 添加了必要的注释
- [ ] 更新了相关文档
- [ ] Commit 消息符合规范
- [ ] 没有引入新的警告或错误
- [ ] 代码风格一致

## 📚 开发环境设置

```bash
# 克隆项目
git clone https://github.com/xuu-2/VLA-Desk.git
cd VLA-Desk

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 运行测试
python test_pipeline.py
```

## 🙏 感谢

感谢每一位贡献者！你们的参与让这个项目变得更好。

## 📧 联系方式

如有问题，欢迎通过以下方式联系：

- [GitHub Issues](https://github.com/xuu-2/VLA-Desk/issues)
- [GitHub Discussions](https://github.com/xuu-2/VLA-Desk/discussions)

---

再次感谢你的贡献！🎉
