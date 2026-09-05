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
import logging

logger = logging.getLogger(__name__)


def _normalize_font_list(value):
    """
    规范化 font.sans-serif 配置值为列表
    处理 Matplotlib 配置中可能出现的字符串情况
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return []


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
        # Linux 系统路径（常见发行版）
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansSC-Medium.ttf',
        '/usr/share/fonts/opentype/noto/NotoSansSC-Medium.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansSC-Medium.otf',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        # macOS 系统路径
        '/System/Library/Fonts/PingFang.ttc',
        # Windows 系统路径
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
    ]

    for font_path in font_paths:
        if font_path and os.path.exists(font_path):
            try:
                fm.fontManager.addfont(font_path)
                # matplotlib 注册字体时使用的是字体文件自带的 family name，
                # 不一定叫 "Noto Sans SC"，必须读出真实名字再写进 rcParams，
                # 否则 rcParams 里配置的名字对不上已注册字体，会静默回退到
                # 不含中文字形的 DejaVu Sans，导致中文全部变成方块/乱码。
                font_name = fm.FontProperties(fname=font_path).get_name()
                current = _normalize_font_list(plt.rcParams.get('font.sans-serif', []))
                plt.rcParams['font.sans-serif'] = [font_name] + current
                font_loaded = True
                logger.debug(f"[MUC Card] 字体加载成功: {font_path} -> {font_name}")
                break
            except Exception as e:
                logger.debug(f"[MUC Card] 字体加载失败 {font_path}: {e}")
                continue

    # Fallback: 使用系统中文字体（跨平台：Linux / macOS / Windows）
    if not font_loaded:
        current = _normalize_font_list(plt.rcParams.get('font.sans-serif', []))
        # Linux常见中文字体 + macOS + Windows
        plt.rcParams['font.sans-serif'] = [
            'WenQuanYi Micro Hei',      # Linux (Ubuntu, Debian)
            'Noto Sans CJK SC',         # Linux (Noto CJK)
            'Droid Sans Fallback',      # Linux (Android)
            'PingFang SC',              # macOS
            'Hiragino Sans GB',         # macOS
            'SimHei',                    # Windows
            'Microsoft YaHei'           # Windows
        ] + current
        logger.debug("[MUC Card] 使用系统 fallback 字体")

    plt.rcParams['axes.unicode_minus'] = False

_setup_font()

# 民大配色（更沉稳的暗红 + 暖白背景，减少饱和度冲击）
MUC_RED = '#7a1128'       # 深枣红，标题栏
MUC_ACCENT = '#c8102e'    # 稍亮的强调红，用于来源徽标/竖条
MUC_GRAY = '#9a958f'      # 次要文字（日期等）
MUC_BG = '#f6f3ee'        # 暖白背景，比纯白更柔和
CARD_BG = '#ffffff'
CARD_BORDER = '#ece6dd'
CARD_SHADOW = '#ded7cb'
TEXT_DARK = '#20201e'
TEXT_BODY = '#5a564f'
WHITE = '#FFFFFF'


def _text_width(text: str, cjk_w: float = 0.118, ascii_w: float = 0.062) -> float:
    """按字符宽度粗略估算文本渲染宽度（中日韩字符按等宽字形约为拉丁字符两倍计算）。

    之前徽标宽度用 `len(label) * 常数` 统一估算每个字符的宽度，短的英文来源
    key（如 muc_tzgg）测试时看着没问题，但来源名换成中文全称（如
    "研究生院 - 研究生招生网"）后文字比徽标框还宽，导致穿模。
    """
    width = 0.0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF  # CJK 统一表意文字
            or 0x3000 <= code <= 0x303F  # 中文标点
            or 0xFF00 <= code <= 0xFFEF  # 全角字符
        ):
            width += cjk_w
        else:
            width += ascii_w
    return width


def _wrap(text: str, width: int, max_lines: int | None = None) -> str:
    if not text:
        return ""
    lines = textwrap.wrap(text, width=width) or [""]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if len(last) > 1:
            last = last[:-1].rstrip() + "…"
        lines[-1] = last
    return "\n".join(lines)


def render_notices(notices: list[dict], save_path: str):
    """将通知列表渲染为卡片图片"""
    n = len(notices)

    card_width = 7.9
    left = 0.35
    right = left + card_width

    # 卡片内部纵向布局的统一常量：card_h 的计算和实际绘制必须共用同一套
    # 数值，否则两边算出来的高度会对不上，导致文字贴底/溢出卡片边框。
    TOP_PAD = 0.18       # 卡片顶部到来源徽标/日期行的间距
    BADGE_ROW_H = 0.32   # 来源徽标/日期行占用的高度
    TITLE_LINE_H = 0.29  # 标题每行高度
    SUMMARY_GAP = 0.10   # 标题与摘要之间的间距
    SUMMARY_LINE_H = 0.22  # 摘要每行高度
    BOTTOM_PAD = 0.20    # 卡片底部留白

    # 预计算每张卡片需要的行数，从而精确算出画布高度，避免文字溢出卡片
    prepared = []
    for item in notices:
        source = item.get('source', item.get('source_key', ''))
        title = _wrap(item.get('title', ''), width=32, max_lines=2)
        date = item.get('date', '')
        # 大多数来源页面只公布年月日、没有具体时间，抓取时用 00:00 占位；
        # 卡片上原样显示 "00:00" 会让人误以为真的精确到了分钟，这里隐藏掉。
        if date.endswith(' 00:00'):
            date = date[: -len(' 00:00')]
        summary = _wrap(item.get('summary', '')[:120], width=38, max_lines=3)

        title_lines = title.count('\n') + 1 if title else 0
        summary_lines = summary.count('\n') + 1 if summary else 0

        card_h = TOP_PAD + BADGE_ROW_H + title_lines * TITLE_LINE_H + BOTTOM_PAD
        if summary:
            card_h += SUMMARY_GAP + summary_lines * SUMMARY_LINE_H
        prepared.append({
            "source": source,
            "title": title,
            "date": date,
            "summary": summary,
            "card_h": card_h,
        })

    gap = 0.16
    header_h = 0.68
    footer_h = 0.45
    top_margin = 0.3
    content_h = sum(p["card_h"] for p in prepared) + gap * max(n - 1, 0)
    fig_height = max(2.6, top_margin + header_h + 0.2 + content_h + footer_h)

    fig, ax = plt.subplots(figsize=(8.6, fig_height))
    ax.set_xlim(0, 8.6)
    ax.set_ylim(0, fig_height)
    ax.axis('off')
    fig.patch.set_facecolor(MUC_BG)
    ax.set_facecolor(MUC_BG)

    y = fig_height - top_margin

    # 顶部标题栏
    header = FancyBboxPatch((left, y - header_h), card_width, header_h,
                             boxstyle="round,pad=0,rounding_size=0.12",
                             facecolor=MUC_RED, edgecolor='none')
    ax.add_patch(header)
    # 左侧小圆点作为视觉锚点，替代不可靠的 emoji 渲染
    ax.add_patch(plt.Circle((left + 0.32, y - header_h / 2 + 0.06), 0.045,
                             facecolor=WHITE, edgecolor='none', alpha=0.85))
    ax.text(left + 0.55, y - header_h / 2 + 0.06, '中央民族大学 · 通知聚合',
            fontsize=13.5, fontweight='bold', ha='left', va='center', color=WHITE)
    ax.text(right - 0.3, y - header_h / 2 - 0.12, f'共 {n} 条通知',
            fontsize=8, ha='right', va='center', color='#f0d9de')
    y -= header_h + 0.22

    for idx, p in enumerate(prepared):
        card_h = p["card_h"]
        card_y = y - card_h

        # 卡片阴影（用一块略深的圆角矩形做偏移，制造轻微投影层次感）
        shadow = FancyBboxPatch((left + 0.045, card_y - 0.035), card_width, card_h,
                                 boxstyle="round,pad=0,rounding_size=0.09",
                                 facecolor=CARD_SHADOW, edgecolor='none', alpha=0.55)
        ax.add_patch(shadow)

        card = FancyBboxPatch((left, card_y), card_width, card_h,
                               boxstyle="round,pad=0,rounding_size=0.09",
                               facecolor=CARD_BG, edgecolor=CARD_BORDER, linewidth=0.8)
        ax.add_patch(card)

        # 左侧竖条
        stripe = FancyBboxPatch((left, card_y + 0.1), 0.055, card_h - 0.2,
                                 boxstyle="round,pad=0,rounding_size=0.02",
                                 facecolor=MUC_ACCENT, edgecolor='none')
        ax.add_patch(stripe)

        text_x = left + 0.28
        cursor_y = card_y + card_h - TOP_PAD

        # 来源徽标（小胶囊）+ 日期
        if p["source"]:
            label = p["source"]
            badge_w = _text_width(label) + 0.26
            badge = FancyBboxPatch((text_x, cursor_y - BADGE_ROW_H / 2 - 0.11), badge_w, 0.22,
                                    boxstyle="round,pad=0,rounding_size=0.11",
                                    facecolor='#f3dbe0', edgecolor='none')
            ax.add_patch(badge)
            ax.text(text_x + badge_w / 2, cursor_y - BADGE_ROW_H / 2, label.strip(),
                    fontsize=7, color=MUC_ACCENT, fontweight='bold',
                    ha='center', va='center')
        if p["date"]:
            ax.text(right - 0.28, cursor_y - BADGE_ROW_H / 2, p["date"],
                    fontsize=7.5, color=MUC_GRAY, ha='right', va='center')

        cursor_y -= BADGE_ROW_H

        # 标题
        if p["title"]:
            ax.text(text_x, cursor_y, p["title"],
                    fontsize=10, fontweight='bold', color=TEXT_DARK,
                    va='top', linespacing=1.4)
            title_lines = p["title"].count('\n') + 1
            cursor_y -= title_lines * TITLE_LINE_H

        # 摘要
        if p["summary"]:
            cursor_y -= SUMMARY_GAP
            ax.text(text_x, cursor_y, p["summary"],
                    fontsize=8, color=TEXT_BODY, va='top', linespacing=1.5)

        y = card_y - (gap if idx < n - 1 else 0)

    # 底部：细分隔线 + 落款
    footer_y = footer_h * 0.55
    ax.plot([left + 0.2, right - 0.2], [footer_y + 0.2, footer_y + 0.2],
            color=CARD_BORDER, linewidth=1)
    ax.text((left + right) / 2, footer_y - 0.02, 'AstrBot · MUC 通知推送',
            fontsize=7.5, color=MUC_GRAY, ha='center', va='center')

    fig.savefig(save_path, dpi=150, bbox_inches='tight',
                facecolor=MUC_BG, pad_inches=0.25)
    plt.close(fig)
    return save_path
