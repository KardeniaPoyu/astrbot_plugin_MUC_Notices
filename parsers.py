from bs4 import Tag


def parse_title_attr(tag: Tag) -> str:
    return (
        str(tag.get("title")) if tag.get("title") else tag.get_text(" ", strip=True)
    ).strip()


def parse_text_content(tag: Tag) -> str:
    return tag.get_text(" ", strip=True)


def parse_title_with_keyword(tag: Tag, keyword: str = "通知") -> str:
    """解析标题，仅当标题包含指定关键词时返回标题，否则返回空字符串"""
    title = (
        str(tag.get("title")) if tag.get("title") else tag.get_text(" ", strip=True)
    ).strip()
    if keyword in title:
        return title
    return ""


def filter_title_by_keyword(title: str, keyword: str = "通知") -> str:
    """根据关键词过滤字符串标题，用于非 HTML 源（如 JSON API）"""
    title = title.strip()
    if keyword in title:
        return title
    return ""


def parse_selector_generic(tag: Tag) -> str:
    """通用解析：优先取 title 属性，否则取纯文本"""
    return (
        str(tag.get("title")) if tag.get("title") else tag.get_text(" ", strip=True)
    ).strip()
