# learninput

学习输入法 — 轻量辅助工具，个人本地使用。

核心原则：**不要劫持输入，只旁听。** 键盘事件照常交给系统输入法，本工具在旁边记录拼音并显示释义。

## 架构

```
你打字 → 系统输入法正常上屏
              ↓
     Python 旁听 a-z，维护拼音 buffer
              ↓
     停顿 700ms → 调 DeepSeek
              ↓
     HTML 浮动面板显示：window（窗户）
```

- **逻辑**：Python（`listener.py` + `translator.py`）
- **界面**：HTML/CSS（`ui/`）
- **壳**：pywebview 无边框置顶小窗
- **不打包**：终端里 `python main.py` 即可

## 快速开始

```bash
cd learninput
# 首次使用：创建 .env 并填入 DEEPSEEK_API_KEY
chmod +x start stop
./start    # 启动
./stop     # 停止
```

`start` 会自动创建虚拟环境、安装依赖，并在后台运行。日志在 `.learninput.log`。

## macOS 权限

全局旁听键盘需要给**终端 App**（Terminal / iTerm 等）开启：

**系统设置 → 隐私与安全性 → 辅助功能 → 勾选你的终端**

首次运行若面板不更新，先检查这项权限。

## 配置

| 变量 | 说明 | 默认 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 必填 |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEBOUNCE_MS` | 停顿触发毫秒数 | `700` |
| `MIN_PINYIN_LENGTH` | 拼音最短长度，低于此值不请求 | `4` |
| `TRANSLATE_HOTKEY` | 选中文案译英快捷键 | `alt+e`（Option+E） |
| `ACCEPT_HOTKEY` | 采纳当前英文翻译并粘贴 | `alt+enter`（Option+回车） |

释义结果会缓存到 `.cache/translations.json`，相同拼音不重复请求。

## 旁听规则

- 监听 `a-z`，累积拼音（如 `chuanghu`）
- 空格、回车、Tab、标点 → 清空 buffer
- 退格 → 删除最后一个字母
- 停顿达到 `DEBOUNCE_MS` 且拼音长度 ≥ `MIN_PINYIN_LENGTH` → 请求释义

## 选中译英

1. 用鼠标选中文案（输入框 / 网页 / App，取决于系统无障碍是否暴露选区）
2. 按快捷键（默认 `Option+E`，即 `TRANSLATE_HOTKEY=alt+e`）
3. 浮动面板显示：`English（中文）`

**面板消失**（与拼音组字一致）：

- `Esc` / `空格` / `回车` / `Tab` / 标点 → 关闭面板
- 开始输入拼音 → 关闭选中面板，切换为组字模式
- 再次按翻译快捷键 → 刷新翻译内容

可在 `.env` 里改快捷键，例如 `ctrl+shift+t`、`cmd+shift+e`。

## 采纳英文

拼音组字面板显示英文翻译后，可按快捷键将英文直接粘贴进输入框（不劫持输入法，仅在采纳时短暂介入）：

1. 正常输入拼音，例如 `wozuotiangangdaobeijing`
2. 停顿后面板显示：`I just arrived in Beijing yesterday（我昨天刚到北京）`
3. 按 **Option+回车**（默认 `ACCEPT_HOTKEY=alt+enter`）
4. 工具会发送 `Esc` 取消输入法组字，再通过剪贴板粘贴英文

**与正常上屏的关系：**

- 按 **空格** → 仍由输入法上屏中文，面板消失（原有行为不变）
- 按 **Option+回车** → 上屏英文，面板消失
- 翻译尚未返回（loading）或报错时，采纳键无效

**限制：**

- 采纳时会短暂占用剪贴板（约 100ms 后自动恢复）
- 需要与旁听相同的辅助功能权限
- 少数不响应粘贴的输入控件可能无法采纳

## 项目结构

```
learninput/
├── start             # 启动脚本
├── stop              # 停止脚本
├── main.py           # 入口
├── listener.py       # 键盘旁听 + 防抖
├── injector.py       # 采纳英文：Esc + 剪贴板粘贴
├── translator.py     # DeepSeek + 缓存
├── ui/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
└── .env.example
```
