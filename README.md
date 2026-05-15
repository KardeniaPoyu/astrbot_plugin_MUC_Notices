# astrbot_plugin_MUC_Notices

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

聚合抓取**中央民族大学 (MUC)** 多个通知站点，生成 RSS 文件并主动推送到已订阅会话。

## ✨ 功能

- 📡 **14 个通知来源** — 主站、研究生院、人事处、财务处、新闻网、信息门户
- 🔐 **SM2 国密加密登录** — 自动登录信息门户，获取办公/教学/科研通知
- 📝 **内容预览** — 门户通知自带摘要预览（前 80 字）
- 🔄 **智能去重** — 已推送通知不再重复推送
- 🍪 **Cookie 持久化** — 登录一次，后续自动复用
- ⏱️ **定时轮询** — 可配置间隔，自动检查更新
- 🎯 **灵活订阅** — 全局订阅或按来源分类订阅
- 📋 **RSS 2.0** — 生成标准聚合 RSS 供阅读器订阅

## 📡 通知来源

### 公开站点（无需登录）
| Key | 名称 | URL |
|-----|------|-----|
| `muc_tzgg` | 主站 - 通知公告 | `www.muc.edu.cn/tzgg.htm` |
| `grs_zs` | 研究生院 - 招生工作 | `grs.muc.edu.cn` |
| `grs_py` | 研究生院 - 培养工作 | `grs.muc.edu.cn/pygz.htm` |
| `grs_xw` | 研究生院 - 学位工作 | `grs.muc.edu.cn/xwgz.htm` |
| `grs_xj` | 研究生院 - 学籍工作 | `grs.muc.edu.cn/xj_xs_gz.htm` |
| `grs_yjszs` | 研究生院 - 招生网 | `grs.muc.edu.cn/yjsyzsw/` |
| `rsc_tzgg` | 人事处 - 通知公告 | `rsc.muc.edu.cn` |
| `cwc_tzgg` | 财务处 - 通知公告 | `cwc.muc.edu.cn` |
| `news_zh` | 新闻网 - 综合新闻 | `news.muc.edu.cn` |
| `news_xs` | 新闻网 - 学术动态 | `news.muc.edu.cn` |

### 信息门户（需配置账号密码，SM2 加密登录）
| Key | 名称 | 说明 |
|-----|------|------|
| `my_bgtz` | 门户 - 办公通知 | 通过 Portal API 获取，带内容摘要 |
| `my_jxtz` | 门户 - 教学通知 | 通过 Portal API 获取，带内容摘要 |
| `my_kytz` | 门户 - 科研通知 | 通过 Portal API 获取，带内容摘要 |

## 📦 安装

1. 将 `astrbot_plugin_MUC_Notices` 文件夹放入 `AstrBot/data/plugins/`
2. 安装依赖：
```bash
pip install gmssl httpx beautifulsoup4
```
3. 在 AstrBot 中热重载：
```
/plugin reload astrbot_plugin_MUC_Notices
```

## ⚙️ 配置账号（信息门户）

三种方式任选其一：

**方式一：聊天设置（推荐）**
```
/muc_notice set_account 学号 密码
```

**方式二：WebUI 配置**
在 AstrBot 管理面板 → 插件配置 → 填入 `muc_username` 和 `muc_password`

**方式三：环境变量**
```bash
export MUC_USERNAME=学号
export MUC_PASSWORD=密码
```

## 📖 使用

### 用户命令
| 命令 | 说明 |
|------|------|
| `/muc_notice help` | 查看帮助 |
| `/muc_notice sources` | 查看支持的来源和订阅状态 |
| `/muc_notice subscribe` | 订阅全部来源 |
| `/muc_notice unsubscribe` | 取消全部订阅 |
| `/muc_notice subscribe_source <key>` | 订阅指定来源 |
| `/muc_notice unsubscribe_source <key>` | 取消指定来源 |
| `/muc_notice check` | 立即检查更新并推送 |
| `/muc_notice latest` | 查看最近 5 条聚合通知 |
| `/muc_notice latest_source <key>` | 查看指定来源最近 5 条 |
| `/muc_notice latest_muc` | 主站通知公告 |
| `/muc_notice latest_graduate` | 研究生院通知 |
| `/muc_notice latest_rsc` | 人事处通知 |
| `/muc_notice latest_cwc` | 财务处通知 |
| `/muc_notice latest_news` | 新闻网新闻 |
| `/muc_notice latest_portal` | 信息门户通知（需登录） |
| `/muc_notice login_status` | 查看登录状态 |
| `/muc_notice rss` | 查看 RSS 文件路径 |

### 管理员命令
| 命令 | 说明 |
|------|------|
| `/muc_notice set_account <学号> <密码>` | 设置登录账号 |
| `/muc_notice add_push_target` | 添加推送目标 |
| `/muc_notice remove_push_target` | 移除推送目标 |
| `/muc_notice list_push_targets` | 列出推送目标 |

### 示例
```
/muc_notice set_account 22011125 mypassword
/muc_notice subscribe
/muc_notice latest_portal
/muc_notice latest_graduate
```

## 🛠 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `rss_title` | 中央民族大学多站点通知聚合 | RSS 标题 |
| `rss_max_items` | 50 | RSS 保留条数 |
| `poll_interval_minutes` | 15 | 轮询间隔（分钟） |
| `request_timeout_seconds` | 20 | HTTP 请求超时 |
| `muc_username` | (空) | 信息门户账号 |
| `muc_password` | (空) | 信息门户密码 |
| `push_targets` | [] | 推送目标会话列表 |

## 🔐 SM2 加密说明

- 密码使用 **SM2 国密算法**加密传输，不发送明文
- 依赖 `gmssl` Python 库（`pip install gmssl`）
- 登录成功后 Cookie 持久化到 `plugin_data/astrbot_plugin_MUC_Notices/muc_cookies.json`
- Cookie 过期后自动重新登录

## 📂 数据结构

```
astrbot_plugin_MUC_Notices/
├── main.py                # 主插件入口
├── auth_service.py        # 统一身份认证 (SM2 + Cookie)
├── rss_service.py         # 抓取引擎 (HTML + API)
├── sources.py             # 14 个通知来源配置
├── parsers.py             # HTML 解析函数
├── subscription_store.py  # KV 存储 (订阅 + 去重)
├── command_utils.py       # 命令辅助
├── _conf_schema.json      # 配置 Schema
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖
└── README.md              # 本文档
```

## 📄 License

MIT

---

## 📝 更新日志

### v1.0.2 (2026-05-15)

**根据 Sourcery AI Review 修复：**
- 🔧 修复 `font.sans-serif` 类型安全问题：处理配置为字符串时的拼接错误
- 📝 添加字体加载调试日志，便于诊断字体问题
- ⚙️ 并发限制可配置：新增 `max_concurrent_requests` 配置项（默认5）

### v1.0.1 (2026-05-15)

**修复问题：**
- 🔧 修复 `notice_card.py` 硬编码字体路径问题，改为智能路径查找 + 系统字体 fallback
- 🔧 修复 `metadata.yaml` 插件名称拼写错误 (`astrbort` → `astrbot`)

**安全改进：**
- 🔐 Cookie 文件权限设置为 600（仅所有者可读写），防止敏感信息泄露
- 🛡️ 添加并发请求限制（Semaphore=5），避免对目标站点造成压力

**代码质量：**
- 📝 完善日志记录，关键操作增加审计日志
- 🧹 清理冗余代码，优化异常处理

---

**注意**：本插件仅抓取公开可访问的站点信息，信息门户登录仅用于读取通知。
