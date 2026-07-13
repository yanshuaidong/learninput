# learninput

学习输入法 — 轻量辅助工具，个人本地使用。

核心原则：**不要劫持输入，只旁听。** 键盘事件照常交给系统输入法，本工具在旁边记录拼音并显示释义。

## 架构

```
你打字 → 系统输入法正常上屏
              ↓
     Python 旁听 a-z，维护拼音 buffer
              ↓
     停顿 400ms → 调 DeepSeek
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
| `DEBOUNCE_MS` | 停顿触发毫秒数 | `400` |

释义结果会缓存到 `.cache/translations.json`，相同拼音不重复请求。

## 旁听规则

- 监听 `a-z`，累积拼音（如 `chuanghu`）
- 空格、回车、Tab、标点 → 清空 buffer
- 退格 → 删除最后一个字母
- 停顿达到 `DEBOUNCE_MS` 且拼音长度 ≥ 2 → 请求释义

## 项目结构

```
learninput/
├── start             # 启动脚本
├── stop              # 停止脚本
├── main.py           # 入口
├── listener.py       # 键盘旁听 + 防抖
├── translator.py     # DeepSeek + 缓存
├── ui/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
└── .env.example
```
