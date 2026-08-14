from flask import Flask, jsonify, request, render_template_string, session, redirect
from supabase import create_client
import requests
import re
import json
import os
import hmac
from functools import lru_cache
from datetime import datetime, timedelta
import time
import logging
import zlib
import gzip
from io import BytesIO

app = Flask(__name__)
app.secret_key = "belajar-flask-license-123"
LICENSE_KEY = "FAPHOUSE-FJ7TV-DHV4G"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

def check_license(key):
    try:
        result = (
            supabase
            .table("licenses")
            .select("*")
            .eq("license_key", key)
            .single()
            .execute()
        )

        if not result.data:
            return False

        license = result.data

        if not license["active"]:
            return False

        return True

    except Exception as e:
        logger.error(e)
        return False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Add a Faphouse Premium Account
BASE_URL = "https://faphouse2.com"
EMAIL = os.environ.get('EMAIL', 'faphouse@vcc.biz.id') #Email
PASSWORD = os.environ.get('PASSWORD', 'Bangpray#123') #Pass

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

@app.route('/license', methods=['GET', 'POST'])
def license_page():
    if request.method == 'POST':
        key = request.form.get("license", "").strip()

        if key == LICENSE_KEY:
            session["licensed"] = True
            return redirect("/")

        return render_template_string("""
        <!DOCTYPE html>
        <html lang="id">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>License Invalid - Faphouse Player</title>

            <style>
                * {
                    box-sizing: border-box;
                    -webkit-tap-highlight-color: transparent;
                }

                html, body {
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    min-height: 100%;
                    font-family: Arial, Helvetica, sans-serif;
                    background: #08090d;
                    color: #fff;
                }

                body {
                    min-height: 100vh;
                    min-height: 100dvh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 24px 16px;
                    position: relative;
                    overflow-x: hidden;
                }

                body::before {
                    content: "";
                    position: fixed;
                    width: 420px;
                    height: 420px;
                    background: rgba(0, 255, 140, 0.08);
                    filter: blur(100px);
                    border-radius: 50%;
                    top: -180px;
                    left: -160px;
                    pointer-events: none;
                }

                body::after {
                    content: "";
                    position: fixed;
                    width: 380px;
                    height: 380px;
                    background: rgba(80, 100, 255, 0.07);
                    filter: blur(100px);
                    border-radius: 50%;
                    bottom: -180px;
                    right: -140px;
                    pointer-events: none;
                }

                .container {
                    width: 100%;
                    max-width: 430px;
                    position: relative;
                    z-index: 2;
                }

                .box {
                    width: 100%;
                    background: rgba(22, 24, 31, 0.94);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 24px;
                    padding: 30px 26px 25px;
                    text-align: center;
                    box-shadow:
                        0 25px 70px rgba(0,0,0,0.55),
                        inset 0 1px 0 rgba(255,255,255,0.04);
                    backdrop-filter: blur(18px);
                    -webkit-backdrop-filter: blur(18px);
                }

                .logo {
                    width: 76px;
                    height: 76px;
                    margin: 0 auto 18px;
                    border-radius: 22px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 38px;
                    background: linear-gradient(
                        145deg,
                        #1ed760,
                        #0aa85a
                    );
                    box-shadow:
                        0 12px 30px rgba(30,215,96,0.22),
                        inset 0 1px 0 rgba(255,255,255,0.25);
                }

                h1 {
                    margin: 0;
                    font-size: 25px;
                    line-height: 1.2;
                    font-weight: 800;
                    letter-spacing: 1.5px;
                }

                .subtitle {
                    margin: 9px 0 0;
                    color: #9297a5;
                    font-size: 14px;
                    line-height: 1.5;
                }

                .brand {
                    margin: 12px 0 0;
                    color: #45e58a;
                    font-size: 12px;
                    letter-spacing: 0.4px;
                }

                .divider {
                    height: 1px;
                    border: 0;
                    background: linear-gradient(
                        90deg,
                        transparent,
                        rgba(255,255,255,0.1),
                        transparent
                    );
                    margin: 25px 0;
                }

                .error {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    text-align: left;
                    padding: 13px 14px;
                    border-radius: 12px;
                    background: rgba(255, 70, 70, 0.08);
                    border: 1px solid rgba(255, 70, 70, 0.18);
                    color: #ff7777;
                    font-size: 13px;
                    margin-bottom: 20px;
                }

                .label {
                    display: block;
                    text-align: left;
                    margin-bottom: 9px;
                    color: #dfe2e8;
                    font-size: 13px;
                    font-weight: 700;
                }

                .input-wrapper {
                    position: relative;
                    width: 100%;
                }

                .input-icon {
                    position: absolute;
                    left: 15px;
                    top: 50%;
                    transform: translateY(-50%);
                    font-size: 17px;
                    pointer-events: none;
                    opacity: 0.7;
                }

                input {
                    display: block;
                    width: 100%;
                    height: 52px;
                    padding: 0 15px 0 45px;
                    border-radius: 13px;
                    border: 1px solid #343842;
                    outline: none;
                    background: #101217;
                    color: #fff;
                    font-family: inherit;
                    font-size: 16px;
                    font-weight: 500;
                    letter-spacing: 0.5px;
                    transition:
                        border-color 0.2s ease,
                        box-shadow 0.2s ease,
                        background 0.2s ease;
                    -webkit-appearance: none;
                    appearance: none;
                }

                input::placeholder {
                    color: #666b76;
                    font-size: 14px;
                }

                input:focus {
                    border-color: #20d76b;
                    background: #12151a;
                    box-shadow:
                        0 0 0 3px rgba(32,215,107,0.10),
                        0 8px 25px rgba(0,0,0,0.2);
                }

                button {
                    width: 100%;
                    height: 52px;
                    margin-top: 14px;
                    border: 0;
                    border-radius: 13px;
                    background: linear-gradient(
                        135deg,
                        #20d76b,
                        #0eb85a
                    );
                    color: #06130b;
                    font-family: inherit;
                    font-size: 14px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                    cursor: pointer;
                    box-shadow:
                        0 10px 25px rgba(32,215,107,0.18),
                        inset 0 1px 0 rgba(255,255,255,0.25);
                    transition:
                        transform 0.15s ease,
                        filter 0.15s ease;
                    -webkit-appearance: none;
                    appearance: none;
                }

                button:active {
                    transform: scale(0.98);
                    filter: brightness(0.92);
                }

                .features {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 8px;
                }

                .feature {
                    min-width: 0;
                    padding: 12px 6px;
                    border-radius: 12px;
                    background: rgba(255,255,255,0.025);
                    border: 1px solid rgba(255,255,255,0.05);
                }

                .feature-icon {
                    font-size: 17px;
                    margin-bottom: 6px;
                }

                .feature-title {
                    color: #d8dbe1;
                    font-size: 10px;
                    font-weight: 700;
                    line-height: 1.3;
                }

                .feature-text {
                    color: #777d89;
                    font-size: 9px;
                    margin-top: 3px;
                }

                .copyright {
                    margin-top: 22px;
                    color: #555a65;
                    font-size: 10px;
                    line-height: 1.7;
                }

                @media (max-width: 380px) {
                    body {
                        padding: 16px 12px;
                    }

                    .box {
                        padding: 25px 18px 20px;
                        border-radius: 20px;
                    }

                    .logo {
                        width: 68px;
                        height: 68px;
                        font-size: 34px;
                    }

                    h1 {
                        font-size: 22px;
                    }

                    .features {
                        gap: 5px;
                    }

                    .feature {
                        padding: 10px 4px;
                    }
                }

                @media (min-width: 600px) {
                    .box {
                        padding: 38px 34px 30px;
                    }
                }
            </style>
        </head>

        <body>

            <main class="container">

                <section class="box">

                    <div class="logo">🎬</div>

                    <h1>FAPHOUSE PLAYER</h1>

                    <p class="subtitle">
                        Premium License Manager
                    </p>

                    <p class="brand">
                        Powered by <b>LAPAK ANGKER</b>
                    </p>

                    <div class="divider"></div>

                    <div class="error">
                        <span>❌</span>
                        <span>License key yang kamu masukkan tidak valid.</span>
                    </div>

                    <form method="POST">

                        <label class="label">
                            🔑 License Key
                        </label>

                        <div class="input-wrapper">
                            <span class="input-icon">🔐</span>

                            <input
                                type="text"
                                name="license"
                                placeholder="FAPHOUSE-XXXXX-XXXXX"
                                autocomplete="off"
                                autocapitalize="characters"
                                spellcheck="false"
                                required
                            >
                        </div>

                        <button type="submit">
                            ⚡ AKTIVASI LICENSE
                        </button>

                    </form>

                    <div class="divider"></div>

                    <div class="features">

                        <div class="feature">
                            <div class="feature-icon">🛡️</div>
                            <div class="feature-title">SECURE</div>
                            <div class="feature-text">Protected</div>
                        </div>

                        <div class="feature">
                            <div class="feature-icon">⚡</div>
                            <div class="feature-title">FAST</div>
                            <div class="feature-text">Verification</div>
                        </div>

                        <div class="feature">
                            <div class="feature-icon">📦</div>
                            <div class="feature-title">VERSION</div>
                            <div class="feature-text">1.0.0</div>
                        </div>

                    </div>

                    <div class="copyright">
                        © 2026 LAPAK ANGKER<br>
                        All Rights Reserved
                    </div>

                </section>

            </main>

        </body>
        </html>
        """)

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"
        >

        <title>Faphouse Player - License</title>

        <style>
            * {
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            html, body {
                margin: 0;
                padding: 0;
                width: 100%;
                min-height: 100%;
                font-family: Arial, Helvetica, sans-serif;
                background: #08090d;
                color: #fff;
            }

            body {
                min-height: 100vh;
                min-height: 100dvh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 24px 16px;
                position: relative;
                overflow-x: hidden;
            }

            body::before {
                content: "";
                position: fixed;
                width: 420px;
                height: 420px;
                background: rgba(0, 255, 140, 0.08);
                filter: blur(100px);
                border-radius: 50%;
                top: -180px;
                left: -160px;
                pointer-events: none;
            }

            body::after {
                content: "";
                position: fixed;
                width: 380px;
                height: 380px;
                background: rgba(80, 100, 255, 0.07);
                filter: blur(100px);
                border-radius: 50%;
                bottom: -180px;
                right: -140px;
                pointer-events: none;
            }

            .container {
                width: 100%;
                max-width: 430px;
                position: relative;
                z-index: 2;
            }

            .box {
                width: 100%;
                background: rgba(22, 24, 31, 0.94);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 24px;
                padding: 30px 26px 25px;
                text-align: center;
                box-shadow:
                    0 25px 70px rgba(0,0,0,0.55),
                    inset 0 1px 0 rgba(255,255,255,0.04);
                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
            }

            .logo {
                width: 76px;
                height: 76px;
                margin: 0 auto 18px;
                border-radius: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 38px;
                background: linear-gradient(
                    145deg,
                    #1ed760,
                    #0aa85a
                );
                box-shadow:
                    0 12px 30px rgba(30,215,96,0.22),
                    inset 0 1px 0 rgba(255,255,255,0.25);
            }

            h1 {
                margin: 0;
                font-size: 25px;
                line-height: 1.2;
                font-weight: 800;
                letter-spacing: 1.5px;
            }

            .subtitle {
                margin: 9px 0 0;
                color: #9297a5;
                font-size: 14px;
                line-height: 1.5;
            }

            .brand {
                margin: 12px 0 0;
                color: #45e58a;
                font-size: 12px;
                letter-spacing: 0.4px;
            }

            .divider {
                height: 1px;
                border: 0;
                background: linear-gradient(
                    90deg,
                    transparent,
                    rgba(255,255,255,0.1),
                    transparent
                );
                margin: 25px 0;
            }

            .label {
                display: block;
                text-align: left;
                margin-bottom: 9px;
                color: #dfe2e8;
                font-size: 13px;
                font-weight: 700;
            }

            .input-wrapper {
                position: relative;
                width: 100%;
            }

            .input-icon {
                position: absolute;
                left: 15px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 17px;
                pointer-events: none;
                opacity: 0.7;
            }

            input {
                display: block;
                width: 100%;
                height: 52px;
                padding: 0 15px 0 45px;
                border-radius: 13px;
                border: 1px solid #343842;
                outline: none;
                background: #101217;
                color: #fff;
                font-family: inherit;
                font-size: 16px;
                font-weight: 500;
                letter-spacing: 0.5px;
                transition:
                    border-color 0.2s ease,
                    box-shadow 0.2s ease,
                    background 0.2s ease;
                -webkit-appearance: none;
                appearance: none;
            }

            input::placeholder {
                color: #666b76;
                font-size: 14px;
            }

            input:focus {
                border-color: #20d76b;
                background: #12151a;
                box-shadow:
                    0 0 0 3px rgba(32,215,107,0.10),
                    0 8px 25px rgba(0,0,0,0.2);
            }

            button {
                width: 100%;
                height: 52px;
                margin-top: 14px;
                border: 0;
                border-radius: 13px;
                background: linear-gradient(
                    135deg,
                    #20d76b,
                    #0eb85a
                );
                color: #06130b;
                font-family: inherit;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
                cursor: pointer;
                box-shadow:
                    0 10px 25px rgba(32,215,107,0.18),
                    inset 0 1px 0 rgba(255,255,255,0.25);
                transition: transform 0.15s ease;
                -webkit-appearance: none;
                appearance: none;
            }

            button:active {
                transform: scale(0.98);
            }

            .features {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
            }

            .feature {
                min-width: 0;
                padding: 12px 6px;
                border-radius: 12px;
                background: rgba(255,255,255,0.025);
                border: 1px solid rgba(255,255,255,0.05);
            }

            .feature-icon {
                font-size: 17px;
                margin-bottom: 6px;
            }

            .feature-title {
                color: #d8dbe1;
                font-size: 10px;
                font-weight: 700;
                line-height: 1.3;
            }

            .feature-text {
                color: #777d89;
                font-size: 9px;
                margin-top: 3px;
            }

            .copyright {
                margin-top: 22px;
                color: #555a65;
                font-size: 10px;
                line-height: 1.7;
            }

            @media (max-width: 380px) {
                body {
                    padding: 16px 12px;
                }

                .box {
                    padding: 25px 18px 20px;
                    border-radius: 20px;
                }

                .logo {
                    width: 68px;
                    height: 68px;
                    font-size: 34px;
                }

                h1 {
                    font-size: 22px;
                }

                .features {
                    gap: 5px;
                }

                .feature {
                    padding: 10px 4px;
                }
            }

            @media (min-width: 600px) {
                .box {
                    padding: 38px 34px 30px;
                }
            }
        </style>
    </head>

    <body>

        <main class="container">

            <section class="box">

                <div class="logo">🎬</div>

                <h1>FAPHOUSE PLAYER</h1>

                <p class="subtitle">
                    Premium License Manager
                </p>

                <p class="brand">
                    Powered by <b>LAPAK ANGKER</b>
                </p>

                <div class="divider"></div>

                <form method="POST">

                    <label class="label">
                        🔑 License Key
                    </label>

                    <div class="input-wrapper">
                        <span class="input-icon">🔐</span>

                        <input
                            type="text"
                            name="license"
                            placeholder="FAPHOUSE-XXXXX-XXXXX"
                            autocomplete="off"
                            autocapitalize="characters"
                            spellcheck="false"
                            required
                        >
                    </div>

                    <button type="submit">
                        ⚡ AKTIVASI LICENSE
                    </button>

                </form>

                <div class="divider"></div>

                <div class="features">

                    <div class="feature">
                        <div class="feature-icon">🛡️</div>
                        <div class="feature-title">SECURE</div>
                        <div class="feature-text">Protected</div>
                    </div>

                    <div class="feature">
                        <div class="feature-icon">⚡</div>
                        <div class="feature-title">FAST</div>
                        <div class="feature-text">Verification</div>
                    </div>

                    <div class="feature">
                        <div class="feature-icon">📦</div>
                        <div class="feature-title">VERSION</div>
                        <div class="feature-text">1.0.0</div>
                    </div>

                </div>

                <div class="copyright">
                    © 2026 LAPAK ANGKER<br>
                    All Rights Reserved
                </div>

            </section>

        </main>

    </body>
    </html>
    """)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():

    # Jika sudah login admin
    if session.get("admin_logged_in"):
        return redirect("/admin/dashboard")

    if request.method == 'POST':

        pin = request.form.get("pin", "").strip()

        admin_pin = os.environ.get("ADMIN_PIN", "")

        if admin_pin and hmac.compare_digest(pin, admin_pin):

            session["admin_logged_in"] = True

            return redirect("/admin/dashboard")

        error = True

    else:
        error = False

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"
        >

        <title>Admin Login - Lapak Angker</title>

        <style>

            * {
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            html,
            body {
                margin: 0;
                padding: 0;
                width: 100%;
                min-height: 100%;
            }

            body {

                min-height: 100vh;
                min-height: 100dvh;

                display: flex;
                align-items: center;
                justify-content: center;

                padding: 24px 16px;

                background: #08090d;

                color: #fff;

                font-family:
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    Roboto,
                    Arial,
                    sans-serif;

                position: relative;

                overflow: hidden;
            }


            /* Background Glow */

            body::before {

                content: "";

                position: fixed;

                width: 420px;
                height: 420px;

                top: -200px;
                left: -180px;

                background: rgba(0,255,140,0.07);

                filter: blur(100px);

                border-radius: 50%;

                pointer-events: none;
            }


            body::after {

                content: "";

                position: fixed;

                width: 380px;
                height: 380px;

                right: -180px;
                bottom: -200px;

                background: rgba(80,100,255,0.07);

                filter: blur(110px);

                border-radius: 50%;

                pointer-events: none;
            }


            .container {

                width: 100%;

                max-width: 410px;

                position: relative;

                z-index: 2;
            }


            .box {

                width: 100%;

                padding: 32px 26px 26px;

                background: rgba(22,24,31,0.95);

                border: 1px solid rgba(255,255,255,0.08);

                border-radius: 24px;

                text-align: center;

                box-shadow:
                    0 25px 70px rgba(0,0,0,0.55),
                    inset 0 1px 0 rgba(255,255,255,0.04);

                backdrop-filter: blur(18px);

                -webkit-backdrop-filter: blur(18px);
            }


            .logo {

                width: 76px;
                height: 76px;

                margin: 0 auto 18px;

                display: flex;

                align-items: center;

                justify-content: center;

                border-radius: 22px;

                font-size: 36px;

                background:
                    linear-gradient(
                        145deg,
                        #1ed760,
                        #0aa85a
                    );

                box-shadow:
                    0 12px 30px rgba(30,215,96,0.22),
                    inset 0 1px 0 rgba(255,255,255,0.25);
            }


            h1 {

                margin: 0;

                font-size: 25px;

                line-height: 1.2;

                font-weight: 800;

                letter-spacing: 1.3px;
            }


            .subtitle {

                margin: 9px 0 0;

                color: #9297a5;

                font-size: 13px;
            }


            .brand {

                margin-top: 11px;

                color: #45e58a;

                font-size: 11px;
            }


            .divider {

                height: 1px;

                margin: 25px 0;

                background:
                    linear-gradient(
                        90deg,
                        transparent,
                        rgba(255,255,255,0.1),
                        transparent
                    );
            }


            .error {

                display: flex;

                align-items: center;

                gap: 9px;

                margin-bottom: 18px;

                padding: 12px;

                border-radius: 12px;

                background: rgba(255,70,70,0.08);

                border: 1px solid rgba(255,70,70,0.18);

                color: #ff7777;

                font-size: 12px;

                text-align: left;
            }


            .label {

                display: block;

                text-align: left;

                margin-bottom: 9px;

                color: #dfe2e8;

                font-size: 13px;

                font-weight: 700;
            }


            .input-wrapper {

                position: relative;
            }


            .input-icon {

                position: absolute;

                left: 15px;

                top: 50%;

                transform: translateY(-50%);

                font-size: 17px;

                opacity: 0.7;

                pointer-events: none;
            }


            input {

                display: block;

                width: 100%;

                height: 52px;

                padding: 0 15px 0 45px;

                border-radius: 13px;

                border: 1px solid #343842;

                outline: none;

                background: #101217;

                color: #fff;

                font-family: inherit;

                font-size: 16px;

                letter-spacing: 3px;

                transition:
                    border-color 0.2s ease,
                    box-shadow 0.2s ease,
                    background 0.2s ease;

                -webkit-appearance: none;

                appearance: none;
            }


            input:focus {

                border-color: #20d76b;

                background: #12151a;

                box-shadow:
                    0 0 0 3px rgba(32,215,107,0.10),
                    0 8px 25px rgba(0,0,0,0.2);
            }


            input::placeholder {

                color: #666b76;

                font-size: 12px;

                letter-spacing: 1px;
            }


            button {

                width: 100%;

                height: 52px;

                margin-top: 14px;

                border: 0;

                border-radius: 13px;

                background:
                    linear-gradient(
                        135deg,
                        #20d76b,
                        #0eb85a
                    );

                color: #06130b;

                font-family: inherit;

                font-size: 14px;

                font-weight: 800;

                letter-spacing: 0.5px;

                cursor: pointer;

                box-shadow:
                    0 10px 25px rgba(32,215,107,0.18),
                    inset 0 1px 0 rgba(255,255,255,0.25);

                transition: transform 0.15s ease;

                -webkit-appearance: none;

                appearance: none;
            }


            button:active {

                transform: scale(0.98);
            }


            .security {

                margin-top: 22px;

                padding: 12px;

                border-radius: 12px;

                background: rgba(255,255,255,0.025);

                border: 1px solid rgba(255,255,255,0.05);

                color: #686e7a;

                font-size: 10px;

                line-height: 1.6;
            }


            .footer {

                margin-top: 20px;

                color: #4f545e;

                font-size: 9px;

                line-height: 1.6;
            }


            @media (max-width: 380px) {

                body {
                    padding: 16px 12px;
                }

                .box {

                    padding: 26px 18px 22px;

                    border-radius: 20px;
                }

                .logo {

                    width: 68px;
                    height: 68px;

                    font-size: 33px;
                }

                h1 {
                    font-size: 22px;
                }
            }

        </style>

    </head>


    <body>

        <main class="container">

            <section class="box">

                <div class="logo">
                    🛡️
                </div>

                <h1>
                    ADMIN PANEL
                </h1>

                <p class="subtitle">
                    Secure License Management
                </p>

                <p class="brand">
                    Powered by <b>LAPAK ANGKER</b>
                </p>

                <div class="divider"></div>

                {% if error %}

                <div class="error">

                    <span>❌</span>

                    <span>
                        PIN admin salah. Silakan coba kembali.
                    </span>

                </div>

                {% endif %}

                <form method="POST">

                    <label class="label">
                        🔐 Administrator PIN
                    </label>

                    <div class="input-wrapper">

                        <span class="input-icon">
                            🔑
                        </span>

                        <input
                            type="password"
                            name="pin"
                            placeholder="Masukkan PIN admin"
                            inputmode="numeric"
                            autocomplete="off"
                            required
                        >

                    </div>

                    <button type="submit">
                        🔓 LOGIN ADMIN
                    </button>

                </form>

                <div class="security">

                    🛡️ Secure administrator access<br>

                    Only authorized administrators can access this panel.

                </div>

                <div class="footer">

                    © 2026 LAPAK ANGKER<br>

                    All Rights Reserved

                </div>

            </section>

        </main>

    </body>

    </html>
    """, error=error)

