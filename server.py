import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.environ.get('STATIC_DIR', os.path.join(HERE, 'docs'))
DATA_FILE = os.environ.get('DATA_FILE', os.path.join(HERE, 'data', 'state.json'))
PORT = int(os.environ.get('PORT', '8090'))
MAX_BODY = 1_000_000

lock = threading.Lock()


def load():
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(state):
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    os.replace(tmp, DATA_FILE)


def valid(s):
    return (isinstance(s, dict) and isinstance(s.get('t'), (int, float))
            and isinstance(s.get('days'), list) and isinstance(s.get('items'), list))


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webmanifest': 'application/manifest+json', '.js': 'text/javascript'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def is_api(self):
        return self.path.split('?')[0] == '/api/state'

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store' if self.is_api() else 'no-cache')
        super().end_headers()

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.is_api():
            with lock:
                return self.send_json(200, {'state': load()})
        super().do_GET()

    def do_PUT(self):
        if not self.is_api():
            return self.send_error(404)
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > MAX_BODY:
            return self.send_error(413)
        try:
            s = json.loads(self.rfile.read(n))
        except ValueError:
            s = None
        if not valid(s):
            return self.send_error(400)
        with lock:
            cur = load()
            # Last write wins by the client's edit timestamp; stale writers get the newer state back.
            if cur and cur.get('t', 0) > s['t']:
                return self.send_json(409, {'state': cur})
            save(s)
        self.send_json(200, {'state': s})


if __name__ == '__main__':
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    print(f'Serving {STATIC_DIR} on :{PORT}, data in {DATA_FILE}', flush=True)
    ThreadingHTTPServer(('', PORT), Handler).serve_forever()
