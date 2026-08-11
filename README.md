# 易课 EasyClass v1.0.0 | Silicon UI

> 基于 **Python + PySide6** 的 Windows 桌面灵动岛（Dynamic Island）教室信息看板。

## ✨ 功能特性

- **灵动岛信息栏**：置顶显示 [课程信息 | 时间 | 天气 | 预警]，课程切换自动更新
- **全面自适应**：按屏幕 DPI 与分辨率动态缩放（1024×768 ~ 8K），支持屏幕热插拔 / 多显示器
- **深色 / 浅色主题**：两套 QSS 一键切换（`ThemeManager` 动态加载，无需重启），状态持久化
- **课程表编辑**：周一到周日七天 Tab，增删改课程，双击灵动岛 / Ctrl+E 进入（默认密码 `admin123`）
- **智能课程判断**：正在上课 / 下课休息 / 下节课提前 10 分钟预告 / 周末无课
- **天气看板**：和风天气免费 API，30 分钟自动刷新，异常时显示缓存 + 网络异常动画
- **系统托盘**：左键显隐，右键菜单（主题 / 透明度 / 显示器 / 全屏 / 穿透 / 刷新天气…）
- **精美动画**：时间弹性缩放、课程呼吸灯、预警脉冲、网络摇摆、密码抖动、滑入滑出等

## 🚀 安装与运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py
```

首次运行会自动生成 `config.json`（从模板复制）。请在 `config.json` 中填写和风天气 API Key：

```json
{ "weather_api_key": "你的KEY", "weather_city": "北京" }
```

免费 Key 申请地址：https://dev.qweather.com/

## ⌨️ 快捷操作

| 操作 | 说明 |
| --- | --- |
| 双击灵动岛 | 打开课程表编辑器（需密码） |
| Ctrl+E（全局） | 打开课程表编辑器 |
| 托盘左键单击 | 显示 / 隐藏灵动岛 |
| 灵动岛右下角手柄 | 拖拽调整宽度（50%~95%），双击重置 85% |

## ⚙️ 配置文件

`config.json`（运行时生成）：

```json
{
  "app_name": "易课",
  "app_version": "1.0.0",
  "weather_api_key": "请填写你的API密钥",
  "weather_city": "北京",
  "opacity": 0.65,
  "password": "admin123",
  "api_provider": "hefeng",
  "island_width_ratio": 0.85,
  "theme": "dark"
}
```

`schedule.json`：一周课程表数据；`weather_cache.json`：最近一次天气缓存（自动生成）。

## 📁 项目结构

```
EasyClass/
├── main.py                  # 程序入口
├── theme_manager.py         # 主题管理模块（QSS 变量替换 / 主题持久化）
├── island_window.py         # 灵动岛主窗口
├── course_manager.py        # 课程表数据管理
├── weather_manager.py       # 天气管理（和风天气 + 缓存 + QThread）
├── icon_drawer.py           # 矢量图标绘制（托盘 / 天气）
├── tray_icon.py             # 系统托盘
├── settings_dialog.py       # 设置 / 课程表编辑 / 密码 / Toast
├── utils.py                 # 自适应缩放 / 配置 / 动画 / 热键 / 毛玻璃
├── res/
│   ├── style_dark.qss       # 深色主题
│   └── style_light.qss      # 浅色主题
├── config.template.json
├── schedule.template.json
└── requirements.txt
```

## 📌 说明

- 界面全部使用布局管理器 + `utils.s()` 缩放函数，无固定坐标，适配任意分辨率。
- QSS 采用 Silicon UI 设计规范（毛玻璃卡片 / 柔光阴影 / 16px 圆角 / 胶囊 Tab / iOS 开关）。
- 灵动岛默认可交互（支持双击编辑）；如需鼠标穿透，请勾选托盘菜单「鼠标穿透模式」。
- 天气 API 未配置或断网时不弹任何错误框，仅显示「⚡ 网络异常 / [缓存]」提示。

## 🛠 技术栈

- Python 3.9+ / PySide6 ≥ 6.5
- requests（天气接口）
