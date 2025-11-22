import http.server
import socketserver
import json
import time
from datetime import datetime, timezone, timedelta

PORT = 8000

class TradingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Mock data matching the expected format
            now = datetime.now(timezone.utc)
            competition_start = now - timedelta(minutes=10) # Started 10 mins ago
            
            response_data = {
                "strategies": [
                    {"id": "s1", "name": "Trend Fast", "pnl": 125.50, "trades": 12},
                    {"id": "s2", "name": "Trend Slow", "pnl": -45.20, "trades": 5},
                    {"id": "s3", "name": "Mean Reversion", "pnl": 89.00, "trades": 8},
                    {"id": "s4", "name": "Range Reversion", "pnl": 12.30, "trades": 3},
                    {"id": "s5", "name": "Cross Section", "pnl": -10.50, "trades": 2}
                ],
                "competition_time": competition_start.isoformat(),
                "is_active": True
            }
            
            self.wfile.write(json.dumps(response_data).encode())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

print(f"Serving mock API on port {PORT}")
with socketserver.TCPServer(("", PORT), TradingHTTPRequestHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