@app.route('/admin/dashboard')
def admin_dashboard():

    if not session.get("admin_logged_in"):
        return redirect("/admin")

    return render_template_string("""
    <!DOCTYPE html>

    <html lang="id">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"
        >

        <title>Admin Dashboard - Lapak Angker</title>

        <style>

            * {
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            body {

                margin: 0;

                min-height: 100vh;
                min-height: 100dvh;

                background: #08090d;

                color: white;

                font-family:
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    Roboto,
                    Arial,
                    sans-serif;

                padding: 20px 16px;
            }


            .page {

                width: 100%;

                max-width: 700px;

                margin: auto;
            }


            .header {

                display: flex;

                align-items: center;

                justify-content: space-between;

                margin-bottom: 16px;
            }


            .brand {

                display: flex;

                align-items: center;

                gap: 11px;
            }


            .brand-icon {

                width: 45px;
                height: 45px;

                display: flex;

                align-items: center;

                justify-content: center;

                border-radius: 13px;

                background:
                    linear-gradient(
                        145deg,
                        #1ed760,
                        #0aa85a
                    );

                font-size: 21px;
            }


            .brand-title {

                font-size: 15px;

                font-weight: 800;
            }


            .brand-subtitle {

                margin-top: 3px;

                color: #666c78;

                font-size: 10px;
            }


            .logout {

                padding: 9px 12px;

                border-radius: 10px;

                border:
                    1px solid rgba(255,80,80,0.18);

                background:
                    rgba(255,70,70,0.08);

                color: #ff7777;

                text-decoration: none;

                font-size: 10px;

                font-weight: 800;
            }


            .hero {

                padding: 24px 20px;

                border-radius: 20px;

                background:
                    rgba(22,24,31,0.94);

                border:
                    1px solid rgba(255,255,255,0.08);

                box-shadow:
                    0 20px 55px rgba(0,0,0,0.45),
                    inset 0 1px 0 rgba(255,255,255,0.04);

                margin-bottom: 12px;
            }


            .hero h1 {

                margin: 0;

                font-size: 23px;

                letter-spacing: 0.8px;
            }


            .hero p {

                margin: 8px 0 0;

                color: #858b97;

                font-size: 12px;
            }


            .cards {

                display: grid;

                grid-template-columns:
                    repeat(2, 1fr);

                gap: 10px;

                margin-bottom: 12px;
            }


            .card {

                padding: 17px;

                border-radius: 15px;

                background:
                    rgba(22,24,31,0.94);

                border:
                    1px solid rgba(255,255,255,0.07);
            }


            .card-icon {

                font-size: 20px;

                margin-bottom: 9px;
            }


            .card-label {

                color: #666c78;

                font-size: 10px;
            }


            .card-value {

                margin-top: 5px;

                font-size: 20px;

                font-weight: 800;

                color: #45e58a;
            }


            .manager {

                padding: 20px;

                border-radius: 18px;

                background:
                    rgba(22,24,31,0.94);

                border:
                    1px solid rgba(255,255,255,0.07);
            }


            .manager-title {

                display: flex;

                align-items: center;

                gap: 9px;

                color: #dfe2e8;

                font-size: 14px;

                font-weight: 800;
            }


            .manager-description {

                margin-top: 7px;

                color: #666c78;

                font-size: 11px;

                line-height: 1.6;
            }


            .coming {

                margin-top: 17px;

                padding: 16px;

                border-radius: 13px;

                background:
                    rgba(32,215,107,0.04);

                border:
                    1px dashed rgba(32,215,107,0.16);

                text-align: center;

                color: #686e7a;

                font-size: 11px;

                line-height: 1.7;
            }


            .coming strong {

                display: block;

                color: #45e58a;

                margin-bottom: 4px;
            }


            .footer {

                text-align: center;

                margin-top: 18px;

                color: #4f545e;

                font-size: 9px;

                line-height: 1.6;
            }


            @media (max-width: 380px) {

                body {
                    padding: 16px 12px;
                }

                .hero {
                    padding: 21px 17px;
                }

                .cards {
                    gap: 7px;
                }

                .card {
                    padding: 14px;
                }

            }

        </style>

    </head>


    <body>

        <main class="page">


            <header class="header">

                <div class="brand">

                    <div class="brand-icon">
                        🎛️
                    </div>

                    <div>

                        <div class="brand-title">
                            LAPAK ANGKER
                        </div>

                        <div class="brand-subtitle">
                            Administrator Control
                        </div>

                    </div>

                </div>


                <a
                    href="/admin/logout"
                    class="logout"
                >
                    🚪 Logout
                </a>

            </header>


            <section class="hero">

                <h1>
                    License Dashboard
                </h1>

                <p>
                    Kelola license Faphouse Player dari satu tempat.
                </p>

            </section>


            <section class="cards">

                <div class="card">

                    <div class="card-icon">
                        🔑
                    </div>

                    <div class="card-label">
                        TOTAL LICENSE
                    </div>

                    <div class="card-value">
                        0
                    </div>

                </div>


                <div class="card">

                    <div class="card-icon">
                        🟢
                    </div>

                    <div class="card-label">
                        ACTIVE LICENSE
                    </div>

                    <div class="card-value">
                        0
                    </div>

                </div>

            </section>


            <section class="manager">

                <div class="manager-title">
                    🔐 License Manager
                </div>

                <div class="manager-description">

                    Panel pembuatan dan pengelolaan license
                    akan kita tambahkan pada tahap berikutnya.

                </div>


                <div class="coming">

                    <strong>
                        🚀 LICENSE GENERATOR
                    </strong>

                    Tahap berikutnya kita akan membuat
                    generator license otomatis, daftar license,
                    status aktif/nonaktif, copy license,
                    dan penghapusan license.

                </div>

            </section>


            <div class="footer">

                © 2026 LAPAK ANGKER<br>

                Administrator Panel

            </div>


        </main>

    </body>

    </html>
    """)

