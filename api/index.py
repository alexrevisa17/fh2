from flask import Flask, jsonify, request, render_template_string
import requests
import re
import json
import os
from functools import lru_cache
from datetime import datetime, timedelta
import time
import logging
import zlib
import gzip
from io import BytesIO

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Add a Faphouse Premium Account
BASE_URL = "https://faphouse2.com"
EMAIL = os.environ.get('EMAIL', 'ENTER_YOUR_EMAIL') #Email
PASSWORD = os.environ.get('PASSWORD', 'ENTER_YOUR_PASSWORD') #Pass

CACHE_DURATION = 300

class FaphouseClient:
    def __init__(self):
        self.session = None
        self.logged_in = False
        self.session_created = False
        
    def ensure_session(self):
        if not self.session or not self.logged_in:
            logger.info("🔄 Creating new session...")
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            self.login()
        return self.session
    
    def login(self):
        logger.info(f"🔐 Attempting login with email: {EMAIL[:5]}...")
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'Origin': BASE_URL,
            'Referer': f'{BASE_URL}/',
            'DNT': '1',
            'Connection': 'keep-alive'
        })
        
        try:
            logger.info("  📡 Getting initial page...")
            init_res = self.session.get(BASE_URL, timeout=10)
            logger.info(f"  📡 Initial page status: {init_res.status_code}")
            
            payload = {
                "login": EMAIL,
                "password": PASSWORD,
                "rememberMe": "1",
                "recaptcha": "",
                "trackingParamsBag": "eyJwcm9tb19pZCI6IiIsInZpZGVvX2lkIjpudWxsLCJzdHVkaW9faWQiOm51bGwsInByb2R1Y2VyX2lkIjpudWxsLCJvcmllbnRhdGlvbiI6InN0cmFpZ2h0IiwibWxfcGFnZSI6Im1haW5fcGFnZSIsIm1sX3BhZ2VfdmFsdWVfaWQiOm51bGwsIm1sX3BhZ2VfdmFsdWUiOm51bGwsIm1sX3BhZ2VfbnVtYmVyIjpudWxsLCJtbF9yZWZfcGFnZV92YWx1ZV9pZCI6bnVsbCwibWxfcmVmX3BhZ2VfdmFsdWUiOiIiLCJtbF9yZWZfcGFnZV9udW1iZXIiOm51bGwsIm1sX3JlZl9wYWdlIjoiZGlyZWN0In0="
            }
            
            logger.info("  📡 Sending login request...")
            login_res = self.session.post(
                f"{BASE_URL}/api/auth/signin",
                json=payload,
                timeout=15
            )
            
            logger.info(f"  📡 Login response status: {login_res.status_code}")
            
            if login_res.status_code == 200:
                try:
                    data = login_res.json()
                    if data.get('success') or data.get('data'):
                        self.logged_in = True
                        logger.info("✅ Login successful!")
                        return True
                except:
                    pass
                
                if len(self.session.cookies) > 0:
                    self.logged_in = True
                    logger.info(f"✅ Login successful (session established)!")
                    return True
            
            self.logged_in = False
            return False
            
        except Exception as e:
            logger.error(f"❌ Login error: {str(e)}")
            self.logged_in = False
            return False
    
    def _decode_response(self, response):
        try:
            content_encoding = response.headers.get('Content-Encoding', '')
            
            if content_encoding:
                logger.info(f"  🔓 Decoding {content_encoding} response...")

            if 'gzip' in content_encoding:
                try:
                    return gzip.decompress(response.content).decode('utf-8', errors='ignore')
                except:
                    pass

            if 'deflate' in content_encoding:
                try:
                    return zlib.decompress(response.content).decode('utf-8', errors='ignore')
                except:
                    try:
                        return zlib.decompress(response.content, -zlib.MAX_WBITS).decode('utf-8', errors='ignore')
                    except:
                        pass

            if 'br' in content_encoding:
                try:
                    import brotli
                    return brotli.decompress(response.content).decode('utf-8', errors='ignore')
                except ImportError:
                    logger.warning("  ⚠️ Brotli not installed, skipping...")
                except:
                    pass

            try:
                return response.text
            except:
                pass
            
            return response.text if response.text else str(response.content)
            
        except Exception as e:
            logger.error(f"  ❌ Decoding error: {str(e)}")
            return response.text if response.text else str(response.content)
    
    @lru_cache(maxsize=100)
    def get_m3u8_url(self, video_url):

        logger.info(f"🔍 Processing video URL: {video_url[:80]}...")
        
        if '#' in video_url:
            video_url = video_url.split('#')[0]

        session = self.ensure_session()
        if session:
            try:
                logger.info("📡 Attempt 1: Using authenticated session...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Referer': BASE_URL,
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                response = session.get(video_url, timeout=15, headers=headers)
                logger.info(f"📡 Session GET Status: {response.status_code}")
                
                if response.status_code == 200:
                    html = self._decode_response(response)
                    if html:
                        m3u8 = self._extract_m3u8(html)
                        if m3u8:
                            logger.info("✅ Found M3U8 URL with session!")
                            return m3u8
            except Exception as e:
                logger.warning(f"⚠️ Session attempt failed: {str(e)}")

        logger.info("🔄 Attempt 2: Trying guest fetch...")
        try:
            guest_session = requests.Session()
            guest_session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': BASE_URL,
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            
            response = guest_session.get(video_url, timeout=15)
            logger.info(f"📡 Guest Status: {response.status_code}")
            
            if response.status_code == 200:
                html = self._decode_response(response)
                if html:
                    m3u8 = self._extract_m3u8(html)
                    if m3u8:
                        logger.info("✅ Found M3U8 URL with guest!")
                        return m3u8
        except Exception as e:
            logger.warning(f"⚠️ Guest attempt failed: {str(e)}")
        
        logger.error("❌ Failed to find M3U8 URL with all attempts.")
        return None
    
    def _extract_m3u8(self, html_content):

        if not html_content:
            return None

        html_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', html_content)
        
        patterns = [
            r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*',
            r'https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?',
            r'//[^\s"\'<>]+\.m3u8[^\s"\'<>]*',

            r'src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'src\s*=\s*["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']',
            r'href\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',

            r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'file\s*:\s*["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']',
            r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        ]
        
        found_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    m3u8_url = match.strip()
                    if '"' in m3u8_url:
                        m3u8_url = m3u8_url.split('"')[0]
                    if "'" in m3u8_url:
                        m3u8_url = m3u8_url.split("'")[0]
                    if '&amp;' in m3u8_url:
                        m3u8_url = m3u8_url.replace('&amp;', '&')
                    if m3u8_url.startswith('//'):
                        m3u8_url = 'https:' + m3u8_url

                    if m3u8_url.startswith('http') and '.m3u8' in m3u8_url:
                        found_urls.append(m3u8_url)

        seen = set()
        unique_urls = []
        for url in found_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        if unique_urls:
            logger.info(f"✅ Found {len(unique_urls)} M3U8 URLs")
            return unique_urls[0] 
        
        return None

client = FaphouseClient()


@app.route('/')
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🎬 Faphouse Player</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    background: #0a0a0a;
                    color: #fff;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }
                .container {
                    max-width: 600px;
                    width: 100%;
                    background: #1a1a1a;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.8);
                    text-align: center;
                }
                h1 { font-size: 32px; margin-bottom: 10px; }
                .subtitle { color: #888; margin-bottom: 30px; }
                .url-input {
                    margin: 20px 0;
                }
                .url-input input {
                    width: 100%;
                    padding: 15px;
                    background: #333;
                    border: 1px solid #444;
                    border-radius: 8px;
                    color: #fff;
                    font-size: 16px;
                }
                .url-input input:focus {
                    outline: none;
                    border-color: #4CAF50;
                }
                .url-input button {
                    width: 100%;
                    padding: 15px;
                    margin-top: 15px;
                    background: #4CAF50;
                    border: none;
                    border-radius: 8px;
                    color: #fff;
                    font-weight: bold;
                    font-size: 18px;
                    cursor: pointer;
                    transition: background 0.3s;
                }
                .url-input button:hover {
                    background: #45a049;
                }
                .hint {
                    color: #666;
                    font-size: 13px;
                    margin-top: 15px;
                }
                .hint code {
                    background: #222;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    word-break: break-all;
                }
                .endpoints {
                    margin-top: 30px;
                    padding: 20px;
                    background: #222;
                    border-radius: 8px;
                    text-align: left;
                }
                .endpoints h3 {
                    color: #888;
                    font-size: 14px;
                    margin-bottom: 10px;
                }
                .endpoint {
                    padding: 8px 0;
                    border-bottom: 1px solid #333;
                    font-size: 13px;
                    color: #aaa;
                }
                .endpoint:last-child { border-bottom: none; }
                .endpoint strong { color: #4CAF50; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎬 Faphouse Player</h1>
                <p class="subtitle">Enter any video URL to watch</p>
                
                <div class="url-input">
                    <form method="GET" action="/play">
                        <input type="text" name="url" placeholder="Paste video URL here..." required>
                        <button type="submit">▶ Watch Now</button>
                    </form>
                    <div class="hint">
                        💡 Example: <code>https://faphouse2.com/videos/shared-bed-stepsister-fuck-C6Qi1u</code>
                    </div>
                </div>
                
                <div class="endpoints">
                    <h3>📡 API Endpoints</h3>
                    <div class="endpoint"><strong>GET</strong> /play?url=VIDEO_URL - Watch video</div>
                    <div class="endpoint"><strong>GET</strong> /api/m3u8?url=VIDEO_URL - Get M3U8 URL</div>
                    <div class="endpoint"><strong>GET</strong> /api/status - Check status</div>
                </div>
            </div>
        </body>
        </html>
    """)

@app.route('/play')
def play_video():
    video_url = request.args.get('url')
    
    if not video_url:
        return "❌ No URL provided", 400
    
    if '#' in video_url:
        video_url = video_url.split('#')[0]
    
    try:
        logger.info(f"🎬 Play request for: {video_url}")
        m3u8_url = client.get_m3u8_url(video_url)
        
        if m3u8_url:
            return render_template_string("""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>🎬 Video Player</title>
                    <link href="https://vjs.zencdn.net/8.0.0/video-js.css" rel="stylesheet" />
                    <style>
                        * { margin: 0; padding: 0; box-sizing: border-box; }
                        body {
                            background: #0a0a0a;
                            color: #fff;
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            padding: 20px;
                        }
                        .container {
                            max-width: 1200px;
                            width: 100%;
                            background: #1a1a1a;
                            border-radius: 12px;
                            padding: 20px;
                            box-shadow: 0 8px 32px rgba(0,0,0,0.8);
                        }
                        .video-wrapper {
                            width: 100%;
                            background: #000;
                            border-radius: 8px;
                            overflow: hidden;
                            position: relative;
                            aspect-ratio: 16/9;
                        }
                        #player {
                            width: 100%;
                            height: 100%;
                        }
                        .info {
                            margin-top: 15px;
                            padding: 15px;
                            background: #222;
                            border-radius: 8px;
                            font-size: 13px;
                            word-break: break-all;
                        }
                        .info a { color: #4CAF50; text-decoration: none; }
                        .badge {
                            display: inline-block;
                            background: #4CAF50;
                            color: #fff;
                            padding: 2px 12px;
                            border-radius: 20px;
                            font-size: 11px;
                            font-weight: bold;
                            margin-left: 10px;
                        }
                        .status-bar {
                            display: flex;
                            align-items: center;
                            gap: 20px;
                            margin-bottom: 15px;
                            flex-wrap: wrap;
                        }
                        .status-bar h2 {
                            display: flex;
                            align-items: center;
                            font-size: 20px;
                        }
                        .status-dot {
                            display: inline-block;
                            width: 10px;
                            height: 10px;
                            border-radius: 50%;
                            background: #4CAF50;
                            animation: pulse 1.5s infinite;
                        }
                        @keyframes pulse {
                            0% { opacity: 1; }
                            50% { opacity: 0.3; }
                            100% { opacity: 1; }
                        }
                        .back-link {
                            display: inline-block;
                            margin-top: 10px;
                            color: #888;
                            text-decoration: none;
                        }
                        .back-link:hover { color: #fff; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="status-bar">
                            <h2>
                                🎬 Faphouse
                                <span class="badge">ULTRA</span>
                            </h2>
                            <span class="status-dot"></span>
                            <span class="video-title">Playing</span>
                        </div>
                        
                        <div class="video-wrapper">
                            <video id="player" class="video-js vjs-default-skin" controls autoplay preload="auto">
                                <source src="{{ m3u8_url }}" type="application/x-mpegURL">
                            </video>
                        </div>
                        
                        <div class="info">
                            <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                                <div>
                                    <strong>📹 Video:</strong> 
                                    <a href="{{ video_url }}" target="_blank">{{ video_url[:60] }}...</a>
                                </div>
                                <div>
                                    <strong>📊 Status:</strong> 
                                    <span style="color: #4CAF50;">● Playing</span>
                                </div>
                            </div>
                        </div>
                        
                        <a href="/" class="back-link">← Back to Home</a>
                    </div>
                    
                    <script src="https://vjs.zencdn.net/8.0.0/video.min.js"></script>
                    <script>
                        document.addEventListener('DOMContentLoaded', function() {
                            var player = videojs('player', {
                                html5: {
                                    hls: {
                                        enableLowInitialPlaylist: true,
                                        smoothQualityChange: true,
                                        overrideNative: true
                                    }
                                }
                            });
                            
                            player.ready(function() {
                                console.log('✅ Player ready');
                                this.play().catch(function(e) {
                                    console.log('Auto-play prevented:', e);
                                });
                            });
                        });
                    </script>
                </body>
                </html>
            """, m3u8_url=m3u8_url, video_url=video_url)
        else:
            return render_template_string("""
                <div style="padding: 40px; text-align: center; background: #0a0a0a; color: #fff; min-height: 100vh; font-family: Arial;">
                    <div style="max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #ff4444;">❌ Could not find M3U8 URL</h2>
                        <p style="color: #888; margin: 20px 0;">The video might be unavailable or blocked in your region.</p>
                        <a href="/" style="color: #4CAF50; text-decoration: none; display: inline-block; padding: 10px 30px; background: #222; border-radius: 6px;">← Go Home</a>
                    </div>
                </div>
            """)
    except Exception as e:
        logger.error(f"❌ Play error: {str(e)}")
        return render_template_string("""
            <div style="padding: 40px; text-align: center; background: #0a0a0a; color: #fff; min-height: 100vh; font-family: Arial;">
                <div style="max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #ff4444;">❌ Error</h2>
                    <p style="color: #888; margin: 20px 0;">{{ error }}</p>
                    <a href="/" style="color: #4CAF50; text-decoration: none; display: inline-block; padding: 10px 30px; background: #222; border-radius: 6px;">← Go Home</a>
                </div>
            </div>
        """, error=str(e))

@app.route('/api/m3u8')
def get_m3u8():
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    
    try:
        if '#' in video_url:
            video_url = video_url.split('#')[0]
            
        m3u8_url = client.get_m3u8_url(video_url)
        
        if m3u8_url:
            return jsonify({
                "success": True,
                "m3u8_url": m3u8_url,
                "video_url": video_url
            })
        else:
            return jsonify({
                "success": False,
                "error": "No M3U8 URL found"
            }), 404
    except Exception as e:
        logger.error(f"❌ API error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status')
def status():
    return jsonify({
        "status": "online",
        "logged_in": client.logged_in,
        "session_created": client.session_created,
        "cache_info": client.get_m3u8_url.cache_info()._asdict()
    })

def handler(request, context):
    return app(request.environ, context)

if __name__ == "__main__":
    print(f"""
{'='*70}
🎬 Faphouse Player API (Vercel Ready - Working!)
{'='*70}

✅ Features:
  • Properly decodes compressed (brotli) responses
  • Finds M3U8 URLs reliably
  • LRU caching for fast responses
  • Works on Vercel serverless

📌 Endpoints:
  📺 /play?url=VIDEO_URL     - Watch video
  📡 /api/m3u8?url=VIDEO_URL - Get M3U8 URL
  📊 /api/status             - Check status

🔐 Credentials:
  EMAIL: {EMAIL[:5]}... 
  PASSWORD: {'*' * 8}
{'='*70}
""")
    
    print("🚀 Starting server for local testing...")
    app.run(host='0.0.0.0', port=5000, debug=True)
