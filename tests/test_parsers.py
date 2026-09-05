"""
测试 parsers.py 中的 HTML 解析函数
"""
from bs4 import BeautifulSoup
import parsers


class TestParseTitleAttr:
    """测试 parse_title_attr 函数"""
    
    def test_with_title_attribute(self):
        """测试标签有 title 属性时返回 title"""
        html = '<a href="#" title="测试标题">链接文本</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_attr(tag)
        assert result == "测试标题"
    
    def test_without_title_attribute(self):
        """测试标签没有 title 属性时返回文本内容"""
        html = '<a href="#">链接文本</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_attr(tag)
        assert result == "链接文本"
    
    def test_with_empty_title(self):
        """测试 title 属性为空时返回文本内容"""
        html = '<a href="#" title="">链接文本</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_attr(tag)
        assert result == "链接文本"
    
    def test_with_whitespace(self):
        """测试返回结果去除首尾空格"""
        html = '<a href="#" title="  测试标题  ">链接</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_attr(tag)
        assert result == "测试标题"


class TestParseTextContent:
    """测试 parse_text_content 函数"""
    
    def test_simple_text(self):
        """测试简单文本提取"""
        html = '<p>这是一段文本</p>'
        tag = BeautifulSoup(html, 'html.parser').p
        result = parsers.parse_text_content(tag)
        assert result == "这是一段文本"
    
    def test_nested_tags(self):
        """测试嵌套标签的文本提取"""
        html = '<div><p>段落1</p><p>段落2</p></div>'
        tag = BeautifulSoup(html, 'html.parser').div
        result = parsers.parse_text_content(tag)
        assert "段落1" in result
        assert "段落2" in result


class TestParseTitleWithKeyword:
    """测试 parse_title_with_keyword 函数"""
    
    def test_title_contains_keyword(self):
        """测试标题包含关键词时返回标题"""
        html = '<a href="#" title="关于发布通知的声明">链接</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_with_keyword(tag, "通知")
        assert result == "关于发布通知的声明"
    
    def test_title_not_contains_keyword(self):
        """测试标题不包含关键词时返回空字符串"""
        html = '<a href="#" title="新闻动态">链接</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_with_keyword(tag, "通知")
        assert result == ""
    
    def test_custom_keyword(self):
        """测试自定义关键词"""
        html = '<a href="#" title="学术讲座预告">链接</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_with_keyword(tag, "讲座")
        assert result == "学术讲座预告"
    
    def test_use_text_when_no_title(self):
        """测试没有 title 属性时使用文本内容"""
        html = '<a href="#">关于通知的说明</a>'
        tag = BeautifulSoup(html, 'html.parser').a
        result = parsers.parse_title_with_keyword(tag, "通知")
        assert result == "关于通知的说明"


class TestFilterTitleByKeyword:
    """测试 filter_title_by_keyword 函数"""
    
    def test_contains_keyword(self):
        """测试字符串包含关键词"""
        result = parsers.filter_title_by_keyword("关于发布通知的声明", "通知")
        assert result == "关于发布通知的声明"
    
    def test_not_contains_keyword(self):
        """测试字符串不包含关键词"""
        result = parsers.filter_title_by_keyword("新闻动态", "通知")
        assert result == ""
    
    def test_strips_whitespace(self):
        """测试去除首尾空格"""
        result = parsers.filter_title_by_keyword("  关于通知的声明  ", "通知")
        assert result == "关于通知的声明"
    
    def test_custom_keyword(self):
        """测试自定义关键词"""
        result = parsers.filter_title_by_keyword("学术讲座预告", "讲座")
        assert result == "学术讲座预告"


class TestParseSelectorGeneric:
    """测试 parse_selector_generic 函数"""
    
    def test_with_title_attribute(self):
        """测试有 title 属性"""
        html = '<div title="通用解析">内容</div>'
        tag = BeautifulSoup(html, 'html.parser').div
        result = parsers.parse_selector_generic(tag)
        assert result == "通用解析"
    
    def test_without_title_attribute(self):
        """测试没有 title 属性"""
        html = '<div>通用解析内容</div>'
        tag = BeautifulSoup(html, 'html.parser').div
        result = parsers.parse_selector_generic(tag)
        assert result == "通用解析内容"
