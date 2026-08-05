---
name: countly-data-analysis
description: Query and analyze Countly analytics/crash data via the self-hosted Read API at analytics.jzj.plus (multi-app：玩清单 flutter_todo、笔笔记账 flutter_bbjz 等). Use whenever the user asks about Countly, 打点 / 埋点数据、事件上报情况、页面浏览 views、crash 崩溃链接、analytics.jzj.plus、validating tracking events, checking event counts, comparing code-declared events with server-side data, diagnosing why an event has zero / abnormally high traffic, or fixing a bug from a Countly crash URL.
---

# Countly Data Analysis

自建 Countly：`https://analytics.jzj.plus`，**一个实例挂多个 App**（玩清单 `flutter_todo`、笔笔记账 `flutter_bbjz` …）。本 Skill 用于通过 **Read API** 拉取后台数据、与项目内事件常量对账、定位上报异常、根据 Countly crash 链接定位线上崩溃。

各 App 客户端的事件清单与 segmentation 字段以**该项目仓库内**的 `docs/countly_events.md` 为准。

## 1. 必要凭据

| 凭据 | 说明 | 用途 |
|------|------|------|
| Server URL | `https://analytics.jzj.plus` | 写入 + 读取 |
| **App ID** | Dashboard → App Settings | 读 API 必填 |
| **Auth Token / API Key** | Dashboard 登录会话 token 或 User Profile → API Key | 读 API 鉴权 |
| **App Key**（SDK 上报用） | 客户端 `CountlyService` 配置 | 仅 SDK `/i` 写入，**不要拿来读** |

**凭据按项目隔离**（多 Agent 通用，勿写入仓库或对话）。脚本按 **git 根目录名**去找配置：

```bash
SKILL_DIR=~/.claude/skills/countly-data-analysis   # 本 skill 根目录

# 在目标项目仓库里执行，<项目名> 即 git 根目录名
mkdir -p ~/.config/ai-ignore-config/flutter_bbjz
cp "$SKILL_DIR/config.example.env" ~/.config/ai-ignore-config/flutter_bbjz/countly.env
# 填 COUNTLY_APP_ID 与 COUNTLY_TOKEN
```

脚本 [`countly_query.sh`](scripts/countly_query.sh) 按顺序解析配置：

1. `--config /path/to/file`（命令行任意位置，也支持 `--config=PATH`）
2. `$COUNTLY_CONFIG`
3. `~/.config/ai-ignore-config/<git 根目录名>/countly.env` ← **默认**

> **为什么按项目隔离**：一个 Countly 实例挂着多个 App，配置若共用一份，从 A 项目跑脚本
> 会静默查到 B 项目的数据——数据看着正常但不是你要的那个应用，比报错难查得多。
> 不在 git 仓库里时退回当前目录名。

已知 App（`COUNTLY_APP_ID`，非机密，dashboard URL 里就有）：

| 项目 | 应用 | App ID |
|---|---|---|
| `flutter_todo` | 玩清单 | `69ddec1f1497fce717232422` |
| `flutter_bbjz` | 笔笔记账 | `6a72d917c8e49a9991a96a23` |

| 变量 | 说明 |
|------|------|
| `COUNTLY_TOKEN` | Read API `auth_token`（或长期 `api_key`，见下） |
| `COUNTLY_APP_ID` | App ID |
| `COUNTLY_BASE` | 可选，默认 `https://analytics.jzj.plus/o` |

**鉴权注意**：

- 官方推荐参数名是 **`api_key=<key>`**（Dashboard → User Profile → API Key，长期有效）。
- 本实例也接受 **`auth_token=<token>`**（登录会话 token，**会过期**）。
- Token 过期时：Dashboard 重新登录复制 token，或改用 API Key，**只改本地 `countly.env`**，不要改 SKILL / 脚本 / 对话。
- 已设置的 shell 环境变量 `COUNTLY_TOKEN` / `COUNTLY_APP_ID` 会覆盖配置文件中的值。
  这条容易咬人：在同一个 shell 里 `source` 过某个 `countly.env` 再跑 `--config 另一份`，
  环境变量会赢，看起来像 `--config` 没生效。干净复现用
  `env -u COUNTLY_APP_ID -u COUNTLY_TOKEN bash …`。

