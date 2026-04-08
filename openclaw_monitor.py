#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 状态监控器 - 实时检测 AI 工作状态并更新 LED 显示
"""

import requests
import subprocess
import time
import json
import os
import signal

LED_SERVER = "http://localhost:5000"
UPDATE_INTERVAL = 5  # 每5秒检测一次（降低CPU占用）

# OpenClaw 状态
class OpenClawMonitor:
    def __init__(self):
        self.was_busy = False  # 记录上次状态
        self._weather_cache = None
        self._weather_fetch_time = 0
        self._weather_location = 'Shanghai'  # 可以改成其他城市
    
    def get_openclaw_status(self):
        """获取 OpenClaw 状态 - 仅使用系统资源，不调用 openclaw 命令"""
        status = {
            'session_count': 0,
            'active_sessions': 0,
            'memory_usage': 0.0,
            'cpu_load': 0.0,
            'is_busy': False,
            'last_message': 'Ready',
            'token_usage': None,
        }
        
        try:
            # CPU 负载
            with open('/proc/loadavg', 'r') as f:
                load = float(f.read().split()[0])
                cpu_count = os.cpu_count() or 4
                status['cpu_load'] = min(load / cpu_count, 1.0)
        except:
            pass
        
        try:
            # 内存使用
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemAvailable:'):
                        avail = int(line.split()[1])
                    elif line.startswith('MemTotal:'):
                        total = int(line.split()[1])
                status['memory_usage'] = 1.0 - (avail / total)
        except:
            pass
        
        # 天气信息（每10分钟更新一次）
        weather = self._get_weather()
        if weather:
            status['weather'] = weather

        # 解析 session 文件获取 token 用量
        token_usage = self._get_token_usage()
        if token_usage:
            status['token_usage'] = token_usage
        
        # 根据 CPU 负载判断工作状态
        if status['cpu_load'] > 0.5:  # CPU > 50%
            status['is_busy'] = True
        elif status['cpu_load'] > 0.3:  # CPU > 30%
            status['is_busy'] = status.get('active_sessions', 0) > 0
        
        return status
    
    def _get_weather(self):
        """获取天气信息（10分钟缓存）"""
        import urllib.request
        now = time.time()
        if self._weather_cache and (now - self._weather_fetch_time) < 600:
            return self._weather_cache
        try:
            url = f"https://wttr.in/{self._weather_location}?format=j1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
            current = data['current_condition'][0]
            weather = {
                'temp': int(current['temp_C']),
                'code': int(current['weatherCode']),
                'desc': current['weatherDesc'][0]['value'] if current.get('weatherDesc') else '',
            }
            self._weather_cache = weather
            self._weather_fetch_time = now
            return weather
        except Exception as e:
            # 如果获取失败，返回缓存（如果有）
            return self._weather_cache

    def _get_token_usage(self):
        """从 session 文件中解析 token 使用量"""
        import glob
        
        sessions_dir = os.path.expanduser('~/.openclaw/agents/main/sessions')
        pattern = os.path.join(sessions_dir, '*.jsonl')
        
        total_input = 0
        total_output = 0
        total_cost = 0.0
        
        try:
            for session_file in glob.glob(pattern):
                if session_file.endswith('.reset.'):
                    continue  # 跳过重置的旧 session
                try:
                    with open(session_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                if obj.get('type') == 'message':
                                    msg = obj.get('message', {})
                                    usage = msg.get('usage')
                                    if usage:
                                        total_input += usage.get('input', 0)
                                        total_output += usage.get('output', 0)
                                        cost_info = usage.get('cost', {})
                                        if isinstance(cost_info, dict):
                                            total_cost += cost_info.get('total', 0)
                                        elif isinstance(cost_info, (int, float)):
                                            total_cost += cost_info
                            except json.JSONDecodeError:
                                continue
                except (IOError, OSError):
                    continue
            
            if total_input > 0 or total_output > 0:
                return {
                    'input_tokens': total_input,
                    'output_tokens': total_output,
                    'total_tokens': total_input + total_output,
                    'total_cost': total_cost,
                }
        except Exception as e:
            print(f"Token usage parse error: {e}")
        
        return None
    
    def get_work_message(self, status):
        """根据状态生成消息"""
        if status['is_busy']:
            if not self.was_busy:
                # 刚进入工作状态
                self.was_busy = True
            return "⚡ AI工作中..."
        else:
            self.was_busy = False
            return "✅ 就绪"
    
    def update_led(self, status):
        """更新 LED 显示"""
        try:
            # 添加工作消息
            status['last_message'] = self.get_work_message(status)
            
            response = requests.post(
                f"{LED_SERVER}/api/openclaw-status",
                json=status,
                timeout=2
            )
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False
        except Exception as e:
            print(f"Update error: {e}")
            return False
    
    def run(self):
        """主循环"""
        print("🚀 OpenClaw 状态监控器启动")
        print(f"📡 LED Server: {LED_SERVER}")
        print(f"⏱️  检测间隔: {UPDATE_INTERVAL}秒")
        print("-" * 40)
        
        consecutive_errors = 0
        
        while True:
            try:
                # 获取状态
                status = self.get_openclaw_status()
                
                # 更新 LED
                success = self.update_led(status)
                
                if success:
                    consecutive_errors = 0
                    # 简洁输出
                    busy = "🔥" if status['is_busy'] else "💤"
                    mem = int(status['memory_usage'] * 100)
                    cpu = int(status['cpu_load'] * 100)
                    print(f"\r{busy} 工作中: {status['is_busy']} | MEM: {mem}% | CPU: {cpu}% | {status['last_message']}", end='')
                else:
                    consecutive_errors += 1
                    if consecutive_errors <= 3:
                        print(f"\n⚠️  LED 连接失败 ({consecutive_errors}/3)")
                
                if consecutive_errors >= 10:
                    print(f"\n❌ 连接失败次数过多，退出")
                    break
                    
            except KeyboardInterrupt:
                print("\n👋 监控器已停止")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                consecutive_errors += 1
            
            time.sleep(UPDATE_INTERVAL)

def main():
    monitor = OpenClawMonitor()
    
    # 处理信号
    def signal_handler(sig, frame):
        print("\n👋 收到停止信号")
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    monitor.run()

if __name__ == '__main__':
    main()
