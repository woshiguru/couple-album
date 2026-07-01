"""
情侣相册 - 安装程序
用 tkinter 做界面，选择安装目录，复制文件，创建桌面快捷方式
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

# PyInstaller 打包后的资源路径
def get_resource_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def get_self_dir():
    """安装包自身所在目录（包含要安装的文件）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def create_shortcut(target_path, shortcut_path, icon_path, working_dir):
    """创建桌面快捷方式 (.lnk)"""
    # 使用 PowerShell 创建快捷方式
    ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{shortcut_path}')
$sc.TargetPath = '{target_path}'
$sc.WorkingDirectory = '{working_dir}'
$sc.IconLocation = '{icon_path},0'
$sc.Description = '情侣相册'
$sc.Save()
'''
    subprocess.run(
        ['powershell', '-NoProfile', '-Command', ps_script],
        capture_output=True, timeout=10
    )


def install_app(install_dir, progress_callback=None):
    """执行安装"""
    install_dir = Path(install_dir)
    app_dir = install_dir / "情侣相册"
    source_dir = get_self_dir()

    # 要复制的文件和目录（从安装包同级目录 dist 中取）
    dist_dir = source_dir / "dist" / "情侣相册"
    if not dist_dir.exists():
        # 如果 dist 不存在，尝试从 _MEIPASS 中找
        dist_dir = get_resource_dir() / "dist" / "情侣相册"

    if not dist_dir.exists():
        raise FileNotFoundError(f"找不到安装文件: {dist_dir}")

    # 创建安装目录
    app_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制主程序文件
    items_to_copy = []
    for item in dist_dir.iterdir():
        items_to_copy.append(item)

    total = len(items_to_copy)
    for i, item in enumerate(items_to_copy):
        dest = app_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
        if progress_callback:
            progress_callback(i + 1, total, f"正在复制: {item.name}")

    # 2. 创建 storage 目录结构（如果不存在）
    storage_dir = app_dir / "storage"
    storage_dir.mkdir(exist_ok=True)
    (storage_dir / "photos").mkdir(exist_ok=True)
    (storage_dir / "music").mkdir(exist_ok=True)
    (storage_dir / "thumbnails").mkdir(exist_ok=True)

    # 创建初始 metadata.json（如果不存在）
    metadata_file = storage_dir / "metadata.json"
    if not metadata_file.exists():
        import json
        metadata = {
            "albums": [],
            "music": [],
            "lastUpdated": "",
            "version": "1.0.0",
            "appName": "情侣相册"
        }
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(total, total, "创建桌面快捷方式...")

    # 3. 创建桌面快捷方式
    desktop = Path(os.path.join(os.environ['USERPROFILE'], 'Desktop'))
    shortcut_path = desktop / "情侣相册.lnk"
    exe_path = app_dir / "情侣相册.exe"
    icon_path = app_dir / "_internal" / "icon.ico"

    # 如果 _internal 里没有 icon，用安装包自带的
    if not icon_path.exists():
        icon_path = get_resource_dir() / "icon.ico"
    if not icon_path.exists():
        icon_path = exe_path  # fallback 用 exe 自带图标

    create_shortcut(str(exe_path), str(shortcut_path), str(icon_path), str(app_dir))

    return app_dir


# ============================================================
# GUI 界面
# ============================================================

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("情侣相册 - 安装程序")
    root.geometry("520x380")
    root.resizable(False, False)
    root.configure(bg="#fff0f5")

    # 尝试设置图标
    try:
        icon_path = get_resource_dir() / "icon.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except:
        pass

    # ===== 标题区域 =====
    title_frame = tk.Frame(root, bg="#ff5c7a", height=70)
    title_frame.pack(fill='x')
    title_frame.pack_propagate(False)

    tk.Label(
        title_frame, text="💕 情侣相册", font=("Microsoft YaHei", 20, "bold"),
        fg="white", bg="#ff5c7a"
    ).pack(pady=15)

    # ===== 内容区域 =====
    content = tk.Frame(root, bg="#fff0f5")
    content.pack(fill='both', expand=True, padx=30, pady=15)

    tk.Label(
        content, text="欢迎安装情侣相册桌面版",
        font=("Microsoft YaHei", 12), bg="#fff0f5", fg="#333"
    ).pack(pady=(5, 15))

    # 安装路径
    path_frame = tk.Frame(content, bg="#fff0f5")
    path_frame.pack(fill='x', pady=5)

    tk.Label(
        path_frame, text="安装位置:", font=("Microsoft YaHei", 10),
        bg="#fff0f5", fg="#555"
    ).pack(anchor='w')

    entry_frame = tk.Frame(path_frame, bg="#fff0f5")
    entry_frame.pack(fill='x', pady=(3, 0))

    default_path = os.path.join(os.environ.get('USERPROFILE', 'C:\\Users'), '情侣相册')
    path_var = tk.StringVar(value=default_path)

    path_entry = tk.Entry(
        entry_frame, textvariable=path_var, font=("Microsoft YaHei", 10),
        relief='solid', bd=1
    )
    path_entry.pack(side='left', fill='x', expand=True, ipady=4)

    def browse_dir():
        folder = filedialog.askdirectory(
            initialdir=os.path.dirname(path_var.get()),
            title="选择安装位置"
        )
        if folder:
            path_var.set(os.path.join(folder, "情侣相册"))

    browse_btn = tk.Button(
        entry_frame, text="浏览", command=browse_dir,
        font=("Microsoft YaHei", 9), bg="#f0f0f0", relief='solid', bd=1,
        cursor='hand2'
    )
    browse_btn.pack(side='right', padx=(8, 0), ipady=2)

    # 进度
    progress_label = tk.Label(
        content, text="", font=("Microsoft YaHei", 9),
        bg="#fff0f5", fg="#888"
    )
    progress_label.pack(pady=(15, 3))

    progress_bar = tk.Frame(content, bg="#eee", height=8, highlightthickness=0)
    progress_bar.pack(fill='x', pady=(0, 5))

    progress_fill = tk.Frame(progress_bar, bg="#ff5c7a", height=8, width=0)
    progress_fill.pack(side='left')

    # ===== 按钮区域 =====
    btn_frame = tk.Frame(root, bg="#fff0f5")
    btn_frame.pack(fill='x', padx=30, pady=(0, 20))

    def start_install():
        install_dir = path_var.get().strip()
        if not install_dir:
            messagebox.showwarning("提示", "请选择安装位置")
            return

        # 禁用按钮
        install_btn.config(state='disabled', text="安装中...")
        browse_btn.config(state='disabled')

        def update_progress(current, total, msg):
            pct = current / total if total > 0 else 0
            bar_width = int(460 * pct)
            progress_fill.config(width=bar_width)
            progress_label.config(text=f"{msg}  ({current}/{total})")
            root.update_idletasks()

        try:
            app_dir = install_app(install_dir, update_progress)

            progress_fill.config(width=460)
            progress_label.config(text="安装完成！")
            root.update_idletasks()

            messagebox.showinfo(
                "安装完成",
                f"情侣相册已安装到:\n{app_dir}\n\n桌面已创建快捷方式「情侣相册」"
            )
            root.destroy()

        except Exception as e:
            messagebox.showerror("安装失败", str(e))
            install_btn.config(state='normal', text="开始安装")
            browse_btn.config(state='normal')

    install_btn = tk.Button(
        btn_frame, text="开始安装", command=start_install,
        font=("Microsoft YaHei", 12, "bold"),
        bg="#ff5c7a", fg="white", relief='flat',
        cursor='hand2', width=15, height=1
    )
    install_btn.pack(side='right')

    cancel_btn = tk.Button(
        btn_frame, text="取消", command=root.destroy,
        font=("Microsoft YaHei", 10),
        bg="#e0e0e0", fg="#555", relief='flat',
        cursor='hand2', width=8, height=1
    )
    cancel_btn.pack(side='right', padx=(0, 10))

    root.mainloop()


if __name__ == '__main__':
    run_gui()
