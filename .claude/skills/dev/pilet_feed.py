"""Serve built pilets as one pilet feed, for a host page that loads its pilets from a feed URL.

Usage: pilet_feed.py <port> <name>@<version>=<dir> [...]. GET /feed answers a bare array, the shape
`pilet debug` serves; /<n>/<file> is a file from the n-th pilet's directory. CORS lets the host page read both.
"""
import json, os, re, sys, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
PILETS = []
for arg in sys.argv[2:]:
    spec, _, directory = arg.partition('=')
    name, _, version = spec.rpartition('@')
    PILETS.append((name, version, os.path.abspath(directory)))
HEADER = re.compile(r'^//@pilet v:2\(([^,]+),(\{.*\})\)')


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def translate_path(self, path):
        head, _, rest = path.lstrip('/').partition('/')
        if not head.isdigit() or int(head) >= len(PILETS):
            return ''
        self.directory = PILETS[int(head)][2]
        return super().translate_path('/' + rest)

    def do_GET(self):
        if self.path.split('?')[0] != '/feed':
            return super().do_GET()
        entries = []
        for n, (name, version, directory) in enumerate(PILETS):
            index = os.path.join(directory, 'index.js')
            require_ref, deps = HEADER.match(open(index).readline()).groups()
            base = f'http://localhost:{PORT}/{n}/'
            entries.append({'name': name, 'version': version, 'spec': 'v2', 'requireRef': require_ref,
                            'link': f'{base}index.js?built={int(os.path.getmtime(index))}',
                            'dependencies': {k: base + v for k, v in json.loads(deps).items()}})
        body = json.dumps(entries).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), fmt % args))


ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
