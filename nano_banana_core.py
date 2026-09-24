"""Shared generation logic for Nano Banana 2 (Gemini 3.1 Flash Image) on Vertex AI.

This module has no MCP or Gradio dependencies — it just talks to Vertex AI via
the google-genai SDK. Both the MCP server (server.py) and the web UI (app.py)
import from here so there is a single source of truth.

Configure with environment variables:
  GOOGLE_CLOUD_PROJECT   (required) GCP project id to bill against
  GOOGLE_CLOUD_LOCATION  (default "global") Vertex AI location
  NANO_BANANA_MODEL      (default "gemini-3.1-flash-image-preview")
  NANO_BANANA_OUTPUT_DIR (default "~/nano-banana-images")
"""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Prefer the long-lived service account key if it's present on disk. This
# avoids the periodic re-auth that `gcloud auth application-default login`
# requires. Honor an explicit GOOGLE_APPLICATION_CREDENTIALS if already set.
_SA_KEY_DEFAULT = os.path.expanduser("~/.config/gcloud/nano-banana-sa-key.json")
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.isfile(_SA_KEY_DEFAULT):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _SA_KEY_DEFAULT

DEFAULT_MODEL = "gemini-3.1-flash-image"
DEFAULT_LOCATION = "global"
DEFAULT_OUTPUT_DIR = "~/nano-banana-images"

# Aspect ratios accepted by the model's ImageConfig.
VALID_ASPECT_RATIOS = (
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
)

# Output resolutions accepted by ImageConfig.image_size (default 1K).
VALID_RESOLUTIONS = ("1K", "2K", "4K")

# Upper bound on images per request, to avoid runaway calls.
MAX_IMAGES = 8

# Map response mime types to a sensible file extension.
_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# The genai client is created lazily on first use and cached here.
_client = None


@dataclass
class GeneratedImage:
    """One generated image: where it was saved, its bytes, and its mime type."""
    path: Path
    data: bytes
    mime: str

    @property
    def image_format(self) -> str:
        """e.g. "png", "jpeg" — suitable for building an image/<fmt> mime type."""
        return self.mime.split("/")[-1].split("+")[0]


