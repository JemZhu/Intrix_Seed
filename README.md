# Intrix 无限矩阵 / Intrix Seed

<p align="center">
  <img src="https://github.com/JemZhu/Intrix_Seed/blob/main/Intrix_LOGO.png" width="200" alt="Intrix Logo">
</p>

**Intrix 无限矩阵**（Infinity Matrix）是一款高度自由的 64×64 像素 RGB LED 屏幕控制服务端，4096 颗全彩 RGB LED 可显示 16 万种颜色。

完全接入 Openclaw 生态，告诉他你想要显示什么，无需编写代码即可完成专属设计。

<p align="center">
  <img src="https://img.shields.io/badge/LED-64×64-FF5722?style=flat-square" alt="LED Size">
  <img src="https://img.shields.io/badge/Python-3.11+-00ACC1?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Linux/macOS-4CAF50?style=flat-square" alt="Platform">
</p>

---

## 控制 64×64 RGB LED 矩阵屏幕，显示 OpenClaw 工作状态、天气和 Token 消耗。

## 启动说明

需要同时运行两个程序：

### 1. LED 服务器（主程序）

```bash
cd /home/jem/Intrix_Seed
python3 server.py
```

- **Web 界面**: http://localhost:5000
- **TCP 端口**: 8080 (用于 ESP32 硬件连接)

### 2. 状态监控器（获取天气 + Token 消耗）

```bash
cd /home/jem/Intrix_Seed
python3 openclaw_monitor.py
```

负责：
- 每 5 秒检测 CPU / 内存使用率
- 每 10 分钟从 wttr.in 获取天气数据
- 解析 session 文件统计 Token 消耗
- 自动推送状态到 LED 服务器

### 3. 开机自启（可选）

使用 systemd 服务：

```bash
# 创建服务文件
sudo nano /etc/systemd/system/hub75-led.service
```

```ini
[Unit]
Description=Hub75 LED Matrix Server
After=network.target

[Service]
Type=simple
User=jem
WorkingDirectory=/home/jem/Intrix_Seed
ExecStart=/usr/bin/python3 /home/jem/Intrix_Seed/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable hub75-led.service
sudo systemctl start hub75-led.service
```

**注意**：`openclaw_monitor.py` 也需要自启，可以写在 `server.py` 启动时自动调用，或者另外建一个 service。

## API 调用

### 更新状态

```bash
curl -X POST http://localhost:5000/api/openclaw-status \
  -H "Content-Type: application/json" \
  -d '{
    "is_busy": true,
    "session_count": 2,
    "active_sessions": 1,
    "memory_usage": 0.45,
    "cpu_load": 0.35,
    "last_message": "工作中"
  }'
```

### 参数说明

| 参数 | 类型 | 描述 |
|------|------|------|
| `is_busy` | bool | 忙碌状态（true=彩虹色猫，false=粉色猫） |
| `session_count` | int | 会话总数 |
| `active_sessions` | int | 活跃会话数 |
| `memory_usage` | float | 内存使用率 (0.0-1.0) |
| `cpu_load` | float | CPU 负载 (0.0-1.0) |
| `last_message` | string | 底部滚动字幕（支持中文、英文、emoji） |
| `weather` | object | 天气数据 `{temp, code, desc}` |
| `token_usage` | object | Token 统计 `{total_tokens, total_cost}` |

### 获取当前状态

```bash
curl http://localhost:5000/api/openclaw-status
```

### 获取预览图像

```bash
curl http://localhost:5000/api/preview -o preview.png
```

### 切换显示模式

```bash
curl -X POST http://localhost:5000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "kitten"}'
```

可用模式：`openclaw_status`, `kitten`, `demo`, `rainbow`, `clock`, `matrix`, `pulse`

## 显示效果（Kitten 主题）

### 布局
```
┌─────────────────────────┐
│ 16°C ☁  右上角: 小猫咪  │
│ MEM ████░░  CPU ██░░    │
│ 03-29 SUN  22:48       │
├─────────────────────────┤
│ T:40.8M $13.28 滚动字幕 │
└─────────────────────────┘
```

- **左上角**: 温度 + 天气图标
- **右上角**: 像素小猫动画（粉色=空闲，彩虹=忙碌）
- **中间左侧**: MEM / CPU 进度条
- **中间右侧**: 日期 + 星期（周末红色）+ 时间
- **底部**: Token 消耗（绿色数字）+ $金额（金色）+ 滚动消息

## 文件结构

```
/home/jem/Intrix_Seed/
├── server.py              # LED 主服务器
├── openclaw_monitor.py    # 状态监控器（天气+Token）
├── themes/
│   └── kitten.py          # 小猫主题
├── HZK12                  # 12x12 中文字库
├── HZK16                  # 16x16 中文字库（备用）
└── README.md              # 本文件
```

## 故障排查

### LED 屏幕不动
```bash
# 检查 server 是否在跑
ps aux | grep server.py | grep -v grep

# 重启
cd /home/jem/Intrix_Seed && python3 server.py
```

### 天气 / Token 消耗不显示
```bash
# 检查 monitor 是否在跑
ps aux | grep openclaw_monitor | grep -v grep

# 重启
cd /home/jem/Intrix_Seed && python3 openclaw_monitor.py
```

### 切换到 kitten 模式
```bash
curl -X POST http://localhost:5000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "kitten"}'
```

### 播放视频 / GIF
在网页 http://localhost:5000 上传，视频需要 ffmpeg 支持（已通过 imageio-ffmpeg 解决，无需手动安装）。

## 注意事项

- 中文支持：需要 HZK12 或 HZK16 字库文件
- 分辨率：64×64 像素
- 滚动字幕：中英文混合，英文 12px，中文 12px（HZK12）
