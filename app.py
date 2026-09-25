import io
import os
import re
from functools import lru_cache

from flask import Flask, jsonify, make_response, request
from PIL import Image, ImageColor, ImageFilter, ImageOps, UnidentifiedImageError
from rembg import new_session, remove


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

DEFAULT_MODEL = os.getenv("BG_MODEL", "birefnet-general")
API_SECRET = os.getenv("API_SECRET", "")
ALLOWED_MODELS = {
    "birefnet-general",
    "birefnet-general-lite",
    "birefnet-hrsod",
    "isnet-general-use",
}


@lru_cache(maxsize=2)
def model_session(model_name: str):
    return new_session(model_name)


def header_bool(name: str, default: bool = False) -> bool:
    raw = request.headers.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def requested_model() -> str:
    requested = request.headers.get("X-Model", DEFAULT_MODEL).strip().lower()
    return requested if requested in ALLOWED_MODELS else DEFAULT_MODEL


def parse_colour(raw: str) -> tuple[int, int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", raw or ""):
        raw = "#F0F0F0"
    red, green, blue = ImageColor.getrgb(raw)
    return red, green, blue, 255


def sharpen_foreground(cutout: Image.Image) -> Image.Image:
    """Sharpen garment detail without hardening or moving the alpha edge."""
    cutout = cutout.convert("RGBA")
    alpha = cutout.getchannel("A")
    rgb = cutout.convert("RGB").filter(
        ImageFilter.UnsharpMask(radius=0.75, percent=115, threshold=3)
    )
    rgb.putalpha(alpha)
    return rgb


def instagram_canvas(cutout: Image.Image, size: int = 1080) -> Image.Image:
    # Leave breathing room around the garment while preserving its aspect ratio.
    max_subject = int(size * 0.90)
    scale = min(max_subject / cutout.width, max_subject / cutout.height)
    target = (
        max(1, round(cutout.width * scale)),
        max(1, round(cutout.height * scale)),
    )
    resized = cutout.resize(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(
        resized,
        ((size - resized.width) // 2, (size - resized.height) // 2),
    )
    return canvas


@app.get("/health")
def health():
    return jsonify(
        status="ok",
        model=DEFAULT_MODEL,
        quality="high",
        edge_cleanup="decontaminate",
    )


@app.post("/remove-bg")
def remove_background():
    if API_SECRET and request.headers.get("X-API-Secret", "") != API_SECRET:
        return jsonify(error="Unauthorized"), 401

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(error="No image was uploaded"), 400

    try:
        source = Image.open(upload.stream)
        source = ImageOps.exif_transpose(source).convert("RGB")
        source.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify(error="The uploaded file is not a valid image"), 400

    model_name = requested_model()
    try:
        # BiRefNet already returns a detailed soft alpha. Decontamination removes
        # the old background colour from semi-transparent edge pixels without
        # shrinking collars, sleeves, labels, or thin straps.
        cutout = remove(
            source,
            session=model_session(model_name),
            alpha_matting=False,
            post_process_mask=False,
            decontaminate=header_bool("X-Decontaminate", True),
        ).convert("RGBA")
    except Exception as exc:
        app.logger.exception("Background removal failed")
        return jsonify(error="Background removal failed", detail=str(exc)), 500

    if request.headers.get("X-Quality", "high").lower() == "high":
        cutout = sharpen_foreground(cutout)

    mode = request.headers.get("X-Mode", "website").lower()
    if mode == "instagram":
        cutout = instagram_canvas(cutout)

    transparent = header_bool("X-Transparent", mode == "instagram")
    output_format = request.headers.get(
        "X-Output-Format", "png" if transparent else "jpeg"
    ).lower()
    output = io.BytesIO()

    if transparent or output_format == "png":
        cutout.save(output, "PNG", optimize=True, compress_level=6)
        content_type = "image/png"
    else:
        background = Image.new("RGBA", cutout.size, parse_colour(request.headers.get("X-BG-Color", "#F0F0F0")))
        background.alpha_composite(cutout)
        background.convert("RGB").save(
            output,
            "JPEG",
            quality=96,
            subsampling=0,
            optimize=True,
        )
        content_type = "image/jpeg"

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = content_type
    response.headers["X-BG-Model"] = model_name
    response.headers["X-BG-Quality"] = "high"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Image exceeds the upload limit"), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
