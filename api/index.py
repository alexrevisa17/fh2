from flask import Flask, jsonify, request, render_template, render_template_string, session, redirect
from supabase import create_client
from urllib.parse import urljoin, unquote
from html import unescape

import requests
import re
import json
import os
import hmac
from functools import lru_cache
from datetime import datetime, timedelta, timezone
import time
import logging
import zlib
import gzip
import random
import string
from io import BytesIO


# ============================================================
# APP
# ============================================================

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static"
)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-secret-key"
)


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY wajib diatur di Vercel Environment Variables."
    )

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# LICENSE SYSTEM
# ============================================================

@app.before_request
def verify_license():

    # Route admin tidak membutuhkan lisensi user
    if request.endpoint and request.endpoint.startswith("admin_"):
        return

    # Static files
    if request.endpoint == "static":
        return

    # Halaman license
    if request.endpoint == "license_page":
        return

    license_key = session.get("license_key")
    device_id = session.get("device_id")

    if not license_key or not device_id:
        session.clear()
        return redirect("/license")

    if not check_license(license_key):
        session.clear()
        return redirect("/license")

    try:

        license_result = (
            supabase
            .table("licenses")
            .select("id")
            .eq("license_key", license_key)
            .single()
            .execute()
        )

        if not license_result.data:
            session.clear()
            return redirect("/license")

        license_id = license_result.data["id"]

        device_result = (
            supabase
            .table("license_devices")
            .select("id")
            .eq("license_id", license_id)
            .eq("device_id", device_id)
            .limit(1)
            .execute()
        )

        if not device_result.data:
            session.clear()
            return redirect("/license")

    except Exception as e:

        logger.error(
            f"Device verification error: {e}"
        )

        session.clear()

        return redirect("/license")


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

        license_data = result.data

        # Status
        if str(
            license_data.get("status", "")
        ).lower() != "active":
            return False

        # Aktivasi pertama
        if license_data.get("activated_at") is None:

            activated = datetime.now(timezone.utc)

            expires = activated + timedelta(
                days=int(
                    license_data.get(
                        "duration_days",
                        30
                    )
                )
            )

            (
                supabase
                .table("licenses")
                .update({
                    "activated_at": activated.isoformat(),
                    "expires_at": expires.isoformat()
                })
                .eq("id", license_data["id"])
                .execute()
            )

            license_data["expires_at"] = expires.isoformat()

        # Expired
        expires_raw = license_data.get("expires_at")

        if not expires_raw:
            return False

        expires_at = datetime.fromisoformat(
            str(expires_raw).replace(
                "Z",
                "+00:00"
            )
        )

        if datetime.now(timezone.utc) > expires_at:

            (
                supabase
                .table("licenses")
                .update({
                    "status": "expired"
                })
                .eq("id", license_data["id"])
                .execute()
            )

            return False

        # Device
        session_device_id = session.get(
            "device_id"
        )

        if session_device_id:

            device_result = (
                supabase
                .table("license_devices")
                .select("id, device_id")
                .eq(
                    "license_id",
                    license_data["id"]
                )
                .eq(
                    "device_id",
                    session_device_id
                )
                .maybe_single()
                .execute()
            )

            if not device_result or not device_result.data:

                logger.warning(
                    "Device tidak terdaftar: %s",
                    session_device_id
                )

                return False

            # Update last_seen
            try:

                (
                    supabase
                    .table("license_devices")
                    .update({
                        "last_seen": datetime.now(
                            timezone.utc
                        ).isoformat()
                    })
                    .eq(
                        "id",
                        device_result.data["id"]
                    )
                    .execute()
                )

            except Exception as e:

                logger.warning(
                    "Gagal update last_seen: %s",
                    e
                )

        return True

    except Exception as e:

        logger.error(
            "License Error: %s",
            e
        )

        return False


