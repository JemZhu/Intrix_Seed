#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vocab Theme - 背单词主题
使用 quan.ttf 中英日 8x8 点阵字体
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class VocabTheme:
    """背单词主题 - 64x64 LED 矩阵显示"""

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        # 调色板
        self.COLORS = {
            'bg': (5, 5, 18),
            'word': (80, 200, 255),     # 天蓝色
            'trans': (255, 200, 100),   # 金色
            'streak': (255, 150, 80),  # 橙红
            'divider': (35, 35, 60),
        }

        # 加载 quan.ttf 字体
        self._font = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 8)
        # 加载 HZK12
        self._load_hzk12()

        # 单词列表
        self._word_list = [
            ('apple', '苹果'),
            ('banana', '香蕉'),
            ('cherry', '樱桃'),
            ('dragon', '龙'),
            ('elephant', '大象'),
            ('flower', '花'),
            ('garden', '花园'),
            ('horizon', '地平线'),
            ('island', '岛屿'),
            ('journey', '旅程'),
            ('kitchen', '厨房'),
            ('library', '图书馆'),
            ('mountain', '山'),
            ('network', '网络'),
            ('ocean', '海洋'),
            ('palace', '宫殿'),
            ('quantum', '量子'),
            ('rainbow', '彩虹'),
            ('sunset', '日落'),
            ('thunder', '雷声'),
        ]
        self._current_idx = 0
        self._anim_frame = 0

    def set_word_list(self, words: list):
        """设置单词列表，格式: [(word, translation), ...]"""
        if words and len(words[0]) >= 2:
            self._word_list = words
            self._current_idx = 0

    def get_current_word(self) -> tuple:
        return self._word_list[self._current_idx % len(self._word_list)]

    def advance_word(self):
        self._current_idx = (self._current_idx + 1) % len(self._word_list)

    def _text_width(self, text: str) -> int:
        """计算文字占用宽度（像素）"""
        # quan.ttf: 英文字符5宽，中文8宽
        w = 0
        for ch in text:
            if self._is_cjk(ch):
                w += 8
            else:
                w += 5
        return w

    def _is_cjk(self, ch: str) -> bool:
        """判断是否为中日韩字符"""
        code = ord(ch)
        return (0x4E00 <= code <= 0x9FFF or    # CJK Unified Ideographs
                0x3040 <= code <= 0x30FF or    # Hiragana/Katakana
                0xAC00 <= code <= 0xD7AF)      # Korean Hangul

    def _draw_word(self, draw: ImageDraw, word: str, scroll_offset: int):
        """英文单词（可滚动）"""
        word_w = self._text_width(word)
        screen_w = 60  # 可用宽度

        if word_w <= screen_w:
            # 居中显示
            x = (64 - word_w) // 2
            y = 15
            draw.text((x, y), word, font=self._font, fill=self.COLORS['word'])
        else:
            # 滚动：计算偏移（向右为正，向左滚动）
            offset = scroll_offset % (word_w + 20)  # 留20像素空白间隔
            if offset > word_w:
                # 字符还在屏幕外
                draw.text((2, 15), word, font=self._font, fill=self.COLORS['word'])
            else:
                # 绘制第一个片段（从offset开始到末尾）
                visible1_len = word_w - offset
                # 计算屏幕上能显示多少字符
                chars_on_screen = 0
                pixel_count = 0
                for i, ch in enumerate(word):
                    char_w = 8 if self._is_cjk(ch) else 5
                    if pixel_count + char_w > visible1_len:
                        break
                    pixel_count += char_w
                    chars_on_screen += 1

                x = 2
                for ch in word[:chars_on_screen]:
                    draw.text((x, 15), ch, font=self._font, fill=self.COLORS['word'])
                    x += 8 if self._is_cjk(ch) else 5

                # 如果还有剩余字符（从开头画）
                remaining = word[chars_on_screen:]
                if remaining and x < 64:
                    remaining_w = self._text_width(remaining)
                    if x + remaining_w > 64:
                        # 截断
                        for ch in remaining:
                            ch_w = 8 if self._is_cjk(ch) else 5
                            if x + ch_w > 64:
                                break
                            draw.text((x, 15), ch, font=self._font, fill=self.COLORS['word'])
                            x += ch_w

    def _load_hzk12(self):
        """加载 HZK12 字体"""
        try:
            with open('/home/jem/Intrix_Seed/HZK12', 'rb') as f:
                self._hzk12 = f.read()
        except:
            self._hzk12 = None

    def _get_hzk12_bitmap(self, char: str) -> bytes:
        """获取汉字12x12点阵"""
        if not self._hzk12:
            return b'\x00' * 24
        try:
            gb = char.encode('gb2312')
            if len(gb) != 2:
                return b'\x00' * 24
            area = gb[0] - 0xA1
            pos = gb[1] - 0xA1
            offset = (area * 94 + pos) * 24
            if 0 <= offset < len(self._hzk12):
                return self._hzk12[offset:offset + 24]
        except:
            pass
        return b'\x00' * 24

    def _draw_hzk12_char(self, draw: ImageDraw, x: int, y: int, ch: str, color: tuple):
        """绘制一个 HZK12 汉字"""
        bitmap = self._get_hzk12_bitmap(ch)
        for row in range(12):
            byte1 = bitmap[row * 2]
            byte2 = bitmap[row * 2 + 1]
            for col in range(12):
                if col < 8:
                    bit = (byte1 >> (7 - col)) & 1
                else:
                    bit = (byte2 >> (15 - col)) & 1
                if bit:
                    draw.point([x + col, y + row], fill=color)

    def _draw_translation(self, draw: ImageDraw, trans: str):
        """中文释义（HZK12 12x12点阵）"""
        # 每个汉字12x12，最多4个
        display = trans[:4]
        n = len(display)
        char_w = 12
        total_w = n * char_w
        x = (64 - total_w) // 2
        y = 30  # 紧跟英文单词下方

        for i, ch in enumerate(display):
            self._draw_hzk12_char(draw, x + i * char_w, y, ch, self.COLORS['trans'])

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        import time
        if t is None:
            t = time.time()

        self._anim_frame += 1

        word, trans = self.get_current_word()

        # 每180帧（约3分钟）自动换词
        if self._anim_frame % 180 == 0:
            self.advance_word()

        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        # 顶部：连续天数 + 火焰图标
        self._draw_streak(draw, status, t)

        # 分隔线
        draw.line([(2, 12), (61, 12)], fill=self.COLORS['divider'], width=1)

        # 英文单词（可能滚动）
        scroll_offset = int(t * 8)  # 每秒滚动8像素
        self._draw_word(draw, word.upper(), scroll_offset)

        # 中文释义
        self._draw_translation(draw, trans)

        return np.array(img)

    def _draw_streak(self, draw: ImageDraw, status: dict, t: float):
        """连续学习天数"""
        study_info = status or {}
        streak = study_info.get('streak', 7)

        # 火焰图标（几个像素块拼成）
        flicker = int(2 * np.sin(t * 12))
        cx, cy = 6, 3

        # 火焰（用椭圆）
        draw.ellipse([cx - 1, cy - 2 + flicker, cx + 2, cy + 2], fill=(255, 100, 30))
        draw.rectangle([cx - 2, cy + 1, cx + 3, cy + 5], fill=(200, 80, 20))

        # 天数数字
        s = str(streak)
        draw.text((12, 1), s, font=self._font, fill=self.COLORS['streak'])


if __name__ == '__main__':
    import time
    theme = VocabTheme()

    print("📚 测试背单词主题 (quan.ttf)...")
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_vocab', exist_ok=True)

    # Test different scroll states
    for i in range(6):
        frame = theme.generate_frame({'streak': 7}, t=i * 0.5)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_vocab/frame_{i:02d}.png')
        word, tr = theme.get_current_word()
        print(f"  帧 {i:02d}: {word} -> {tr}")
        theme.advance_word()

    print("✅ 测试完成！")
