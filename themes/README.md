# Hub75 LED 主题包

独立的主题文件，方便随时切换显示风格。

## 📁 目录结构

```
themes/
├── __init__.py          # 主题包入口
├── kitten.py            # 🐱 小猫主题（默认）
├── theme_manager.py     # 主题管理器
└── README.md            # 本说明
```

## 🐱 小猫主题 (Kitten Theme)

可爱的像素小猫动画主题，显示：
- 64×64 LED 矩阵上的动画像素小猫
- 顶部：小猫眨眼、弹跳、摇尾巴动画
- 忙碌时小猫眼睛变红，闲暇时变绿
- 中部：MEM/CPU 资源使用率条 + 日期时间
- 底部：中英文滚动消息

## 🔧 API 切换主题

```bash
# 切换到小猫主题
curl -X POST http://localhost:5000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "kitten"}'

# 切换回 OpenClaw 状态
curl -X POST http://localhost:5000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "openclaw_status"}'
```

## 🌐 网页控制面板

启动 server.py 后访问 http://localhost:5000 ，点击「小猫」按钮即可切换。

## 📝 添加新主题

1. 在 `themes/` 目录创建新主题文件，如 `my_theme.py`
2. 定义一个主题类，必须有 `generate_frame(status, t)` 方法
3. 在 `__init__.py` 中导入并注册
4. 在 `theme_manager.py` 中 `register_theme('my_theme', MyThemeClass)`

```python
# themes/my_theme.py
class MyTheme:
    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

    def generate_frame(self, status=None, t=None):
        import numpy as np
        import time
        if t is None:
            t = time.time()
        if status is None:
            status = {}
        # 返回 np.ndarray (height, width, 3)
        return np.zeros((self.height, self.width, 3), dtype=np.uint8)
```

## 🔄 可用主题列表

```bash
curl http://localhost:5000/api/status
# 查看 mode 字段
```
