#!/usr/bin/env python3
# led_status_updater.py - 持续向 LED 服务器推送 OpenClaw 状态
# 每2秒更新一次，显示 OpenClaw 工作状态

import requests
import time
import subprocess
import json
import os

LED_SERVER = "http://localhost:5000"
UPDATE_INTERVAL = 2  # 秒


def get_openclaw_status():
    """从系统获取状态（不调用耗能的 openclaw status）"""
    status = {
        'session_count': 0,
        'active_sessions': 0,
        'memory_usage': 0.0,
        'cpu_load': 0.0,
        'is_busy': False,
        'last_message': '',
        'model': '',
    }

    # 从 /proc/meminfo 获取内存使用率
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    avail_kb = int(line.split()[1])
                elif line.startswith('MemTotal:'):
                    total_kb = int(line.split()[1])
            status['memory_usage'] = 1.0 - (avail_kb / total_kb)
    except:
        pass

    # 从 /proc/loadavg 获取 CPU 负载（更准确的瞬时值）
    try:
        with open('/proc/loadavg', 'r') as f:
            parts = f.read().split()
            load_1min = float(parts[0])
            # 获取 CPU 核心数
            with open('/proc/cpuinfo', 'r') as f2:
                cpu_count = sum(1 for line in f2 if line.startswith('processor'))
            if cpu_count == 0:
                cpu_count = 4  # 默认
            status['cpu_load'] = min(load_1min / cpu_count, 1.0)
    except:
        pass

    # 如果 CPU 负载过高，标记为 busy
    status['is_busy'] = status['cpu_load'] > 0.7

    return status


def main():
    print(f"[LED] 状态更新器启动，每 {UPDATE_INTERVAL} 秒更新一次")
    print(f"[LED] LED 服务器: {LED_SERVER}")

    consecutive_errors = 0

    while True:
        try:
            status = get_openclaw_status()
            response = requests.post(
                f"{LED_SERVER}/api/openclaw-status",
                json=status,
                timeout=2
            )

            if response.status_code == 200:
                consecutive_errors = 0
                # 简洁输出
                busy_marker = "🔴" if status['is_busy'] else "🟢"
                mem_pct = int(status['memory_usage'] * 100)
                cpu_pct = int(status['cpu_load'] * 100)
                print(f"\r{busy_marker} MEM:{mem_pct}% CPU:{cpu_pct}% sessions:{status['session_count']}", end='')
            else:
                consecutive_errors += 1
                print(f"\n[LED] 服务器响应异常: {response.status_code}")

        except requests.exceptions.ConnectionError:
            consecutive_errors += 1
            if consecutive_errors <= 3:
                print(f"\n[LED] 无法连接到 LED 服务器 ({consecutive_errors}/3)")
        except Exception as e:
            consecutive_errors += 1
            print(f"\n[LED] 异常: {e}")

        if consecutive_errors >= 10:
            print(f"\n[LED] 连接失败次数过多，退出")
            break

        time.sleep(UPDATE_INTERVAL)


if __name__ == '__main__':
    main()
