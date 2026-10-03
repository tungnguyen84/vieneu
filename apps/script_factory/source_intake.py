"""Bounded public-source extraction. Never treats source content as instructions."""
from __future__ import annotations

import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs

MAX_TEXT = int(os.getenv('STUDIO_SOURCE_MAX_TEXT', '100000'))
MAX_BYTES = int(os.getenv('STUDIO_SOURCE_MAX_BYTES', '10485760'))
TIMEOUT = int(os.getenv('STUDIO_SOURCE_TIMEOUT', '30'))


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def checked_text(text):
    text = text.replace('\ufeff', '').replace('\r\n', '\n').strip()
    if not text or len(text.split()) < 20:
        raise ValueError('Nguồn quá ngắn hoặc rỗng; cần ít nhất 20 từ nội dung thực.')
    if len(text) > MAX_TEXT:
        raise ValueError(f'Nguồn vượt giới hạn {MAX_TEXT:,} ký tự; hãy chia nhỏ, không tự cắt nội dung.')
    if '\x00' in text:
        raise ValueError('File không phải văn bản UTF-8 hợp lệ.')
    return text


def public_address(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Chỉ nhận URL http/https công khai, không có thông tin đăng nhập.')
    if p.port not in (None, 80, 443):
        raise ValueError('Nguồn chỉ hỗ trợ cổng web 80/443.')
    if p.hostname.lower() in ('localhost', 'localhost.localdomain'):
        raise ValueError('Không đọc địa chỉ nội bộ.')
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    ips = {a[4][0] for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Không đọc địa chỉ IP nội bộ hoặc reserved.')
    return p, addresses[0][4][0]


def fetch_public(url, redirects=5):
    """Pin the checked IP when connecting; TLS still verifies the original host."""
    for hop in range(redirects + 1):
        p, ip = public_address(url)
        port = p.port or (443 if p.scheme == 'https' else 80)
        conn = http.client.HTTPConnection(p.hostname, port, timeout=TIMEOUT)
        sock = socket.create_connection((ip, port), timeout=TIMEOUT)
        if p.scheme == 'https':
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
        conn.sock = sock
        try:
            conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                         headers={'User-Agent': 'VieNeuStudio/1.0 SourceReader', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if hop == redirects or not location:
                    raise ValueError('URL chuyển hướng quá nhiều hoặc thiếu địa chỉ đích.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'Không đọc được nguồn (HTTP {response.status}); có thể dán văn bản thay thế.')
            if int(response.getheader('Content-Length', '0')) > MAX_BYTES:
                raise ValueError('Nguồn vượt giới hạn tải; không cắt lặng lẽ.')
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError('Nguồn vượt giới hạn tải; không cắt lặng lẽ.')
            return body, response.getheader('Content-Type', ''), url
        finally:
            conn.close()
    raise ValueError('Không đọc được nguồn.')


def _seconds(value):
    parts = value.replace(',', '.').split(':')
    return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))


def subtitle_units(text):
    units = []
    previous = []
    previous_end = -100
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        lines = block.strip().splitlines()
        ix = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if ix is None:
            continue
        match = re.match(r'([\d:.,]+)\s*-->\s*([\d:.,]+)', lines[ix])
        if not match:
            continue
        start, end = map(_seconds, match.groups())
        if start < 0 or end < start or end > 7200:
            raise ValueError('Phụ đề có thời gian không hợp lệ hoặc vượt 2 giờ.')
        words = html.unescape(re.sub(r'<[^>]*>', '', ' '.join(lines[ix+1:]))).split()
        raw_words = words[:]
        # Remove ONLY adjacent rolling-caption overlap, not later repeated speech.
        if start <= previous_end + 1:
            overlap = next((n for n in range(min(len(previous), len(words)), 1, -1)
                            if previous[-n:] == words[:n]), 0)
            words = words[overlap:]
        previous, previous_end = raw_words, end
        if words:
            units.append({'unit_id': f'U{len(units)+1:04d}', 'text': ' '.join(words), 'start_sec': start, 'end_sec': end})
    if not units:
        raise ValueError('Không đọc được các câu phụ đề; hãy dán transcript văn bản.')
    return units


def text_units(text):
    return [{'unit_id': f'U{i:04d}', 'text': paragraph.strip()}
            for i, paragraph in enumerate(re.split(r'\n+', text.strip()), 1) if paragraph.strip()]


def read_text(text, filename=''):
    if filename and not filename.lower().endswith(('.txt', '.srt', '.vtt')):
        raise ValueError('Chỉ nhận file TXT, SRT hoặc VTT UTF-8.')
    if len(text) > MAX_TEXT:
        raise ValueError(f'Nguồn vượt giới hạn {MAX_TEXT:,} ký tự.')
    units = subtitle_units(text) if filename.lower().endswith(('.srt', '.vtt')) else text_units(checked_text(text))
    content = checked_text('\n'.join(u['text'] for u in units))
    return {'text': content, 'units': units, 'source_type': 'FILE' if filename else 'TEXT',
            'title': filename or 'Văn bản tham khảo', 'extraction_method': 'user_text', 'limitations': []}


def youtube_url(url):
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        return None
    if p.scheme not in ('http', 'https') or p.username or p.password or p.port:
        raise ValueError('URL YouTube không hợp lệ.')
    video = (p.path.strip('/') if host == 'youtu.be' else
             p.path.split('/')[2] if p.path.startswith(('/shorts/', '/embed/')) else
             parse_qs(p.query).get('v', [''])[0] if p.path == '/watch' else '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('Nhập URL một video, không phải kênh hoặc playlist.')
    return 'https://www.youtube.com/watch?v=' + video


def read_youtube(url, language='vi'):
    canonical = youtube_url(url)
    if not canonical:
        raise ValueError('URL không phải video YouTube.')
    result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
                             '--skip-download', '--dump-single-json', '--socket-timeout', '15',
                             '--retries', '1', canonical], capture_output=True, timeout=75, encoding='utf-8')
    if result.returncode:
        # Never include credentials, cookie paths or unbounded downloader output.
        raise ValueError('YouTube không cho đọc metadata/phụ đề lúc này. Hãy dán hoặc tải transcript thay thế.')
    info = json.loads(result.stdout)
    if info.get('is_live') or float(info.get('duration') or 0) > 7200:
        raise ValueError('Chưa hỗ trợ live hoặc video dài hơn 2 giờ.')
    selected = None
    for key, kind in [('subtitles', 'MANUAL'), ('automatic_captions', 'AUTOMATIC')]:
        available = info.get(key) or {}
        langs = sorted(available, key=lambda x: (x != language, not x.startswith(language + '-'), x != 'en', x))
        langs = [l for l in langs if l == language or l.startswith(language + '-')]
        for lang in langs:
            caption = next((c for c in available[lang] if c.get('ext') == 'vtt'), None)
            if caption:
                selected = caption, lang, kind
                break
        if selected:
            break
    if not selected:
        raise ValueError(f'Không có phụ đề {language}; yt-dlp không tự nhận dạng giọng nói. Hãy tải/dán transcript hoặc đổi ngôn ngữ.')
    caption, lang, kind = selected
    body, _, _ = fetch_public(caption['url'])
    data = read_text(body.decode('utf-8-sig'), 'captions.vtt')
    return {**data, 'source_type': 'YOUTUBE', 'title': info.get('title'), 'author_or_channel': info.get('channel'),
            'published_at': info.get('upload_date'), 'language': lang, 'caption_kind': kind,
            'resolved_url': canonical, 'extraction_method': 'yt-dlp-vtt',
            'limitations': ['Phụ đề tự động có thể sai tên riêng/con số; kiểm tra trước xác nhận.'] if kind == 'AUTOMATIC' else []}


def read_article(url):
    from trafilatura import bare_extraction
    body, content_type, resolved = fetch_public(url)
    if not any(t in content_type.lower() for t in ('text/html', 'application/xhtml')):
        raise ValueError('URL không phải trang bài viết HTML; hãy nhập văn bản.')
    doc = bare_extraction(body, url=resolved, include_comments=False, include_tables=True, with_metadata=True)
    if not doc or not doc.text or len(doc.text.split()) < 80:
        raise ValueError('Không lấy được đủ thân bài (có thể paywall/trang động). Hãy dán nội dung; không sinh từ tiêu đề.')
    data = read_text(doc.text)
    return {**data, 'source_type': 'ARTICLE', 'title': doc.title or 'Bài viết tham khảo',
            'author_or_channel': doc.author, 'published_at': doc.date, 'resolved_url': resolved,
            'language': doc.language, 'extraction_method': 'trafilatura',
            'limitations': ['App lấy nội dung trang, không xác minh độc lập các lời kể trong bài.']}
