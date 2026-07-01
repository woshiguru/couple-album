# 💕 情侣相册

一款基于 Python + pywebview 的本地情侣相册桌面应用，支持照片/视频管理、多收藏夹、音乐播放和程序内更新。

---

## ✨ 功能

### 📷 相册管理
- 创建多个相册，导入照片和视频
- 瀑布流布局浏览，支持懒加载
- 自动为视频生成缩略图（需 ffmpeg）
- **删除相册** — 管理模式下鼠标悬停相册名，点击 × 即可删除

### ❤️ 多收藏夹
- 创建多个收藏夹（如"旅游"、"纪念日"等）
- 一张照片可加入多个收藏夹
- 点击 ➕ 按钮选择要加入的收藏夹
- 点击 ❤️ 按钮可从所有收藏夹中移除
- 数据持久化存储，重启不丢失

### 🎵 音乐播放
- 导入本地音乐文件
- 支持顺序播放 / 随机播放 / 单曲循环
- 播放列表管理，可删除歌曲

### 📦 程序内更新
- 无需重新安装，放入更新包即可升级
- 自动备份当前版本，支持回滚
- 详见 [更新接口使用说明](./更新接口使用说明.md)

### 🔧 其他
- 自定义应用名称（显示在标题栏）
- 扫描同步 — 手动放入 storage 文件夹的文件一键识别
- 左下角显示当前版本号

---

## 📋 环境要求

- **Python** 3.8+
- **系统** Windows 10/11（使用 Edge WebView2 渲染界面）
- **ffmpeg**（用于视频缩略图，需自行下载）

### 📥 下载 ffmpeg

ffmpeg 文件较大，不随项目上传。请自行下载：

1. 访问 [ffmpeg 官网下载页](https://ffmpeg.org/download.html)
2. 下载 Windows 版本（推荐 `ffmpeg-release-essentials.zip`）
3. 解压后找到 `ffmpeg.exe`
4. 放入项目根目录下的 `ffmpeg/` 文件夹

最终路径：`项目根目录/ffmpeg/ffmpeg.exe`

---

## 🚀 安装运行

### 方法一：直接运行源码

```bash
# 安装依赖
pip install pywebview

# 启动程序
python src/app.py
```

或双击 `启动.bat`

### 方法二：免安装版

直接运行 `情侣相册.exe`（需确保 `情侣相册.exe` 和 `_internal/` 文件夹在同一目录）。

### 方法三：使用安装程序

双击 `情侣相册安装程序.exe`，选择安装目录，完成后桌面会创建快捷方式。

---

## 📁 目录结构

```
情侣相册/
├── src/
│   └── app.py              # 后端主程序
├── ffmpeg/
│   └── ffmpeg.exe          # 视频处理工具（需自行下载）
├── storage/                # 数据目录（首次运行自动创建）
│   ├── photos/             # 照片和视频
│   ├── music/              # 音乐文件
│   ├── thumbnails/         # 视频缩略图
│   ├── overlay/            # 更新覆盖层
│   ├── updates/            # 更新包存放目录
│   │   └── backup_*/       # 更新备份
│   └── metadata.json       # 元数据（版本、相册、收藏夹等）
├── index.html              # 前端界面
├── icon.ico                # 应用图标
├── requirements.txt        # Python 依赖
├── 启动.bat                # 启动脚本
├── 打包.bat                # 打包脚本
├── installer.py            # 安装程序生成脚本
└── 更新接口使用说明.md      # 更新功能文档
```

---

## 📦 更新功能

程序支持离线更新，无需重新安装。

### 快速使用

1. 将更新包（`.zip`）放入 `storage/updates/` 文件夹
2. 打开程序 → 管理 → 检查更新
3. 点击"立即更新"，程序自动升级并重启

### 更新包格式

```
update_1.2.0.zip
├── update.json          # 更新说明（必须有）
├── index.html           # 要替换的文件
└── src/app.py           # 要替换的文件
```

`update.json` 示例：

```json
{
  "version": "1.2.0",
  "description": "修复了收藏功能的bug，新增了删除相册功能",
  "files": [
    { "path": "index.html", "action": "replace" },
    { "path": "src/app.py", "action": "replace" }
  ]
}
```

详细文档见 → [更新接口使用说明](./更新接口使用说明.md)

---

## 🔨 打包为 exe

```bash
# 安装打包工具
pip install pyinstaller

# 执行打包
打包.bat
```

打包完成后在 `dist/情侣相册/` 目录生成可执行文件。

### 打包安装程序

```bash
# 先打包主程序
打包.bat

# 再打包安装程序
pyinstaller --noconfirm --name "情侣相册安装程序" \
    --add-data "dist/情侣相册;dist/情侣相册" \
    --add-data "icon.ico;." \
    --windowed --clean --icon "icon.ico" \
    installer.py
```

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python + http.server |
| 前端 | 原生 HTML / CSS / JavaScript |
| 桌面窗口 | pywebview（Edge WebView2） |
| 打包 | PyInstaller |
| 视频处理 | ffmpeg |

---

## 📄 License

MIT License
