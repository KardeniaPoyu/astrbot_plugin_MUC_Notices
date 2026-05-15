"""
MUC 通知卡片渲染器
将通知列表渲染为精美的卡片图片
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch
import os
import textwrap

# 字体配置 - 支持多种路径查找和fallback机制
def _setup_font():
    """设置中文字体，优先使用本地字体，fallback到系统字体"""
    font_loaded = False
    
    # 尝试的字体路径（按优先级）
    font_paths = [
        # 插件本地字体目录（推荐）
        os.path.join(os.path.dirname(__file__), 'fonts', 'NotoSansSC-Medium.ttf'),
        # AstrBot 插件数据目录
        os.path.join(os.path.dirname(__file__), '..', '..', 'fonts', 'NotoSansSC-Medium.ttf'),
        # 常见系统路径
        '/usr/share/fonts/truetype/noto/NotoSansSC-Medium.ttf',
        'C:/Windows/Fonts/NotoSansSC-Medium.ttf',
    ]
    
    for font_path in font_paths:
        if font_path and os.path.exists(font_path):
            try:
                fm.fontManager.addfont(font_path)
                plt.rcParams['font.sans-serif'] = ['Noto Sans SC'] + plt.rcParams['font.sans-serif']
                font_loaded = True
                break
            except Exception:
                continue
    
    # Fallback: 使用系统中文字体
    if not font_loaded:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB'] + plt.rcParams['font.sans-serif']
    
    plt.rcParams['axes.unicode_minus'] = False

_setup_font()

# 民大配色
MUC_RED = '#b30216'
MUC_GRAY = '#9B9B9B'
MUC_LIGHT = '#f0f2f5'
WHITE = '#FFFFFF'
DARK = '#1a1a1a'


def render_notices(notices: list[dict], save_path: str):
    """将通知列表渲染为卡片图片"""
    n = len(notices)
    fig_height = max(2.5, 1.5 + n * 1.5)
    
    fig, ax = plt.subplots(figsize=(8.5, fig_height))
    ax.set_xlim(0, 8.5)
    ax.set_ylim(0, fig_height)
    ax.axis('off')
    fig.patch.set_facecolor(MUC_LIGHT)
    
    y = fig_height - 0.3
    
    # 顶部标题栏
    header_h = 0.6
    header = FancyBboxPatch((0.3, y - header_h), 7.9, header_h,
                           boxstyle="round,pad=0", facecolor=MUC_RED, edgecolor='none')
    ax.add_patch(header)
    ax.text(4.25, y - header_h/2, '中央民族大学 · 通知聚合',
            fontsize=13, fontweight='bold', ha='center', va='center', color=WHITE)
    y -= header_h + 0.15
    
    # 每条通知
    for item in notices:
        source = item.get('source', item.get('source_key', ''))
        title = item.get('title', '')
        date = item.get('date', '')
        summary = item.get('summary', '')[:100]
        
        # 自动换行
        wrapped_summary = textwrap.fill(summary, width=35) if summary else ""
        summary_lines = 0
        if wrapped_summary:
            summary_lines = wrapped_summary.count('\n') + 1
        # 根据内容动态调整卡片高度
        card_h = 0.9 + summary_lines * 0.18
        card_y = y - card_h
        
        # 卡片背景
        card = FancyBboxPatch((0.3, card_y), 7.9, card_h,
                             boxstyle="round,pad=0.05", 
                             facecolor=WHITE, edgecolor='#e8e8e8', linewidth=0.5)
        ax.add_patch(card)
        
        # 红色竖条
        stripe = FancyBboxPatch((0.3, card_y + 0.08), 0.06, card_h - 0.16,
                               boxstyle="round,pad=0", facecolor=MUC_RED, edgecolor='none')
        ax.add_patch(stripe)
        
        # 来源 + 日期
        ax.text(0.55, card_y + card_h - 0.25, f'[{source}]',
                fontsize=7, color=MUC_RED, va='top')
        ax.text(7.9, card_y + card_h - 0.25, date,
                fontsize=7, color=MUC_GRAY, ha='right', va='top')
        
        # 标题
        ax.text(0.55, card_y + card_h - 0.50, title,
                fontsize=9.5, fontweight='bold', color=DARK, va='top')
        
        # 摘要（自动换行）
        if wrapped_summary:
            ax.text(0.55, card_y + card_h - 0.80, wrapped_summary,
                    fontsize=7.5, color='#555', va='top')
        
        y = card_y
    
    # 底部
    ax.text(4.25, 0.1, 'Powered by Azi', fontsize=7,
            color=MUC_GRAY, ha='center', va='bottom')
    
    fig.savefig(save_path, dpi=150, bbox_inches='tight', 
                facecolor=MUC_LIGHT, pad_inches=0.3)
    plt.close()
    return save_path
