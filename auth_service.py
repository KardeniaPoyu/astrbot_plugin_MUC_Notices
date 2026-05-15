"""
中央民族大学统一身份认证服务
支持 SM2 国密加密的模拟登录 + Cookie 持久化
"""
import asyncio
import json
import re
import base64
from pathlib import Path
from typing import Any, Optional

import httpx

from astrbot.api import logger

MUC_SM2_PUBLIC_KEY = (
    "BMgXvoCLbC9cF8JAS/bv6Gd82+K+fFC2nRi7QJO3GvDkx0iLBmqDMpQUBxjC3yTfXN83cPVZRplPDsvr92K4omA="
)
LOGIN_PAGE_URL = "https://ca.muc.edu.cn/zfca/login"
PORTAL_SERVICE = "http://my.muc.edu.cn/user/simpleSSOLogin"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
AJAX_HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://my.muc.edu.cn",
    "Referer": "https://my.muc.edu.cn/page/11",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


class MucAuthService:
    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self._client: Optional[httpx.AsyncClient] = None
        self._cookies_loaded = False
        self._login_success = False

    @property
    def username(self) -> str:
        return str(self.config.get("muc_username", "")).strip()

    @property
    def password(self) -> str:
        return str(self.config.get("muc_password", "")).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    @property
    def cookie_file_path(self) -> Path:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            base = get_astrbot_data_path() / "plugin_data" / "astrbot_plugin_MUC_Notices"
        except Exception:
            base = Path("data") / "plugin_data" / "astrbot_plugin_MUC_Notices"
        return base / "muc_cookies.json"

    async def ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=self._cfg_int("request_timeout_seconds", 20),
            )
        return self._client

    async def get_authenticated_client(self) -> Optional[httpx.AsyncClient]:
        client = await self.ensure_client()

        if not self.is_configured:
            return None

        # 已有成功的登录态，直接返回
        if self._login_success:
            return client

        # 尝试加载缓存的 Cookie
        if not self._cookies_loaded:
            loaded = await self._load_cookies()
            if loaded:
                ok = await self._verify_login(client)
                if ok:
                    logger.info("[MUC AUTH] 缓存 Cookie 有效，直接复用。")
                    self._login_success = True
                    self._cookies_loaded = True
                    return client
                else:
                    logger.info("[MUC AUTH] 缓存 Cookie 已过期，重新登录。")
            self._cookies_loaded = True

        # 执行登录
        success = await self._do_login(client)
        if success:
            await self._save_cookies(client)
            self._login_success = True
            return client

        logger.warning("[MUC AUTH] 登录失败，请检查用户名密码配置。")
        return None

    async def _do_login(self, client: httpx.AsyncClient) -> bool:
        try:
            login_url = f"{LOGIN_PAGE_URL}?service={httpx.URL(PORTAL_SERVICE)}"
            resp = await client.get(login_url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            resp.raise_for_status()

            # 提取 flowId
            html = resp.text
            m = re.search(r'name="flowId"\s+value="([^"]+)"', html)
            if not m:
                logger.error("[MUC AUTH] 未找到 flowId")
                return False
            flow_id = m.group(1)

            # SM2 加密密码
            encrypted_password = await self._sm2_encrypt(self.password)

            # 提交登录
            resp = await client.post(
                login_url,
                data={
                    "username": self.username,
                    "password": encrypted_password,
                    "loginType": "username_password",
                    "flowId": flow_id,
                    "captcha": "", "delegator": "", "tokenCode": "",
                    "continue": "", "asserts": "", "submit": "登录",
                },
                headers={
                    "Referer": login_url,
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            # 跟随重定向链
            ru = resp.headers.get("Location", "")
            max_redirects = 10
            while ru and max_redirects > 0:
                if ru.startswith("/"):
                    ru = f"{resp.url.scheme}://{resp.url.netloc}{ru}"
                resp = await client.get(ru, follow_redirects=False)
                ru = resp.headers.get("Location", "")
                max_redirects -= 1

            if "my.muc.edu.cn" in str(resp.url) and resp.status_code == 200:
                logger.info("[MUC AUTH] 登录成功！")
                return True

            logger.warning(f"[MUC AUTH] 登录异常，最终URL={resp.url}, 状态码={resp.status_code}")
            return False

        except Exception as exc:
            logger.error(f"[MUC AUTH] 登录异常：{exc}")
            return False

    async def _sm2_encrypt(self, plaintext: str) -> str:
        try:
            from gmssl.sm2 import CryptSM2
            pubkey_bytes = base64.b64decode(MUC_SM2_PUBLIC_KEY)
            if len(pubkey_bytes) == 65 and pubkey_bytes[0] == 0x04:
                x_hex = pubkey_bytes[1:33].hex()
                y_hex = pubkey_bytes[33:65].hex()
                sm2 = CryptSM2("placeholder", x_hex + y_hex, mode=1)
                encrypted = sm2.encrypt(plaintext.encode("utf-8"))
                result = base64.b64encode(encrypted).decode("ascii")
                logger.info("[MUC AUTH] SM2 加密成功。")
                return result
        except ImportError:
            logger.warning("[MUC AUTH] gmssl 未安装，使用原始密码（可能失败）。")
        except Exception as exc:
            logger.warning(f"[MUC AUTH] SM2 加密失败: {exc}，使用原始密码。")
        return plaintext

    async def _verify_login(self, client: httpx.AsyncClient) -> bool:
        """验证当前登录态是否有效（通过调用 API 而非访问首页）"""
        try:
            # 直接调用一个轻量 API 来验证 Cookie 是否有效
            resp = await client.post(
                "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
                data={"currentPage": 1, "pageSize": 1, "type": 5},
                headers=AJAX_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("state") is not False:  # state=false 表示失败
                    return True
            return False
        except Exception:
            return False

    async def _save_cookies(self, client: httpx.AsyncClient):
        """持久化保存 Cookie"""
        try:
            cookies_data = []
            for cookie in client.cookies.jar:
                cookies_data.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path or "/",
                })

            if not cookies_data:
                logger.warning("[MUC AUTH] 无 Cookie 可保存")
                return

            self.cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.cookie_file_path.write_text(
                json.dumps(cookies_data, ensure_ascii=False),
                encoding="utf-8"
            )
            # 设置文件权限为仅所有者可读写 (0o600)，防止其他用户读取敏感Cookie
            try:
                import stat
                self.cookie_file_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except Exception as perm_exc:
                logger.warning(f"[MUC AUTH] 设置Cookie文件权限失败: {perm_exc}")
            logger.info(f"[MUC AUTH] {len(cookies_data)} 个 Cookie 已保存")
        except Exception as exc:
            logger.warning(f"[MUC AUTH] 保存 Cookie 失败: {exc}")

    async def _load_cookies(self) -> bool:
        """从文件加载持久化的 Cookie"""
        if not self.cookie_file_path.exists():
            return False

        try:
            cookies_data = json.loads(
                self.cookie_file_path.read_text(encoding="utf-8")
            )
            client = await self.ensure_client()
            for c in cookies_data:
                client.cookies.set(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
            logger.info(f"[MUC AUTH] 从文件加载了 {len(cookies_data)} 个 Cookie")
            return bool(cookies_data)
        except Exception as exc:
            logger.warning(f"[MUC AUTH] 加载 Cookie 失败: {exc}")
            return False

    async def fetch_portal_notices(self, type_id: int = 5) -> list[dict]:
        """通过门户 API 获取通知（外部调用）"""
        client = await self.get_authenticated_client()
        if client is None:
            return []

        try:
            resp = await client.post(
                "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage",
                data={"currentPage": 1, "pageSize": 10, "type": type_id},
                headers=AJAX_HEADERS,
            )
            data = resp.json()
            return data.get("datas", {}).get("tables", [])
        except Exception as exc:
            logger.warning(f"[MUC AUTH] 获取门户通知失败: {exc}")
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
            self._login_success = False
            self._cookies_loaded = False

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default