def output_dir() -> Path:
    """The directory generated images are written to."""
    return Path(os.environ.get("NANO_BANANA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)).expanduser()


def auth_hint(error: Exception) -> str:
    """Return a friendly message, upgrading common failures to actionable advice."""
    text = str(error)
    low = text.lower()

    auth_markers = (
        "default credentials",
        "could not automatically determine credentials",
        "reauth",
        "unauthenticated",
        "invalid_grant",
        "401",
    )
    if any(marker in low for marker in auth_markers):
        return (
            "Vertex AI authentication failed. Run:\n"
            "    gcloud auth application-default login\n"
            "and make sure GOOGLE_CLOUD_PROJECT points at a project with the "
            "Vertex AI API (aiplatform.googleapis.com) enabled.\n\n"
            f"Original error: {text}"
        )

    if "404" in low or "not found" in low or "was not found" in low:
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
        model = os.environ.get("NANO_BANANA_MODEL", DEFAULT_MODEL)
        return (
            f"The model `{model}` was not found in location '{location}'.\n"
            "Nano Banana 2 (gemini-3.1-flash-image) is served only from the "
            "`global` endpoint. If NANO_BANANA_MODEL is set to a `-preview` name, "
            "unset it — the preview endpoint was retired when the model went GA.\n\n"
            f"Original error: {text}"
        )

    if "permission" in low or "403" in low or "aiplatform.googleapis.com" in low:
        return (
            "Permission denied or API disabled. Make sure the Vertex AI API is "
            "enabled and your account has access:\n"
            "    gcloud services enable aiplatform.googleapis.com\n\n"
            f"Original error: {text}"
        )

    return text


def get_client():
    """Create (once) and return a Vertex AI genai client."""
    global _client
    if _client is not None:
        return _client

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set. Set it to the Google Cloud project "
            "you want to bill against."
        )
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "The google-genai package is not installed. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    try:
        _client = genai.Client(vertexai=True, project=project, location=location)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise RuntimeError(auth_hint(exc)) from exc

    return _client


def _resolve_output_path(filename: str, extension: str, index: int = 0, total: int = 1) -> Path:
    """Decide where to write one generated image.

    When more than one image is produced, a 1-based index is appended so the
    files do not collide (e.g. "cat_1.png", "cat_2.png").
    """
    base_dir = output_dir()

    if filename:
        candidate = Path(filename).expanduser()
        suffix = candidate.suffix or extension
        stem = candidate.with_suffix("")
        if total > 1:
            stem = stem.with_name(f"{stem.name}_{index + 1}")
        candidate = stem.with_suffix(suffix)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        name = f"nano-banana_{stamp}"
        if total > 1:
            name = f"{name}_{index + 1}"
        candidate = base_dir / f"{name}{extension}"

    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _build_config(aspect_ratio: str, resolution: str):
    """Build a GenerateContentConfig that asks for an image back.

    Note: the image model only supports 1 candidate per call (Vertex returns
    400 INVALID_ARGUMENT otherwise), so we never set candidate_count here —
    `generate()` makes multiple parallel calls when num_images > 1.
    """
    from google.genai import types

    image_kwargs = {}
    if aspect_ratio:
        if aspect_ratio not in VALID_ASPECT_RATIOS:
            raise RuntimeError(
                f"Invalid aspect_ratio {aspect_ratio!r}. Valid values: "
                + ", ".join(VALID_ASPECT_RATIOS)
            )
        image_kwargs["aspect_ratio"] = aspect_ratio
    if resolution:
        normalized = resolution.upper()
        if normalized not in VALID_RESOLUTIONS:
            raise RuntimeError(
                f"Invalid resolution {resolution!r}. Valid values: "
                + ", ".join(VALID_RESOLUTIONS)
            )
        image_kwargs["image_size"] = normalized

    config_kwargs = {"response_modalities": ["IMAGE"]}
    if image_kwargs:
        config_kwargs["image_config"] = types.ImageConfig(**image_kwargs)

    return types.GenerateContentConfig(**config_kwargs)


def _extract_images(response):
    """Pull every inline image from a response as a list of (bytes, mime_type)."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("The model returned no candidates.")

    images = []
    text_chunks = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                mime = getattr(inline, "mime_type", None) or "image/png"
                images.append((inline.data, mime))
                continue
            text = getattr(part, "text", None)
            if text:
                text_chunks.append(text)

    if not images:
        detail = " ".join(text_chunks).strip()
        raise RuntimeError(
            "The model did not return an image."
            + (f" It said: {detail}" if detail else "")
        )
    return images


def generate(
    prompt: str,
    input_image_paths: list[str] | None = None,
    aspect_ratio: str = "",
    resolution: str = "",
    num_images: int = 1,
    filename: str = "",
) -> list[GeneratedImage]:
    """Generate image(s) with Nano Banana 2 and save them to disk.

    Pass one or more `input_image_paths` to edit/compose from reference images,
    or none for pure text-to-image. Returns a list of GeneratedImage.
    """
    if not (prompt or "").strip():
        raise RuntimeError("A prompt is required.")
    if num_images < 1 or num_images > MAX_IMAGES:
        raise RuntimeError(f"num_images must be between 1 and {MAX_IMAGES}.")

    client = get_client()
    from google.genai import types

    model = os.environ.get("NANO_BANANA_MODEL", DEFAULT_MODEL)

    contents: list = []
    for raw_path in input_image_paths or []:
        source = Path(raw_path).expanduser()
        if not source.is_file():
            raise RuntimeError(f"Input image not found: {source}")
        in_mime = mimetypes.guess_type(str(source))[0] or "image/png"
        contents.append(
            types.Part.from_bytes(data=source.read_bytes(), mime_type=in_mime)
        )
    contents.append(prompt)

    config = _build_config(aspect_ratio, resolution)

    def _one_call():
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            raise RuntimeError(auth_hint(exc)) from exc
        return _extract_images(response)

    if num_images <= 1:
        images = _one_call()
    else:
        # The image model only returns 1 candidate per request, so we fan out
        # `num_images` parallel calls (capped to avoid hammering the API).
        from concurrent.futures import ThreadPoolExecutor, as_completed

        images = []
        errors = []
        with ThreadPoolExecutor(max_workers=min(num_images, 4)) as pool:
            futures = [pool.submit(_one_call) for _ in range(num_images)]
            for fut in as_completed(futures):
                try:
                    images.extend(fut.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        # If everything failed, surface the first error so the user sees it.
        if not images and errors:
            raise errors[0]
    total = len(images)

    results: list[GeneratedImage] = []
    for index, (image_bytes, mime) in enumerate(images):
        extension = _EXT_BY_MIME.get(mime, "." + mime.split("/")[-1].split("+")[0])
        out_path = _resolve_output_path(filename, extension, index=index, total=total)
        out_path.write_bytes(image_bytes)
        results.append(GeneratedImage(path=out_path, data=image_bytes, mime=mime))

    return results
