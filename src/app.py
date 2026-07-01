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


class AlbumRequestHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def do_GET(self):
        path = self.path

        # 根路径返回 index.html
        if path == '/':
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

        # /photos/... - 照片/视频文件
        if path.startswith('/photos/'):
            return self.handle_photo_file(path)

        # /music/... - 音乐文件
        if path.startswith('/music/'):
            return self.handle_music_file(path)

        # /thumbnails/... - 缩略图文件
        if path.startswith('/thumbnails/'):
            return self.handle_thumbnail_file(path)

        # 其他静态文件
        return super().do_GET()

    def do_POST(self):
        path = self.path

        # /api/admin/rename - 修改应用名称
        if path == '/api/admin/rename':
            return self.handle_rename()

        # /api/admin/albums - 创建相册
        if path == '/api/admin/albums':
            return self.handle_create_album()

        # /api/admin/photos/{album}/{photoId}/favorite - 切换收藏
        if '/favorite' in path:
            return self.handle_toggle_favorite(path)

        # /api/admin/photos/{album}/{photoId} - 更新照片
        if path.startswith('/api/admin/photos/') and '/favorite' not in path:
            return self.handle_update_photo(path)

        self.send_error(404)

    def do_DELETE(self):
        path = self.path

        # /api/admin/albums/{name} - 删除相册
        if path.startswith('/api/admin/albums/'):
            return self.handle_delete_album(path)

        self.send_error(404)

    def do_PUT(self):
        path = self.path

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
        all_photos = []
        for album in metadata.get('albums', []):
            for photo in album.get('photos', []):
                photo['album'] = album['name']
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

    def handle_toggle_favorite(self, path):
        # /api/admin/photos/{album}/{photoId}/favorite
        parts = path.split('/')
        if len(parts) < 6:
            self.send_error(400)
            return

        album_name = unquote(parts[4])
        photo_id = parts[5]

        metadata = load_metadata()

        for album in metadata.get('albums', []):
            if album['name'] == album_name:
                for photo in album.get('photos', []):
                    if photo['id'] == photo_id:
                        photo['favorite'] = not photo.get('favorite', False)
                        save_metadata(metadata)
                        self.send_json(photo)
                        return

        self.send_json({'error': '照片不存在'}, 404)

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
