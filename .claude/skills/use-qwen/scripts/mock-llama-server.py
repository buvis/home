#!/usr/bin/env python3
# Mock llama.cpp server for tests: reproduces the 2026-06-19 false-healthy
# incident shape (GET /v1/models can be 200 while POST /v1/chat/completions
# is 500) so qwen-run.sh/run-eval.sh tests can drive both without a real
# llama-server. Shared by test_qwen_run.sh and test_eval_automation.sh.
import http.server
import json
import sys

PORT = int(sys.argv[1])
MODE_FILE = sys.argv[2]
# Variadic: one id per trailing argv (order preserved). A single trailing arg
# reproduces the original single-id behavior byte-for-byte.
MODEL_IDS = sys.argv[3:]


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') == '/v1/models':
            data = [{"id": m, "object": "model"} for m in MODEL_IDS]
            body = json.dumps({"object": "list", "data": data}).encode()
            self._send(200, body)
        else:
            self._send(404, b'{}')

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(n)
        with open(MODE_FILE) as f:
            mode = f.read().strip()
        if self.path.rstrip('/') == '/v1/chat/completions' and mode == 'ok':
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "x"}}]}).encode()
            self._send(200, body)
        else:
            self._send(500, b'{"error": "failed to spawn server instance"}')


http.server.HTTPServer(('127.0.0.1', PORT), H).serve_forever()
