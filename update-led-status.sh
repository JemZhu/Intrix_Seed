#!/bin/bash
# LED Status Updater for OpenClaw
# 用法: ./update-led-status.sh [json_data]

LED_SERVER="http://localhost:5000"

if [ -z "$1" ]; then
    # 如果没有参数，生成默认状态
    # 这里可以通过 openclaw status 命令获取真实数据
    cat <<EOF
用法:
  ./update-led-status.sh '{"session_count": 1, "active_sessions": 0, "memory_usage": 0.5, "cpu_load": 0.3, "is_busy": false}'
EOF
    exit 1
fi

curl -s -X POST "$LED_SERVER/api/openclaw-status" \
  -H "Content-Type: application/json" \
  -d "$1" | jq .

echo ""
echo "✅ LED 状态已更新"