def register_device(
    license_key,
    device_id
):

    try:

        logger.info(
            "REGISTER DEVICE: %s",
            device_id
        )

        result = (
            supabase
            .table("licenses")
            .select("*")
            .eq(
                "license_key",
                license_key
            )
            .single()
            .execute()
        )

        if not result.data:
            return False

        license_data = result.data

        license_id = license_data["id"]

        # Apakah device sudah ada?
        device = (
            supabase
            .table("license_devices")
            .select("*")
            .eq(
                "license_id",
                license_id
            )
            .eq(
                "device_id",
                device_id
            )
            .execute()
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        if device.data:

            (
                supabase
                .table("license_devices")
                .update({
                    "last_seen": now
                })
                .eq(
                    "id",
                    device.data[0]["id"]
                )
                .execute()
            )

            return True

        # Hitung device
        devices = (
            supabase
            .table("license_devices")
            .select("id")
            .eq(
                "license_id",
                license_id
            )
            .execute()
        )

        used_devices = len(
            devices.data or []
        )

        max_devices = int(
            license_data.get(
                "max_devices",
                1
            )
        )

        if used_devices >= max_devices:
            return False

        # Platform
        ua = (
            request.user_agent.string
            or ""
        ).lower()

        if "android" in ua:
            platform = "Android"

        elif (
            "iphone" in ua
            or "ipad" in ua
            or "ios" in ua
        ):
            platform = "iOS"

        elif "windows" in ua:
            platform = "Windows"

        elif (
            "macintosh" in ua
            or "mac os" in ua
        ):
            platform = "macOS"

        elif "linux" in ua:
            platform = "Linux"

        else:
            platform = "Unknown"

        (
            supabase
            .table("license_devices")
            .insert({
                "license_id": license_id,
                "device_id": device_id,
                "device_name": (
                    request.user_agent.string
                    or "Unknown Device"
                )[:120],
                "platform": platform,
                "first_seen": now,
                "last_seen": now
            })
            .execute()
        )

        return True

    except Exception as e:

        logger.exception(
            "Register device error"
        )

        return False


def generate_license_key():

    chars = (
        string.ascii_uppercase
        + string.digits
    )

    parts = [
        ''.join(
            random.choices(
                chars,
                k=4
            )
        )
        for _ in range(3)
    ]

    return (
        "FAPHOUSE-"
        + "-".join(parts)
    )


# ============================================================
# FAPHOUSE CONFIG
# ============================================================

BASE_URL = "https://faphouse2.com"

EMAIL = os.environ.get(
    "EMAIL",
    ""
)

PASSWORD = os.environ.get(
    "PASSWORD",
    ""
)

CACHE_DURATION = 300


# ============================================================
# FAPHOUSE CLIENT
# ============================================================

class FaphouseClient:

    def __init__(self):

        self.session = None

        self.logged_in = False

        self.session_created = False


    # --------------------------------------------------------
    # CREATE AUTH SESSION
    # --------------------------------------------------------

    def ensure_session(self):

        if (
            not self.session
            or not self.logged_in
        ):

            logger.info(
                "Creating authenticated Faphouse session..."
            )

            self.session = requests.Session()

            self.session.headers.update({
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0.0.0 "
                    "Safari/537.36",

                "Accept":
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "image/avif,image/webp,"
                    "image/apng,*/*;q=0.8",

                "Accept-Language":
                    "en-US,en;q=0.9",

                "Accept-Encoding":
                    "gzip, deflate, br",

                "DNT": "1",

                "Connection": "keep-alive",

                "Upgrade-Insecure-Requests":
                    "1"
            })

            self.login()

        return self.session


    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    def login(self):

        if not EMAIL or not PASSWORD:

            logger.error(
                "EMAIL/PASSWORD belum tersedia."
            )

            self.logged_in = False

            return False

        logger.info(
            "Attempting Faphouse login: %s...",
            EMAIL[:5]
        )

        self.session.headers.update({

            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 "
                "Safari/537.36",

            "Accept":
                "application/json,"
                "text/plain,*/*",

            "Accept-Language":
                "en-US,en;q=0.9",

            "Accept-Encoding":
                "gzip, deflate, br",

            "Content-Type":
                "application/json",

            "Origin":
                BASE_URL,

            "Referer":
                BASE_URL + "/",

            "DNT":
                "1"
        })

        try:

            # Initial page
            init_res = self.session.get(
                BASE_URL,
                timeout=15
            )

            logger.info(
                "Initial page status: %s",
                init_res.status_code
            )

            payload = {
                "login": EMAIL,
                "password": PASSWORD,
                "rememberMe": "1",
                "recaptcha": "",
                "trackingParamsBag":
                    "eyJwcm9tb19pZCI6IiIsInZpZGVvX2lkIjpudWxsLCJzdHVkaW9faWQiOm51bGwsInByb2R1Y2VyX2lkIjpudWxsLCJvcmllbnRhdGlvbiI6InN0cmFpZ2h0IiwibWxfcGFnZSI6Im1haW5fcGFnZSIsIm1sX3BhZ2VfdmFsdWVfaWQiOm51bGwsIm1sX3BhZ2VfdmFsdWUiOm51bGwsIm1sX3BhZ2VfbnVtYmVyIjpudWxsLCJtbF9yZWZfcGFnZV92YWx1ZV9pZCI6bnVsbCwibWxfcmVmX3BhZ2VfdmFsdWUiOiIiLCJtbF9yZWZfcGFnZV9udW1iZXIiOm51bGwsIm1sX3JlZl9wYWdlIjoiZGlyZWN0In0="
            }

            login_res = self.session.post(
                f"{BASE_URL}/api/auth/signin",
                json=payload,
                timeout=20
            )

            logger.info(
                "Login status: %s",
                login_res.status_code
            )

            if login_res.status_code == 200:

                try:

                    data = login_res.json()

                    if (
                        data.get("success")
                        or data.get("data")
                    ):

                        self.logged_in = True

                        self.session_created = True

                        logger.info(
                            "Faphouse login successful."
                        )

                        return True

                except Exception:
                    pass

                # Cookie fallback
                if len(
                    self.session.cookies
                ) > 0:

                    self.logged_in = True

                    self.session_created = True

                    logger.info(
                        "Faphouse login successful via session cookie."
                    )

                    return True

            self.logged_in = False

            self.session_created = False

            return False

        except Exception as e:

            logger.error(
                "Faphouse login error: %s",
                e
            )

            self.logged_in = False

            self.session_created = False

            return False


    # --------------------------------------------------------
    # RESPONSE DECODER
    # --------------------------------------------------------

    def _decode_response(
        self,
        response
    ):

        try:

            encoding = (
                response.headers
                .get(
                    "Content-Encoding",
                    ""
                )
                .lower()
            )

            raw = response.content

            if "br" in encoding:

                try:

                    import brotli

                    return brotli.decompress(
                        raw
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:
                    pass

            if "gzip" in encoding:

                try:

                    return gzip.decompress(
                        raw
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:
                    pass

            if "deflate" in encoding:

                try:

                    return zlib.decompress(
                        raw
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:

                    try:

                        return zlib.decompress(
                            raw,
                            -zlib.MAX_WBITS
                        ).decode(
                            "utf-8",
                            errors="ignore"
                        )

                    except Exception:
                        pass

            return response.text or ""

        except Exception as e:

            logger.warning(
                "Response decode error: %s",
                e
            )

            return response.text or ""


    # --------------------------------------------------------
    # NORMALIZE URL
    # --------------------------------------------------------

    def _normalize_url(
        self,
        value,
        page_url
    ):

        if not value:
            return None

        value = str(value)

        value = (
            unescape(value)
        )

        value = (
            value
            .replace("\\/", "/")
            .replace("\\u002F", "/")
            .replace("\\u002f", "/")
            .replace("\\u003A", ":")
            .replace("\\u003a", ":")
            .replace("\\u0026", "&")
            .replace("\\u003F", "?")
            .replace("\\u003f", "?")
            .replace("&amp;", "&")
        )

        try:
            value = unquote(value)
        except Exception:
            pass

        value = value.strip()

        value = value.strip(
            "\"'`<> "
        )

        if value.startswith("//"):
            value = "https:" + value

        if value.startswith("/"):
            value = urljoin(
                page_url,
                value
            )

        if (
            value.startswith("http://")
            or value.startswith("https://")
        ):

            return value

        return None


    # --------------------------------------------------------
    # EXTRACT VIDEO URLs
    # --------------------------------------------------------

    def _extract_video_urls(
        self,
        html,
        page_url
    ):

        if not html:
            return []

        # Bersihkan control characters
        html = re.sub(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
            "",
            html
        )

        # HTML entity
        html = unescape(html)

        found = []

        def add(value):

            normalized = self._normalize_url(
                value,
                page_url
            )

            if not normalized:
                return

            lower = normalized.lower()

            # Hanya kandidat stream video
            if (
                ".m3u8" in lower
                or "video-pr.xhcdn.com" in lower
                or ".mp4" in lower
                or "/hls/" in lower
            ):

                if normalized not in found:

                    found.append(
                        normalized
                    )


        # ====================================================
        # 1. URL M3U8 langsung
        # ====================================================

        patterns = [

            r'https?://[^"\'<>\s\\]+\.m3u8(?:\?[^"\'<>\s\\]*)?',

            r'//[^"\'<>\s\\]+\.m3u8(?:\?[^"\'<>\s\\]*)?',

            r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']',

            r'["\']([^"\']*video-pr\.xhcdn\.com[^"\']*)["\']',

            r'["\']([^"\']+\.mp4(?:\?[^"\']*)?)["\']',

            r'["\']([^"\']+/hls/[^"\']+)["\']'
        ]

        for pattern in patterns:

            try:

                matches = re.findall(
                    pattern,
                    html,
                    re.IGNORECASE
                )

                for match in matches:

                    if isinstance(
                        match,
                        tuple
                    ):
                        match = match[0]

                    add(match)

            except Exception:
                pass


        # ====================================================
        # 2. JSON-like fields
        # ====================================================

        field_patterns = [

            r'["\']?(?:src|url|file|source|videoUrl|video_url|stream|streamUrl|stream_url)["\']?\s*[:=]\s*["\']([^"\']+)["\']',

            r'["\']?(?:hls|hlsUrl|hls_url|m3u8)["\']?\s*[:=]\s*["\']([^"\']+)["\']',

            r'["\']?(?:playlist|playlistUrl|playlist_url)["\']?\s*[:=]\s*["\']([^"\']+)["\']'
        ]

        for pattern in field_patterns:

            matches = re.findall(
                pattern,
                html,
                re.IGNORECASE
            )

            for match in matches:
                add(match)


        # ====================================================
        # 3. data-* attributes
        # ====================================================

        data_patterns = [

            r'data-(?:src|url|video|source|file|stream)\s*=\s*["\']([^"\']+)["\']',

            r'data-(?:video-url|video_url|stream-url|stream_url)\s*=\s*["\']([^"\']+)["\']',

            r'data-sources\s*=\s*["\']([^"\']+)["\']'
        ]

        for pattern in data_patterns:

            matches = re.findall(
                pattern,
                html,
                re.IGNORECASE
            )

            for match in matches:

                add(match)

                # Kadang data-sources berisi JSON
                try:

                    decoded = unescape(
                        match
                    )

                    parsed = json.loads(
                        decoded
                    )

                    self._extract_from_json(
                        parsed,
                        page_url,
                        found
                    )

                except Exception:
                    pass


        # ====================================================
        # 4. Cari video-pr di seluruh HTML
        # ====================================================

        video_pr_matches = re.findall(
            r'https?://video-pr\.xhcdn\.com[^"\'<>\s\\]+',
            html,
            re.IGNORECASE
        )

        for value in video_pr_matches:
            add(value)


        # ====================================================
        # 5. Cari URL yang di-escape
        # ====================================================

        escaped_matches = re.findall(
            r'https?:\\\\?/\\\\?/[^"\'<>\s]+',
            html,
            re.IGNORECASE
        )

        for value in escaped_matches:
            add(value)


        return found


    # --------------------------------------------------------
    # RECURSIVE JSON EXTRACTION
    # --------------------------------------------------------

    def _extract_from_json(
        self,
        data,
        page_url,
        found
    ):

        if isinstance(data, dict):

            for key, value in data.items():

                key_lower = str(
                    key
                ).lower()

                if isinstance(
                    value,
                    str
                ):

                    if (
                        "url" in key_lower
                        or "src" in key_lower
                        or "file" in key_lower
                        or "video" in key_lower
                        or "stream" in key_lower
                        or "hls" in key_lower
                        or "source" in key_lower
                        or "playlist" in key_lower
                    ):

                        normalized = (
                            self._normalize_url(
                                value,
                                page_url
                            )
                        )

                        if normalized:

                            lower = normalized.lower()

                            if (
                                ".m3u8" in lower
                                or ".mp4" in lower
                                or "video-pr.xhcdn.com" in lower
                                or "/hls/" in lower
                            ):

                                if normalized not in found:

                                    found.append(
                                        normalized
                                    )

                    # JSON tersimpan sebagai string
                    if value.strip().startswith(
                        "{"
                    ) or value.strip().startswith(
                        "["
                    ):

                        try:

                            nested = json.loads(
                                value
                            )

                            self._extract_from_json(
                                nested,
                                page_url,
                                found
                            )

                        except Exception:
                            pass

                elif isinstance(
                    value,
                    (dict, list)
                ):

                    self._extract_from_json(
                        value,
                        page_url,
                        found
                    )

        elif isinstance(
            data,
            list
        ):

            for item in data:

                self._extract_from_json(
                    item,
                    page_url,
                    found
                )


    # --------------------------------------------------------
    # GET M3U8
    # --------------------------------------------------------

    @lru_cache(maxsize=100)
    def get_m3u8_url(
        self,
        video_url
    ):

        logger.info(
            "Processing video URL: %s",
            video_url[:120]
        )

        if "#" in video_url:
            video_url = video_url.split(
                "#",
                1
            )[0]

        # ====================================================
        # AUTHENTICATED SESSION
        # ====================================================

        session = self.ensure_session()

        if session:

            try:

                headers = {

                    "User-Agent":
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/120.0.0.0 "
                        "Safari/537.36",

                    "Accept":
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,"
                        "image/avif,image/webp,"
                        "image/apng,*/*;q=0.8",

                    "Accept-Language":
                        "en-US,en;q=0.9",

                    "Referer":
                        BASE_URL + "/",

                    "DNT":
                        "1",

                    "Upgrade-Insecure-Requests":
                        "1"
                }

                response = session.get(
                    video_url,
                    timeout=20,
                    headers=headers,
                    allow_redirects=True
                )

                logger.info(
                    "Authenticated page status: %s",
                    response.status_code
                )

                logger.info(
                    "Authenticated final URL: %s",
                    response.url
                )

                if response.status_code == 200:

                    html = (
                        self._decode_response(
                            response
                        )
                    )

                    candidates = (
                        self._extract_video_urls(
                            html,
                            response.url
                        )
                    )

                    logger.info(
                        "Authenticated candidates: %s",
                        len(candidates)
                    )

                    if candidates:

                        # Utamakan m3u8
                        for candidate in candidates:

                            if ".m3u8" in candidate.lower():

                                logger.info(
                                    "M3U8 found: %s",
                                    candidate[:180]
                                )

                                return candidate

                        # Jika hanya video-pr/mp4
                        logger.info(
                            "Video candidate found: %s",
                            candidates[0][:180]
                        )

                        return candidates[0]

            except Exception as e:

                logger.warning(
                    "Authenticated fetch failed: %s",
                    e
                )


        # ====================================================
        # PUBLIC/GUEST FALLBACK
        # ====================================================

        logger.info(
            "Trying public page fallback..."
        )

        try:

            guest_session = requests.Session()

            guest_session.headers.update({

                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0.0.0 "
                    "Safari/537.36",

                "Accept":
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "image/avif,image/webp,"
                    "*/*;q=0.8",

                "Accept-Language":
                    "en-US,en;q=0.9",

                "Referer":
                    BASE_URL + "/"
            })

            response = guest_session.get(
                video_url,
                timeout=20,
                allow_redirects=True
            )

            logger.info(
                "Guest status: %s",
                response.status_code
            )

            if response.status_code == 200:

                html = (
                    self._decode_response(
                        response
                    )
                )

                candidates = (
                    self._extract_video_urls(
                        html,
                        response.url
                    )
                )

                logger.info(
                    "Guest candidates: %s",
                    len(candidates)
                )

                for candidate in candidates:

                    if ".m3u8" in candidate.lower():

                        return candidate

                if candidates:
                    return candidates[0]

        except Exception as e:

            logger.warning(
                "Guest fetch failed: %s",
                e
            )


        logger.error(
            "No playable video source found."
        )

        return None


# ============================================================
# GLOBAL CLIENT
# ============================================================

client = FaphouseClient()


# ============================================================
# TEST ROUTE
# ============================================================

@app.route(
    "/api/test-route"
)
def test_route():

    return jsonify({

        "success": True,

        "message":
            "TEST ROUTE AKTIF",

        "version":
            "FAPHOUSE-PLAYER-OPTIMIZED-001"
    })


# ============================================================
# ADMIN - GENERATE LICENSE
# ============================================================

@app.route(
    "/admin/generate-license",
    methods=["POST"]
)
def admin_generate_license():

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        name = str(
            data.get(
                "name",
                ""
            )
        ).strip()

        duration_days = int(
            data.get(
                "duration_days",
                30
            )
        )

        max_devices = int(
            data.get(
                "max_devices",
                1
            )
        )

        notes = str(
            data.get(
                "notes",
                ""
            )
        ).strip()

        if duration_days <= 0:
            return jsonify({
                "success": False,
                "message":
                    "duration_days harus lebih dari 0"
            }), 400

        if max_devices <= 0:
            return jsonify({
                "success": False,
                "message":
                    "max_devices harus lebih dari 0"
            }), 400

        license_key = (
            generate_license_key()
        )

        (
            supabase
            .table("licenses")
            .insert({

                "license_key":
                    license_key,

                "name":
                    name,

                "status":
                    "active",

                "duration_days":
                    duration_days,

                "max_devices":
                    max_devices,

                "notes":
                    notes
            })
            .execute()
        )

        return jsonify({

            "success":
                True,

            "license_key":
                license_key
        })

    except Exception as e:

        logger.error(
            "Generate License Error: %s",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# ADMIN - LIST LICENSE
# ============================================================

@app.route(
    "/admin/licenses",
    methods=["GET"]
)
def admin_list_license():

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False
        }), 401

    try:

        result = (
            supabase
            .table("licenses")
            .select("*")
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        licenses = (
            result.data
            or []
        )

        total_license = len(
            licenses
        )

        active_license = sum(
            1
            for item in licenses
            if item.get(
                "status"
            ) == "active"
        )

        return jsonify({

            "success":
                True,

            "licenses":
                licenses,

            "total":
                total_license,

            "active":
                active_license
        })

    except Exception as e:

        logger.error(
            "List License Error: %s",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# ADMIN - LICENSE DEVICES
# ============================================================

@app.route(
    "/admin/license-devices/<license_id>"
)
def admin_license_devices(
    license_id
):

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    try:

        result = (
            supabase
            .table("license_devices")
            .select("*")
            .eq(
                "license_id",
                license_id
            )
            .order(
                "first_seen",
                desc=False
            )
            .execute()
        )

        return jsonify({

            "success":
                True,

            "devices":
                result.data
                or []
        })

    except Exception as e:

        logger.error(
            "Device List Error: %s",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# ADMIN - UPDATE LICENSE
# ============================================================

@app.route(
    "/admin/update-license",
    methods=["POST"]
)
def admin_update_license():

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        license_id = data.get(
            "id"
        )

        status = data.get(
            "status"
        )

        if not license_id:

            return jsonify({
                "success": False,
                "message":
                    "License ID tidak ditemukan"
            }), 400

        if status not in [
            "active",
            "inactive"
        ]:

            return jsonify({
                "success": False,
                "message":
                    "Status license tidak valid"
            }), 400

        result = (
            supabase
            .table("licenses")
            .update({
                "status":
                    status
            })
            .eq(
                "id",
                license_id
            )
            .execute()
        )

        if not result.data:

            return jsonify({
                "success": False,
                "message":
                    "License tidak ditemukan"
            }), 404

        return jsonify({

            "success":
                True,

            "message":
                (
                    "License berhasil diaktifkan"
                    if status == "active"
                    else
                    "License berhasil dinonaktifkan"
                )
        })

    except Exception as e:

        logger.error(
            "Update License Error: %s",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# ADMIN - DELETE LICENSE
# ============================================================

@app.route(
    "/admin/delete-license",
    methods=["POST"]
)
def admin_delete_license():

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        license_id = data.get(
            "id"
        )

        if not license_id:

            return jsonify({
                "success": False,
                "message":
                    "License ID tidak ditemukan"
            }), 400

        result = (
            supabase
            .table("licenses")
            .delete()
            .eq(
                "id",
                license_id
            )
            .execute()
        )

        if not result.data:

            return jsonify({
                "success": False,
                "message":
                    "License tidak ditemukan"
            }), 404

        return jsonify({

            "success":
                True,

            "message":
                "License berhasil dihapus"
        })

    except Exception as e:

        logger.error(
            "Delete License Error: %s",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# ADMIN - RESET DEVICE
# ============================================================

@app.route(
    "/admin/reset-device",
    methods=["POST"]
)
def admin_reset_device():

    if not session.get(
        "admin_logged_in"
    ):

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        device_id = data.get(
            "device_id"
        )

        if not device_id:

            return jsonify({
                "success": False,
                "message":
                    "Device ID tidak ditemukan"
            }), 400

        existing = (
            supabase
            .table("license_devices")
            .select("*")
            .eq(
                "id",
                device_id
            )
            .maybe_single()
            .execute()
        )

        if not existing or not existing.data:

            return jsonify({
                "success": False,
                "message":
                    "Device tidak ditemukan"
            }), 404

        (
            supabase
            .table("license_devices")
            .delete()
            .eq(
                "id",
                device_id
            )
            .execute()
        )

        verify = (
            supabase
            .table("license_devices")
            .select("id")
            .eq(
                "id",
                device_id
            )
            .maybe_single()
            .execute()
        )

        if verify and verify.data:

            return jsonify({
                "success": False,
                "message":
                    "Device gagal dihapus dari database"
            }), 500

        return jsonify({

            "success":
                True,

            "message":
                "Device berhasil direset",

            "device_id":
                device_id
        })

    except Exception as e:

        logger.exception(
            "Reset Device Error"
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)
        }), 500


# ============================================================
# LICENSE PAGE
# ============================================================

@app.route(
    "/license",
    methods=["GET", "POST"]
)
def license_page():

    key = session.get(
        "license_key"
    )

    device_id = session.get(
        "device_id"
    )

    # Session masih valid
    if (
        key
        and device_id
        and check_license(key)
    ):

        try:

            license_result = (
                supabase
                .table("licenses")
                .select("id")
                .eq(
                    "license_key",
                    key
                )
                .single()
                .execute()
            )

            if license_result.data:

                license_id = (
                    license_result
                    .data["id"]
                )

                device_result = (
                    supabase
                    .table(
                        "license_devices"
                    )
                    .select("id")
                    .eq(
                        "license_id",
                        license_id
                    )
                    .eq(
                        "device_id",
                        device_id
                    )
                    .execute()
                )

                if device_result.data:

                    return redirect("/")

        except Exception as e:

            logger.error(
                "License Session Check Error: %s",
                e
            )

        session.clear()

    if request.method == "POST":

        key = (
            request.form
            .get(
                "license",
                ""
            )
            .strip()
        )

        device_id = (
            request.form
            .get(
                "device_id",
                ""
            )
            .strip()
        )

        if not device_id:

            return render_template(
                "license.html",
                error=True,
                message=
                    "Device ID tidak ditemukan."
            )

        if check_license(key):

            if not register_device(
                key,
                device_id
            ):

                return render_template(
                    "license.html",
                    error=True,
                    message=
                        "Batas maksimum perangkat telah tercapai."
                )

            session["licensed"] = True

            session["license_key"] = key

            session["device_id"] = device_id

            return redirect("/")

        return render_template(
            "license.html",
            error=True
        )

    return render_template(
        "license.html",
        error=False
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin_login():

    if session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin/dashboard"
        )

    if request.method == "POST":

        pin = (
            request.form
            .get(
                "pin",
                ""
            )
            .strip()
        )

        admin_pin = os.environ.get(
            "ADMIN_PIN",
            ""
        )

        if (
            admin_pin
            and hmac.compare_digest(
                pin,
                admin_pin
            )
        ):

            session[
                "admin_logged_in"
            ] = True

            return redirect(
                "/admin/dashboard"
            )

        return render_template(
            "admin_login.html",
            error=True
        )

    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route(
    "/admin/dashboard"
)
def admin_dashboard():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin"
        )

    return render_template(
        "admin_dashboard.html"
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        "/admin"
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    key = session.get(
        "license_key"
    )

    if not key:

        return redirect(
            "/license"
        )

    if not check_license(key):

        session.clear()

        return redirect(
            "/license"
        )

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

html,
body {
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

body::before {

    content: "";

    position: fixed;

    width: 430px;
    height: 430px;

    top: -220px;
    left: -180px;

    background:
        rgba(0,255,140,0.07);

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

    background:
        rgba(70,90,255,0.06);

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

.player-box {

    width: 100%;

    background:
        rgba(22,24,31,0.94);

    border:
        1px solid
        rgba(255,255,255,0.08);

    border-radius: 24px;

    padding: 32px 26px;

    box-shadow:
        0 25px 70px rgba(0,0,0,0.55),
        inset 0 1px 0
        rgba(255,255,255,0.04);

    backdrop-filter:
        blur(18px);

    -webkit-backdrop-filter:
        blur(18px);

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
        0 12px 30px
        rgba(30,215,96,0.22),

        inset 0 1px 0
        rgba(255,255,255,0.25);
}

h1 {

    font-size: 28px;

    line-height: 1.2;

    font-weight: 800;

    letter-spacing: 1.3px;
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

.form-title {

    text-align: left;

    color: #dfe2e8;

    font-size: 13px;

    font-weight: 700;

    margin-bottom: 9px;
}

.url-wrapper {

    position: relative;

    width: 100%;
}

.url-icon {

    position: absolute;

    left: 15px;
    top: 50%;

    transform:
        translateY(-50%);

    font-size: 17px;

    opacity: 0.7;

    pointer-events: none;
}

.url-input input {

    display: block;

    width: 100%;

    height: 52px;

    padding:
        0 15px 0 45px;

    background: #101217;

    border:
        1px solid #343842;

    border-radius: 13px;

    color: #fff;

    font-family: inherit;

    font-size: 16px;

    outline: none;
}

.url-input input::placeholder {

    color: #666b76;

    font-size: 14px;
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

    cursor: pointer;
}

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

    border:
        1px solid
        rgba(255,255,255,0.05);

    border-radius: 9px;

    color: #777e8b;

    font-size: 10px;

    line-height: 1.5;

    word-break: break-all;
}

.endpoints {

    margin-top: 25px;

    padding: 18px;

    background:
        rgba(255,255,255,0.025);

    border:
        1px solid
        rgba(255,255,255,0.06);

    border-radius: 15px;

    text-align: left;
}

.endpoints-header {

    display: flex;

    align-items: center;

    gap: 8px;

    margin-bottom: 13px;
}

.endpoints h3 {

    color: #d8dbe1;

    font-size: 13px;
}

.endpoint {

    padding: 11px 0;

    border-bottom:
        1px solid
        rgba(255,255,255,0.06);

    color: #858b97;

    font-size: 11px;

    line-height: 1.5;
}

.endpoint:last-child {

    border-bottom: none;
}

.endpoint strong {

    color: #45e58a;

    font-size: 10px;

    margin-right: 5px;
}

.account-box {

    width: 100%;

    margin-top: 16px;

    padding: 22px 20px 20px;

    background:
        rgba(22,24,31,0.94);

    border:
        1px solid
        rgba(255,255,255,0.08);

    border-radius: 20px;

    box-shadow:
        0 18px 45px
        rgba(0,0,0,0.35);
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

    background:
        rgba(32,215,107,0.10);

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

    background:
        rgba(32,215,107,0.08);

    color: #45e58a;

    font-size: 9px;

    font-weight: 800;
}

.status-dot {

    width: 6px;
    height: 6px;

    border-radius: 50%;

    background: #20d76b;
}

.account-info {

    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 8px;

    margin-bottom: 18px;
}

.info-item {

    padding: 12px;

    background:
        rgba(255,255,255,0.025);

    border:
        1px solid
        rgba(255,255,255,0.05);

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
        rgba(255,70,70,0.12);

    border:
        1px solid
        rgba(255,80,80,0.18);

    color: #ff7777;

    text-decoration: none;

    font-size: 12px;

    font-weight: 800;
}

.account-footer {

    margin-top: 17px;

    text-align: center;

    color: #4f545e;

    font-size: 9px;

    line-height: 1.6;
}

@media (max-width:380px) {

    body {
        padding: 16px 12px;
    }

    .player-box {
        padding:
            26px 18px 22px;
    }

    h1 {
        font-size: 23px;
    }

    .account-box {
        padding:
            19px 15px 17px;
    }
}

@media (min-width:600px) {

    body {
        padding: 40px 20px;
    }

    .player-box {
        padding:
            38px 34px 32px;
    }
}

</style>

</head>

<body>

<main class="page">

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

<form
method="GET"
action="/play"
>

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

<span>
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
1.1.0
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


# ============================================================
# PLAY
# ============================================================

@app.route(
    "/play"
)
def play_video():

    video_url = (
        request.args
        .get(
            "url",
            ""
        )
        .strip()
    )

    if not video_url:

        return (
            "❌ No URL provided",
            400
        )

    if "#" in video_url:

        video_url = video_url.split(
            "#",
            1
        )[0]

    try:

        logger.info(
            "Play request: %s",
            video_url
        )

        m3u8_url = (
            client.get_m3u8_url(
                video_url
            )
        )

        if m3u8_url:

            return render_template_string(
                """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>🎬 Video Player</title>

<link
href="https://vjs.zencdn.net/8.0.0/video-js.css"
rel="stylesheet"
/>

<style>

* {
    margin:0;
    padding:0;
    box-sizing:border-box;
}

body {

    background:#0a0a0a;

    color:#fff;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        sans-serif;

    min-height:100vh;

    padding:20px;
}

.container {

    max-width:1200px;

    width:100%;

    margin:auto;

    background:#1a1a1a;

    border-radius:12px;

    padding:20px;

    box-shadow:
        0 8px 32px
        rgba(0,0,0,0.8);
}

.video-wrapper {

    width:100%;

    background:#000;

    border-radius:8px;

    overflow:hidden;

    aspect-ratio:16/9;
}

#player {

    width:100%;
    height:100%;
}

.status-bar {

    display:flex;

    align-items:center;

    gap:12px;

    margin-bottom:15px;

    flex-wrap:wrap;
}

.status-dot {

    width:10px;
    height:10px;

    border-radius:50%;

    background:#4CAF50;

    animation:
        pulse 1.5s infinite;
}

@keyframes pulse {

    0% {
        opacity:1;
    }

    50% {
        opacity:.3;
    }

    100% {
        opacity:1;
    }
}

.badge {

    display:inline-block;

    background:#4CAF50;

    color:#fff;

    padding:
        2px 10px;

    border-radius:20px;

    font-size:10px;

    font-weight:bold;
}

.info {

    margin-top:15px;

    padding:15px;

    background:#222;

    border-radius:8px;

    font-size:13px;

    word-break:break-all;
}

.info a {

    color:#4CAF50;

    text-decoration:none;
}

.back-link {

    display:inline-block;

    margin-top:15px;

    color:#888;

    text-decoration:none;
}

</style>

</head>

<body>

<div class="container">

<div class="status-bar">

<h2>
🎬 Faphouse
<span class="badge">
ULTRA
</span>
</h2>

<span class="status-dot"></span>

<span>
Playing
</span>

</div>

<div class="video-wrapper">

<video
id="player"
class="video-js vjs-default-skin"
controls
autoplay
preload="auto"
playsinline
>

<source
src="{{ m3u8_url }}"
type="application/x-mpegURL"
>

</video>

</div>

<div class="info">

<strong>
📹 Video:
</strong>

<a
href="{{ video_url }}"
target="_blank"
rel="noopener noreferrer"
>
{{ video_url[:100] }}
</a>

<br><br>

<strong>
📊 Status:
</strong>

<span style="color:#4CAF50">
● Playing
</span>

</div>

<a
href="/"
class="back-link"
>
← Back to Home
</a>

</div>

<script
src="https://vjs.zencdn.net/8.0.0/video.min.js"
></script>

<script>

document.addEventListener(
"DOMContentLoaded",
function() {

    var player =
        videojs(
            "player",
            {
                html5: {
                    hls: {
                        enableLowInitialPlaylist:
                            true,

                        smoothQualityChange:
                            true,

                        overrideNative:
                            true
                    }
                }
            }
        );

    player.ready(
        function() {

            this.play()
                .catch(
                    function() {}
                );

        }
    );

});

</script>

</body>

</html>
                """,
                m3u8_url=m3u8_url,
                video_url=video_url
            )

        return render_template_string(
            """
<div style="
padding:40px;
text-align:center;
background:#0a0a0a;
color:#fff;
min-height:100vh;
font-family:Arial;
">

<div style="
max-width:600px;
margin:auto;
">

<h2 style="color:#ff4444;">
❌ Could not find playable video source
</h2>

<p style="
color:#888;
margin:20px 0;
">
Video source tidak ditemukan dari halaman yang dapat diakses.
</p>

<a
href="/"
style="
color:#4CAF50;
text-decoration:none;
display:inline-block;
padding:10px 30px;
background:#222;
border-radius:6px;
"
>
← Go Home
</a>

</div>

</div>
            """
        )

    except Exception as e:

        logger.exception(
            "Play error"
        )

        return render_template_string(
            """
<div style="
padding:40px;
text-align:center;
background:#0a0a0a;
color:#fff;
min-height:100vh;
font-family:Arial;
">

<div style="
max-width:600px;
margin:auto;
">

<h2 style="color:#ff4444;">
❌ Error
</h2>

<p style="
color:#888;
margin:20px 0;
word-break:break-word;
">
{{ error }}
</p>

<a
href="/"
style="
color:#4CAF50;
text-decoration:none;
display:inline-block;
padding:10px 30px;
background:#222;
border-radius:6px;
"
>
← Go Home
</a>

</div>

</div>
            """,
            error=str(e)
        )


# ============================================================
# API M3U8
# ============================================================

@app.route(
    "/api/m3u8"
)
def get_m3u8():

    video_url = (
        request.args
        .get(
            "url",
            ""
        )
        .strip()
    )

    if not video_url:

        return jsonify({
            "success":
                False,

            "error":
                "Missing 'url' parameter"
        }), 400

    try:

        if "#" in video_url:

            video_url = video_url.split(
                "#",
                1
            )[0]

        stream_url = (
            client.get_m3u8_url(
                video_url
            )
        )

        if stream_url and (
            ".m3u8" in stream_url.lower()
            or stream_url.lower().endswith(".m3u8")
        ):
            return jsonify({
                "success": True,
                "m3u8_url": stream_url,
                "video_url": video_url
            })

        if stream_url and (
            ".m3u8" in stream_url.lower()
            or stream_url.lower().endswith(".m3u8")
        ):
            return jsonify({
                "success": True,
                "m3u8_url": stream_url,
                "video_url": video_url
            })

        return jsonify({
            "success": False,
            "error": "Resolved URL is not a valid HLS playlist"
        }), 422
        
        return jsonify({

            "success":
                False,

            "error":
                "No playable video source found"
        }), 404

    except Exception as e:

        logger.exception(
            "M3U8 API error"
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)
        }), 500


# ============================================================
# DEBUG
# ============================================================

@app.route(
    "/api/debug"
)
def api_debug():

    video_url = (
        request.args
        .get(
            "url",
            ""
        )
        .strip()
    )

    if not video_url:

        return jsonify({

            "success":
                False,

            "error":
                "Missing 'url' parameter"
        }), 400

    clean_url = video_url.split(
        "#",
        1
    )[0]

    try:

        debug_session = requests.Session()

        debug_session.headers.update({

            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 "
                "Safari/537.36",

            "Accept":
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/webp,*/*;q=0.8",

            "Accept-Language":
                "en-US,en;q=0.9"
        })

        response = debug_session.get(
            clean_url,
            timeout=20,
            allow_redirects=True
        )

        html = (
            response.text
            or ""
        )

        html_lower = (
            html.lower()
        )

        def find_context(
            keyword,
            radius=2000
        ):

            pos = (
                html_lower
                .find(
                    keyword.lower()
                )
            )

            if pos == -1:
                return None

            start = max(
                0,
                pos - radius
            )

            end = min(
                len(html),
                pos + radius
            )

            return {

                "position":
                    pos,

                "context":
                    html[start:end]
            }

        return jsonify({

            "success":
                True,

            "debug_version":
                "OPTIMIZED-DEBUG-001",

            "request": {

                "original_url":
                    video_url,

                "clean_url":
                    clean_url
            },

            "response": {

                "status_code":
                    response.status_code,

                "final_url":
                    response.url,

                "content_type":
                    response.headers.get(
                        "Content-Type"
                    ),

                "content_encoding":
                    response.headers.get(
                        "Content-Encoding"
                    ),

                "content_length":
                    len(
                        response.content
                    )
            },

            "cookies": [
                cookie.name
                for cookie
                in debug_session.cookies
            ],

            "indicators": {

                "contains_m3u8":
                    ".m3u8"
                    in html_lower,

                "contains_video_pr":
                    "video-pr"
                    in html_lower,

                "contains_sources":
                    "sources"
                    in html_lower,

                "contains_hls":
                    "hls"
                    in html_lower,

                "contains_video":
                    "<video"
                    in html_lower,

                "contains_script":
                    "<script"
                    in html_lower
            },

            "keyword_context": {

                "video_pr":
                    find_context(
                        "video-pr"
                    ),

                "hls":
                    find_context(
                        "hls"
                    ),

                "sources":
                    find_context(
                        "sources"
                    )
            },

            "html_preview":
                html[:3000]
        })

    except Exception as e:

        logger.exception(
            "Debug request failed"
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)
        }), 500


# ============================================================
# DEBUG2
# ============================================================

@app.route(
    "/api/debug2"
)
def api_debug2():

    video_url = (
        request.args
        .get(
            "url",
            ""
        )
        .strip()
    )

    if not video_url:

        return jsonify({

            "success":
                False,

            "error":
                "Missing 'url' parameter"
        }), 400

    clean_url = video_url.split(
        "#",
        1
    )[0]

    try:

        debug_session = requests.Session()

        debug_session.headers.update({

            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 "
                "Safari/537.36",

            "Accept":
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/webp,*/*;q=0.8",

            "Accept-Language":
                "en-US,en;q=0.9"
        })

        response = debug_session.get(
            clean_url,
            timeout=20,
            allow_redirects=True
        )

        html = (
            response.text
            or ""
        )

        html_lower = (
            html.lower()
        )

        def find_all_contexts(
            keyword,
            radius=1500,
            limit=10
        ):

            results = []

            start_from = 0

            keyword_lower = (
                keyword.lower()
            )

            while len(results) < limit:

                pos = html_lower.find(
                    keyword_lower,
                    start_from
                )

                if pos == -1:
                    break

                start = max(
                    0,
                    pos - radius
                )

                end = min(
                    len(html),
                    pos
                    + len(keyword)
                    + radius
                )

                results.append({

                    "position":
                        pos,

                    "context":
                        html[start:end]
                })

                start_from = (
                    pos + len(keyword)
                )

            return results

        keywords = [

            "video-pr.xhcdn.com",

            "data-sources",

            "data-video",

            "video_url",

            "videoUrl",

            "video_data",

            "videoData",

            "player",

            "media=",

            "format/",

            ".m3u8",

            "m3u8",

            "hls",

            "sources",

            "source"
        ]

        contexts = {}

        for keyword in keywords:

            contexts[keyword] = (
                find_all_contexts(
                    keyword,
                    radius=1200,
                    limit=5
                )
            )

        return jsonify({

            "success":
                True,

            "debug_version":
                "OPTIMIZED-DEBUG2-001",

            "request": {

                "original_url":
                    video_url,

                "clean_url":
                    clean_url
            },

            "response": {

                "status_code":
                    response.status_code,

                "final_url":
                    response.url,

                "content_type":
                    response.headers.get(
                        "Content-Type"
                    ),

                "content_encoding":
                    response.headers.get(
                        "Content-Encoding"
                    ),

                "content_length":
                    len(
                        response.content
                    )
            },

            "cookies": [
                cookie.name
                for cookie
                in debug_session.cookies
            ],

            "keyword_counts": {

                keyword:
                    html_lower.count(
                        keyword.lower()
                    )

                for keyword
                in keywords
            },

            "contexts":
                contexts

        })

    except Exception as e:

        logger.exception(
            "Debug2 request failed"
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)
        }), 500


# ============================================================
# DEBUG VIDEO
# ============================================================

@app.route(
    "/api/debug-video"
)
def api_debug_video():

    video_url = (
        request.args
        .get(
            "url",
            ""
        )
        .strip()
    )

    if not video_url:

        return jsonify({

            "success":
                False,

            "error":
                "Missing 'url' parameter"
        }), 400

    clean_url = video_url.split(
        "#",
        1
    )[0]

    try:

        debug_session = requests.Session()

        debug_session.headers.update({

            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 "
                "Safari/537.36",

            "Accept":
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/webp,*/*;q=0.8",

            "Accept-Language":
                "en-US,en;q=0.9"
        })

        response = debug_session.get(
            clean_url,
            timeout=20,
            allow_redirects=True
        )

        html = (
            response.text
            or ""
        )

        video_pr_urls = re.findall(
            r'https?://video-pr\.xhcdn\.com[^"\'<>\s]+',
            html,
            re.IGNORECASE
        )

        contexts = []

        keywords = [

            "video-pr.xhcdn.com",

            "data-sources",

            "sources:",

            '"sources"',

            "'sources'",

            "hls",

            "player",

            "media",

            "video_url",

            "videoUrl"
        ]

        html_lower = (
            html.lower()
        )

        for keyword in keywords:

            pos = html_lower.find(
                keyword.lower()
            )

            if pos != -1:

                start = max(
                    0,
                    pos - 1500
                )

                end = min(
                    len(html),
                    pos + 3000
                )

                contexts.append({

                    "keyword":
                        keyword,

                    "position":
                        pos,

                    "context":
                        html[start:end]
                })

        return jsonify({

            "success":
                True,

            "response": {

                "status_code":
                    response.status_code,

                "final_url":
                    response.url,

                "content_length":
                    len(
                        response.content
                    )
            },

            "video_pr_urls":
                list(
                    dict.fromkeys(
                        video_pr_urls
                    )
                ),

            "video_pr_count":
                len(
                    video_pr_urls
                ),

            "contexts":
                contexts[:20]
        })

    except Exception as e:

        logger.exception(
            "Debug video request failed"
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)
        }), 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/api/status"
)
def status():

    return jsonify({

        "status":
            "online",

        "logged_in":
            client.logged_in,

        "session_created":
            client.session_created,

        "cache_info":
            client
            .get_m3u8_url
            .cache_info()
            ._asdict()
    })


# ============================================================
# LOGOUT LICENSE
# ============================================================

@app.route(
    "/logout"
)
def logout():

    session.clear()

    return redirect(
        "/license"
    )


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 70
    )

    print(
        "🎬 FAPHOUSE PLAYER"
    )

    print(
        "Optimized Vercel Flask"
    )

    print(
        "=" * 70
    )

    print(
        "EMAIL:",
        (
            EMAIL[:5] + "..."
            if EMAIL
            else "NOT SET"
        )
    )

    print(
        "PASSWORD:",
        (
            "*" * 8
            if PASSWORD
            else "NOT SET"
        )
    )

    print(
        "=" * 70
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
