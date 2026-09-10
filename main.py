import asyncio
import importlib.util
import sys
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.event.filter import PermissionType
from astrbot.api.star import Context, Star, register


def _load_local_module(module_name: str):
    module_path = Path(__file__).resolve().with_name(f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Cannot load local plugin module: {module_name}")

    sys.modules.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


for _module_name in (
    "parsers",
    "sources",
    "rss_service",
    "command_utils",
    "subscription_store",
    "auth_service",
    "notice_card",
):
    _load_local_module(_module_name)

from auth_service import MucAuthService
from command_utils import extract_command_args, format_latest_lines
from notice_card import render_notices
import tempfile

def _render_and_send(event, notices: list, title: str = ""):
    """渲染通知卡片图片并返回chain_result"""
    if not notices:
        return event.plain_result("暂未获取到通知。")
    fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="muc_notice_")
    os.close(fd)
    try:
        for n in notices:
            if "source_key" in n and "source" not in n:
                n["source"] = n["source_key"]
        render_notices(notices[:5], tmp_path)
        # 拼接链接列表
        link_lines = ["\n\U0001f517 原文链接："]
        for i, n in enumerate(notices[:5], 1):
            link_lines.append(f"{i}. {n.get('link', '无链接')}")
        return event.chain_result([
            Image.fromFileSystem(tmp_path),
            Plain("\n".join(link_lines))
        ])
    except Exception as e:
        logger.error(f"渲染通知卡片失败: {e}")
        return event.plain_result(format_latest_lines(title, notices))
from rss_service import MucRssService, Notice, CHINA_TZ
from datetime import datetime, timedelta
from sources import SourceConfig, format_source_lines, resolve_source, SOURCES
from subscription_store import SubscriptionStore

# 从环境变量读取备用
_ENV_USERNAME = __import__("os").environ.get("MUC_USERNAME", "")
_ENV_PASSWORD = __import__("os").environ.get("MUC_PASSWORD", "")



# 防止命令重复回复的标记
_HANDLED_EVENTS = set()


def _prevent_double_reply(event_id: str) -> bool:
    """如果事件已处理过则返回 True，否则标记并返回 False"""
    if event_id in _HANDLED_EVENTS:
        return True
    _HANDLED_EVENTS.add(event_id)
    if len(_HANDLED_EVENTS) > 100:
        _HANDLED_EVENTS.clear()
    return False


