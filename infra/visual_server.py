"""Read-only visual harness for verified Demo/build artifacts; not a production server."""
import argparse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import ssl
import hashlib

FIXED='2026-09-08T04:00:00.000Z'
parser=argparse.ArgumentParser()
parser.add_argument('--directory',type=Path,required=True)
parser.add_argument('--font',type=Path,required=True)
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--tls-directory',type=Path,default=Path('.tools/tls'))
args=parser.parse_args()
font=args.font.read_bytes()
print('font_sha256='+hashlib.sha256(font).hexdigest(),flush=True)
injection=f'''<script>const OriginalDate=Date;window.Date=class extends OriginalDate{{constructor(...a){{super(...(a.length?a:['{FIXED}']))}}static now(){{return new OriginalDate('{FIXED}').getTime()}}}};let visualSeed=7;Math.random=()=>((visualSeed=(visualSeed*16807)%2147483647)/2147483647);</script>
<style>@font-face{{font-family:SiliconBaseline;src:url('/__visual_font')}}html,body,button,input,select,textarea{{font-family:SiliconBaseline,sans-serif!important}}*,*::before,*::after{{animation:none!important;transition:none!important;caret-color:transparent!important}}</style>'''
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(args.directory),**kw)
    def do_GET(self):
        if self.path=='/__visual_font':
            self.send_response(200);self.send_header('Content-Type','font/collection');self.end_headers();self.wfile.write(font);return
        if self.path.split('?')[0] in ('/','/index.html'):
            content=(args.directory/'index.html').read_text().replace('</head>',injection+'</head>')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(content.encode());return
        super().do_GET()
    def log_message(self,*a):pass
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(args.tls_directory/'localhost.crt',args.tls_directory/'localhost.key')
server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
server.socket=context.wrap_socket(server.socket,server_side=True)
try:server.serve_forever()
finally:server.server_close()
