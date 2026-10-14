# 备用方案：本地 CORS 服务 + 页面 fetch（回环）

> **默认不用。** 主路径是 SKILL.md 的 opencli 分块注入。只有在**没有 opencli、只能用 chrome-devtools MCP /
> Claude in Chrome 扩展**驱动浏览器时才退回这里。

让页面**自己**去本地 HTTP 服务把文件拉下来，再用 JS 构造 `File` 塞进 `<input type=file>`。
文件字节不经过 MCP 通道，所以没有 10MB 上限。

## 适用与不适用（2026-10-14 实测）

| 浏览器 | 结果 |
| --- | --- |
| chrome-devtools MCP 拉起的 Chrome | ✅ 首次 fetch 挂起，用户在地址栏点「允许」本地网络访问后可用（360、百度、讯飞都这样传过 42MB 包） |
| 用户主 Chrome（opencli Browser Bridge） | ❌ `fetch('http://127.0.0.1:…')` 直接 `TypeError: Failed to fetch`，不弹权限框，`local-network-access` 一直是 `prompt` |
| Claude in Chrome 扩展 | ✅ 同第一行，需用户放行一次 |

另外 chrome-devtools MCP 拉起的 Chrome 带 `navigator.webdriver === true`，阿里（淘宝滑块）、三星账号登录会被拦，
这类站点只能走主 Chrome + opencli。

## 步骤

### 1. 把文件收进一个目录，起服务

```bash
SP=<scratchpad>/upload            # 会话级临时目录，不要放进项目仓库
mkdir -p "$SP" && cp <文件> "$SP/"
python3 scripts/cors_server.py 8912 --root "$SP"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8912/<文件名>   # 期望 200
```

服务带 `Access-Control-Allow-Origin: *` 和 `Access-Control-Allow-Private-Network: true`，只绑 `127.0.0.1`。

### 2. 首次放行本地源

从 HTTPS 页面发往 `127.0.0.1` 的第一个请求会**挂起**（永远 pending，服务端日志看不到），
Chrome 在地址栏弹「访问本地网络设备」提示，**需要用户点「允许」**。先用小文件探活：

```js
window.__probe = { state: 'start' };
fetch('http://127.0.0.1:8912/<小文件>?r=' + Date.now())
  .then(r => r.blob()).then(b => { window.__probe = { state: 'blob', size: b.size }; })
  .catch(e => { window.__probe = { state: 'error', msg: String(e) }; });
'kicked';
```

`navigator.permissions.query({name: 'local-network-access'})` 返回 `granted` 后，挂起的那次请求会自己继续完成。

### 3. 注入（异步启动 + 下一次调用读结果）

```js
window.__up = { state: 'running' };
(async () => {
  try {
    const r = await fetch('http://127.0.0.1:8912/app.apk?r=' + Date.now());
    const b = await r.blob();
    const input = document.querySelector('<已核对的 input 选择器>');
    const dt = new DataTransfer();
    dt.items.add(new File([b], 'app.apk', { type: 'application/vnd.android.package-archive' }));
    input.files = dt.files;
    setTimeout(() => input.dispatchEvent(new Event('change', { bubbles: true })), 0);
    window.__up = { state: 'done', size: b.size };
  } catch (e) { window.__up = { state: 'error', msg: String(e) }; }
})();
'kicked';
```

直接 `await` 大文件 fetch 会撞 CDP 45s 超时。表单在同源 iframe 里时，`File` / `DataTransfer` / `Event`
要用 iframe 自己的 `contentWindow` 构造。

### 4. 收尾

```bash
pkill -f cors_server.py
rm -rf "$SP"
```

## 坑

| 坑 | 处理 |
|----|------|
| 第一个跨源请求永远 pending | 本地网络访问没放行，等用户点允许；服务端日志空白说明请求没出浏览器 |
| 主 Chrome 里 `Failed to fetch`、不弹框 | 本方案在主 Chrome 不可用，改走 opencli 分块注入 |
| 顶层 `await` 撞 45s CDP 超时 | IIFE 异步启动，结果写 `window.__x`，下一次调用再读 |
| 注入后 `input.files.length === 0` | 组件已接管，属正常，看页面回显 |
| 重启服务端口被占 | 起服务前 `pkill -f cors_server.py` |
