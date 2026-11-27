import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.environ.get('STATIC_DIR', os.path.join(HERE, 'docs'))
DATA_FILE = os.environ.get('DATA_FILE', os.path.join(HERE, 'data', 'state.json'))
PORT = int(os.environ.get('PORT', '8090'))
MAX_BODY = 1_000_000
API = '/api/v2/state'
OLD_API = '/api/state'  # whole-list saves from app versions before merging; refused so they can't overwrite merged data

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


def normalize(s):
    # Data saved before merging has no per-record edit time (u) or item order (o); use the list's time and position.
    if not s:
        return s
    t = s.get('t', 0)
    return {
        't': t,
        'sample': s.get('sample', False),
        'gone': dict(s.get('gone') or {}),
        'days': [{**d, 'u': d.get('u', t)} for d in s.get('days', [])],
        'items': [{**it, 'u': it.get('u', t), 'o': it.get('o', i)} for i, it in enumerate(s.get('items', []))],
    }


def merge(a, b):
    # Must match merge() in docs/index.html. Per record the newest edit wins; a deletion (gone) beats edits made
    # before it. On equal times a's record is kept, and both sides pass the server's copy as a, so they agree.
    a, b = normalize(a), normalize(b)
    if not a:
        return b
    gone = dict(a['gone'])
    for k, v in b['gone'].items():
        if v > gone.get(k, 0):
            gone[k] = v
    out = {'gone': gone, 'sample': (a if a['t'] >= b['t'] else b)['sample']}
    stamps = [a['t'], b['t'], *gone.values()]
    for kind in ('days', 'items'):
        best = {}
        for r in a[kind] + b[kind]:
            cur = best.get(r['id'])
            if cur is None or r['u'] > cur['u']:
                best[r['id']] = r
        out[kind] = sorted((r for r in best.values() if r['u'] > gone.get(r['id'], -1)), key=lambda r: r['id'])
        stamps += [r['u'] for r in out[kind]]
    day_ids = {d['id'] for d in out['days']}
    out['items'] = [{**it, 'day': None} if it.get('day') and it['day'] not in day_ids else it for it in out['items']]
    out['t'] = max(stamps)
    return out


def valid(s):
    if not (isinstance(s, dict) and isinstance(s.get('t'), (int, float)) and isinstance(s.get('gone'), dict)):
        return False
    return all(isinstance(rs, list) and all(isinstance(r, dict) and isinstance(r.get('id'), str)
                                            and isinstance(r.get('u'), (int, float)) for r in rs)
               for rs in (s.get('days'), s.get('items')))


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webmanifest': 'application/manifest+json', '.js': 'text/javascript'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def route(self):
        return self.path.split('?')[0]

    def is_api(self):
        return self.route() in (API, OLD_API)

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
        if self.route() == OLD_API:
            return self.send_error(410)
        if self.route() == API:
            with lock:
                return self.send_json(200, {'state': normalize(load())})
        super().do_GET()

    def do_PUT(self):
        if self.route() == OLD_API:
            return self.send_error(410)
        if self.route() != API:
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
            merged = merge(load(), s)
            save(merged)
        self.send_json(200, {'state': merged})


if __name__ == '__main__':
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    print(f'Serving {STATIC_DIR} on :{PORT}, data in {DATA_FILE}', flush=True)
    ThreadingHTTPServer(('', PORT), Handler).serve_forever()