@register("astrbot_plugin_MUC_Notices", "Rozens", "抓取中央民族大学多站点通知并推送到订阅会话", "1.1.0")
class MucNoticePlugin(Star):
    def __init__(self, context: Context, config: Optional[dict[str, Any]] = None):
        super().__init__(context)
        self.config = config or {}
        # 环境变量覆盖
        if _ENV_USERNAME and not self.config.get("muc_username"):
            self.config["muc_username"] = _ENV_USERNAME
        if _ENV_PASSWORD and not self.config.get("muc_password"):
            self.config["muc_password"] = _ENV_PASSWORD
        self._poll_task: Optional[asyncio.Task] = None
        self._summary_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._auth_service = MucAuthService(self.config)
        self._rss_service = MucRssService(self.config, auth_service=self._auth_service)
        self._subscription_store = SubscriptionStore(self.get_kv_data, self.put_kv_data)

    async def initialize(self):
        self._stop_event.clear()
        self._poll_task = asyncio.create_task(self._polling_loop())
        if self._cfg_bool("daily_summary_enable", True):
            self._summary_task = asyncio.create_task(self._daily_summary_loop())
        logger.info("[MUC RSS] 插件初始化完成，多源轮询任务已启动。")

    async def terminate(self):
        self._stop_event.set()
        for task in (self._poll_task, self._summary_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self._auth_service.close()
        logger.info("[MUC RSS] 插件已停止。")

    # ======================== 命令组 ========================

    @filter.command_group("muc_notice")
    def muc_notice_group(self):
        pass

    @muc_notice_group.command("help")
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result(self._help_text())

    @muc_notice_group.command("sources")
    async def sources(self, event: AstrMessageEvent):
        if _prevent_double_reply(event.unified_msg_origin + "_sources"):
            return
        try:
            global_enabled = event.unified_msg_origin in await self._subscription_store.get_global_sessions()
            source_subscriptions = await self._subscription_store.get_source_subscriptions()
            subscribed_keys = set(source_subscriptions.get(event.unified_msg_origin, []))

            lines = ["可用来源 (共{}个):".format(len(SOURCES))]
            lines.extend(format_source_lines(subscribed_keys))
            if global_enabled:
                lines.append("\n当前会话已开启全局订阅，所有来源的新通知都会推送。")
            elif subscribed_keys:
                lines.append('\n当前会话仅会收到标记为"已单独订阅"的来源推送。')
            else:
                lines.append("\n当前会话尚未订阅任何来源。输入 /muc_notice subscribe 订阅全部。")
            
            result = "\n".join(lines)
            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"[MUC RSS] sources 命令异常: {e}")
            yield event.plain_result(f"查询来源失败: {e}")

    @muc_notice_group.command("subscribe")
    async def subscribe(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        sessions = await self._subscription_store.get_global_sessions()
        if umo not in sessions:
            sessions.append(umo)
            await self._subscription_store.save_global_sessions(sessions)
        yield event.plain_result("已订阅全部 MUC 来源通知推送。")

    @muc_notice_group.command("unsubscribe")
    async def unsubscribe(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        sessions = await self._subscription_store.get_global_sessions()
        if umo in sessions:
            sessions.remove(umo)
            await self._subscription_store.save_global_sessions(sessions)
            yield event.plain_result("已取消全部 MUC 来源通知推送。")
            return
        source_subscriptions = await self._subscription_store.get_source_subscriptions()
        if umo in source_subscriptions:
            del source_subscriptions[umo]
            await self._subscription_store.save_source_subscriptions(source_subscriptions)
        yield event.plain_result("已取消全部 MUC 来源通知推送。")

    @muc_notice_group.command("subscribe_source")
    async def subscribe_source(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        error = "参数错误，请使用 /muc_notice subscribe_source <来源 key|来源名>"
        source = self._resolve_source_from_event(event, "subscribe_source")
        if source is None:
            yield event.plain_result(error)
            return

        source_subscriptions = await self._subscription_store.get_source_subscriptions()
        if umo not in source_subscriptions:
            source_subscriptions[umo] = []
        if source["key"] not in source_subscriptions[umo]:
            source_subscriptions[umo].append(source["key"])
            await self._subscription_store.save_source_subscriptions(source_subscriptions)
        yield event.plain_result(f"已订阅 {source['name']} 来源通知推送。")

    @muc_notice_group.command("unsubscribe_source")
    async def unsubscribe_source(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        error = "参数错误，请使用 /muc_notice unsubscribe_source <来源 key|来源名>"
        source = self._resolve_source_from_event(event, "unsubscribe_source")
        if source is None:
            yield event.plain_result(error)
            return

        source_subscriptions = await self._subscription_store.get_source_subscriptions()
        if umo in source_subscriptions and source["key"] in source_subscriptions[umo]:
            source_subscriptions[umo].remove(source["key"])
            if not source_subscriptions[umo]:
                del source_subscriptions[umo]
            await self._subscription_store.save_source_subscriptions(source_subscriptions)
        yield event.plain_result(f"已取消订阅 {source['name']} 来源通知推送。")

    @muc_notice_group.command("check")
    async def check_now(self, event: AstrMessageEvent):
        count = await self._run_check(push=True)
        yield event.plain_result(f"已检查更新，共发现 {count} 条新通知。")

    @muc_notice_group.command("summary")
    @filter.permission_type(PermissionType.ADMIN)
    async def summary_now(self, event: AstrMessageEvent):
        """立即生成一次今日 AI 通知速览并推送。"""
        yield event.plain_result("正在生成今日通知速览…")
        try:
            text = await self._run_daily_summary(force=True)
        except Exception as exc:
            yield event.plain_result(f"生成失败：{exc}")
            return
        if text:
            yield event.plain_result(text)
        else:
            yield event.plain_result(
                f"过去 {self._cfg_int('daily_summary_lookback_hours', 24)} 小时没有新通知，或 LLM 不可用。"
            )

    @muc_notice_group.command("add_push_target")
    @filter.permission_type(PermissionType.ADMIN)
    async def add_push_target(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        push_targets = self.config.get("push_targets", [])
        if not isinstance(push_targets, list):
            push_targets = []
        if umo not in push_targets:
            push_targets.append(umo)
            self.config["push_targets"] = push_targets
            self.config.save_config()
            yield event.plain_result(f"已添加推送目标：{umo}")
        else:
            yield event.plain_result(f"当前会话已是推送目标：{umo}")

    @muc_notice_group.command("remove_push_target")
    @filter.permission_type(PermissionType.ADMIN)
    async def remove_push_target(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        push_targets = self.config.get("push_targets", [])
        if not isinstance(push_targets, list):
            push_targets = []
        if umo in push_targets:
            push_targets.remove(umo)
            self.config["push_targets"] = push_targets
            self.config.save_config()
            yield event.plain_result(f"已移除推送目标：{umo}")
        else:
            yield event.plain_result(f"当前会话不是推送目标：{umo}")

    @muc_notice_group.command("list_push_targets")
    @filter.permission_type(PermissionType.ADMIN)
    async def list_push_targets(self, event: AstrMessageEvent):
        push_targets = self.config.get("push_targets", [])
        if not isinstance(push_targets, list) or not push_targets:
            yield event.plain_result("当前没有配置的推送目标。")
            return
        lines = ["推送目标会话:"]
        for target in push_targets:
            lines.append(f"- {target}")
        yield event.plain_result("\n".join(lines))

    @muc_notice_group.command("list_platforms")
    @filter.permission_type(PermissionType.ADMIN)
    async def list_platforms(self, event: AstrMessageEvent):
        platform_ids = [p.meta().id for p in self.context.platform_manager.platform_insts]
        if not platform_ids:
            yield event.plain_result("当前没有已连接的消息平台。")
            return
        lines = ["已连接平台 ID："] + [f"- {pid}" for pid in platform_ids]
        yield event.plain_result("\n".join(lines))

    @muc_notice_group.command("add_push_group")
    @filter.permission_type(PermissionType.ADMIN)
    async def add_push_group(self, event: AstrMessageEvent):
        args = extract_command_args(event, "add_push_group")
        parts = args.split()
        if not parts:
            yield event.plain_result(
                "用法：/muc_notice add_push_group <群号> [平台ID]\n"
                "不填平台ID时，若只连接了一个平台会自动使用；"
                "连接了多个平台时请先用 /muc_notice list_platforms 查看后指定。"
            )
            return

        group_id = parts[0]
        platform_id = parts[1] if len(parts) > 1 else None
        if platform_id is None:
            platform_ids = [p.meta().id for p in self.context.platform_manager.platform_insts]
            if not platform_ids:
                yield event.plain_result("当前没有已连接的消息平台。")
                return
            if len(platform_ids) > 1:
                lines = ["检测到多个平台，请指定平台ID：", *[f"- {pid}" for pid in platform_ids]]
                yield event.plain_result("\n".join(lines))
                return
            platform_id = platform_ids[0]

        umo = f"{platform_id}:GroupMessage:{group_id}"
        push_targets = self.config.get("push_targets", [])
        if not isinstance(push_targets, list):
            push_targets = []
        if umo in push_targets:
            yield event.plain_result(f"该群已是推送目标：{umo}")
            return
        push_targets.append(umo)
        self.config["push_targets"] = push_targets
        self.config.save_config()
        yield event.plain_result(f"已添加推送目标群：{umo}")

    @muc_notice_group.command("remove_push_group")
    @filter.permission_type(PermissionType.ADMIN)
    async def remove_push_group(self, event: AstrMessageEvent):
        args = extract_command_args(event, "remove_push_group")
        parts = args.split()
        if not parts:
            yield event.plain_result("用法：/muc_notice remove_push_group <群号> [平台ID]")
            return

        group_id = parts[0]
        platform_id = parts[1] if len(parts) > 1 else None
        if platform_id is None:
            platform_ids = [p.meta().id for p in self.context.platform_manager.platform_insts]
            if len(platform_ids) != 1:
                yield event.plain_result(
                    "无法确定平台ID，请显式指定：/muc_notice remove_push_group <群号> <平台ID>"
                )
                return
            platform_id = platform_ids[0]

        umo = f"{platform_id}:GroupMessage:{group_id}"
        push_targets = self.config.get("push_targets", [])
        if not isinstance(push_targets, list):
            push_targets = []
        if umo in push_targets:
            push_targets.remove(umo)
            self.config["push_targets"] = push_targets
            self.config.save_config()
            yield event.plain_result(f"已移除推送目标群：{umo}")
        else:
            yield event.plain_result(f"该群不是推送目标：{umo}")

    @muc_notice_group.command("rss")
    async def show_rss_info(self, event: AstrMessageEvent):
        path = self._rss_service.rss_file_path
        yield event.plain_result(f"RSS 文件路径：{path}")

    @muc_notice_group.command("latest")
    async def latest(self, event: AstrMessageEvent):
        notices = await self._rss_service.fetch_notices()
        yield _render_and_send(event, notices[:5], "最近通知")

    @muc_notice_group.command("latest_source")
    async def latest_source(self, event: AstrMessageEvent):
        source = self._resolve_source_from_event(event, "latest_source")
        if source is None:
            error = "未找到来源，可先使用 /muc_notice sources 查看可用来源。"
            yield event.plain_result(error)
            return

        source_key = source.get("key")
        source_name = source.get("name", "Unknown")
        if not source_key:
            yield event.plain_result("来源配置不完整，缺少 key。")
            return

        logger.info(f"[MUC RSS] latest_source 开始抓取 source_key={source_key}")
        notices = await self._rss_service.fetch_notices(source_keys={source_key})
        if not notices:
            yield event.plain_result(f"来源 {source_name} 暂未抓取到通知。")
            return
        yield _render_and_send(event, notices[:5], f"{source_name} ({source_key})")

    # ======================== 快捷查看指令 ========================

    @muc_notice_group.command("latest_muc")
    async def latest_muc(self, event: AstrMessageEvent):
        notices = await self._rss_service.fetch_notices(source_keys={"muc_tzgg"})
        if not notices:
            yield event.plain_result("主站通知公告暂无通知。")
            return
        yield _render_and_send(event, notices[:5], "主站通知公告")

    @muc_notice_group.command("latest_graduate")
    async def latest_graduate(self, event: AstrMessageEvent):
        source_keys = {"grs_zs", "grs_py", "grs_xw", "grs_xj", "grs_yjszs"}
        notices = await self._rss_service.fetch_notices(source_keys=source_keys)
        if not notices:
            yield event.plain_result("研究生院暂无通知。")
            return
        yield _render_and_send(event, notices[:5], "研究生院")

    @muc_notice_group.command("latest_rsc")
    async def latest_rsc(self, event: AstrMessageEvent):
        notices = await self._rss_service.fetch_notices(source_keys={"rsc_tzgg"})
        if not notices:
            yield event.plain_result("人事处暂无通知。")
            return
        yield _render_and_send(event, notices[:5], "人事处")

    @muc_notice_group.command("latest_cwc")
    async def latest_cwc(self, event: AstrMessageEvent):
        notices = await self._rss_service.fetch_notices(source_keys={"cwc_tzgg"})
        if not notices:
            yield event.plain_result("财务处暂无通知。")
            return
        yield _render_and_send(event, notices[:5], "财务处")

    @muc_notice_group.command("latest_news")
    async def latest_news(self, event: AstrMessageEvent):
        source_keys = {"news_zh", "news_xs"}
        notices = await self._rss_service.fetch_notices(source_keys=source_keys)
        if not notices:
            yield event.plain_result("新闻网暂无新闻。")
            return
        yield _render_and_send(event, notices[:5], "新闻网")

    @muc_notice_group.command("latest_portal")
    async def latest_portal(self, event: AstrMessageEvent):
        source_keys = {"my_bgtz", "my_jxtz", "my_kytz", "my_xgtz"}
        notices = await self._rss_service.fetch_notices(source_keys=source_keys)
        if not notices:
            yield event.plain_result("信息门户暂无通知。需确保已配置正确的账号密码。")
            return
        yield _render_and_send(event, notices[:5], "信息门户")

    @muc_notice_group.command("login_status")
    async def login_status(self, event: AstrMessageEvent):
        if not self._auth_service.is_configured:
            msg = (
                "未配置统一身份认证账号。\n"
                "三种配置方式：\n"
                "1. WebUI 配置页填写 muc_username / muc_password\n"
                "2. 聊天发送：/muc_notice set_account <学号> <密码>\n"
                "3. 设置环境变量：MUC_USERNAME / MUC_PASSWORD"
            )
            yield event.plain_result(msg)
            return

        client = await self._auth_service.get_authenticated_client()
        if client is not None:
            msg = (
                "统一身份认证登录成功\n"
                f"账号：{self._auth_service.username}\n"
                f"Cookie 缓存：{self._auth_service.cookie_file_path}"
            )
            yield event.plain_result(msg)
        else:
            msg = (
                "统一身份认证登录失败\n"
                f"账号：{self._auth_service.username}\n"
                "请检查：\n"
                "1. 密码是否正确\n"
                "2. gmssl 库是否已安装 (pip install gmssl)\n"
                "3. 尝试 /muc_notice set_account 重新设置"
            )
            yield event.plain_result(msg)

    @muc_notice_group.command("set_account")
    @filter.permission_type(PermissionType.ADMIN)
    async def set_account(self, event: AstrMessageEvent):
        args = extract_command_args(event, "set_account")
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result("用法：/muc_notice set_account <学号> <密码>")
            return
        username, password = parts[0], parts[1]
        self.config["muc_username"] = username
        self.config["muc_password"] = password
        self.config.save_config()
        self._auth_service = MucAuthService(self.config)
        self._rss_service = MucRssService(self.config, auth_service=self._auth_service)
        yield event.plain_result(f"账号已设置为 {username}，正在尝试登录...")
        client = await self._auth_service.get_authenticated_client()
        if client:
            yield event.plain_result(f"登录成功！账号 {username} 已验证通过！")
        else:
            yield event.plain_result(f"登录失败，请检查密码。确保已安装 gmssl 库。")

    # ======================== 内部方法 ========================

    async def _polling_loop(self):
        interval_minutes = self._cfg_int("poll_interval_minutes", 5)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_minutes * 60)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await self._run_check(push=True)
            except Exception as exc:
                logger.error(f"[MUC RSS] 轮询检查失败：{exc}")

    async def _run_check(self, push: bool) -> int:
        notices = await self._rss_service.fetch_notices()
        if not notices:
            return 0

        await self._rss_service.write_rss(notices)

        if not push:
            return len(notices)

        # 过滤已推送过的通知
        new_ids = await self._subscription_store.filter_new_notices(
            [n["id"] for n in notices]
        )
        
        # 过滤器：只推送 30 天内的通知，且排除了解析失败（2000年）的条目
        now = datetime.now(CHINA_TZ)
        threshold = now - timedelta(days=30)
        
        new_notices = []
        for n in notices:
            if n["id"] in new_ids:
                pub_at = n["published_at"]
                if pub_at.year > 2000 and pub_at > threshold:
                    new_notices.append(n)

        if new_notices:
            await self._push_new_items(new_notices)
            # 无论是否通过时间过滤，都标记为已推送，避免重复检查旧条目
            await self._subscription_store.mark_as_pushed(new_ids)

        return len(new_notices)

    async def _push_new_items(self, items: list[Notice]):
        global_sessions = set(await self._subscription_store.get_global_sessions())
        source_subscriptions = await self._subscription_store.get_source_subscriptions()
        push_targets = set(self.config.get("push_targets", []))

        # 为每个 session 构建它应该收到的 items
        session_to_items: dict[str, list[Notice]] = {}

        for item in items:
            source_key = item["source_key"]
            
            # 全局订阅者和 push_targets 收到所有内容
            for session in global_sessions | push_targets:
                if session not in session_to_items:
                    session_to_items[session] = []
                session_to_items[session].append(item)
                
            # 部分订阅者只收到自己订阅的来源
            for session, subscribed_keys in source_subscriptions.items():
                if source_key in subscribed_keys and session not in global_sessions and session not in push_targets:
                    if session not in session_to_items:
                        session_to_items[session] = []
                    session_to_items[session].append(item)

        for session, session_items in session_to_items.items():
            if not session_items:
                continue
                
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix=f"muc_push_{session}_")
                os.close(fd)
                for n in session_items:
                    if "source_key" in n and "source" not in n:
                        n["source"] = n["source_key"]
                render_notices(session_items, tmp_path)
                
                await self.context.send_message(
                    session,
                    MessageChain(chain=[Image.fromFileSystem(tmp_path)])
                )
            except Exception as e:
                logger.error(f"[MUC RSS] 向会话 {session} 渲染/推送卡片失败: {e}")
                # 文本 fallback
                for item in session_items:
                    summary = item.get("summary", "")
                    parts = [
                        f"[MUC 新通知][{item['source']}]",
                        item['title'],
                    ]
                    if summary:
                        parts.append(summary)
                    parts.append(f"{item['date']} | \U0001f517 {item['link']}")
                    text = "\n".join(parts)
                    try:
                        await self.context.send_message(session, MessageChain().plain(text))
                    except Exception as exc:
                        logger.warning(f"[MUC RSS] 向会话推送文本失败 {session}: {exc}")

    def _resolve_source_from_event(
        self, event: AstrMessageEvent, command_name: str
    ) -> Optional[SourceConfig]:
        query = extract_command_args(event, command_name)
        if not query:
            return None

        source = resolve_source(query)
        if source is None:
            logger.info(
                f"[MUC RSS] 未找到匹配的来源，输入：{query}，"
                f"可用来源：{[s['key'] for s in SOURCES]}"
            )
        return source

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (ValueError, TypeError):
            return default

    def _cfg_bool(self, key: str, default: bool) -> bool:
        v = self.config.get(key, default)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    # ==================== 每日 AI 通知总结 ====================

    def _seconds_until_next_summary(self) -> float:
        hour = max(0, min(23, self._cfg_int("daily_summary_hour", 8)))
        minute = max(0, min(59, self._cfg_int("daily_summary_minute", 0)))
        now = datetime.now(CHINA_TZ)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    async def _daily_summary_loop(self):
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._seconds_until_next_summary()
                )
                break
            except asyncio.TimeoutError:
                pass
            if not self._cfg_bool("daily_summary_enable", True):
                continue
            try:
                await self._run_daily_summary()
            except Exception as exc:
                logger.error(f"[MUC RSS] 每日总结失败：{exc}")

    async def _run_daily_summary(self, force: bool = False) -> Optional[str]:
        """收集回溯窗口内的通知，交给 LLM 生成速览并推送。返回速览文本 / None。"""
        today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")
        if not force and await self.get_kv_data("last_summary_date", "") == today:
            return None

        lookback = self._cfg_int("daily_summary_lookback_hours", 24)
        notices = await self._rss_service.fetch_notices()
        cutoff = datetime.now(CHINA_TZ) - timedelta(hours=lookback)
        recent = [
            n for n in notices
            if n["published_at"].year > 2000 and n["published_at"] >= cutoff
        ]
        recent.sort(key=lambda n: n["published_at"], reverse=True)

        if not recent:
            await self.put_kv_data("last_summary_date", today)
            logger.info(f"[MUC RSS] 每日总结：过去 {lookback}h 无新通知，跳过")
            return None

        summary = await self._summarize_notices(recent, lookback)
        if summary:
            await self._push_text(summary)
            logger.info(f"[MUC RSS] 每日总结已推送（{len(recent)} 条通知）")
        await self.put_kv_data("last_summary_date", today)
        return summary

    async def _summarize_notices(self, notices: list[Notice], lookback: int) -> Optional[str]:
        provider = self.context.get_using_provider()
        if provider is None:
            logger.warning("[MUC RSS] 无可用 LLM，跳过每日总结")
            return None

        items = notices[:30]  # 防止某天通知过多把上下文撑爆
        rows = []
        for n in items:
            extra = (n.get("summary") or "").strip()
            rows.append(
                f"- [{n['source']}] {n['title']}｜发布于 {n['date']}"
                + (f"｜摘要：{extra}" if extra else "")
            )
        listing = "\n".join(rows)

        system_prompt = (
            "你是中央民族大学的通知助理。用户给你一份过去一段时间学校各部门发布的通知清单，"
            "你要汇总成一条「今日通知速览」，直接发到学生群里。要求：\n"
            "1. 开头用一句话总括今天主要有哪几类事。\n"
            "2. 然后按重要程度分点（最多 8 点），每点一行，一句话说清这条通知是什么、面向谁。\n"
            "3. 【严格】只能写清单里真实出现的通知，一条都不能多加、不能合并杜撰。\n"
            "4. 【严格】清单里的日期是『发布日期』，不是截止/报名/考试日期。除非某条的标题或摘要里"
            "明确写了具体的截止时间 / 报名时间 / 考试时间 / 地点，否则不要提任何时间和地点，"
            "更不能把发布日期当成截止日期。\n"
            "5. 涉及报名、缴费、补考、四六级、放假、班车调整这类和学生切身相关的，排前面。\n"
            "6. 全文 400 字以内，不要客套话、不要逐条照抄完整标题。\n"
            "7. 拿不准的条目宁可不写，不要为了凑数硬编。"
        )
        prompt = (
            f"以下是过去 {lookback} 小时中央民族大学发布的通知，共 {len(items)} 条"
            f"（按发布时间倒序）：\n\n{listing}"
        )
        try:
            resp = await provider.text_chat(prompt=prompt, system_prompt=system_prompt)
            text = (getattr(resp, "completion_text", "") or "").strip()
        except Exception as exc:
            logger.error(f"[MUC RSS] LLM 总结请求失败：{exc}")
            return None
        if not text:
            return None
        header = f"📮 民大今日通知速览 · {datetime.now(CHINA_TZ).strftime('%m月%d日')}\n\n"
        footer = f"\n\n— AI 依据学校官网自动汇总，共 {len(items)} 条，可能有遗漏，以官方通知原文为准"
        return header + text + footer

    async def _push_text(self, text: str):
        global_sessions = set(await self._subscription_store.get_global_sessions())
        push_targets = set(self.config.get("push_targets", []))
        for session in global_sessions | push_targets:
            try:
                await self.context.send_message(session, MessageChain().plain(text))
            except Exception as exc:
                logger.warning(f"[MUC RSS] 每日总结推送失败 {session}: {exc}")

    def _help_text(self) -> str:
        auth_count = sum(1 for s in SOURCES if s.get("requires_auth", False))
        lines = [
            "中央民族大学 MUC RSS 插件使用说明",
            "",
            "用户指令:",
            "- /muc_notice help: 查看本帮助",
            "- /muc_notice sources: 查看支持的来源",
            "- /muc_notice subscribe: 订阅全部来源",
            "- /muc_notice unsubscribe: 取消订阅全部来源",
            "- /muc_notice subscribe_source <来源 key|来源名>: 订阅单个来源",
            "- /muc_notice unsubscribe_source <来源 key|来源名>: 取消订阅单个来源",
            "- /muc_notice check: 立即检查更新",
            "- /muc_notice latest: 查看最近 5 条聚合通知",
            "- /muc_notice latest_source <来源 key|来源名>: 查看单个来源最近 5 条通知",
            "- /muc_notice latest_muc: 查看主站通知公告最近 5 条通知",
            "- /muc_notice latest_graduate: 查看研究生院最近 5 条通知",
            "- /muc_notice latest_rsc: 查看人事处最近 5 条通知",
            "- /muc_notice latest_cwc: 查看财务处最近 5 条通知",
            "- /muc_notice latest_news: 查看新闻网最近 5 条新闻",
            "- /muc_notice latest_portal: 查看信息门户最近 5 条通知(需登录)",
            "- /muc_notice login_status: 查看统一身份认证登录状态",
            "- /muc_notice set_account <学号> <密码>: 在聊天中设置账号密码(管理员)",
            "- /muc_notice rss: 查看 RSS 文件路径",
            "",
            "管理员指令:",
            "- /muc_notice summary: 立即生成一次今日 AI 通知速览并推送",
            "- /muc_notice add_push_target: 添加当前会话为推送目标",
            "- /muc_notice remove_push_target: 移除当前会话的推送目标",
            "- /muc_notice list_push_targets: 列出所有推送目标",
            "- /muc_notice list_platforms: 列出已连接的平台ID",
            "- /muc_notice add_push_group <群号> [平台ID]: 免入群直接添加指定群为推送目标",
            "- /muc_notice remove_push_group <群号> [平台ID]: 免入群移除指定群的推送目标",
            "",
            "配置项:",
            "- rss_title: RSS 标题",
            "- rss_max_items: RSS 最大条目数",
            "- poll_interval_minutes: 轮询间隔（分钟，默认 240）",
            "- daily_summary_enable / daily_summary_hour / daily_summary_minute / daily_summary_lookback_hours: 每日 AI 通知速览",
            "- request_timeout_seconds: 请求超时（秒）",
            "- muc_username / muc_password: 统一身份认证账号",
            "- push_targets: 推送目标会话列表",
            "",
            "认证说明:",
            "  密码使用 SM2 国密加密传输，Cookie 持久化缓存。",
            "  需安装 gmssl(Python) 或 sm-crypto(Node.js) 以启用加密。",
            f"  当前共 {len(SOURCES)} 个来源（含 {auth_count} 个需登录来源）。",
        ]
        return "\n".join(lines)
