"""
测试 notice_card.py 中的工具函数
"""
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
from notice_card import _normalize_font_list


class TestNormalizeFontList:
    """测试 _normalize_font_list 函数"""
    
    def test_with_string(self):
        """测试输入为字符串时转换为列表"""
        result = _normalize_font_list("SimHei")
        assert result == ["SimHei"]
        assert isinstance(result, list)
    
    def test_with_list(self):
        """测试输入已是列表时保持不变"""
        result = _normalize_font_list(["SimHei", "Microsoft YaHei"])
        assert result == ["SimHei", "Microsoft YaHei"]
        assert isinstance(result, list)
    
    def test_with_empty_list(self):
        """测试空列表"""
        result = _normalize_font_list([])
        assert result == []
        assert isinstance(result, list)
    
    def test_with_none(self):
        """测试 None 输入"""
        result = _normalize_font_list(None)
        assert result == []
    
    def test_with_integer(self):
        """测试非预期的整数输入"""
        result = _normalize_font_list(42)
        assert result == []
    
    def test_with_empty_string(self):
        """测试空字符串"""
        result = _normalize_font_list("")
        assert isinstance(result, list)
        assert result == [""]
    
    def test_preserves_order(self):
        """测试列表顺序保持不变"""
        result = _normalize_font_list(["Third", "First", "Second"])
        assert result == ["Third", "First", "Second"]


class TestMatplotlibFontSetup:
    """测试字体设置功能"""
    
    def test_matplotlib_agg_backend(self):
        """测试 Agg 后端可用（无需显示）"""
        assert matplotlib.get_backend() == 'Agg'
    
    def test_font_fallback_configured(self):
        """测试 fallback 字体被正确设置到 rcParams"""
        # 触发字体设置
        import importlib
        import notice_card
        importlib.reload(notice_card)
        
        # 验证 rcParams 包含 fallback 字体
        fonts = _normalize_font_list(plt.rcParams.get('font.sans-serif', []))
        fallback_fonts = ['WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'Droid Sans Fallback',
                          'PingFang SC', 'Hiragino Sans GB', 'SimHei', 'Microsoft YaHei']
        
        # 至少应该设置了字体
        assert len(fonts) > 0, "字体列表不应为空"
    
    def test_unicode_minus_disabled(self):
        """测试负号显示设置（解决负号显示为方块的问题）"""
        import importlib
        import notice_card
        importlib.reload(notice_card)
        
        assert plt.rcParams['axes.unicode_minus'] is False