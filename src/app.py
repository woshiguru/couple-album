"""
情侣相册 - 桌面版
使用 pywebview 创建原生窗口，内置 HTTP 服务器
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import zipfile
from pathlib import Path
from urllib.parse import unquote

# 设置 UTF-8 输出（windowed 模式下 stdout 可能为 None）
if sys.stdout is not None and sys.stdout.encoding != 'utf-8':
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except AttributeError:
        pass
elif sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

# 获取应用根目录（兼容打包后和开发环境）
def get_app_dir():
    if getattr(sys, 'frozen', False):
        # 打包后的环境
        return Path(sys._MEIPASS)
    else:
        # 开发环境，app.py 在 src/ 里，index.html 在上一级
        return Path(__file__).parent.parent

def get_storage_dir():
    """获取存储目录"""
    if getattr(sys, 'frozen', False):
        # 打包后，storage 在 exe 同级目录
        return Path(os.path.dirname(sys.executable)) / "storage"
    else:
        # 开发环境，app.py 在 src/ 里，storage 在上一级
        return Path(__file__).parent.parent / "storage"

def get_ffmpeg_path():
    """获取 ffmpeg 路径"""
    app_dir = get_app_dir()
    ffmpeg_dir = app_dir / "ffmpeg"

    # 查找 ffmpeg.exe
    if ffmpeg_dir.exists():
        for item in ffmpeg_dir.rglob("ffmpeg.exe"):
            return str(item)

    # 尝试系统路径
    return "ffmpeg"

APP_DIR = get_app_dir()
STORAGE_DIR = get_storage_dir()
FFMPEG_PATH = get_ffmpeg_path()
THUMBNAIL_DIR = STORAGE_DIR / "thumbnails"
METADATA_FILE = STORAGE_DIR / "metadata.json"
OVERLAY_DIR = STORAGE_DIR / "overlay"
UPDATES_DIR = STORAGE_DIR / "updates"

# HTTP 服务器端口
PORT = 18080

# 全局窗口引用（用于改名后自动重启）
_window = None


class JsApi:
    """暴露给前端JS的接口 - 本地文件操作"""
    def restart_app(self):
        """重启程序以更新窗口标题"""
        if sys.executable:
            subprocess.Popen([sys.executable] + sys.argv)
        else:
            subprocess.Popen(sys.argv)
        os._exit(0)

    def upload_photos(self, album_name):
        """弹出文件选择框，上传照片/视频到指定相册"""
        try:
            import webview
            if _window is None:
                return {'success': False, 'error': '窗口未就绪'}

            result = _window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=['图片和视频文件 (*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp;*.mp4;*.mov;*.avi;*.mkv)']
            )

            if not result:
                return {'success': False, 'error': '未选择文件'}

            file_paths = [f for f in result if isinstance(f, str)]

            if not file_paths:
                return {'success': False, 'error': '未选择文件'}

            metadata = load_metadata()
            target_album = None
            for album in metadata.get('albums', []):
                if album['name'] == album_name:
                    target_album = album
                    break
            if not target_album:
                return {'success': False, 'error': '相册不存在'}

            all_ids = []
            for a in metadata.get('albums', []):
                for p in a.get('photos', []):
                    try:
                        all_ids.append(int(p['id'].replace('photo_', '')))
                    except (ValueError, KeyError):
                        pass
            next_id = max(all_ids) + 1 if all_ids else 1

            album_dir = STORAGE_DIR / "photos" / album_name
            album_dir.mkdir(parents=True, exist_ok=True)

            uploaded = 0
            for fpath in file_paths:
                src = Path(fpath)
                if not src.exists():
                    continue
                filename = src.name
                target = album_dir / filename
                counter = 1
                while target.exists():
                    stem, ext = os.path.splitext(filename)
                    filename = f"{stem}_{counter}{ext}"
                    target = album_dir / filename
                    counter += 1

                shutil.copy2(str(src), str(target))

                ext = os.path.splitext(filename)[1].lower()
                photo_type = 'video' if ext in ['.mp4', '.mov', '.avi', '.mkv'] else 'image'

                if photo_type == 'video':
                    generate_single_thumbnail(album_name, filename)

                photo_entry = {
                    'id': f'photo_{next_id}',
                    'filename': filename,
                    'description': '',
                    'tags': [],
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'favorite': False,
                    'type': photo_type,
                    'size': target.stat().st_size,
                    'path': f'photos/{album_name}/{filename}'
                }
                target_album['photos'].append(photo_entry)
                uploaded += 1
                next_id += 1

            save_metadata(metadata)
            return {'success': True, 'uploaded': uploaded}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def upload_music(self):
        """弹出文件选择框，上传音乐"""
        try:
            import webview
            if _window is None:
                return {'success': False, 'error': '窗口未就绪'}

            result = _window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=['音乐文件 (*.mp3;*.wav;*.flac;*.aac;*.ogg;*.m4a;*.wma)']
            )

            if not result:
                return {'success': False, 'error': '未选择文件'}

            file_paths = [f for f in result if isinstance(f, str)]

            if not file_paths:
                return {'success': False, 'error': '未选择文件'}

            metadata = load_metadata()
            music_dir = STORAGE_DIR / "music"
            music_dir.mkdir(parents=True, exist_ok=True)

            uploaded = 0
            for fpath in file_paths:
                src = Path(fpath)
                if not src.exists():
                    continue
                filename = src.name
                target = music_dir / filename
                counter = 1
                while target.exists():
                    stem, ext = os.path.splitext(filename)
                    filename = f"{stem}_{counter}{ext}"
                    target = music_dir / filename
                    counter += 1

                shutil.copy2(str(src), str(target))

                music_id = f"music_{int(time.time() * 1000)}_{uploaded}"
                music_entry = {
                    'id': music_id,
                    'filename': filename,
                    'name': os.path.splitext(filename)[0],
                    'path': f'music/{filename}',
                    'size': target.stat().st_size,
                }
                metadata.setdefault('music', []).append(music_entry)
                uploaded += 1

            save_metadata(metadata)
            return {'success': True, 'uploaded': uploaded}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_photo(self, album_name, photo_id):
        """删除照片/视频文件及元数据"""
        try:
            metadata = load_metadata()
            for album in metadata.get('albums', []):
                if album['name'] == album_name:
                    for i, photo in enumerate(album.get('photos', [])):
                        if photo['id'] == photo_id:
                            file_path = STORAGE_DIR / "photos" / album_name / photo['filename']
                            if file_path.exists():
                                file_path.unlink()
                            # 删除视频缩略图
                            if photo.get('type') == 'video':
                                thumb_name = f"{album_name}_{photo['filename']}.jpg"
                                thumb_path = THUMBNAIL_DIR / thumb_name
                                if thumb_path.exists():
                                    thumb_path.unlink()
                            album['photos'].pop(i)
                            save_metadata(metadata)
                            return {'success': True}
            return {'success': False, 'error': '照片不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def sync_files(self):
        """扫描 storage 文件夹，同步新增和删除的文件"""
        try:
            metadata = load_metadata()

            deleted_music_count = 0
            deleted_photo_count = 0
            deleted_video_count = 0
            deleted_album_count = 0
            new_music_count = 0
            new_photo_count = 0
            new_video_count = 0
            new_album_count = 0

            music_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            video_extensions = {'.mp4', '.mov', '.avi', '.mkv'}
            media_extensions = image_extensions | video_extensions

            # ============================================
            # 第一步：检测删除
            # ============================================

            # 1. 检测被删除的音乐
            music_dir = STORAGE_DIR / "music"
            music_list = metadata.get('music', [])
            surviving_music = []
            for m in music_list:
                fpath = STORAGE_DIR / m['path']
                if fpath.exists():
                    surviving_music.append(m)
                else:
                    deleted_music_count += 1
            metadata['music'] = surviving_music

            # 2. 检测被删除的相册（整个文件夹消失）和其中的照片/视频
            photos_dir = STORAGE_DIR / "photos"
            surviving_albums = []
            for album in metadata.get('albums', []):
                album_folder = photos_dir / album['name']
                if not album_folder.exists():
                    # 整个相册文件夹没了 → 整个相册删除
                    deleted_album_count += 1
                    for p in album.get('photos', []):
                        if p.get('type') == 'video':
                            deleted_video_count += 1
                            # 同时清理缩略图
                            thumb_name = f"{album['name']}_{p['filename']}.jpg"
                            thumb_path = THUMBNAIL_DIR / thumb_name
                            if thumb_path.exists():
                                thumb_path.unlink()
                        else:
                            deleted_photo_count += 1
                else:
                    # 相册文件夹还在，检查里面的单个文件是否被删
                    surviving_photos = []
                    for p in album.get('photos', []):
                        fpath = album_folder / p['filename']
                        if fpath.exists():
                            surviving_photos.append(p)
                        else:
                            if p.get('type') == 'video':
                                deleted_video_count += 1
                                thumb_name = f"{album['name']}_{p['filename']}.jpg"
                                thumb_path = THUMBNAIL_DIR / thumb_name
                                if thumb_path.exists():
                                    thumb_path.unlink()
                            else:
                                deleted_photo_count += 1
                    album['photos'] = surviving_photos
                    surviving_albums.append(album)
            metadata['albums'] = surviving_albums

            # ============================================
            # 第二步：检测新增
            # ============================================

            # 3. 检测新增音乐
            existing_music_files = set(m.get('filename', '') for m in metadata.get('music', []))
            if music_dir.exists():
                for f in music_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in music_extensions:
                        if f.name not in existing_music_files:
                            music_id = f"music_{int(time.time() * 1000)}_{new_music_count}"
                            metadata.setdefault('music', []).append({
                                'id': music_id,
                                'filename': f.name,
                                'name': f.stem,
                                'path': f'music/{f.name}',
                                'size': f.stat().st_size,
                            })
                            new_music_count += 1

            # 4. 检测新增相册和照片/视频
            if photos_dir.exists():
                existing_album_names = set(a['name'] for a in metadata.get('albums', []))

                for album_dir in photos_dir.iterdir():
                    if not album_dir.is_dir():
                        continue
                    album_name = album_dir.name

                    # 找已有相册
                    target_album = None
                    for album in metadata.get('albums', []):
                        if album['name'] == album_name:
                            target_album = album
                            break

                    # 新相册文件夹 → 自动创建
                    if not target_album:
                        target_album = {
                            'name': album_name,
                            'description': '',
                            'photos': [],
                            'createdDate': datetime.now().strftime('%Y-%m-%d')
                        }
                        metadata.setdefault('albums', []).append(target_album)
                        new_album_count += 1

                    # 已有的文件名
                    existing_photo_files = set(p.get('filename', '') for p in target_album.get('photos', []))

                    # 获取最大 photo id
                    all_ids = []
                    for a in metadata.get('albums', []):
                        for p in a.get('photos', []):
                            try:
                                all_ids.append(int(p['id'].replace('photo_', '')))
                            except (ValueError, KeyError):
                                pass
                    next_id = max(all_ids) + 1 if all_ids else 1

                    # 扫描新文件
                    for f in album_dir.iterdir():
                        if not f.is_file() or f.suffix.lower() not in media_extensions:
                            continue
                        if f.name in existing_photo_files:
                            continue

                        ext = f.suffix.lower()
                        photo_type = 'video' if ext in video_extensions else 'image'

                        if photo_type == 'video':
                            generate_single_thumbnail(album_name, f.name)
                            new_video_count += 1
                        else:
                            new_photo_count += 1

                        target_album['photos'].append({
                            'id': f'photo_{next_id}',
                            'filename': f.name,
                            'description': '',
                            'tags': [],
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'favorite': False,
                            'type': photo_type,
                            'size': f.stat().st_size,
                            'path': f'photos/{album_name}/{f.name}'
                        })
                        next_id += 1

            save_metadata(metadata)

            return {
                'success': True,
                'newMusic': new_music_count,
                'newPhotos': new_photo_count,
                'newVideos': new_video_count,
                'newAlbums': new_album_count,
                'deletedMusic': deleted_music_count,
                'deletedPhotos': deleted_photo_count,
                'deletedVideos': deleted_video_count,
                'deletedAlbums': deleted_album_count
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_music(self, music_id):
        """删除音乐文件及元数据"""
        try:
            metadata = load_metadata()
            music_list = metadata.get('music', [])
            for i, music in enumerate(music_list):
                if music['id'] == music_id or music.get('filename') == music_id:
                    file_path = STORAGE_DIR / "music" / music['filename']
                    if file_path.exists():
                        file_path.unlink()
                    music_list.pop(i)
                    save_metadata(metadata)
                    return {'success': True}
            return {'success': False, 'error': '音乐不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ===== 收藏夹功能 =====

    def get_collections(self):
        """获取所有收藏夹"""
        try:
            metadata = load_metadata()
            return metadata.get('collections', [])
        except Exception as e:
            return []

    def create_collection(self, name, description=''):
        """创建收藏夹"""
        try:
            name = name.strip()
            if not name:
                return {'success': False, 'error': '收藏夹名称不能为空'}
            metadata = load_metadata()
            collections = metadata.setdefault('collections', [])
            for c in collections:
                if c['name'] == name:
                    return {'success': False, 'error': f'收藏夹已存在：{name}'}
            new_collection = {
                'id': f'collection_{int(time.time() * 1000)}',
                'name': name,
                'description': description,
                'photoIds': [],
                'createdDate': get_current_time()
            }
            collections.append(new_collection)
            save_metadata(metadata)
            return {'success': True, 'collection': new_collection}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_collection(self, collection_id):
        """删除收藏夹"""
        try:
            metadata = load_metadata()
            collections = metadata.get('collections', [])
            for i, c in enumerate(collections):
                if c['id'] == collection_id:
                    collections.pop(i)
                    save_metadata(metadata)
                    return {'success': True}
            return {'success': False, 'error': '收藏夹不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def rename_collection(self, collection_id, new_name):
        """重命名收藏夹"""
        try:
            new_name = new_name.strip()
            if not new_name:
                return {'success': False, 'error': '名称不能为空'}
            metadata = load_metadata()
            for c in metadata.get('collections', []):
                if c['id'] == collection_id:
                    c['name'] = new_name
                    save_metadata(metadata)
                    return {'success': True}
            return {'success': False, 'error': '收藏夹不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_photo_to_collection(self, collection_id, album_name, photo_id):
        """把照片加入收藏夹"""
        try:
            metadata = load_metadata()
            for c in metadata.get('collections', []):
                if c['id'] == collection_id:
                    entry = {'album': album_name, 'photoId': photo_id}
                    for existing in c.get('photoIds', []):
                        if existing.get('album') == album_name and existing.get('photoId') == photo_id:
                            return {'success': True, 'message': '已在收藏夹中'}
                    c.setdefault('photoIds', []).append(entry)
                    save_metadata(metadata)
                    return {'success': True}
            return {'success': False, 'error': '收藏夹不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def remove_photo_from_collection(self, collection_id, album_name, photo_id):
        """从收藏夹移除照片"""
        try:
            metadata = load_metadata()
            for c in metadata.get('collections', []):
                if c['id'] == collection_id:
                    c['photoIds'] = [
                        p for p in c.get('photoIds', [])
                        if not (p.get('album') == album_name and p.get('photoId') == photo_id)
                    ]
                    save_metadata(metadata)
                    return {'success': True}
            return {'success': False, 'error': '收藏夹不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def remove_photo_from_all_collections(self, album_name, photo_id):
        """把照片从所有收藏夹中移除"""
        try:
            metadata = load_metadata()
            removed_count = 0
            for c in metadata.get('collections', []):
                original = len(c.get('photoIds', []))
                c['photoIds'] = [
                    p for p in c.get('photoIds', [])
                    if not (p.get('album') == album_name and p.get('photoId') == photo_id)
                ]
                removed_count += original - len(c['photoIds'])
            save_metadata(metadata)
            return {'success': True, 'removedCount': removed_count}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def migrate_old_favorites(self):
        """把旧版 favorite:true 的照片迁移到"我的收藏"收藏夹"""
        try:
            metadata = load_metadata()
            if metadata.get('_favoritesMigrated'):
                return
            old_favs = []
            for album in metadata.get('albums', []):
                for photo in album.get('photos', []):
                    if photo.get('favorite'):
                        old_favs.append({'album': album['name'], 'photoId': photo['id']})
            if old_favs:
                collections = metadata.setdefault('collections', [])
                collections.append({
                    'id': f'collection_{int(time.time() * 1000)}',
                    'name': '我的收藏',
                    'description': '从旧版收藏自动迁移',
                    'photoIds': old_favs,
                    'createdDate': get_current_time()
                })
            metadata['_favoritesMigrated'] = True
            save_metadata(metadata)
        except Exception as e:
            print(f"迁移旧收藏失败: {e}")

    # ===== 更新功能 =====

    def check_update(self):
        """扫描更新文件夹，返回最新可用更新"""
        try:
            if not UPDATES_DIR.exists():
                return {'hasUpdate': False, 'currentVersion': get_current_version()}
            metadata = load_metadata()
            current_version = metadata.get('version', '1.0.0')
            best_zip = None
            best_version = None
            best_meta = {}
            for f in UPDATES_DIR.iterdir():
                if not f.suffix.lower() == '.zip':
                    continue
                zip_version = None
                zip_meta = {}
                stem = f.stem
                if stem.startswith('update_'):
                    stem_version = stem[7:]
                    if stem_version.replace('.', '').isdigit():
                        zip_version = stem_version
                try:
                    with zipfile.ZipFile(str(f), 'r') as zf:
                        if 'update.json' in zf.namelist():
                            info = zf.read('update.json')
                            zip_meta = json.loads(info.decode('utf-8'))
                            if 'version' in zip_meta:
                                zip_version = zip_meta['version']
                except Exception:
                    pass
                if zip_version and _version_gt(zip_version, current_version):
                    if best_version is None or _version_gt(zip_version, best_version):
                        best_zip = f
                        best_version = zip_version
                        best_meta = zip_meta
            if best_zip is None:
                return {'hasUpdate': False, 'currentVersion': current_version}
            return {
                'hasUpdate': True,
                'currentVersion': current_version,
                'newVersion': best_version,
                'description': best_meta.get('description', ''),
                'packageName': best_zip.name
            }
        except Exception as e:
            return {'hasUpdate': False, 'error': str(e)}

    def apply_update(self):
        """应用更新：备份、解压、替换"""
        try:
            check = self.check_update()
            if not check.get('hasUpdate'):
                return {'success': False, 'error': '没有可用的更新包'}
            pkg_path = UPDATES_DIR / check['packageName']
            app_dir = get_app_dir()
            is_frozen = getattr(sys, 'frozen', False)

            # 创建备份
            backup_dir = UPDATES_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            if is_frozen:
                exe_src = Path(sys.executable)
                shutil.copy2(str(exe_src), str(backup_dir / exe_src.name))
            else:
                src_file = Path(__file__)
                shutil.copy2(str(src_file), str(backup_dir / src_file.name))
            html_src = APP_DIR / "index.html"
            if html_src.exists():
                shutil.copy2(str(html_src), str(backup_dir / "index.html"))
            with open(backup_dir / "backup_info.json", 'w', encoding='utf-8') as f:
                json.dump({
                    'backupTime': get_current_time(),
                    'fromVersion': check['currentVersion'],
                    'toVersion': check['newVersion'],
                    'isFrozen': is_frozen
                }, f, ensure_ascii=False, indent=2)

            # 解压更新包
            with zipfile.ZipFile(str(pkg_path), 'r') as zf:
                zf.extractall(str(UPDATES_DIR / 'temp_extract'))
            extract_dir = UPDATES_DIR / 'temp_extract'
            update_meta_path = extract_dir / 'update.json'
            files_to_update = []
            new_version = check['newVersion']
            update_description = check.get('description', '')
            if update_meta_path.exists():
                with open(update_meta_path, 'r', encoding='utf-8') as f:
                    update_meta = json.load(f)
                    files_to_update = update_meta.get('files', [])
                    new_version = update_meta.get('version', new_version)
                    update_description = update_meta.get('description', update_description)
            else:
                for item in extract_dir.iterdir():
                    if item.name != 'update.json':
                        files_to_update.append({'path': item.name, 'action': 'replace'})

            # 更新 metadata.json 里的版本号
            metadata = load_metadata()
            metadata['version'] = new_version
            metadata['lastUpdateDescription'] = update_description
            save_metadata(metadata)

            # 判断是否需要替换 exe
            exe_target = None
            if is_frozen:
                exe_name = Path(sys.executable).name
                for fi in files_to_update:
                    if Path(fi['path']).name == exe_name:
                        exe_target = fi
                        break
            if exe_target:
                new_exe = extract_dir / exe_target['path']
                if new_exe.exists():
                    temp_exe = UPDATES_DIR / f"new_{Path(sys.executable).name}"
                    shutil.copy2(str(new_exe), str(temp_exe))
                    helper = _create_update_helper(temp_exe, UPDATES_DIR, extract_dir)
                    self.restart_with_helper(helper)
                    return {'success': True, 'restarting': True, 'message': '正在更新，程序将自动重启'}
            else:
                for fi in files_to_update:
                    src = extract_dir / fi['path']
                    if not src.exists() or not src.is_file():
                        continue
                    if is_frozen:
                        # 打包模式：静态文件写入 overlay，下次启动时优先读取
                        dst = OVERLAY_DIR / fi['path']
                    else:
                        # 开发模式：直接替换源文件
                        dst = app_dir / fi['path']
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                _cleanup(extract_dir)
                # 非 exe 更新，延迟重启让响应先返回给浏览器
                threading.Timer(0.5, self.restart_app).start()
                return {'success': True, 'restarting': True, 'message': '更新完成，正在重启'}
            return {'success': False, 'error': '更新包中没有可应用的文件'}
        except Exception as e:
            return {'success': False, 'error': f'更新失败：{e}'}

    def rollback_update(self):
        """回滚到上一个版本（从备份恢复）"""
        try:
            if not UPDATES_DIR.exists():
                return {'success': False, 'error': '没有可用的备份'}
            backups = sorted(
                [d for d in UPDATES_DIR.iterdir() if d.is_dir() and d.name.startswith('backup_')],
                key=lambda x: x.name, reverse=True
            )
            if not backups:
                return {'success': False, 'error': '没有找到备份'}
            latest_backup = backups[0]
            app_dir = get_app_dir()
            is_frozen = getattr(sys, 'frozen', False)
            if is_frozen:
                exe_name = Path(sys.executable).name
                backup_exe = latest_backup / exe_name
                if backup_exe.exists():
                    temp_exe = UPDATES_DIR / f"rollback_{exe_name}"
                    shutil.copy2(str(backup_exe), str(temp_exe))
                    helper = _create_update_helper(temp_exe, UPDATES_DIR, None)
                    self.restart_with_helper(helper)
                    return {'success': True, 'restarting': True, 'message': '正在回滚，程序将自动重启'}
            else:
                app_py_backup = latest_backup / "app.py"
                if app_py_backup.exists():
                    shutil.copy2(str(app_py_backup), str(Path(__file__)))
                html_backup = latest_backup / "index.html"
                if html_backup.exists():
                    shutil.copy2(str(html_backup), str(app_dir / "index.html"))
                threading.Timer(0.5, self.restart_app).start()
                return {'success': True, 'restarting': True, 'message': '回滚完成，正在重启'}
            return {'success': False, 'error': '备份文件中没有可恢复的程序'}
        except Exception as e:
            return {'success': False, 'error': f'回滚失败：{e}'}

    def restart_with_helper(self, helper_path):
        """用辅助脚本重启（用于 exe 替换场景）"""
        import subprocess
        if sys.platform == 'win32':
            subprocess.Popen([str(helper_path)], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen(['bash', str(helper_path)])
        os._exit(0)


class AlbumRequestHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def do_GET(self):
        path = self.path

        # 根路径返回 index.html（覆盖层优先）
        if path == '/':
            override_index = OVERLAY_DIR / "index.html"
            if override_index.exists():
                return self.serve_file(override_index)
            self.path = '/index.html'
            return super().do_GET()
        # /api/status - 系统状态
        if path == '/api/status':
            return self.handle_api_status()

        # /api/albums - 获取所有相册
        if path == '/api/albums':
            return self.handle_api_albums()

        # /api/photos - 获取所有照片
        if path == '/api/photos':
            return self.handle_api_photos()

        # /api/music - 获取所有音乐
        if path == '/api/music':
            return self.handle_api_music()

        # /api/collections - 获取所有收藏夹
        if path == '/api/collections':
            return self.handle_api_collections()

        # /api/admin/update/check - 检查更新
        if path == '/api/admin/update/check':
            return self.handle_check_update()

        # /photos/... - 照片/视频文件
        if path.startswith('/photos/'):
            return self.handle_photo_file(path)

        # /music/... - 音乐文件
        if path.startswith('/music/'):
            return self.handle_music_file(path)

        # /thumbnails/... - 缩略图文件
        if path.startswith('/thumbnails/'):
            return self.handle_thumbnail_file(path)

        # 其他静态文件（覆盖层优先）
        if path.startswith('/overlay/'):
            relative = unquote(path[9:])
            file_path = OVERLAY_DIR / relative
            return self.serve_file(file_path)
        return super().do_GET()

    def do_POST(self):
        path = self.path

        # /api/admin/rename - 修改应用名称
        if path == '/api/admin/rename':
            return self.handle_rename()

        # /api/admin/albums - 创建相册
        if path == '/api/admin/albums':
            return self.handle_create_album()

        # /api/admin/collections - 创建收藏夹
        if path == '/api/admin/collections':
            return self.handle_create_collection()

        # /api/admin/collections/{id}/photos - 加入收藏夹
        if path.startswith('/api/admin/collections/') and path.endswith('/photos'):
            return self.handle_add_photo_to_collection(path)

        # /api/admin/photos/{album}/{photoId}/unfavorite - 从所有收藏夹移除
        if path.startswith('/api/admin/photos/') and path.endswith('/unfavorite'):
            return self.handle_unfavorite_photo(path)

        # /api/admin/update/apply - 应用更新
        if path == '/api/admin/update/apply':
            return self.handle_apply_update()

        # /api/admin/update/rollback - 回滚
        if path == '/api/admin/update/rollback':
            return self.handle_rollback_update()

        # /api/admin/photos/{album}/{photoId} - 更新照片
        if path.startswith('/api/admin/photos/'):
            return self.handle_update_photo(path)

        self.send_error(404)

    def do_DELETE(self):
        path = self.path

        # /api/admin/albums/{name} - 删除相册
        if path.startswith('/api/admin/albums/'):
            return self.handle_delete_album(path)

        # /api/admin/collections/{id}/photos/{album}/{photoId} - 从收藏夹移除
        if path.startswith('/api/admin/collections/') and '/photos/' in path:
            return self.handle_remove_photo_from_collection(path)

        # /api/admin/collections/{id} - 删除收藏夹
        if path.startswith('/api/admin/collections/'):
            return self.handle_delete_collection(path)

        self.send_error(404)

    def do_PUT(self):
        path = self.path

        # /api/admin/collections/{id} - 重命名收藏夹
        if path.startswith('/api/admin/collections/'):
            return self.handle_rename_collection(path)

        # /api/admin/photos/{album}/{photoId} - 更新照片
        if path.startswith('/api/admin/photos/'):
            return self.handle_update_photo(path)

        self.send_error(404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error(self, code, message=None, explain=None):
        """覆盖默认错误处理，API 请求返回 JSON 而非 HTML"""
        # 对 API 请求返回 JSON 错误
        if self.path.startswith('/api/'):
            self.send_json({'error': message or '请求错误'}, code)
        else:
            # 静态文件请求仍用默认 HTML 错误页
            super().send_error(code, message, explain)

    def handle_api_status(self):
        metadata = load_metadata()
        total_photos = sum(len(a.get('photos', [])) for a in metadata.get('albums', []))
        self.send_json({
            'albumCount': len(metadata.get('albums', [])),
            'photoCount': total_photos,
            'musicCount': len(metadata.get('music', [])),
            'lastUpdated': metadata.get('lastUpdated', ''),
            'version': metadata.get('version', '1.0.0'),
            'appName': metadata.get('appName', '情侣相册')
        })

    def handle_api_albums(self):
        metadata = load_metadata()
        albums = metadata.get('albums', [])
        # 添加 photoCount 计算属性
        for album in albums:
            album['photoCount'] = len(album.get('photos', []))
        self.send_json(albums)

    def handle_api_photos(self):
        metadata = load_metadata()
        # 构建 photoId → 所在收藏夹列表 的映射
        collections = metadata.get('collections', [])
        photo_collections = {}
        for c in collections:
            for p in c.get('photoIds', []):
                key = (p.get('album', ''), p.get('photoId', ''))
                photo_collections.setdefault(key, []).append({
                    'id': c['id'],
                    'name': c['name']
                })
        all_photos = []
        for album in metadata.get('albums', []):
            for photo in album.get('photos', []):
                photo['album'] = album['name']
                photo['collections'] = photo_collections.get(
                    (album['name'], photo['id']), []
                )
                # 添加缩略图路径
                if photo.get('type') == 'video':
                    thumb_name = f"{album['name']}_{photo['filename']}.jpg"
                    thumb_path = THUMBNAIL_DIR / thumb_name
                    if thumb_path.exists():
                        photo['thumbnail'] = f"/thumbnails/{thumb_name}"
                all_photos.append(photo)
        self.send_json(all_photos)

    def handle_api_music(self):
        metadata = load_metadata()
        self.send_json(metadata.get('music', []))

    def handle_photo_file(self, path):
        # /photos/洛阳/xxx.MP4 -> storage/photos/洛阳/xxx.MP4
        relative = unquote(path[8:])  # 去掉 /photos/ 并解码中文
        file_path = STORAGE_DIR / "photos" / relative
        return self.serve_file(file_path)

    def handle_music_file(self, path):
        relative = unquote(path[7:])  # 去掉 /music/ 并解码中文
        file_path = STORAGE_DIR / "music" / relative
        return self.serve_file(file_path)

    def handle_thumbnail_file(self, path):
        relative = unquote(path[12:])  # 去掉 /thumbnails/ 并解码中文
        file_path = THUMBNAIL_DIR / relative
        return self.serve_file(file_path)

    def serve_file(self, file_path):
        # 覆盖层优先：storage/overlay 中有同名文件就用它
        if OVERLAY_DIR.exists() and str(file_path).startswith(str(STORAGE_DIR)):
            try:
                rel = file_path.relative_to(STORAGE_DIR)
                override = OVERLAY_DIR / rel
                if override.exists() and override.is_file():
                    file_path = override
            except ValueError:
                pass
        if not file_path.exists():
            self.send_error(404)
            return

        # 确定 content type
        ext = file_path.suffix.lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css',
            '.js': 'application/javascript',
        }

        content_type = content_types.get(ext, 'application/octet-stream')

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(file_path.stat().st_size))
        self.send_header('Access-Control-Allow-Origin', '*')

        # 支持视频/音频的 range 请求
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav']:
            self.send_header('Accept-Ranges', 'bytes')

        self.end_headers()

        # 分块读取文件
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (ConnectionResetError, BrokenPipeError):
            # 客户端断开连接，忽略
            pass

    def handle_create_album(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        name = data.get('name', '').strip()
        if not name:
            self.send_json({'error': '相册名称不能为空'}, 400)
            return

        metadata = load_metadata()

        # 检查是否已存在
        for album in metadata.get('albums', []):
            if album['name'] == name:
                self.send_json({'error': f'相册已存在: {name}'}, 400)
                return

        # 创建新相册
        new_album = {
            'name': name,
            'description': data.get('description', ''),
            'photos': [],
            'createdDate': get_current_time()
        }

        metadata.setdefault('albums', []).append(new_album)

        # 创建相册文件夹
        album_dir = STORAGE_DIR / "photos" / name
        album_dir.mkdir(parents=True, exist_ok=True)

        save_metadata(metadata)
        self.send_json(new_album)

    def handle_rename(self):
        """修改应用名称"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        new_name = data.get('name', '').strip()
        if not new_name:
            self.send_json({'error': '名称不能为空'}, 400)
            return

        metadata = load_metadata()
        metadata['appName'] = new_name
        save_metadata(metadata)
        self.send_json({'appName': new_name})

    def handle_update_photo(self, path):
        # /api/admin/photos/{album}/{photoId}
        parts = path.split('/')
        if len(parts) < 6:
            self.send_error(400)
            return

        album_name = unquote(parts[4])
        photo_id = parts[5]

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        metadata = load_metadata()

        for album in metadata.get('albums', []):
            if album['name'] == album_name:
                for photo in album.get('photos', []):
                    if photo['id'] == photo_id:
                        if 'description' in data:
                            photo['description'] = data['description']
                        if 'tags' in data:
                            photo['tags'] = data['tags']
                        save_metadata(metadata)
                        self.send_json(photo)
                        return

        self.send_json({'error': '照片不存在'}, 404)

    def handle_delete_album(self, path):
        # /api/admin/albums/{name}
        parts = path.split('/')
        if len(parts) < 5:
            self.send_error(400)
            return

        album_name = unquote(parts[4])
        metadata = load_metadata()

        metadata['albums'] = [a for a in metadata.get('albums', []) if a['name'] != album_name]
        save_metadata(metadata)

        # 删除文件夹
        album_dir = STORAGE_DIR / "photos" / album_name
        if album_dir.exists():
            shutil.rmtree(album_dir, ignore_errors=True)

        self.send_json({'message': '删除成功'})

    def handle_api_collections(self):
        api = JsApi()
        self.send_json(api.get_collections())

    def handle_check_update(self):
        api = JsApi()
        result = api.check_update()
        self.send_json(result)

    def handle_create_collection(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        name = data.get('name', '').strip()
        description = data.get('description', '')
        api = JsApi()
        result = api.create_collection(name, description)
        if result.get('success'):
            self.send_json(result['collection'])
        else:
            self.send_json(result, 400)

    def handle_delete_collection(self, path):
        # /api/admin/collections/{id}
        parts = path.split('/')
        if len(parts) < 5:
            self.send_error(400)
            return
        collection_id = unquote(parts[4])
        api = JsApi()
        result = api.delete_collection(collection_id)
        self.send_json(result)

    def handle_add_photo_to_collection(self, path):
        # /api/admin/collections/{id}/photos
        parts = path.split('/')
        if len(parts) < 6:
            self.send_error(400)
            return
        collection_id = unquote(parts[4])
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        album_name = data.get('album', '')
        photo_id = data.get('photoId', '')
        api = JsApi()
        result = api.add_photo_to_collection(collection_id, album_name, photo_id)
        self.send_json(result)

    def handle_unfavorite_photo(self, path):
        # /api/admin/photos/{album}/{photoId}/unfavorite
        parts = path.split('/')
        if len(parts) < 6:
            self.send_error(400)
            return
        album_name = unquote(parts[4])
        photo_id = unquote(parts[5])
        api = JsApi()
        result = api.remove_photo_from_all_collections(album_name, photo_id)
        self.send_json(result)

    def handle_remove_photo_from_collection(self, path):
        # /api/admin/collections/{id}/photos/{album}/{photoId}
        parts = path.split('/')
        if len(parts) < 8:
            self.send_error(400)
            return
        collection_id = unquote(parts[4])
        album_name = unquote(parts[6])
        photo_id = unquote(parts[7])
        api = JsApi()
        result = api.remove_photo_from_collection(collection_id, album_name, photo_id)
        self.send_json(result)

    def handle_rename_collection(self, path):
        # /api/admin/collections/{id}
        parts = path.split('/')
        if len(parts) < 5:
            self.send_error(400)
            return
        collection_id = unquote(parts[4])
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        new_name = data.get('name', '')
        api = JsApi()
        result = api.rename_collection(collection_id, new_name)
        self.send_json(result)

    def handle_apply_update(self):
        api = JsApi()
        result = api.apply_update()
        self.send_json(result)

    def handle_rollback_update(self):
        api = JsApi()
        result = api.rollback_update()
        self.send_json(result)

    def log_message(self, format, *args):
        # 减少日志输出
        pass


def load_metadata():
    """加载元数据"""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    return {'albums': [], 'music': [], 'version': '1.0.0'}


def save_metadata(metadata):
    """保存元数据"""
    metadata['lastUpdated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def get_current_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_current_version():
    """获取当前程序版本号"""
    metadata = load_metadata()
    return metadata.get('version', '1.0.0')


def _version_gt(v1, v2):
    """判断版本号 v1 是否大于 v2（如 1.2.0 > 1.1.0）"""
    def parse(v):
        parts = []
        for p in str(v).split('.'):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)
    return parse(v1) > parse(v2)


def _create_update_helper(new_exe, updates_dir, extract_dir):
    """生成 Windows 辅助脚本：等待主程序退出 → 替换 exe → 重启"""
    helper_path = updates_dir / '_update_helper.bat'
    current_exe = Path(sys.executable)
    exe_name = current_exe.name

    lines = [
        '@echo off',
        'chcp 65001 >nul',
        f'timeout /t 2 /nobreak >nul',
        f':wait_loop',
        f'tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I "{exe_name}" >NUL',
        'if errorlevel 0 (',
        '    timeout /t 1 /nobreak >nul',
        '    goto wait_loop',
        ')',
        f'copy /Y "{new_exe}" "{current_exe}" >nul',
        f'start "" "{current_exe}"',
    ]
    if extract_dir:
        lines.append(f'rmdir /s /q "{extract_dir}" >nul 2>&1')
    lines.append(f'del "{helper_path}" >nul 2>&1')

    with open(helper_path, 'w', encoding='gbk') as f:
        f.write('\n'.join(lines))
    return helper_path


def _cleanup(path):
    """安全删除目录"""
    if path and path.exists():
        shutil.rmtree(str(path), ignore_errors=True)


def start_server():
    """启动 HTTP 服务器"""
    server = HTTPServer(('127.0.0.1', PORT), AlbumRequestHandler)
    print(f"服务器启动在 http://127.0.0.1:{PORT}")
    server.serve_forever()


def generate_single_thumbnail(album_name, filename):
    """为单个视频生成缩略图"""
    video_path = STORAGE_DIR / "photos" / album_name / filename
    thumb_name = f"{album_name}_{filename}.jpg"
    thumb_path = THUMBNAIL_DIR / thumb_name

    if thumb_path.exists():
        return

    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            FFMPEG_PATH,
            '-i', str(video_path),
            '-ss', '00:00:01',
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-q:v', '5',
            str(thumb_path)
        ]
        subprocess.run(cmd, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"缩略图已生成: {thumb_name}")
    except Exception as e:
        print(f"生成缩略图失败: {e}")


