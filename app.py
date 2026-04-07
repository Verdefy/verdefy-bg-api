"""
Verdefy Background Removal — Cloud API
Deploy this to Railway or Render (free tier).
WordPress plugin sends clothing images here → gets back processed image.
"""

import os
import io
import json
import hmac
import hashlib
from PIL import Image
from rembg import remove, new_session
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BG_COLOR_HEX = os.environ.get("BG_COLOR", "#F0F0F0")
API_SECRET   = os.environ.get("API_SECRET", "")   # Set this in Railway env vars

SESSION = None  # lazy-loaded on first request

def get_session():
    global SESSION
    if SESSION is None:
        SESSION = new_session("u2netp")
    return SESSION

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def verify_secret(req):
    """Reject requests that don't have the correct API secret header."""
    if not API_SECRET:
        return True  # no secret configured — open (not recommended for production)
    return req.headers.get("X-API-Secret") == API_SECRET

def place_on_bg(subject_rgba, bg_rgb, size):
    canvas_w, canvas_h = size
    bg = Image.new("RGB", size, bg_rgb)
    subj_w, subj_h = subject_rgba.size
    if subj_w == 0 or subj_h == 0:
        return bg
    scale  = min(canvas_w / subj_w, canvas_h / subj_h)
    new_w  = int(subj_w * scale)
    new_h  = int(subj_h * scale)
    subject_rgba = subject_rgba.resize((new_w, new_h), Image.LANCZOS)
    x = (canvas_w - new_w) // 2
    y = (canvas_h - new_h) // 2
    bg.paste(subject_rgba, (x, y), mask=subject_rgba.split()[3])
    return bg

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": "u2netp"})

@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    """
    POST /remove-bg
    Headers:
        X-API-Secret: <your secret>
        X-Mode: website | instagram  (default: website)
        X-BG-Color: #F0F0F0          (optional override)
    Body: raw image bytes (multipart OR raw)
    Returns: JPEG image
    """
    if not verify_secret(request):
        return jsonify({"error": "Unauthorized"}), 401

    if "file" in request.files:
        file_bytes = request.files["file"].read()
    elif request.data:
        file_bytes = request.data
    else:
        return jsonify({"error": "No image provided"}), 400

    mode     = request.headers.get("X-Mode", "website")
    bg_hex   = request.headers.get("X-BG-Color", BG_COLOR_HEX)
    bg_rgb   = hex_to_rgb(bg_hex) if bg_hex.lower() not in ("transparent", "none") else (240, 240, 240)

    try:
        orig = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
        subject_rgba = remove(orig, session=get_session())

        # Tight-crop to subject
        bbox = subject_rgba.getbbox()
        if bbox:
            subject_rgba = subject_rgba.crop(bbox)
            w, h = subject_rgba.size
            pad = int(max(w, h) * 0.08)
            canvas = Image.new("RGBA", (w + pad*2, h + pad*2), (0,0,0,0))
            canvas.paste(subject_rgba, (pad, pad), mask=subject_rgba.split()[3])
            subject_rgba = canvas

        # Transparent mode: return PNG with no background fill
        if bg_hex.lower() in ("transparent", "none"):
            out = io.BytesIO()
            subject_rgba.save(out, "PNG")
            out.seek(0)
            return send_file(out, mimetype="image/png",
                             download_name="processed_transparent.png")

        if mode == "instagram":
            result = place_on_bg(subject_rgba, bg_rgb, (1080, 1080))
        else:
            subj_w, subj_h = subject_rgba.size
            scale = min(1200 / subj_w, 1600 / subj_h, 1.0)
            result = place_on_bg(subject_rgba, bg_rgb,
                                 (int(subj_w * scale), int(subj_h * scale)))

        out = io.BytesIO()
        result.save(out, "JPEG", quality=95, optimize=True)
        out.seek(0)
        return send_file(out, mimetype="image/jpeg",
                         download_name=f"processed_{mode}.jpg")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