**与 Agent 协作**：让 Agent **执行脚本**查数据，不要 `@` 凭据文件或在聊天里贴 token。

## 2. 官方 API 文档（权威）

- **入口**：<https://api.count.ly/reference/rest-api-reference>
- 所有方法都是 `GET https://<server>/o?...`（读）或 `POST https://<server>/i?...`（写），payload 都是 JSON
- 内部事件名（写 API 自动生成 / Drill 可查）：
  `[CLY]_session` / `[CLY]_crash` / `[CLY]_view` / `[CLY]_action` /
  `[CLY]_push_action` / `[CLY]_push_open` / `[CLY]_push_sent`

### 2.1 读 API 方法速查

`GET https://analytics.jzj.plus/o?method=<method>&auth_token=<token>&app_id=<id>&...`
（或 `?api_key=<key>` 等价，下同）

| Endpoint / method | 用途 | 关键参数 | 官方文档 |
|---|---|---|---|
| `?method=get_events` | 列出所有事件名 + segmentation key | — | [link](https://api.count.ly/reference/omethodget_events) |
| `?method=events` | 单事件按时间桶统计（**本实例 period 失效**，见 §3） | `event=<name>`、`segmentation=<key>`、`events=<JSON array>`（合并多事件） | [link](https://api.count.ly/reference/omethodevents) |
| `?method=crashes` | 不带 `group`：crash group **列表**（`aaData`，仅汇总字段）；带 `group=<id>`：该 group 的**详情文档**（按 app/os 版本、设备、分辨率拆分 + RAM/磁盘/电量/运行时长统计 + 最近 `data` 报告数组） | crash group id 在 URL `/crashes/<id>` 末尾；脚本对单个 group 用 `group=<id>` 拉详情 | Dashboard 内部接口 |
| `?method=crash`（**单数**） | 本实例**不可用**，返回 `Invalid method`；详情统一走上面的 `crashes&group=<id>` | — | — |
| `?method=segmentation` | Drill 高级查询（支持内部事件 `[CLY]_*`） | `event=<name>`、`bucket=hourly\|daily\|weekly\|monthly`、`projectionKey`、`queryObject`（mongo JSON 字符串） | [link](https://api.count.ly/reference/omethodsegmentation) |
| `?method=user_details` | 用户列表（分页 / 搜索 / mongo 过滤） | `iDisplayStart`、`iDisplayLength`、`sSearch`、`filter`、`query` | [link](https://api.count.ly/reference/omethoduser_details) |
| `/o/analytics/dashboard` | 仪表盘聚合：30d/7d/today 各指标 | `app_id` | [link](https://api.count.ly/reference/oanalyticsdashboard) |
| `/o/analytics/sessions` | 按时间桶的 session/u/n/d/e 时序 | `period=...` | [link](https://api.count.ly/reference/oanalyticssessions) |
| `/o/analytics/metric` | 维度聚合（设备 / OS / 国家 / 渠道等） | `metric=app_versions\|carriers\|countries\|density\|devices\|langs\|os\|os_versions\|resolutions` | [link](https://api.count.ly/reference/oanalyticsmetric) |
| `/o/compare/events` | 多事件对比（≤ 10 个） | `events=<JSON array>` | [link](https://api.count.ly/reference/ocompareevents) |
| `/o/users/all` | 全量用户（要求**管理员** api_key） | `api_key=<admin>` | [link](https://api.count.ly/reference/ousersall) |

### 2.2 写 API（仅供查阅，**不要从脚本写入**）

`POST https://analytics.jzj.plus/i?app_key=<key>&device_id=<id>&events=<JSON>...`

事件对象字段：`key`(M)、`count`(M)、`sum`、`dur`、`segmentation`、`timestamp`、`hour`、`dow`。
这些 App 都启用了 `setParameterTamperingProtectionSalt`，**直接 curl 写入会被服务端拒** (`Request does not match checksum`)；要灌测试数据请走 SDK 或在 Dashboard 关闭防篡改。
官方文档：<https://api.count.ly/reference/i>

### 2.3 period 参数标准值

官方所有支持 `period` 的方法都接受：

```
month | 60days | 30days | 7days | yesterday | hour
[<startMs>, <endMs>]    // 例：[1417730400000,1420149600000]
```

**关键发现**：本实例的 `/o?method=events` **忽略 `period` 参数**——无论传 `hour` / `yesterday` / `7days` / `30days`，返回值都是完整的历史每日 + 每小时分桶。要拿真实时间窗内的总数，必须**自己在客户端按日期切片求和**（脚本的 `range` 与 `summary --from/--to` 已经这么做）。`/o/analytics/sessions`、`/o/analytics/dashboard` 等方法的 `period` 仍然生效。

`events` 响应结构是按时间嵌套的 `c`/`u`/`s`/`dur` 树（**每一层都重复同一份合计**）：

```text
{
  "2026": {                 // 年级 c = 该年总次数
    "c": 211,
    "5": {                  // 月级 c = 该月总次数
      "c": 211,
      "28": {               // 日级 c = 该日总次数
        "c": 6,
        "9": { "c": 3 }     // 小时级
      }
    }
  },
  "meta": {...}
}
```

- `c` 出现次数 / `u` 唯一用户 / `s` sum / `dur` 累计 duration
- **不要递归求和所有 `c`**（会重复加 4 倍：年+月+日+时）。正确做法二选一：
  - 取顶层「年级」`c` 求和 → 历史总数
  - 只对日级 `c` 在窗口内求和 → 真实时间窗

## 3. 推荐使用脚本

工具脚本：[scripts/countly_query.sh](scripts/countly_query.sh)（依赖 `curl` + `python3`；凭据见 §1）。

**在目标项目的仓库目录里执行**——脚本靠 git 根目录名挑配置，跑错目录就会查错 App。

```bash
SKILL_DIR=~/.claude/skills/countly-data-analysis   # 本 skill 根目录
cd <目标项目仓库根>

# 1. 列出后台已收到的所有事件
bash "$SKILL_DIR/scripts/countly_query.sh" list

# 2. 根据 Dashboard 崩溃链接获取 crash group 摘要 + stack
bash "$SKILL_DIR/scripts/countly_query.sh" crash \
  'https://analytics.jzj.plus/dashboard#/69ddec1f1497fce717232422/crashes/9f5df2af4516a03202f74eb9590f59a3e7e45d50'

# 也可以只传 crash group id
bash "$SKILL_DIR/scripts/countly_query.sh" crash 9f5df2af4516a03202f74eb9590f59a3e7e45d50

# 3. 查单个事件总数 + 最近 14 天每日分桶
bash "$SKILL_DIR/scripts/countly_query.sh" event todo_create

# 4. 按真实时间窗统计（脚本本地切片，绕过服务端 period 失效）
bash "$SKILL_DIR/scripts/countly_query.sh" range skin_change 2026-05-22 2026-05-28

# 5. 全量对账（默认按 "全部历史" 求和；可选 --from/--to 给出真实窗口）
bash "$SKILL_DIR/scripts/countly_query.sh" summary
bash "$SKILL_DIR/scripts/countly_query.sh" summary --from 2026-04-29 --to 2026-05-28

# 6. 页面浏览（视图名 / 总次数 / 独立数 / 平均时长）
bash "$SKILL_DIR/scripts/countly_query.sh" views
bash "$SKILL_DIR/scripts/countly_query.sh" views --period 7days --limit 20

# 临时查另一个 App，不用切目录：--config 放哪都行，前后均可
bash "$SKILL_DIR/scripts/countly_query.sh" views --config ~/.config/ai-ignore-config/flutter_bbjz/countly.env
```

若未配置 `countly.env`，脚本会提示创建路径。不要用 curl 手贴 token；统一走脚本。

> **`--config` 位置**：现在命令行任意位置都生效（也支持 `--config=PATH`）。
> 早期版本只在子命令**之前**解析，写成 `list --config x.env` 会被静默忽略、
> 回落到默认配置去查**另一个 App** 的数据——现象是数据"看起来对但不是你要的那个应用"。
> 指定的文件不存在现在会直接报错，不再静默回落。

### 3.1 查页面浏览的坑（`method=views` 必须带 `action`）

`/o?method=views` **不带 `action` 会返回 `{"data":[]}`**。那不是"没有视图数据"，
而是查询本身不完整：空 `action` 走的是「指定视图的时间序列」分支，需要配套
`selectedViews=[{view,action}]`。曾据此误判过「视图没上报」，实际数据一直都在。

| action | 用途 |
|---|---|
| `getTable` | 视图列表 + 指标（`views` 子命令用它）|
| `getTotals` | Total / Unique / sessions / bounce 汇总 |
| `get_view_count` | 视图总数 |

**视图名在每行的 `view` 字段**（`display` 是展示名），`_id` 是 Mongo ObjectId——
只看 `_id` 会以为拿不到名字。

排查"后台查不到数据"时，先确认查询姿势对不对，再怀疑客户端：空结果既可能是没上报，
也可能是参数缺失，两者要分清。摸不准接口形状就直接在 dashboard 对应页面抓 XHR
看它自己调什么，比猜参数快得多。

## 4. 工作流：对账与异常诊断

### 4.0 收到 Countly crash 链接时的修 bug 工作流

用户常会直接发这样的链接：

```text
https://analytics.jzj.plus/dashboard#/69ddec1f1497fce717232422/crashes/<crash_group_id>
```

处理顺序：

1. 先运行脚本，不要手动读取或输出 token：
   `bash "$SKILL_DIR/scripts/countly_query.sh" crash '<url-or-id>'`
2. 记录输出中的 `name`、`os`、`latest_version`、`reports`、`users`、`stack`，以及详情字段 `app_versions` / `os_versions` / `devices` / `resolutions` / `resources(avg)` 与 `recent reports`。这些字段用于判断影响面、定位平台、识别机型/系统版本/资源相关性。
3. 用 stack 里的包名、类名、方法名、Dart 文件路径、Android/Kotlin 类名在代码里 `rg`。混淆后的 `SourceFile` 行号只能辅助，优先相信未混淆的 Flutter stack、异常类型和组件名。
4. 判断 crash 是否线上优先级高：`users >= 3` 或当前/最新版本复现优先；`users == 1` 且 reports 很高可能是开发机或单用户重复触发，但仍应修明显的空指针、越界、组件缺失等问题。
5. 修复时优先做最小闭环：崩溃入口要能容错或回退，不要让 broadcast receiver、widget provider、startup、notification callback 这类系统入口因为可选数据缺失直接崩。
6. 验证优先跑和改动面匹配的命令。例如 Android/Kotlin crash 先跑 `./gradlew :app:compileDebugKotlin`；Dart 逻辑再跑 `fvm flutter analyze` / 相关测试。若全量 analyze 因既有问题失败，要说明失败点不是本次改动。

Countly crash group 常见字段：

| 字段 | 用途 |
|------|------|
| `_id` | crash group id，对应 Dashboard 链接末尾 |
| `name` | 异常标题，通常含 Java/Kotlin/Flutter 异常类型 |
| `error` | stack trace，脚本会 HTML unescape 后输出 |
| `os` | 平台 |
| `latest_version` / `app_version` | 受影响版本 |
| `reports` / `users` | 次数与用户数 |
| `nonfatal` | 是否全部为 handled/nonfatal |
| `is_resolved` | Dashboard 中是否已标记解决 |

> `crash` 子命令对单个 group 改用 `method=crashes&group=<id>` 拉**详情文档**，因此除上表外还会输出（脚本已按数量倒序聚合）：
>
> | 字段 | 用途 |
> |------|------|
> | `app_version` / `os_version` | 受影响的 app / 系统版本分布（key `3:1:0` 即 3.1.0） |
> | `device` / `resolution` / `cpu` | 机型、分辨率、ABI 分布，判断是否机型/架构相关 |
> | `orientation` / `root` / `muted` / `online` / `background` | 触发时的设备状态分布 |
> | `ram` / `disk` / `bat` / `run`（`{count,min,max,total}`） | 资源占用 / 电量 / 运行时长，脚本输出均值 |
> | `startTs` / `lastTs` | 首次 / 最近一次出现时间 |
> | `data[]` | 最近若干条**单次报告**（含 `ts`/`app_version`/`os_version`/`device`/`bat` 等），脚本默认列出最近 5 条 |

### 4.1 验证新加事件是否真的入库

1. 使用 **Release 包**（Debug / Profile 不会上报 Countly）
2. 让用户在真机操作目标动作（如新建分类）
3. 等 1–2 分钟（SDK 默认有缓冲队列）
4. `./scripts/countly_query.sh list` 看新事件名是否出现在 `list` 字段
5. `./scripts/countly_query.sh event <name> hour` 看当前小时是否有 `c`

### 4.2 事件 0 次的诊断顺序

按可能性从高到低：

1. **触发条件没满足**：很多事件只在网络 `onSuccess` 内打点（如 `category_create`、`feedback_submit`），离线 / 失败不会上报
2. **隐私同意未授予**：`CountlyService.setRequiresConsent(true)`；Android 用户未点同意前 `recordEvent` 静默丢弃
3. **平台不支持**：Web / Windows / macOS / Linux 都不会上报（`isSupportedPlatform == false`）
4. **写在了过早时机**：`!isReady` 时静默 return
5. **事件名拼写漂移**：用 `list` 接口对照常量与后台是否同名

### 4.3 事件量异常高的诊断顺序

1. **自动恢复路径误触发**：监听器 / 启动恢复 / 远端同步里不应打点
2. **系统级回调误触发**：例如 `didChangePlatformBrightness`、`AppLifecycleState.resumed` 等
3. **重复入口**：多处 UI 都调同一接口（搜 `recordEvent(<name>` 看调用点数）
4. **segmentation 高基数**：URL 带 query、ID 拼时间戳等会撑爆 `event_segmentation_value_limit: 1000`

`docs/countly_events.md` 第 6 节列出了已知的正确触发位置；偏离即是噪声。

### 4.4 区分本地调试 vs 线上数据

客户端仅在 **Release** 构建上报 Countly（见 `CountlyService.isAnalyticsEnabled`）。分析存量数据时：

| 信号 | 解读 |
|------|------|
| Debug / Profile 运行 | 修复后**不应再产生**新 event / crash |
| crash group `users == 1` 且 `reports > 20` | 高概率开发机反复触发 |
| URL 含 `wqd-admin-test.jzj.red` | 测试环境，非线上 |
| 同一 Countly uid 单日爆发（如 >10 次） | 本地 retest |
| crash group `users >= 3` | 优先当真实线上问题排查 |
| 版本 `1.6.0+` 且最近日期 | 与当前发版相关 |

验证新事件 / crash 是否入库：必须用 Release 包操作，等 1–2 分钟后查 Dashboard 或脚本。

## 5. 与代码事件常量对账

各 App 的客户端事件常量集中在项目内的 `lib/core/services/countly_service.dart`（`event*` 静态常量）；
新增 / 删除事件必须同步更新该项目的 `docs/countly_events.md`。两个已接入的 App 都遵循这个布局。

`summary` 子命令会读取 `lib/core/services/countly_service.dart` 中的 `event*` 常量，拿到「代码里声明的事件名集合」，再和后台 `get_events.list` 求交集 / 差集，输出三列：

```text
event_name               server_30d_count   in_code   in_server
todo_create              844                ✓         ✓
category_create          0                  ✓         ✗     <- 代码有、后台从未收到
ohos_probe_checksum_event 4                 ✗         ✓     <- 后台残留、代码未声明
```

## 6. Dashboard 操作提醒（非脚本能做的）

- **删除残留事件**：Dashboard → 选 App → Data Manager → Events → 删除
- **生成长期 API Key**（替代会过期的 auth_token）：Dashboard → User Profile → API Key
- **查 Funnel / Retention 等高级分析**：需在 Dashboard UI 配置，不在 Read API 范围

## 7. 何时**不要**用本 Skill

- 用户问的是「怎么加一条新打点」→ 走正常代码改动，最多读本 Skill 第 5 节确认命名规范
- 用户问的是 Countly SDK 本身的 API 用法 → 查 `packages/countly_flutter/` 或官方文档，本 Skill 只覆盖 Read API
- 写入测试事件 → 客户端被 `setParameterTamperingProtectionSalt` 强校验，从 curl 发 `/i` 会被拒（`Request does not match checksum`），不要尝试用 Read API 凭据写入
