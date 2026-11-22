"""Vercel serverless function:  POST /api/compile  ->  every compiler phase as JSON."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logicc.web import JSONHandlerMixin  # noqa: E402


class handler(JSONHandlerMixin, BaseHTTPRequestHandler):
    def do_POST(self):
        self.handle_compile()

    def do_GET(self):
        self._json(405, {"error": "use POST with a JSON body {source, optimize, regs}"})
