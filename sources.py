import re
from collections.abc import Callable
from typing import Optional, TypedDict

from bs4 import Tag

from parsers import parse_text_content, parse_title_attr, parse_selector_generic

Parser = Callable[[Tag], str]


class SourceConfig(TypedDict, total=False):
    key: str
    name: str
    url: str
    selector: str
    parser: Parser
    category: str
    base_url: str
    requires_auth: bool
    api_params: dict  # API 来源的请求参数  # 是否需要统一身份认证登录


SOURCES: list[SourceConfig] = [
    # ========== 主站通知公告（采购招标+公示） ==========
    {
        "key": "muc_tzgg",
        "name": "中央民族大学 - 通知公告",
        "url": "https://www.muc.edu.cn/tzgg.htm",
        "selector": ".list_box2 li a[title]",
        "parser": parse_title_attr,
        "category": "muc",
        "base_url": "https://www.muc.edu.cn/",
    },
    # ========== 研究生院 - 招生工作 ==========
    {
        "key": "grs_zs",
        "name": "研究生院 - 招生工作",
        "url": "https://grs.muc.edu.cn/",
        "selector": 'a[href*="info/1178/"]',
        "parser": parse_selector_generic,
        "category": "graduate",
        "base_url": "https://grs.muc.edu.cn/",
    },
    # ========== 研究生院 - 培养工作 ==========
    {
        "key": "grs_py",
        "name": "研究生院 - 培养工作",
        "url": "https://grs.muc.edu.cn/pygz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
        "base_url": "https://grs.muc.edu.cn/",
    },
    # ========== 研究生院 - 学位工作 ==========
    {
        "key": "grs_xw",
        "name": "研究生院 - 学位工作",
        "url": "https://grs.muc.edu.cn/xwgz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
        "base_url": "https://grs.muc.edu.cn/",
    },
    # ========== 研究生院 - 学籍学生工作 ==========
    {
        "key": "grs_xj",
        "name": "研究生院 - 学籍学生工作",
        "url": "https://grs.muc.edu.cn/xj_xs_gz.htm",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
        "base_url": "https://grs.muc.edu.cn/",
    },
    # ========== 研究生招生网 ==========
    {
        "key": "grs_yjszs",
        "name": "研究生院 - 研究生招生网",
        "url": "https://grs.muc.edu.cn/yjsyzsw/",
        "selector": "a[href*='info/']",
        "parser": parse_text_content,
        "category": "graduate",
        "base_url": "https://grs.muc.edu.cn/",
    },
    # ========== 人事处 - 通知公告 ==========
    {
        "key": "rsc_tzgg",
        "name": "人事处 - 通知公告",
        "url": "https://rsc.muc.edu.cn/",
        "selector": 'a[href*="info/"][title]',
        "parser": parse_title_attr,
        "category": "rsc",
        "base_url": "https://rsc.muc.edu.cn/",
    },
    # ========== 财务处 - 通知公告 ==========
    {
        "key": "cwc_tzgg",
        "name": "财务处 - 通知公告",
        "url": "https://cwc.muc.edu.cn/",
        "selector": 'a[href*="info/"]',
        "parser": parse_selector_generic,
        "category": "cwc",
        "base_url": "https://cwc.muc.edu.cn/",
    },
    # ========== 新闻网 - 综合新闻 ==========
    {
        "key": "news_zh",
        "name": "新闻网 - 综合新闻",
        "url": "https://news.muc.edu.cn/",
        "selector": "a.eclip, a.a, a.ablink",
        "parser": parse_title_attr,
        "category": "news",
        "base_url": "https://news.muc.edu.cn/",
    },
    # ========== 新闻网 - 学术 ==========
    {
        "key": "news_xs",
        "name": "新闻网 - 学术动态",
        "url": "https://news.muc.edu.cn/",
        "selector": "a.zi3",
        "parser": parse_title_attr,
        "category": "news",
        "base_url": "https://news.muc.edu.cn/",
    },
    # ========== 信息门户 - 需登录（API）==========
    {
        "key": "my_bgtz",
        "name": "信息门户 - 办公通知",
        "url": "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
        "selector": 'api:type=5',
        "parser": parse_selector_generic,
        "category": "portal",
        "base_url": "https://my.muc.edu.cn/",
        "requires_auth": True,
        "api_params": {"currentPage": 1, "pageSize": 10, "type": 5},
    },
    {
        "key": "my_jxtz",
        "name": "信息门户 - 教学通知",
        "url": "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
        "selector": 'api:type=6',
        "parser": parse_selector_generic,
        "category": "portal",
        "base_url": "https://my.muc.edu.cn/",
        "requires_auth": True,
        "api_params": {"currentPage": 1, "pageSize": 10, "type": 6},
    },
    {
        "key": "my_kytz",
        "name": "信息门户 - 科研通知",
        "url": "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
        "selector": 'api:type=8',
        "parser": parse_selector_generic,
        "category": "portal",
        "base_url": "https://my.muc.edu.cn/",
        "requires_auth": True,
        "api_params": {"currentPage": 1, "pageSize": 10, "type": 8},
    },
]

SOURCES_BY_KEY = {source["key"]: source for source in SOURCES if "key" in source}


def resolve_source(query: str) -> Optional[SourceConfig]:
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return None

    exact = SOURCES_BY_KEY.get(query.strip())
    if exact is not None:
        return exact

    matches = [
        source
        for source in SOURCES
        if normalized_query in {
            _normalize_query(source.get("key", "")),
            _normalize_query(source.get("name", "")),
        }
        or normalized_query in _normalize_query(source.get("key", ""))
        or normalized_query in _normalize_query(source.get("name", ""))
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def format_source_lines(subscribed_keys: Optional[set[str]] = None) -> list[str]:
    subscribed_keys = subscribed_keys or set()
    lines: list[str] = []
    for source in SOURCES:
        status = " [已单独订阅]" if source["key"] in subscribed_keys else ""
        lines.append(f"- {source['key']}: {source['name']}{status}")
    return lines


def _normalize_query(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", text).casefold()