@app.route('/admin/logout')
def admin_logout():

    session.pop("admin_logged_in", None)

    return redirect("/admin")

@app.route('/')
def index():
    if not session.get("licensed"):
        return redirect("/license")

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"
        >

        <title>🎬 Faphouse Player</title>

        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            html, body {
                width: 100%;
                min-height: 100%;
            }

            body {
                background: #08090d;
                color: #fff;
                font-family:
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    Roboto,
                    Arial,
                    sans-serif;

                min-height: 100vh;
                min-height: 100dvh;

                padding: 24px 16px;

                position: relative;
                overflow-x: hidden;
            }

            /* Background glow */

            body::before {
                content: "";
                position: fixed;

                width: 430px;
                height: 430px;

                top: -220px;
                left: -180px;

                background: rgba(0, 255, 140, 0.07);

                filter: blur(100px);
                border-radius: 50%;

                pointer-events: none;
            }

            body::after {
                content: "";
                position: fixed;

                width: 400px;
                height: 400px;

                right: -180px;
                bottom: -200px;

                background: rgba(70, 90, 255, 0.06);

                filter: blur(110px);
                border-radius: 50%;

                pointer-events: none;
            }

            .page {
                width: 100%;
                max-width: 600px;

                margin: 0 auto;

                position: relative;
                z-index: 2;
            }

            /* =========================
               MAIN PLAYER
            ========================= */

            .player-box {
                width: 100%;

                background: rgba(22, 24, 31, 0.94);

                border: 1px solid rgba(255,255,255,0.08);

                border-radius: 24px;

                padding: 32px 26px;

                box-shadow:
                    0 25px 70px rgba(0,0,0,0.55),
                    inset 0 1px 0 rgba(255,255,255,0.04);

                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);

                text-align: center;
            }

            .logo {
                width: 76px;
                height: 76px;

                margin: 0 auto 18px;

                display: flex;
                align-items: center;
                justify-content: center;

                border-radius: 22px;

                font-size: 38px;

                background:
                    linear-gradient(
                        145deg,
                        #1ed760,
                        #0aa85a
                    );

                box-shadow:
                    0 12px 30px rgba(30,215,96,0.22),
                    inset 0 1px 0 rgba(255,255,255,0.25);
            }

            h1 {
                font-size: 28px;
                line-height: 1.2;

                font-weight: 800;

                letter-spacing: 1.3px;

                margin: 0;
            }

            .subtitle {
                color: #9297a5;

                font-size: 14px;

                margin-top: 9px;

                line-height: 1.5;
            }

            .brand {
                color: #45e58a;

                font-size: 12px;

                margin-top: 11px;

                letter-spacing: 0.4px;
            }

            .divider {
                height: 1px;

                border: 0;

                margin: 25px 0;

                background:
                    linear-gradient(
                        90deg,
                        transparent,
                        rgba(255,255,255,0.1),
                        transparent
                    );
            }

            /* =========================
               URL FORM
            ========================= */

            .form-title {
                text-align: left;

                color: #dfe2e8;

                font-size: 13px;

                font-weight: 700;

                margin-bottom: 9px;
            }

            .url-input {
                width: 100%;
            }

            .url-wrapper {
                position: relative;
                width: 100%;
            }

            .url-icon {
                position: absolute;

                left: 15px;
                top: 50%;

                transform: translateY(-50%);

                font-size: 17px;

                opacity: 0.7;

                pointer-events: none;
            }

            .url-input input {
                display: block;

                width: 100%;
                height: 52px;

                padding: 0 15px 0 45px;

                background: #101217;

                border: 1px solid #343842;

                border-radius: 13px;

                color: #fff;

                font-family: inherit;

                font-size: 16px;

                outline: none;

                transition:
                    border-color 0.2s ease,
                    box-shadow 0.2s ease,
                    background 0.2s ease;

                -webkit-appearance: none;
                appearance: none;
            }

            .url-input input::placeholder {
                color: #666b76;
                font-size: 14px;
            }

            .url-input input:focus {
                border-color: #20d76b;

                background: #12151a;

                box-shadow:
                    0 0 0 3px rgba(32,215,107,0.10),
                    0 8px 25px rgba(0,0,0,0.2);
            }

            .watch-button {
                width: 100%;
                height: 52px;

                margin-top: 14px;

                border: none;

                border-radius: 13px;

                background:
                    linear-gradient(
                        135deg,
                        #20d76b,
                        #0eb85a
                    );

                color: #06130b;

                font-family: inherit;

                font-size: 14px;

                font-weight: 800;

                letter-spacing: 0.5px;

                cursor: pointer;

                box-shadow:
                    0 10px 25px rgba(32,215,107,0.18),
                    inset 0 1px 0 rgba(255,255,255,0.25);

                transition:
                    transform 0.15s ease,
                    filter 0.15s ease;

                -webkit-appearance: none;
                appearance: none;
            }

            .watch-button:active {
                transform: scale(0.98);
                filter: brightness(0.92);
            }

            /* =========================
               HINT
            ========================= */

            .hint {
                margin-top: 14px;

                color: #686e7a;

                font-size: 11px;

                line-height: 1.7;

                text-align: left;
            }

            .hint code {
                display: block;

                margin-top: 6px;

                padding: 9px 10px;

                background: #101217;

                border: 1px solid rgba(255,255,255,0.05);

                border-radius: 9px;

                color: #777e8b;

                font-size: 10px;

                line-height: 1.5;

                word-break: break-all;
            }

            /* =========================
               API ENDPOINTS
            ========================= */

            .endpoints {
                margin-top: 25px;

                padding: 18px;

                background: rgba(255,255,255,0.025);

                border: 1px solid rgba(255,255,255,0.06);

                border-radius: 15px;

                text-align: left;
            }

            .endpoints-header {
                display: flex;

                align-items: center;

                gap: 8px;

                margin-bottom: 13px;
            }

            .endpoints-icon {
                font-size: 18px;
            }

            .endpoints h3 {
                color: #d8dbe1;

                font-size: 13px;

                font-weight: 700;
            }

            .endpoint {
                padding: 11px 0;

                border-bottom: 1px solid rgba(255,255,255,0.06);

                color: #858b97;

                font-size: 11px;

                line-height: 1.5;
            }

            .endpoint:last-child {
                border-bottom: none;
                padding-bottom: 0;
            }

            .endpoint:first-of-type {
                padding-top: 0;
            }

            .endpoint strong {
                color: #45e58a;

                font-size: 10px;

                margin-right: 5px;
            }

            /* =========================
               ACCOUNT PANEL
            ========================= */

            .account-box {
                width: 100%;

                margin-top: 16px;

                padding: 22px 20px 20px;

                background: rgba(22, 24, 31, 0.94);

                border: 1px solid rgba(255,255,255,0.08);

                border-radius: 20px;

                box-shadow:
                    0 18px 45px rgba(0,0,0,0.35),
                    inset 0 1px 0 rgba(255,255,255,0.03);

                backdrop-filter: blur(18px);
                -webkit-backdrop-filter: blur(18px);
            }

            .account-header {
                display: flex;

                align-items: center;

                justify-content: space-between;

                margin-bottom: 18px;
            }

            .account-title {
                display: flex;

                align-items: center;

                gap: 11px;
            }

            .account-icon {
                width: 40px;
                height: 40px;

                display: flex;
                align-items: center;
                justify-content: center;

                border-radius: 12px;

                background: rgba(32,215,107,0.10);

                border: 1px solid rgba(32,215,107,0.15);

                font-size: 20px;
            }

            .account-heading {
                color: #fff;

                font-size: 14px;

                font-weight: 800;
            }

            .account-subheading {
                color: #686e7a;

                font-size: 10px;

                margin-top: 3px;
            }

            .status {
                display: inline-flex;

                align-items: center;

                gap: 5px;

                padding: 6px 9px;

                border-radius: 20px;

                background: rgba(32,215,107,0.08);

                border: 1px solid rgba(32,215,107,0.15);

                color: #45e58a;

                font-size: 9px;

                font-weight: 800;

                letter-spacing: 0.4px;
            }

            .status-dot {
                width: 6px;
                height: 6px;

                border-radius: 50%;

                background: #20d76b;

                box-shadow: 0 0 8px rgba(32,215,107,0.8);
            }

            .account-info {
                display: grid;

                grid-template-columns: 1fr 1fr;

                gap: 8px;

                margin-bottom: 18px;
            }

            .info-item {
                padding: 12px;

                background: rgba(255,255,255,0.025);

                border: 1px solid rgba(255,255,255,0.05);

                border-radius: 12px;
            }

            .info-label {
                color: #666c78;

                font-size: 9px;

                margin-bottom: 5px;
            }

            .info-value {
                color: #dfe2e8;

                font-size: 11px;

                font-weight: 700;
            }

            .info-value.active {
                color: #45e58a;
            }

            .logout-button {
                display: flex;

                align-items: center;
                justify-content: center;

                width: 100%;
                height: 48px;

                border-radius: 12px;

                background:
                    linear-gradient(
                        135deg,
                        rgba(255,70,70,0.12),
                        rgba(180,40,40,0.10)
                    );

                border: 1px solid rgba(255,80,80,0.18);

                color: #ff7777;

                text-decoration: none;

                font-size: 12px;

                font-weight: 800;

                letter-spacing: 0.3px;

                transition:
                    background 0.2s ease,
                    transform 0.15s ease;
            }

            .logout-button:active {
                transform: scale(0.98);

                background:
                    rgba(255,70,70,0.18);
            }

            .account-footer {
                margin-top: 17px;

                text-align: center;

                color: #4f545e;

                font-size: 9px;

                line-height: 1.6;
            }

            /* =========================
               MOBILE
            ========================= */

            @media (max-width: 380px) {

                body {
                    padding: 16px 12px;
                }

                .player-box {
                    padding: 26px 18px 22px;

                    border-radius: 20px;
                }

                .logo {
                    width: 68px;
                    height: 68px;

                    font-size: 34px;

                    border-radius: 20px;
                }

                h1 {
                    font-size: 23px;
                }

                .account-box {
                    padding: 19px 15px 17px;

                    border-radius: 18px;
                }

                .account-info {
                    gap: 6px;
                }

                .info-item {
                    padding: 10px;
                }
            }

            @media (min-width: 600px) {

                body {
                    padding: 40px 20px;
                }

                .player-box {
                    padding: 38px 34px 32px;
                }

                .account-box {
                    padding: 24px 22px 21px;
                }
            }
        </style>
    </head>

    <body>

        <main class="page">

            <!-- =========================
                 MAIN PLAYER BOX
            ========================== -->

            <section class="player-box">

                <div class="logo">
                    🎬
                </div>

                <h1>
                    FAPHOUSE PLAYER
                </h1>

                <p class="subtitle">
                    Enter any video URL to watch
                </p>

                <p class="brand">
                    Powered by <b>LAPAK ANGKER</b>
                </p>

                <div class="divider"></div>

                <div class="url-input">

                    <form method="GET" action="/play">

                        <div class="form-title">
                            🔗 Video URL
                        </div>

                        <div class="url-wrapper">

                            <span class="url-icon">
                                🌐
                            </span>

                            <input
                                type="url"
                                name="url"
                                placeholder="Paste video URL here..."
                                autocomplete="off"
                                spellcheck="false"
                                required
                            >

                        </div>

                        <button
                            type="submit"
                            class="watch-button"
                        >
                            ▶ WATCH NOW
                        </button>

                    </form>

                    <div class="hint">

                        💡 Example:

                        <code>
                            https://faphouse2.com/videos/shared-bed-stepsister-fuck-C6Qi1u
                        </code>

                    </div>

                </div>

                <div class="endpoints">

                    <div class="endpoints-header">

                        <span class="endpoints-icon">
                            📡
                        </span>

                        <h3>
                            API ENDPOINTS
                        </h3>

                    </div>

                    <div class="endpoint">
                        <strong>GET</strong>
                        /play?url=VIDEO_URL
                        — Watch video
                    </div>

                    <div class="endpoint">
                        <strong>GET</strong>
                        /api/m3u8?url=VIDEO_URL
                        — Get M3U8 URL
                    </div>

                    <div class="endpoint">
                        <strong>GET</strong>
                        /api/status
                        — Check status
                    </div>

                </div>

            </section>


            <!-- =========================
                 ACCOUNT BOX
            ========================== -->

            <section class="account-box">

                <div class="account-header">

                    <div class="account-title">

                        <div class="account-icon">
                            👤
                        </div>

                        <div>
                            <div class="account-heading">
                                ACCOUNT
                            </div>

                            <div class="account-subheading">
                                License & Session
                            </div>
                        </div>

                    </div>

                    <div class="status">
                        <span class="status-dot"></span>
                        ACTIVE
                    </div>

                </div>


                <div class="account-info">

                    <div class="info-item">

                        <div class="info-label">
                            🛡 LICENSE
                        </div>

                        <div class="info-value active">
                            ACTIVE
                        </div>

                    </div>

                    <div class="info-item">

                        <div class="info-label">
                            📦 VERSION
                        </div>

                        <div class="info-value">
                            1.0.0
                        </div>

                    </div>

                    <div class="info-item">

                        <div class="info-label">
                            🔐 SESSION
                        </div>

                        <div class="info-value active">
                            SECURED
                        </div>

                    </div>

                    <div class="info-item">

                        <div class="info-label">
                            ⚡ STATUS
                        </div>

                        <div class="info-value active">
                            ONLINE
                        </div>

                    </div>

                </div>


                <a
                    href="/logout"
                    class="logout-button"
                >
                    🚪 LOGOUT LICENSE
                </a>


                <div class="account-footer">
                    License session is protected<br>
                    © 2026 LAPAK ANGKER · All Rights Reserved
                </div>

            </section>

        </main>

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
    
@app.route("/logout")
def logout():
    session.pop("licensed", None)
    return redirect("/license")

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
