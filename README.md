# 💕 情侣相册

一款基于 Python + pywebview 的本地情侣相册桌面应用，支持照片/视频管理和音乐播放。

## ✨ 功能

- 📷 **照片/视频管理** — 创建相册，导入照片和视频，支持瀑布流浏览
- 🎵 **音乐播放** — 导入本地音乐，支持顺序/随机/单曲循环播放
- 🔧 **管理面板** — 创建相册、导入文件、编辑信息、删除管理
- ❤️ **收藏功能** — 收藏喜欢的照片
- ✏️ **自定义名称** — 可以给应用改名，显示在标题栏
- 🖼️ **视频缩略图** — 自动为视频生成缩略图（需要 ffmpeg）
- 🔄 **扫描同步** — 手动放入 storage 文件夹的文件，一键扫描即可识别；手动删除的文件也会自动清理记录

## 📋 环境要求

- Python 3.8+
- Windows 10/11（使用 Edge WebView2 渲染界面）
- ffmpeg（用于视频缩略图生成，需自行下载）

### 📥 下载 ffmpeg

由于 ffmpeg 文件较大（超过 25MB），无法直接上传到 GitHub。请自行下载：

1. 访问 [ffmpeg 官网](https://www.gyan.dev/ffmpeg/builds/) 或 [ffmpeg 下载页](https://ffmpeg.org/download.html)
2. 下载 Windows 版本的 ffmpeg（推荐 `ffmpeg-release-essentials.zip`）
3. 解压后找到 `ffmpeg.exe` 文件
4. 将其放入项目根目录下的 `ffmpeg` 文件夹中（没有就新建一个）

最终路径应该是：`项目根目录/ffmpeg/ffmpeg.exe`

## 🚀 安装运行

### 方法一：直接运行源码

```bash
# 安装依赖
pip install pywebview

# 启动程序
python src/app.py
```

或者双击 `启动.bat`

### 方法二：使用安装包

双击 `情侣相册安装程序.exe`，选择安装目录，安装完成后桌面会创建快捷方式。

### 方法三：免安装版

直接运行 `情侣相册.exe`（需确保 `情侣相册.exe` 和 `_internal` 文件夹在同一目录）。

## 📁 目录结构

```
情侣相册/
├── src/
│   └── app.py          # 后端主程序
├── ffmpeg/
│   └── ffmpeg.exe      # 视频处理工具
├── storage/            # 数据目录（自动生成）
│   ├── photos/         # 照片和视频
│   ├── music/          # 音乐文件
│   ├── thumbnails/     # 视频缩略图
│   └── metadata.json   # 元数据
├── index.html          # 前端界面
├── icon.ico            # 应用图标
├── requirements.txt    # Python 依赖
├── 启动.bat            # 启动脚本
├── 打包.bat            # 打包脚本
└── installer.py        # 安装程序
```

## 🔨 打包为 exe

```bash
# 安装打包工具
pip install pyinstaller

# 执行打包
打包.bat
```

打包完成后在 `dist/情侣相册/` 目录中生成可执行文件。

## 📦 打包安装包

```bash
# 先打包主程序（生成 dist/情侣相册/）
打包.bat

# 再打包安装程序
pyinstaller --noconfirm --name "情侣相册安装程序" \
    --add-data "dist/情侣相册;dist/情侣相册" \
    --add-data "icon.ico;." \
    --windowed --clean --icon "icon.ico" \
    installer.py
```

## 📝 技术栈

- **后端**: Python + http.server
- **前端**: 原生 HTML/CSS/JavaScript
- **桌面窗口**: pywebview (Edge WebView2)
- **打包**: PyInstaller
- **视频处理**: ffmpeg

## 📄 License

MIT License
