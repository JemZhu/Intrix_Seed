# Intrix LED Matrix Firmware — 服务端开发 API 指南

**固件版本：** 20260421  
**适用硬件：** ESP32-WROOM-DA + 64×64 HUB75 LED 矩阵面板 + MAX98357A I2S 音频放大器  
**协议概览：** TCP 长连接（视频帧 + 音频帧） + HTTP REST API（配置与控制） + WebSocket（实时状态推送）

---

## 目录

1. [系统架构](#1-系统架构)
2. [TCP 连接协议](#2-tcp-连接协议)
   - 2.1 建立连接
   - 2.2 握手：client_info
   - 2.3 发送视频帧（frame_data）
   - 2.4 发送音频帧（audio_data）
   - 2.5 控制命令
   - 2.6 协议帧顺序与节奏
3. [HTTP REST API](#3-http-rest-api)
   - GET /api/status
   - POST /api/config
   - GET /api/brightness
   - GET /api/rotation
   - GET /api/colormap
   - POST /api/deviceid
   - POST /api/wifi
   - GET /api/test
   - POST /api/reset
   - POST /api/update（OTA）
   - POST /api/disconnect
4. [WebSocket 状态推送](#4-websocket-状态推送)
5. [设备 ID 机制](#5-设备-id-机制)
6. [工作模式说明](#6-工作模式说明)
7. [像素格式详解：RGB565](#7-像素格式详解rgb565)
8. [音频格式详解：PCM16](#8-音频格式详解pcm16)
9. [服务端实现参考](#9-服务端实现参考)
   - 9.1 Python 最小示例
   - 9.2 多客户端管理
   - 9.3 音视频同步建议
10. [错误处理与重连](#10-错误处理与重连)
11. [完整消息类型速查表](#11-完整消息类型速查表)

---

## 1. 系统架构

```
┌─────────────────────────────────────┐
│            服务端 (Server)           │
│                                     │
│  ┌─────────┐    ┌─────────────────┐ │
│  │ TCP推流  │    │  HTTP REST API  │ │
│  │ :8080   │    │  （可选控制）    │ │
│  └────┬────┘    └────────┬────────┘ │
└───────┼──────────────────┼──────────┘
        │ TCP 长连接        │ HTTP 短连接
        ▼                  ▼
┌─────────────────────────────────────┐
│           ESP32 固件                 │
│                                     │
│  Core 0: AsyncWebServer / AsyncTCP  │
│  Core 1: networkTask  displayTask   │
│                                     │
│  ┌───────────┐  ┌────────────────┐  │
│  │ LED Matrix │  │ MAX98357A I2S  │  │
│  │  64×64    │  │  16kHz Mono    │  │
│  └───────────┘  └────────────────┘  │
└─────────────────────────────────────┘
```

**关键设计要点：**

- ESP32 主动连接服务器，**不是**服务器连接 ESP32。服务器需要监听 TCP 端口等待设备接入。
- TCP 连接用于高频视频/音频数据推送，HTTP API 用于低频配置控制。
- 设备在网页打开期间会主动断开 TCP 连接（释放内存），网页关闭后自动重连。
- 固件使用非阻塞状态机接收数据，服务端无需等待 ACK，可连续推送。

---

## 2. TCP 连接协议

### 2.1 建立连接

服务端监听 TCP 端口（默认 **8080**，可通过网页配置修改）。设备上电并连接 WiFi 后，会主动发起 TCP 连接。

```
服务端监听  0.0.0.0:8080
设备连接    → SYN
服务端接受  → 等待设备发送 client_info
```

设备断线后每 **5 秒**自动重试连接，服务端无需主动处理重连逻辑。

---

### 2.2 握手：client_info

连接建立后，设备**立即主动发送**一条 JSON 握手消息（以 `\n` 结尾）：

```json
{
  "type": "client_info",
  "width": 64,
  "height": 64,
  "format": "RGB565",
  "panels": 1,
  "panel_width": 64,
  "panel_height": 64,
  "device_id": "a3f7k2mx",
  "audio_format": "PCM16",
  "audio_rate": 16000,
  "audio_ch": 1
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定为 `"client_info"` |
| `width` | int | 显示区域总宽度（像素）= panel_width × panels |
| `height` | int | 显示区域总高度（像素） |
| `format` | string | 视频像素格式，固定为 `"RGB565"` |
| `panels` | int | 级联面板数量（当前固件为 1） |
| `panel_width` | int | 单块面板宽度 |
| `panel_height` | int | 单块面板高度 |
| `device_id` | string | 设备唯一标识（8位字母数字串） |
| `audio_format` | string | 音频采样格式，固定为 `"PCM16"` |
| `audio_rate` | int | 采样率（Hz），固定为 `16000` |
| `audio_ch` | int | 声道数，固定为 `1`（单声道） |

> **服务端建议：** 收到 `client_info` 后，根据 `device_id` 识别是哪台设备，并以 `width`/`height` 校验后续帧尺寸是否匹配。

---

### 2.3 发送视频帧（frame_data）

每帧分两步发送：**JSON 头部行** + **裸二进制像素数据**。

**步骤一：发送帧头（JSON + `\n`）**

```json
{"type":"frame_data","width":64,"height":64,"format":"RGB565","data_size":8192}
```

后跟换行符 `\n`（ASCII 0x0A）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定为 `"frame_data"` |
| `width` | int | 必须等于 `client_info.width`（64） |
| `height` | int | 必须等于 `client_info.height`（64） |
| `format` | string | 必须为 `"RGB565"` |
| `data_size` | int | 像素数据字节数 = width × height × 2 = **8192** |

**步骤二：紧接着发送裸像素数据（8192 字节）**

数据布局为行优先（row-major），从左上角 (0,0) 开始，逐行从左到右：

```
pixel[0,0]  pixel[1,0]  ...  pixel[63,0]   ← 第0行
pixel[0,1]  pixel[1,1]  ...  pixel[63,1]   ← 第1行
...
pixel[0,63] pixel[1,63] ...  pixel[63,63]  ← 第63行
```

每个像素占 **2 字节**，格式为 RGB565（详见第7节）。字节序为**小端（little-endian）**。

**Python 示例：发送一帧纯红色**

```python
import struct, socket

W, H = 64, 64
# RGB565: R=31, G=0, B=0 → 0xF800，小端存储
red_pixel = struct.pack('<H', 0xF800)
frame_data = red_pixel * (W * H)  # 8192 字节

header = f'{{"type":"frame_data","width":{W},"height":{H},"format":"RGB565","data_size":{len(frame_data)}}}\n'
sock.sendall(header.encode())
sock.sendall(frame_data)
```

> **注意：** 帧头中的 `width`/`height` 若与设备实际尺寸不符，固件会**静默丢弃**该帧，不发送错误回复。

---

### 2.4 发送音频帧（audio_data）

音频帧与视频帧结构相同：**JSON 头部行** + **裸 PCM 二进制数据**。

**步骤一：发送音频帧头（JSON + `\n`）**

```json
{"type":"audio_data","data_size":3200}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定为 `"audio_data"` |
| `data_size` | int | PCM 数据字节数，最大不超过 **8192** |

**步骤二：紧接着发送裸 PCM 数据**

格式：16kHz、单声道、16-bit 有符号整数、小端字节序（PCM16 LE）。

常见分块大小建议：

| 用途 | 每帧字节数 | 对应时长 |
|------|-----------|---------|
| 低延迟 | 640 | 20ms |
| 标准 | 1600 | 50ms |
| 省带宽 | 3200 | 100ms |

**Python 示例：发送 100ms 静音**

```python
import struct

SAMPLE_RATE = 16000
DURATION_MS = 100
num_samples = SAMPLE_RATE * DURATION_MS // 1000  # 1600 个采样
pcm_data = b'\x00\x00' * num_samples  # 3200 字节静音

header = f'{{"type":"audio_data","data_size":{len(pcm_data)}}}\n'
sock.sendall(header.encode())
sock.sendall(pcm_data)
```

> **注意事项：**
> - `data_size` 超过 8192 字节时固件会丢弃该音频帧。
> - 音频与视频帧交替发送即可，固件内部分别用独立状态机处理。
> - 固件 I2S 写入超时为 0（非阻塞），若 DMA 缓冲满则丢弃数据，服务端无需等待。
> - 音频接收超时为 3 秒，超时后自动复位音频状态机。

---

### 2.5 控制命令

以下 JSON 命令可通过 TCP 连接即时下发，无需二进制数据跟随，每条以 `\n` 结尾。

**设置亮度**

```json
{"type":"brightness","value":200}
```

- `value`：0 ~ 253（建议不超过 253，避免 HUB75 库溢出）
- 效果：立即生效，并持久化保存到 Flash

**清屏**

```json
{"type":"clear"}
```

- 效果：将所有帧缓冲清零，清空帧队列，屏幕立即熄灭

---

### 2.6 协议帧顺序与节奏

固件状态机的处理逻辑如下：

```
状态：双IDLE
  → 读取一行 JSON 头部
  → 若是 frame_data  → 进入 RX_RECEIVING_IMG，读取 data_size 字节
  → 若是 audio_data  → 进入 AUDIO_RECEIVING，读取 data_size 字节
  → 若是 brightness/clear → 立即执行，继续 IDLE
```

**重要限制：视频帧和音频帧不能同时接收。** 状态机每次只处理一种帧。因此推荐服务端按如下顺序交替发送：

```
[视频帧头] [视频二进制] [音频帧头] [音频二进制] [视频帧头] ...
```

或者在每个视频帧之间插入音频帧（音频块时长 ≤ 帧间隔即可避免积压）：

```
以 25fps 视频为例（帧间隔 40ms），每帧插入一块 20ms 音频：

[frame_data header][8192 bytes]
[audio_data header][640 bytes]
[frame_data header][8192 bytes]
[audio_data header][640 bytes]
...
```

**帧超时：** 视频帧和音频帧各有 3000ms 接收超时。若帧头发出后超过 3 秒未收完数据，固件自动复位对应状态机，可继续接收新帧。

---

## 3. HTTP REST API

设备内嵌 HTTP 服务器运行于 **端口 80**。所有接口均返回 JSON。

> **注意：** 设备处于正常 TCP 显示模式时，访问 `/`（根路径）会触发设备重启进入配置模式。服务端程序**不应**访问根路径，仅访问 `/api/` 路径下的接口。

---

### GET /api/status

获取设备当前完整状态。

**响应示例：**

```json
{
  "wifi_connected": true,
  "ssid": "MyWiFi",
  "pass": "password123",
  "ip": "192.168.1.88",
  "server_connected": true,
  "brightness": 200,
  "rotation": 0,
  "color_map": 0,
  "ap_mode": false,
  "server_ip": "192.168.1.100",
  "server_port": 8080,
  "device_id": "a3f7k2mx"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `wifi_connected` | bool | WiFi 连接状态 |
| `ssid` | string | 已配置的 WiFi SSID |
| `ip` | string | 设备当前 IP（AP 模式下为 `192.168.4.1`） |
| `server_connected` | bool | TCP 服务器连接状态（网页打开时为 false） |
| `brightness` | int | 当前亮度值 0~253 |
| `rotation` | int | 旋转方向 0=0° 1=90° 2=180° 3=270° |
| `color_map` | int | RGB 通道映射 0=RGB 1=RBG 2=GRB 3=GBR 4=BRG 5=BGR |
| `ap_mode` | bool | 是否处于 AP 热点模式 |
| `server_ip` | string | 已配置的服务器 IP |
| `server_port` | int | 已配置的服务器端口 |
| `device_id` | string | 设备唯一标识 |

---

### POST /api/config

保存完整配置并重启设备。**重启后设备将以新配置重新连接。**

**请求体（application/json）：**

```json
{
  "mode": "sta",
  "ssid": "MyWiFi",
  "pass": "newpassword",
  "server_ip": "192.168.1.100",
  "server_port": 8080,
  "brightness": 200,
  "rotation": 0,
  "color_map": 0,
  "device_id": "mydevice"
}
```

> `pass` 字段为可选，若不传则保留原有密码。  
> `device_id` 字段为可选，若不传则保留原有 ID。

**响应：**

```json
{"success": true, "message": "已保存"}
```

收到响应后约 2 秒设备重启。

---

### GET /api/brightness

即时设置亮度（无需重启）并持久化。

**参数：** `?value=200`（0 ~ 253）

```
GET /api/brightness?value=150
```

**响应：**

```json
{"success": true, "brightness": 150}
```

---

### GET /api/rotation

即时设置屏幕旋转方向（无需重启）并持久化。

**参数：** `?value=N`

| value | 效果 |
|-------|------|
| 0 | 正常（0°） |
| 1 | 顺时针 90° |
| 2 | 180° |
| 3 | 逆时针 90° |

```
GET /api/rotation?value=2
```

**响应：**

```json
{"success": true, "rotation": 2}
```

---

### GET /api/colormap

即时设置 RGB 通道映射（无需重启）并持久化，用于修正 LED 面板颜色通道接线顺序。

**参数：** `?value=N`

| value | 映射 | 说明 |
|-------|------|------|
| 0 | RGB | 正常（默认） |
| 1 | RBG | 蓝绿互换 |
| 2 | GRB | 常见 WS2812 顺序 |
| 3 | GBR | |
| 4 | BRG | |
| 5 | BGR | |

```
GET /api/colormap?value=2
```

**响应：**

```json
{"success": true, "color_map": 2}
```

---

### POST /api/deviceid

即时修改设备 ID（无需重启），立即持久化，下次 TCP 连接时生效。

**请求体：**

```json
{"device_id": "newid123"}
```

**响应：**

```json
{"success": true, "device_id": "newid123"}
```

---

### POST /api/wifi

**仅 AP 模式下使用。** 配置 WiFi 和服务器信息后重启，设备将以 STA 模式连接指定 WiFi。

**请求体：**

```json
{
  "ssid": "MyWiFi",
  "pass": "password",
  "server_ip": "192.168.1.100",
  "server_port": 8080
}
```

**响应：**

```json
{"success": true}
```

---

### GET /api/test

测试设备到服务器的连通性（设备主动尝试 TCP 连接配置的服务器地址）。

```
GET /api/test
```

**响应（成功）：**

```json
{"success": true, "message": "服务器连接成功"}
```

**响应（失败）：**

```json
{"success": false, "message": "无法连接到服务器"}
```

---

### POST /api/reset

恢复出厂设置并重启。所有 NVS 数据清除，含 WiFi、服务器地址、亮度、旋转、颜色映射和设备 ID。

```
POST /api/reset
```

**响应：**

```json
{"success": true}
```

---

### POST /api/update（OTA 固件升级）

上传 `.bin` 固件文件进行空中升级。使用 `multipart/form-data` 格式，字段名为 `firmware`。

```bash
curl -X POST http://192.168.1.88/api/update \
  -F "firmware=@Intrix_0421.bin"
```

OTA 过程中：
- TCP 服务器连接自动断开
- networkTask 被挂起
- LED 屏幕显示进度提示
- 完成后 SPIFFS 格式化，设备自动重启

**响应（成功）：**

```json
{"success": true}
```

---

### POST /api/disconnect

通知设备当前 Web 会话结束，恢复 TCP 服务器连接。通常由网页的 `beforeunload` 事件自动调用，服务端一般无需手动调用。

---

## 4. WebSocket 状态推送

**端点：** `ws://<device_ip>/ws`

设备每隔约 **200ms** 主动向所有已连接的 WebSocket 客户端推送状态消息：

```json
{
  "free_heap": 187432,
  "fps": 24.8,
  "server_connected": true,
  "wifi_connected": true,
  "mode": "sta",
  "brightness": 200,
  "rotation": 0
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `free_heap` | int | 当前可用堆内存（字节），低于 50000 时需注意 |
| `fps` | float | 当前显示帧率 |
| `server_connected` | bool | TCP 连接状态 |
| `wifi_connected` | bool | WiFi 连接状态 |
| `mode` | string | `"sta"` 或 `"ap"` |
| `brightness` | int | 当前亮度 |
| `rotation` | int | 当前旋转值 |

WebSocket 主要用于监控面板，服务端推流程序通常不需要连接它。

---

## 5. 设备 ID 机制

设备 ID 是一个 **8 位小写字母数字字符串**，用于服务端识别多台设备。

**生成规则：**
- 首次上电时若 NVS 中不存在 ID，使用 `esp_random()` 随机生成并永久存储
- 可通过网页界面手动修改，或通过 `POST /api/deviceid` 接口修改
- 重置出厂设置后 ID 清除，下次上电重新随机生成

**服务端使用建议：**

```python
clients = {}  # device_id → socket

def on_client_connect(sock):
    data = sock.recv(1024).decode()
    info = json.loads(data.strip())
    device_id = info.get('device_id', 'unknown')
    clients[device_id] = {
        'socket': sock,
        'width': info['width'],
        'height': info['height'],
    }
    print(f"设备接入: {device_id}  {info['width']}x{info['height']}")
```

---

## 6. 工作模式说明

固件有三种工作状态，影响 TCP 连接行为：

| 状态 | TCP 连接 | 触发条件 |
|------|---------|---------|
| **正常推流模式** | ✅ 连接中 | WiFi 连接成功后默认状态 |
| **网页配置模式** | ❌ 断开 | 用户打开设置网页，网页关闭后自动恢复 |
| **AP 热点模式** | ❌ 不尝试 | WiFi 连接失败或用户手动设置为 AP |

**服务端应对策略：**

- 客户端随时可能断开（用户开网页、WiFi 抖动等），服务端应对每个连接设置心跳或写超时检测，断开后等待设备重连即可。
- 设备断开后 5 秒会自动重试，无需服务端主动处理。

---

## 7. 像素格式详解：RGB565

每个像素 2 字节，16 位编码，小端字节序：

```
  Byte 1 (低字节)          Byte 0 (高字节)
 ┌───────────────┐        ┌───────────────┐
 │ G[2:0] B[4:0] │        │ R[4:0] G[5:3] │
 └───────────────┘        └───────────────┘

 位分布（从高位到低位，uint16_t 视角）：
 [15:11] = R (5 bits, 0~31)
 [10:5]  = G (6 bits, 0~63)
 [4:0]   = B (5 bits, 0~31)
```

**Python 编解码：**

```python
import struct

def rgb_to_rgb565(r, g, b):
    """将 8-bit RGB 转换为 RGB565 小端字节"""
    r5 = r >> 3          # 8bit → 5bit
    g6 = g >> 2          # 8bit → 6bit
    b5 = b >> 3          # 8bit → 5bit
    value = (r5 << 11) | (g6 << 5) | b5
    return struct.pack('<H', value)  # 小端

def rgb565_to_rgb(data):
    """将 RGB565 小端字节解回 8-bit RGB"""
    value = struct.unpack('<H', data)[0]
    r = ((value >> 11) & 0x1F) << 3
    g = ((value >> 5)  & 0x3F) << 2
    b = ( value        & 0x1F) << 3
    return r, g, b

# 示例：构建纯绿色帧
def make_solid_frame(r, g, b, width=64, height=64):
    pixel = rgb_to_rgb565(r, g, b)
    return pixel * (width * height)

green_frame = make_solid_frame(0, 255, 0)  # 8192 字节
```

**常用颜色速查：**

| 颜色 | R | G | B | RGB565（hex） |
|------|---|---|---|--------------|
| 红 | 255 | 0 | 0 | `0xF800` |
| 绿 | 0 | 255 | 0 | `0x07E0` |
| 蓝 | 0 | 0 | 255 | `0x001F` |
| 白 | 255 | 255 | 255 | `0xFFFF` |
| 黑 | 0 | 0 | 0 | `0x0000` |
| 黄 | 255 | 255 | 0 | `0xFFE0` |
| 青 | 0 | 255 | 255 | `0x07FF` |
| 紫 | 255 | 0 | 255 | `0xF81F` |

---

## 8. 音频格式详解：PCM16

| 参数 | 值 |
|------|---|
| 采样率 | 16000 Hz |
| 声道 | 单声道（Mono） |
| 位深 | 16-bit 有符号整数 |
| 字节序 | 小端（Little-Endian） |
| 每秒字节数 | 32000 bytes/s |
| 每 20ms 字节数 | 640 bytes |

**从常见格式转换：**

```python
# WAV → PCM16（使用 pydub）
from pydub import AudioSegment

def wav_to_pcm16(wav_path):
    audio = AudioSegment.from_wav(wav_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return audio.raw_data  # 即 PCM16 LE

# MP3 → PCM16
def mp3_to_pcm16(mp3_path):
    audio = AudioSegment.from_mp3(mp3_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return audio.raw_data

# numpy 生成 440Hz 正弦波（1秒）
import numpy as np, struct
def sine_wave_pcm(freq=440, duration=1.0, sample_rate=16000):
    t = np.linspace(0, duration, int(sample_rate * duration))
    samples = (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()
```

---

## 9. 服务端实现参考

### 9.1 Python 最小示例

以下示例演示了一个最简服务器，能接受设备连接并循环推送彩色动画帧：

```python
import socket
import struct
import json
import time
import threading
import math

HOST = '0.0.0.0'
PORT = 8080
W, H = 64, 64

def rgb_to_rgb565_le(r, g, b):
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return struct.pack('<H', v)

def make_color_wheel_frame(t):
    """生成随时间旋转的彩虹渐变帧"""
    buf = bytearray(W * H * 2)
    for y in range(H):
        for x in range(W):
            hue = (x / W + y / H + t) % 1.0
            # 简单 HSV→RGB，S=1 V=1
            h6 = hue * 6
            i = int(h6)
            f = h6 - i
            q = int((1 - f) * 255)
            t_ = int(f * 255)
            colors = [
                (255, t_, 0), (q, 255, 0), (0, 255, t_),
                (0, q, 255), (t_, 0, 255), (255, 0, q)
            ]
            r, g, b = colors[i % 6]
            pixel = rgb_to_rgb565_le(r, g, b)
            idx = (y * W + x) * 2
            buf[idx:idx+2] = pixel
    return bytes(buf)

def handle_client(conn, addr):
    print(f"[+] 设备连接: {addr}")
    device_id = 'unknown'
    try:
        # 接收 client_info 握手
        data = b''
        while b'\n' not in data:
            chunk = conn.recv(256)
            if not chunk:
                return
            data += chunk
        info = json.loads(data.split(b'\n')[0])
        device_id = info.get('device_id', 'unknown')
        print(f"    设备ID: {device_id}  分辨率: {info['width']}x{info['height']}")
        print(f"    音频: {info.get('audio_format')} {info.get('audio_rate')}Hz")

        frame_t = 0.0
        while True:
            # 发送视频帧
            frame = make_color_wheel_frame(frame_t)
            header = json.dumps({
                "type": "frame_data",
                "width": W, "height": H,
                "format": "RGB565",
                "data_size": len(frame)
            }) + '\n'
            conn.sendall(header.encode())
            conn.sendall(frame)
            frame_t += 0.03
            time.sleep(1/25)  # ~25fps

    except (ConnectionResetError, BrokenPipeError):
        print(f"[-] 设备 {device_id} 断开连接")
    except Exception as e:
        print(f"[!] 错误: {e}")
    finally:
        conn.close()

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(10)
    print(f"服务器监听 {HOST}:{PORT}")
    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()

if __name__ == '__main__':
    main()
```

---

### 9.2 多客户端管理

```python
import threading, json, socket, time

class IntrixServer:
    def __init__(self, port=8080):
        self.port = port
        self.clients = {}       # device_id → {'socket', 'info', 'lock'}
        self.lock = threading.Lock()

    def broadcast_frame(self, frame_bytes):
        """向所有在线设备推送同一帧"""
        W, H = 64, 64
        header = json.dumps({
            "type": "frame_data", "width": W, "height": H,
            "format": "RGB565", "data_size": len(frame_bytes)
        }) + '\n'
        dead = []
        with self.lock:
            for device_id, c in self.clients.items():
                try:
                    with c['lock']:
                        c['socket'].sendall(header.encode())
                        c['socket'].sendall(frame_bytes)
                except Exception:
                    dead.append(device_id)
        for d in dead:
            self.remove_client(d)

    def send_to(self, device_id, frame_bytes):
        """向指定设备推送帧"""
        with self.lock:
            c = self.clients.get(device_id)
        if not c:
            return False
        W, H = 64, 64
        header = json.dumps({
            "type": "frame_data", "width": W, "height": H,
            "format": "RGB565", "data_size": len(frame_bytes)
        }) + '\n'
        try:
            with c['lock']:
                c['socket'].sendall(header.encode())
                c['socket'].sendall(frame_bytes)
            return True
        except Exception:
            self.remove_client(device_id)
            return False

    def send_audio(self, device_id, pcm_bytes):
        """向指定设备发送音频块"""
        with self.lock:
            c = self.clients.get(device_id)
        if not c:
            return False
        header = json.dumps({
            "type": "audio_data",
            "data_size": len(pcm_bytes)
        }) + '\n'
        try:
            with c['lock']:
                c['socket'].sendall(header.encode())
                c['socket'].sendall(pcm_bytes)
            return True
        except Exception:
            self.remove_client(device_id)
            return False

    def set_brightness(self, device_id, value):
        with self.lock:
            c = self.clients.get(device_id)
        if not c:
            return
        cmd = json.dumps({"type": "brightness", "value": value}) + '\n'
        with c['lock']:
            c['socket'].sendall(cmd.encode())

    def clear_screen(self, device_id):
        with self.lock:
            c = self.clients.get(device_id)
        if not c:
            return
        cmd = json.dumps({"type": "clear"}) + '\n'
        with c['lock']:
            c['socket'].sendall(cmd.encode())

    def remove_client(self, device_id):
        with self.lock:
            c = self.clients.pop(device_id, None)
        if c:
            try:
                c['socket'].close()
            except Exception:
                pass
            print(f"[-] 设备下线: {device_id}")

    def _handle_client(self, conn, addr):
        device_id = None
        try:
            buf = b''
            while b'\n' not in buf:
                chunk = conn.recv(256)
                if not chunk:
                    return
                buf += chunk
            info = json.loads(buf.split(b'\n')[0])
            device_id = info.get('device_id', f'unknown_{addr[0]}')
            with self.lock:
                self.clients[device_id] = {
                    'socket': conn,
                    'info': info,
                    'lock': threading.Lock()
                }
            print(f"[+] 设备上线: {device_id}  {addr}")
            # 保持连接存活
            conn.settimeout(30)
            while True:
                try:
                    conn.recv(1)  # 等待断开
                except socket.timeout:
                    pass
                except Exception:
                    break
        finally:
            if device_id:
                self.remove_client(device_id)

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', self.port))
        srv.listen(20)
        print(f"Intrix 服务器启动，监听端口 {self.port}")
        while True:
            conn, addr = srv.accept()
            threading.Thread(
                target=self._handle_client,
                args=(conn, addr), daemon=True
            ).start()
```

---

### 9.3 音视频同步建议

由于固件的状态机是串行处理的（视频和音频帧不能同时接收），推荐以下调度策略：

```python
def av_sync_push(server, device_id, video_frames, audio_pcm,
                 fps=25, audio_rate=16000):
    """
    同步推送音视频。
    video_frames: list of bytes，每元素为一帧 RGB565 数据
    audio_pcm: bytes，完整 PCM16 LE 音频数据
    """
    frame_interval = 1.0 / fps           # 40ms
    audio_per_frame = int(audio_rate * frame_interval) * 2  # 每帧对应音频字节数

    audio_pos = 0
    for i, frame in enumerate(video_frames):
        t_start = time.time()

        # 1. 先发视频帧
        server.send_to(device_id, frame)

        # 2. 再发对应音频块
        chunk = audio_pcm[audio_pos: audio_pos + audio_per_frame]
        if chunk:
            server.send_audio(device_id, chunk)
        audio_pos += audio_per_frame

        # 3. 等到下一帧时刻
        elapsed = time.time() - t_start
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
```

---

## 10. 错误处理与重连

**设备侧行为（固件保证）：**

- WiFi 断开后每 10 秒重试
- TCP 连接断开后每 5 秒重试
- 帧接收超时（3 秒）后自动复位状态机，继续接受新连接
- JSON 解析失败静默丢弃，不断开连接

**服务端侧建议：**

```python
def safe_send_frame(sock, frame_bytes, W=64, H=64):
    """带异常捕获的帧发送，返回是否成功"""
    try:
        header = json.dumps({
            "type": "frame_data",
            "width": W, "height": H,
            "format": "RGB565",
            "data_size": len(frame_bytes)
        }) + '\n'
        sock.sendall(header.encode())
        sock.sendall(frame_bytes)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False  # 调用者负责清理连接
```

**检测设备在线的方法：**

1. **发送失败检测**：`sendall` 抛出异常时认为设备离线。
2. **心跳机制（可选）**：每隔若干秒发送一条空的 `clear` 命令，若发送失败则标记下线。

---

## 11. 完整消息类型速查表

### TCP 消息（服务端 → 设备）

| 消息类型 | 传输方式 | 说明 |
|---------|---------|------|
| `frame_data` | JSON头 + 二进制 | 推送视频帧（8192 字节 RGB565） |
| `audio_data` | JSON头 + 二进制 | 推送音频块（≤8192 字节 PCM16） |
| `brightness` | 纯 JSON | 设置亮度（0~253） |
| `clear` | 纯 JSON | 清屏 |

### TCP 消息（设备 → 服务端）

| 消息类型 | 传输方式 | 说明 |
|---------|---------|------|
| `client_info` | 纯 JSON | 连接后立即发送的握手消息 |

### HTTP 接口速查

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取设备状态 |
| `/api/config` | POST | 保存配置并重启 |
| `/api/brightness` | GET | 即时调整亮度 |
| `/api/rotation` | GET | 即时调整旋转方向 |
| `/api/colormap` | GET | 即时调整颜色映射 |
| `/api/deviceid` | POST | 修改设备 ID |
| `/api/wifi` | POST | AP模式下配网 |
| `/api/test` | GET | 测试服务器连通性 |
| `/api/reset` | POST | 恢复出厂设置 |
| `/api/update` | POST | OTA 固件升级 |
| `/api/disconnect` | POST | 通知设备恢复 TCP 连接 |

### WebSocket（设备 → 服务端/浏览器）

| 端点 | 推送间隔 | 说明 |
|------|---------|------|
| `ws://<ip>/ws` | 200ms | 实时状态（fps、heap、连接状态等） |

---

*文档对应固件版本：Intrix 20260421*
