from collections.abc import Awaitable, Callable

from sources import SOURCES

GetKV = Callable[[str, object], Awaitable[object]]
PutKV = Callable[[str, object], Awaitable[None]]


class SubscriptionStore:
    def __init__(self, get_kv_data: GetKV, put_kv_data: PutKV):
        self._get_kv_data = get_kv_data
        self._put_kv_data = put_kv_data

    async def get_global_sessions(self) -> list[str]:
        sessions = await self._get_kv_data("muc_subscribed_sessions", [])
        if not isinstance(sessions, list):
            return []
        return [str(session) for session in sessions]

    async def save_global_sessions(self, sessions: list[str]):
        await self._put_kv_data("muc_subscribed_sessions", sessions)

    async def get_source_subscriptions(self) -> dict[str, list[str]]:
        raw_data = await self._get_kv_data("muc_source_subscriptions", {})
        if not isinstance(raw_data, dict):
            return {}

        cleaned: dict[str, list[str]] = {}
        valid_keys = {source["key"] for source in SOURCES}
        for session, keys in raw_data.items():
            if not isinstance(keys, list):
                continue
            normalized = [str(key) for key in keys if str(key) in valid_keys]
            if normalized:
                cleaned[str(session)] = sorted(set(normalized))
        return cleaned

    async def save_source_subscriptions(self, subscriptions: dict[str, list[str]]):
        await self._put_kv_data("muc_source_subscriptions", subscriptions)

    # ========== 已推送通知 ID 追踪（去重） ==========

    async def get_pushed_ids(self) -> set[str]:
        """获取所有已推送过的通知 ID"""
        ids = await self._get_kv_data("muc_pushed_ids", [])
        if not isinstance(ids, list):
            return set()
        return set(str(i) for i in ids)

    async def mark_as_pushed(self, notice_ids: list[str]):
        """标记通知为已推送，保持顺序并只保留最新的 500 个"""
        existing_list = await self._get_kv_data("muc_pushed_ids", [])
        if not isinstance(existing_list, list):
            existing_list = []
            
        seen = set(existing_list)
        for nid in notice_ids:
            if str(nid) not in seen:
                existing_list.append(str(nid))
                seen.add(str(nid))
                
        # 截断时保留列表末尾（最新加入）的元素
        await self._put_kv_data("muc_pushed_ids", existing_list[-500:])

    async def filter_new_notices(self, notice_ids: list[str]) -> list[str]:
        """返回尚未推送过的通知 ID"""
        existing = await self.get_pushed_ids()
        return [nid for nid in notice_ids if nid not in existing]
