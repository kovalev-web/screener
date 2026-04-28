"""
Vercel serverless API — endpoint для ручного запуска INPLAY-скана.
"""

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write('{"status": "ok"}'.encode("utf-8"))