# outlook-digest

定时读取本机 Outlook 邮件，做**翻译 / 分析 / 总结 / 归档**：

- 通过桌面版 Outlook 的 COM 接口读取（不用注册 Azure 应用，不用开 Graph 权限）
- 标题先统一成中文（`argos` 本地离线神经翻译 / `glossary` 术语表 / `off`），再在统一语言上做关键词过滤
- 按 RFC `Message-ID`（缺失时用 发件人+主题+时间 哈希）去重，重复运行不会重复归档
- 分析结果同时写入 **SQLite**（元数据、可查询）和 **Markdown**（按 主题分类/年月 分目录，可被 Obsidian / Everything 检索）
- AI 采用可插拔设计：`provider = "mock"` 时用本地规则，`"openai"` 时调用任意 OpenAI 兼容接口，调用失败自动降级回规则分析
- 由 Windows 计划任务每 30 分钟触发，单实例运行

## 目录结构

```
outlook-digest/
├─ config.toml              # 全部可调参数
├─ requirements.txt         # pywin32 + argostranslate
├─ outlook_digest/
│  ├─ __main__.py           # python -m outlook_digest
│  ├─ cli.py                # run / status / reindex
│  ├─ config.py             # 配置加载
│  ├─ models.py             # Mail / Analysis
│  ├─ outlook_source.py     # Outlook COM 读取
│  ├─ textutil.py           # HTML→文本、去引用、语言识别、句子/行动项抽取
│  ├─ analyze.py            # 规则分析 + 降级包装
│  ├─ ai.py                 # OpenAI 兼容客户端
│  ├─ translate.py          # 标题归一：off / glossary / argos 离线翻译
│  ├─ render.py             # Markdown 渲染
│  ├─ archive.py            # 落盘与日/月索引
│  └─ store.py              # SQLite
├─ scripts/
│  ├─ run.cmd               # 手动运行
│  ├─ install_argos_model.py# 安装 en→zh 离线语言包（约 70MB）
│  ├─ register_task.ps1     # 注册定时任务
│  └─ unregister_task.ps1
├─ tests/                   # unittest，不依赖 Outlook
├─ data/                    # mail.db + logs（自动创建，已 gitignore）
└─ archive/                 # Markdown 归档（自动创建，已 gitignore）
```

## 安装

```powershell
cd C:\Users\XC872TK\Documents\outlook-digest
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 一次性安装 en→zh 离线语言包（之后翻译完全离线，不再联网）
.\.venv\Scripts\python.exe scripts\install_argos_model.py
```

## 用法

```powershell
# 试跑：读最近 24 小时的新邮件，只打印不落库
.\scripts\run.cmd run --dry-run --hours 24 --limit 5

# 正式归档
.\scripts\run.cmd run

# 查看累计统计与上次运行结果
.\scripts\run.cmd status

# 重建最近 7 天的每日索引
.\scripts\run.cmd reindex --days 7
```

单封邮件归档为 `archive/topics/<主题分类>/<年-月>/<日期>_<时间>_<主题>.md`，
含 摘要 / 译文 / 待办 / 原文 四段，front matter 里带 `title_norm`（归一后的中文标题）；
时间索引在 `archive/timeline/<日期>.md` 与 `<年-月>.md`，每行链到对应邮件文件。

## 翻译归一与关键词过滤

`config.toml`：

```toml
[translate]
engine = "argos"        # off | glossary | argos

[filters]
# 对「原文主题 + 归一标题 + 会话主题」一起匹配
skip_subject_keywords = ["退订", "unsubscribe", "newsletter"]
include_keywords = []   # 非空则为白名单：一条都不命中就跳过
```

- `argos`：本地离线神经翻译（CTranslate2），只翻译非中文标题，再套一遍 `[glossary]` 统一缩写与专有名词。
- `glossary`：纯术语表整词替换，零依赖、零延迟；`argos` 不可用时自动回退到它。
- 归一后的标题写入 `mail.title_norm`，参与关键词过滤、分类、优先级判断，并在归档与索引里展示。

## 接入 AI

编辑 `config.toml`：

```toml
[ai]
provider = "openai"
base_url = "https://api.deepseek.com/v1"   # 或 https://api.openai.com/v1、自建网关
model = "deepseek-chat"
api_key_env = "OUTLOOK_DIGEST_API_KEY"
```

然后设置环境变量（计划任务读取的是用户级环境变量，设置后需重新登录或重启任务）：

```powershell
[Environment]::SetEnvironmentVariable("OUTLOOK_DIGEST_API_KEY", "sk-xxxx", "User")
```

密钥只从环境变量读取，不会写进仓库。AI 输出要求为 JSON（摘要/译文/分类/优先级/待办），
解析失败或网络错误时该封邮件自动降级为规则分析，不会中断整轮运行。

## 定时任务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1 -IntervalMinutes 30
```

- 使用当前用户、交互式运行、`pythonw.exe` 无窗口
- `MultipleInstances IgnoreNew`：上一轮没跑完时不会叠加
- 立即试跑一次：`Start-ScheduledTask -TaskName OutlookDigest`
- 卸载：`.\scripts\unregister_task.ps1`

## 已知限制

- **Outlook 必须处于登录并运行状态**，计划任务才能通过 COM 读到邮件；关掉 Outlook 时该轮会记录错误并跳过。若需要完全后台化，需改走 Microsoft Graph API（要 Azure 应用注册）。
- **企业 Outlook 安全策略可能只允许读取元数据**（主题/时间/已读/分类/附件名），此时 `Body`、发件人、收件人都会报 `E_FAIL`。程序会自动降级为元数据归档，并在 Markdown 中标注「正文不可读」；这是策略限制，程序不会绕过（不要用 Redemption/VBA 等规避手段，需 IT 审批）。
- 只读取配置里列出的文件夹；Exchange 环境的发件人 SMTP 地址会自动从 X500 地址解析。
- `provider = "openai"` 意味着邮件正文会发送到你配置的第三方模型服务——请在合规允许的前提下启用。
- 归档目录按文件存放，邮件正文超过 8000 字符会在 Markdown 中截断（全文可在 SQLite 的 `body_text` 查到，上限 50000 字符）。
