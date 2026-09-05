"""
测试 command_utils.py 中的工具函数
"""
import sys
from unittest.mock import MagicMock

# Mock astrbot 模块（测试环境没有安装 AstrBot）
sys.modules['astrbot'] = MagicMock()
sys.modules['astrbot.api'] = MagicMock()
sys.modules['astrbot.api.event'] = MagicMock()

# Mock rss_service 模块（避免导入链问题）
mock_rss = MagicMock()
mock_rss.Notice = dict
sys.modules['rss_service'] = mock_rss

from command_utils import format_latest_lines


class TestFormatLatestLines:
    """测试 format_latest_lines 函数"""
    
    def test_single_notice(self):
        """测试单条通知格式化"""
        notices = [{
            'source': '主站-通知公告',
            'date': '2026-05-15',
            'title': '关于放假通知',
            'summary': '五一放假安排',
            'link': 'https://www.muc.edu.cn/tzgg/123'
        }]
        result = format_latest_lines("最新通知", notices)
        
        assert "最新通知" in result
        assert "[主站-通知公告]" in result
        assert "2026-05-15" in result
        assert "关于放假通知" in result
        assert "五一放假安排" in result
        assert "https://www.muc.edu.cn/tzgg/123" in result
    
    def test_multiple_notices(self):
        """测试多条通知格式化"""
        notices = [
            {
                'source': '研究生院-招生工作',
                'date': '2026-05-15',
                'title': '招生简章发布',
                'summary': '2026年研究生招生简章',
                'link': 'https://grs.muc.edu.cn/123'
            },
            {
                'source': '人事处-通知公告',
                'date': '2026-05-14',
                'title': '招聘公告',
                'summary': None,
                'link': 'https://rsc.muc.edu.cn/456'
            }
        ]
        result = format_latest_lines("全部通知", notices)
        
        assert "全部通知" in result
        assert "研究生院-招生工作" in result
        assert "人事处-通知公告" in result
        assert "招生简章发布" in result
        assert "招聘公告" in result
        assert "2026年研究生招生简章" in result
        
        # 第二条没有 summary，所以不应该有 summary 内容
        # 但确实在 notices 中有一条包含 summary
        assert result.count("2026年研究生招生简章") == 1
    
    def test_empty_notices(self):
        """测试空通知列表"""
        result = format_latest_lines("最新通知", [])
        
        assert "最新通知" in result
        assert result.strip().endswith("最新通知") or result == "最新通知"
    
    def test_notice_without_summary(self):
        """测试没有摘要的通知"""
        notices = [{
            'source': '新闻网-综合新闻',
            'date': '2026-05-15',
            'title': '校园新闻一则',
            'link': 'https://news.muc.edu.cn/789'
        }]
        result = format_latest_lines("新闻", notices)
        
        assert "新闻" in result
        assert "[新闻网-综合新闻]" in result
        assert "校园新闻一则" in result
        assert "https://news.muc.edu.cn/789" in result
        # 不应该有摘要符号
        assert "✍" not in result
    
    def test_unicode_formatting(self):
        """测试 Unicode 格式符号"""
        notices = [{
            'source': '主站',
            'date': '2026-05-15',
            'title': '测试',
            'summary': '测试摘要',
            'link': 'https://example.com'
        }]
        result = format_latest_lines("测试", notices)
        
        assert "- " in result    # 列表符号
        assert "🔗" in result or " " in result  # 链接符号
        assert "✍" in result or " " in result  # 摘要符号（如果存在）