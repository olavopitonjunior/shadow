from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
from datetime import datetime

OUTPUT_HTML = os.path.join(os.path.dirname(__file__), 'qr.html')
LOG_PATH = os.path.join(os.path.dirname(__file__), 'qr-listener.log')

BASE64_RE = re.compile(r'^[A-Za-z0-9+/=]{200,}$')


def find_base64(obj):
    if isinstance(obj, str):
        if obj.startswith('data:image/'):
            return obj
        if BASE64_RE.match(obj):
            return f'data:image/png;base64,{obj}'
        return None
    if isinstance(obj, list):
        for item in obj:
            found = find_base64(item)
            if found:
                return found
    if isinstance(obj, dict):
        for key in ('qrcode', 'qr', 'qrCode', 'qrcodeBase64', 'base64'):
            if key in obj and isinstance(obj[key], str):
                found = find_base64(obj[key])
                if found:
                    return found
        for value in obj.values():
            found = find_base64(value)
            if found:
                return found
    return None


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length) if length else b''
        payload = None
        try:
            payload = json.loads(body.decode('utf-8')) if body else {}
        except Exception:
            payload = {'raw': body.decode('utf-8', errors='ignore')}

        ts = datetime.utcnow().isoformat()
        with open(LOG_PATH, 'a', encoding='utf-8') as log:
            log.write(f'[{ts}] {self.path}\n')
            log.write(json.dumps(payload, ensure_ascii=False, indent=2))
            log.write('\n\n')

        data_uri = find_base64(payload)
        if data_uri:
            html = f"""<!doctype html>
<html>
<head><meta charset=\"utf-8\"><title>Evolution QR</title></head>
<body>
<h2>Evolution QR</h2>
<img src=\"{data_uri}\" alt=\"QR Code\" />
</body>
</html>"""
            with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
                f.write(html)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 3001), Handler)
    print('QR listener running on http://localhost:3001')
    server.serve_forever()
