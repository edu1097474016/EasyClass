# 易课 EasyClass v1.0.0 | Silicon UI

> 基于 **Python + PySide6** 的 Windows 桌面灵动岛（Dynamic Island）教室信息看板。

## ✨ 功能特性

- **灵动岛信息栏**：置顶显示 [课程信息 | 时间 | 天气 | 预警]，课程切换自动更新
- **每日一言**：轮播 Hitokoto 一言，刷新间隔可在管理后台调节
- **全面自适应**：按屏幕 DPI 与分辨率动态缩放（1024×768 ~ 8K），支持屏幕热插拔 / 多显示器
- **深色 / 浅色主题**：两套 QSS 一键切换（`ThemeManager` 动态加载，无需重启），支持自定义主题色
- **灵动岛材质与形状**：毛玻璃 / 亚克力两种材质一键切换，可自定义玻璃底色；外形支持矩形与胶囊（两端圆角）
- **智能课程判断**：正在上课 / 下课休息 / 下节课提前 10 分钟预告 / 周末无课
- **天气看板**：和风天气 API，30 分钟自动刷新；支持公网 IP 自动定位 / 手动填城市。同一城市两种方式统一使用内置城市表（城市中心坐标 + LocationID）查询，天气保持一致且更准；未收录城市可通过 `weather_manager.py` 的 `CITY_LOCATIONS` 表自行扩充
- **丰富天气数据**：实时天气 + 空气质量 AQI（等级着色）+ 天气预警（按预警等级颜色区分、优先展示）+ 7 天预报 + 24 小时 + 分钟级降水 + 生活指数，矢量图标显示在温度左侧
- **天气刷新一键 Toast 提示**：托盘菜单与管理后台任一「刷新天气」按钮，点击后均以 Toast 提示刷新结果（成功显示城市/温度/天气，失败显示原因）
- **数据目录**：启动时自动创建 `data/` 目录，配置、课程表、天气缓存、日志与自定义字体统一写入该目录
- **系统托盘**：左键显隐，右键菜单（主题 / 透明度 / 显示器 / 全屏 / 穿透 / 刷新天气…）
- **开机自启动**：管理后台一键开关，写入注册表 HKCU Run
- **自定义字体**：导入 TTF/OTF 字体并永久保存到 `data/fonts/`，实时生效
- **课程表导入**：管理后台支持导入 JSON 课表，自动校验与提示
- **首次使用引导**：首次启动弹窗提示完成天气与课程表配置，并自动打开管理后台
- **精美动画**：时间弹性缩放、课程呼吸灯、预警脉冲、网络摇摆、密码抖动、滑入滑出等
- **靠近自动隐藏**：鼠标靠近灵动岛时自动隐藏、移开后恢复（默认开启，可在管理后台关闭）

## 🚀 安装与运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py
```

首次运行会自动生成 `data/config.json`（从模板复制）。请在 `data/config.json` 中填写和风天气 API Key，或直接在管理后台「天气」页填写：

```json
{ "weather_api_key": "你的KEY", "weather_city": "北京" }
```

免费 Key 申请地址：https://dev.qweather.com/

### 打包为独立 exe

```bash
pip install pyinstaller
pyinstaller EasyClass.spec
```

产物为 `dist/EasyClass.exe`，运行数据自动写入 exe 同目录下的 `data/`。

## ⌨️ 快捷操作

| 操作 | 说明 |
| --- | --- |
| 托盘右键 → 设置 | 打开管理后台（无需密码） |
| Ctrl+E（全局） | 打开课程表编辑器（直接进入编辑，无需密码） |
| 托盘左键单击 | 显示 / 隐藏灵动岛 |
| 托盘右键 → 刷新天气 | 立即刷新天气并以 Toast 提示结果 |
| 托盘右键 → 全屏 / 穿透 / 显示器 | 切换灵动岛显示模式 |
| 灵动岛右下角手柄 | 拖拽调整宽度（50%~95%），双击重置 85% |

## ⚙️ 配置文件

`config.json`（运行时生成）：

```json
{
  "app_name": "易课",
  "app_version": "1.0.0",
  "weather_api_key": "请填写你的API密钥",
  "weather_city": "北京",
  "api_host": "https://api.qweather.com",
  "auto_locate": true,
  "opacity": 0.65,
  "password": "admin123",
  "api_provider": "hefeng",
  "island_width_ratio": 1.0,
  "island_glass_style": "auto",
  "island_glass_custom": "#1E202D",
  "island_material": "frosted",
  "island_shape": "rect",
  "island_fullscreen": false,
  "island_passthrough": false,
  "island_screen": 0,
  "hover_hide": true,
  "hover_hide_margin": 60,
  "hover_hide_interval": 100,
  "custom_font_file": "",
  "course_progress_height": 3,
  "hitokoto_category": "",
  "hitokoto_refresh_minutes": 15,
  "theme": "dark",
  "theme_color": "#40916C"
}
```

> **注意**：和风天气新版 API 要求每个账号使用专属 API Host（在[控制台-设置](https://console.qweather.com/setting)查看，形如 `https://abc.qweatherapi.com`）。若请求返回 `Invalid Host`，请在管理后台「天气」页填写你的专属 Host。

`schedule.json`：一周课程表数据；`weather_cache.json`：历史天气缓存文件（新版天气数据改为内存缓存，该文件为兼容遗留）。

## 📁 项目结构

```
EasyClass/
├── main.py                  # 程序入口
├── theme_manager.py         # 主题管理模块（QSS 变量替换 / 主题持久化 / 自定义主题色）
├── island_window.py         # 灵动岛主窗口（天气/预警/AQI/每日一言/鼠标靠近自动隐藏）
├── course_manager.py        # 课程表数据管理
├── weather_manager.py       # 天气管理（IP 定位 + 实时/空气/预警/预报 + 内置城市表 + QThread）
├── hitokoto.py              # 每日一言（Hitokoto）
├── icon_drawer.py           # 矢量图标绘制（托盘 / 天气）
├── tray_icon.py             # 系统托盘
├── settings_dialog.py       # 设置 / 课程表编辑 / 密码 / Toast
├── admin_window.py          # 管理后台（左侧导航 + 全部设置 + 关于）
├── utils.py                 # 自适应缩放 / 配置 / 数据目录 / 动画 / 热键 / 开机自启动 / 毛玻璃
├── res/
│   ├── style_dark.qss       # 深色主题
│   └── style_light.qss      # 浅色主题
├── data/                    # 运行时数据（不入库）：config.json / schedule.json / weather_cache.json / fonts / logs
├── config.template.json     # 配置模板（首次运行自动复制为 data/config.json）
├── schedule.template.json   # 课表模板
├── EasyClass.spec           # PyInstaller 打包配置
└── requirements.txt
```

## 📌 说明

- 界面全部使用布局管理器 + `utils.s()` 缩放函数，无固定坐标，适配任意分辨率。
- QSS 采用 Silicon UI 设计规范（毛玻璃卡片 / 柔光阴影 / 16px 圆角 / 胶囊 Tab / iOS 开关）。
- 课程表编辑请通过托盘右键「设置」进入管理后台；如需鼠标穿透，请勾选托盘菜单「鼠标穿透模式」。
- 天气 API 未配置或断网时不弹任何错误框，仅显示「⚡ 网络异常 / [缓存]」提示。

## 🛠 技术栈

- Python 3.9+ / PySide6 ≥ 6.5
- requests（天气接口）