def generate_thumbnails():
    """生成视频缩略图（启动时批量处理）"""
    if not THUMBNAIL_DIR.exists():
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata()
    photos_dir = STORAGE_DIR / "photos"

    for album in metadata.get('albums', []):
        album_name = album['name']
        for photo in album.get('photos', []):
            if photo.get('type') == 'video':
                thumb_name = f"{album_name}_{photo['filename']}.jpg"
                thumb_path = THUMBNAIL_DIR / thumb_name

                if not thumb_path.exists():
                    video_path = photos_dir / album_name / photo['filename']
                    if video_path.exists():
                        print(f"生成缩略图: {thumb_name}")
                        try:
                            # 使用 ffmpeg 生成缩略图（取第1秒的画面）
                            cmd = [
                                FFMPEG_PATH,
                                '-i', str(video_path),
                                '-ss', '00:00:01',
                                '-vframes', '1',
                                '-vf', 'scale=320:-1',
                                '-q:v', '5',
                                str(thumb_path)
                            ]
                            subprocess.run(cmd, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                        except Exception as e:
                            print(f"生成缩略图失败: {e}")


def main():
    print("""
    ╔════════════════════════════════════════╗
    ║        💕 情侣相册 - 桌面版 💕        ║
    ╚════════════════════════════════════════╝
    """)

    # 确保存储目录存在
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STORAGE_DIR / "photos").mkdir(exist_ok=True)
    (STORAGE_DIR / "music").mkdir(exist_ok=True)
    OVERLAY_DIR.mkdir(exist_ok=True)
    UPDATES_DIR.mkdir(exist_ok=True)

    # 迁移旧版收藏数据
    try:
        JsApi().migrate_old_favorites()
    except Exception as e:
        print(f"收藏迁移跳过：{e}")

    # 在后台生成缩略图
    thumb_thread = threading.Thread(target=generate_thumbnails, daemon=True)
    thumb_thread.start()

    # 启动 HTTP 服务器
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 等待服务器启动
    time.sleep(1)

    # 创建并显示窗口
    try:
        import webview
        # 读取保存的应用名称
        metadata = load_metadata()
        app_name = metadata.get('appName', '情侣相册')
        global _window
        _window = webview.create_window(
            f'💕 {app_name}',
            url=f'http://127.0.0.1:{PORT}',
            width=1280,
            height=800,
            min_size=(800, 600),
            resizable=True,
            text_select=True,
            js_api=JsApi()
        )
        webview.start()
    except ImportError:
        print("错误: 需要安装 pywebview")
        print("请运行: pip install pywebview")
        input("按回车键退出...")
    except Exception as e:
        print(f"启动窗口失败: {e}")
        input("按回车键退出...")


if __name__ == '__main__':
    main()
