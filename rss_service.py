import asyncio
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, TypedDict, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from astrbot.api import logger

from sources import SOURCES, SourceConfig

CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})\s*(?:年|[-/.])\s*(?P<month>\d{1,2})\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
)


class Notice(TypedDict):
    id: str
    title: str
    link: str
    source: str
    source_key: str
    category: str
    date: str
    pub_date: str
    published_at: datetime
    summary: str  # 内容摘要/预览


class MucRssService:
    def __init__(self, config: Optional[dict[str, Any]] = None, auth_service=None):
        self.config = config or {}
        self._auth_service = auth_service  # MucAuthService 实例

    async def fetch_notices(self, source_keys: Optional[set[str]] = None) -> list[Notice]:
        timeout_sec = self._cfg_int("request_timeout_seconds", 20)
        max_items = self._cfg_int("rss_max_items", 50)
        selected_sources = [
            source for source in SOURCES if source_keys is None or source["key"] in source_keys
        ]
        if source_keys is not None and not selected_sources:
            logger.info(f"[MUC RSS] 未找到匹配来源 source_keys={sorted(source_keys)}")

        # 分离需要认证和不需要认证的来源
        public_sources = [s for s in selected_sources if not s.get("requires_auth", False)]
        auth_sources = [s for s in selected_sources if s.get("requires_auth", False)]

        # 获取认证客户端（如果有需要认证的来源）
        auth_client = None
        if auth_sources and self._auth_service:
            auth_client = await self._auth_service.get_authenticated_client()
            if auth_client is None:
                logger.warning(
                    f"[MUC RSS] {len(auth_sources)} 个需认证来源跳过（未配置账号或登录失败）"
                )
                auth_sources = []
            else:
                logger.info(
                    f"[MUC RSS] 认证客户端就绪，将抓取 {len(auth_sources)} 个门户来源"
                )

        # 并发抓取所有来源
        async def _fetch_all():
            async with httpx.AsyncClient(
                timeout=timeout_sec,
                follow_redirects=True,
                headers=DEFAULT_HEADERS,
            ) as client:
                # 公开来源用新 client 并发
                pub_tasks = [
                    self._fetch_source_notices(client, source)
                    for source in public_sources
                ]
                pub_results = await asyncio.gather(*pub_tasks, return_exceptions=True)
                
            # 认证来源各自独立client请求
            auth_results = []
            if auth_client and auth_sources:
                for source in auth_sources:
                    try:
                        async with httpx.AsyncClient(
                            timeout=timeout_sec,
                            follow_redirects=True,
                        ) as ac:
                            # 复制cookies到新client
                            if hasattr(auth_client, 'cookies'):
                                ac.cookies = auth_client.cookies
                            result = await self._fetch_source_notices(ac, source)
                            auth_results.append(result)
                    except Exception as e:
                        auth_results.append(e)
            
            return pub_results + auth_results

        results = await _fetch_all()
        all_selected = public_sources + auth_sources

        notices: list[Notice] = []
        for source, result in zip(all_selected, results):
            if isinstance(result, Exception):
                logger.info(f"[MUC RSS] 抓取来源失败 {source['key']} {source['url']}: {result}")
                continue
            notices.extend(result)

        deduped: dict[str, Notice] = {}
        for item in notices:
            deduped[item["link"]] = item

        ordered = sorted(
            deduped.values(),
            key=lambda item: (item["published_at"], item["source"]),
            reverse=True,
        )
        return ordered[:max_items]

    async def write_rss(self, notices: list[Notice]):
        now_str = datetime.now(CHINA_TZ).strftime("%a, %d %b %Y %H:%M:%S +0800")

        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = self._cfg_str("rss_title", "中央民族大学多站点通知聚合")
        ET.SubElement(channel, "link").text = "https://www.muc.edu.cn/tzgg.htm"
        ET.SubElement(channel, "description").text = "中央民族大学多来源通知聚合"
        ET.SubElement(channel, "lastBuildDate").text = now_str

        for notice in notices:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = f"[{notice['source']}] {notice['title']}"
            ET.SubElement(item, "link").text = notice["link"]
            ET.SubElement(item, "guid").text = notice["id"]
            ET.SubElement(item, "pubDate").text = notice["pub_date"]
            ET.SubElement(item, "description").text = (
                f"来源：{notice['source']} | 分类：{notice['category']} | 日期：{notice['date']}"
            )

        xml_data = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
        path = self.rss_file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(xml_data)

        logger.info(f"[MUC RSS] RSS 文件已更新 {path} items={len(notices)}")

    @property
    def rss_file_path(self) -> Path:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            base = get_astrbot_data_path() / "plugin_data" / "astrbot_plugin_MUC_Notices"
        except Exception:
            base = Path("data") / "plugin_data" / "astrbot_plugin_MUC_Notices"
        return base / "muc_notice_rss.xml"

    async def _fetch_source_notices(
        self, client: Optional[httpx.AsyncClient], source: SourceConfig
    ) -> list[Notice]:
        # 判断是否为 API 源
        selector = source.get("selector", "")
        if selector.startswith("api:"):
            return await self._fetch_api_source_notices(client, source)

        # 常规 HTML 抓取
        if client is None:
            return []
        page_urls = [source["url"], *source.get("extra_urls", [])]
        notices: list[Notice] = []
        seen_links: set[str] = set()

        for page_url in page_urls:
            response = await client.get(page_url, headers=self._request_headers(source, page_url))
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            tags = soup.select(source["selector"])
            if not tags:
                logger.info(
                    f"[MUC RSS] 选择器未命中 {source['key']} {page_url} selector={source['selector']}"
                )
                continue

            for tag in tags:
                if not isinstance(tag, Tag):
                    continue

                href = (tag.get("href") or "").strip()
                if not href:
                    continue

                title = source["parser"](tag).strip()
                if not title:
                    continue

                base_url = source.get("base_url") or page_url
                full_url = urljoin(base_url, href)
                if full_url in seen_links:
                    continue

                published_at = self._extract_published_at(tag, source)
                notices.append(
                    {
                        "id": self._make_notice_id(source["key"], full_url),
                        "title": title,
                        "link": full_url,
                        "source": source["name"],
                        "source_key": source["key"],
                        "category": source["category"],
                        "date": published_at.strftime("%Y-%m-%d %H:%M"),
                        "pub_date": published_at.strftime("%a, %d %b %Y %H:%M:%S +0800"),
                        "published_at": published_at,
                        "summary": "",
                    }
                )
                seen_links.add(full_url)

        if not notices:
            logger.info(f"[MUC RSS] 来源无有效条目 {source['key']} urls={page_urls}")
        return notices

    async def _fetch_api_source_notices(
        self, client: Optional[httpx.AsyncClient], source: SourceConfig
    ) -> list[Notice]:
        """通过门户 API 获取通知"""
        if client is None:
            logger.info(f"[MUC RSS] API 来源 {source['key']} 无认证客户端")
            return []

        api_params = source.get("api_params", {})
        ajax_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://my.muc.edu.cn",
            "Referer": "https://my.muc.edu.cn/page/11",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        try:
            response = await client.post(source["url"], data=api_params, headers=ajax_headers)
            response.raise_for_status()
            data = response.json()
            tables = data.get("datas", {}).get("tables", [])
            if not tables:
                return []

            notices: list[Notice] = []
            for item in tables:
                title = item.get("notice_title", "").strip()
                if not title:
                    continue
                notice_id = str(item.get("notice_id", ""))
                notice_type = source.get("api_params", {}).get("type", 5)
                link = f"https://my.muc.edu.cn/page/11#/print?type={notice_type}&notice_id={notice_id}&show_type=1"
                published_at = datetime.now(CHINA_TZ)
                time_val = item.get("notice_release_time")
                if time_val:
                    try:
                        if isinstance(time_val, (int, float)) or (isinstance(time_val, str) and time_val.isdigit()):
                            ts = float(time_val)
                            if ts > 1e11:  # 毫秒级时间戳
                                ts /= 1000.0
                            published_at = datetime.fromtimestamp(ts, tz=CHINA_TZ)
                        elif isinstance(time_val, str):
                            clean_time = time_val.split(".")[0].strip()
                            if len(clean_time) >= 19 and "-" in clean_time:
                                published_at = datetime.strptime(clean_time[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CHINA_TZ)
                            elif len(clean_time) >= 16 and "-" in clean_time:
                                published_at = datetime.strptime(clean_time[:16], "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ)
                            elif len(clean_time) >= 10 and "-" in clean_time:
                                published_at = datetime.strptime(clean_time[:10], "%Y-%m-%d").replace(tzinfo=CHINA_TZ)
                            else:
                                parsed = self._parse_date(time_val)
                                if parsed:
                                    published_at = parsed
                    except Exception:
                        pass
                # 提取纯文本摘要（去掉HTML标签）
                raw_content = item.get("notice_content", "")
                summary_text = ""
                if raw_content:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(raw_content, "html.parser")
                        plain = soup.get_text(separator=" ", strip=True)
                        # 取前 500 个字符作为摘要预览
                        summary_text = plain[:80] + ("..." if len(plain) > 80 else "")
                    except Exception:
                        pass

                notices.append({
                    "id": self._make_notice_id(source["key"], notice_id),
                    "title": title,
                    "link": link,
                    "source": source["name"],
                    "source_key": source["key"],
                    "category": source["category"],
                    "date": published_at.strftime("%Y-%m-%d %H:%M"),
                    "pub_date": published_at.strftime("%a, %d %b %Y %H:%M:%S +0800"),
                    "published_at": published_at,
                    "summary": summary_text,
                })
            return notices
        except Exception as exc:
            logger.info(f"[MUC RSS] API 来源 {source['key']} 失败: {exc}")
            return []

    def _extract_published_at(self, tag: Tag, source: SourceConfig) -> datetime:
        candidates = [
            tag.get_text(" ", strip=True),
            *self._iter_ancestor_texts(tag, depth=3),
            self._collect_sibling_text(tag),
        ]

        for text in candidates:
            extracted = self._parse_date(text)
            if extracted is not None:
                return extracted

        return datetime.now(CHINA_TZ)

    def _iter_ancestor_texts(self, tag: Tag, depth: int) -> Iterable[str]:
        current = tag.parent
        steps = 0
        while isinstance(current, Tag) and steps < depth:
            text = current.get_text(" ", strip=True)
            if text:
                yield text
            current = current.parent
            steps += 1

    def _collect_sibling_text(self, tag: Tag) -> str:
        texts: list[str] = []
        for sibling in list(tag.previous_siblings)[:2]:
            text = self._node_text(sibling)
            if text:
                texts.append(text)
        for sibling in list(tag.next_siblings)[:2]:
            text = self._node_text(sibling)
            if text:
                texts.append(text)
        return " ".join(texts)

    def _node_text(self, node: object) -> str:
        if isinstance(node, Tag):
            return node.get_text(" ", strip=True)
        return str(node).strip()

    def _parse_date(self, text: str) -> Optional[datetime]:
        if not text:
            return None

        match = DATE_PATTERN.search(text)
        if not match:
            return None

        try:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            return datetime(year, month, day, tzinfo=CHINA_TZ)
        except ValueError:
            return None

    def _make_notice_id(self, source_key: str, link: str) -> str:
        digest = sha1(f"{source_key}|{link}".encode("utf-8")).hexdigest()
        return f"{source_key}:{digest}"

    def _request_headers(self, source: SourceConfig, request_url: Optional[str] = None) -> dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = source.get("base_url") or request_url or source["url"]
        return headers

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default

    def _cfg_str(self, key: str, default: str) -> str:
        value = self.config.get(key, default)
        return str(value) if value is not None else default
