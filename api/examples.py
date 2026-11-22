"""Vercel serverless function:  GET /api/examples  ->  the example programs."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logicc.web import JSONHandlerMixin, load_examples  # noqa: E402


class handler(JSONHandlerMixin, BaseHTTPRequestHandler):
    def do_GET(self):
        self._json(200, load_examples())
