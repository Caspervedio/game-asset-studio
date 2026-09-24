"""MCP server for Google's Nano Banana 2 (Gemini 3.1 Flash Image) on Vertex AI.

Exposes two tools over stdio:
  - generate_image: text -> image(s)
  - edit_image:     one or more reference images + instruction -> image(s)

All generation logic lives in nano_banana_core; this file is just the MCP shell.
Configure with environment variables (see nano_banana_core for the full list):
  GOOGLE_CLOUD_PROJECT (required), GOOGLE_CLOUD_LOCATION, NANO_BANANA_MODEL,
  NANO_BANANA_OUTPUT_DIR.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

import nano_banana_core as core

mcp = FastMCP("nano-banana")


def _to_content(results: list[core.GeneratedImage]):
    """Turn saved images into a summary line plus inline Image content."""
    summary = f"Saved {len(results)} image{'s' if len(results) != 1 else ''} to:\n" + "\n".join(
        str(r.path) for r in results
    )
    rendered = [Image(data=r.data, format=r.image_format) for r in results]
    return [summary, *rendered]


@mcp.tool()
def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    resolution: str = "",
    num_images: int = 1,
    filename: str = "",
):
    """Generate image(s) from a text prompt with Nano Banana 2 (Gemini 3.1 Flash Image).

    Args:
        prompt: Description of the image to create.
        aspect_ratio: One of 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9.
        resolution: Optional output size: 1K, 2K, or 4K (default 1K).
        num_images: How many variations to generate (1-8, default 1).
        filename: Optional output filename. If omitted, a timestamped name is used.
            Relative names are written under NANO_BANANA_OUTPUT_DIR. With more than
            one image, a 1-based index is appended.

    Returns the saved path(s) plus each image inline so they are visible.
    """
    results = core.generate(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        num_images=num_images,
        filename=filename,
    )
    return _to_content(results)


@mcp.tool()
def edit_image(
    prompt: str,
    input_image_paths: list[str],
    aspect_ratio: str = "",
    resolution: str = "",
    num_images: int = 1,
    filename: str = "",
):
    """Edit or compose using one or more reference images plus an instruction.

    Pass a single image to edit it, or several images to combine/condition on
    them (Nano Banana 2 can fuse multiple references).

    Args:
        prompt: How to modify or combine the image(s), e.g. "make it a watercolor"
            or "put the product from image 1 into the scene from image 2".
        input_image_paths: One or more paths to source images on disk.
        aspect_ratio: Optional. One of 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16,
            16:9, 21:9. Leave empty to keep the model's default framing.
        resolution: Optional output size: 1K, 2K, or 4K (default 1K).
        num_images: How many variations to generate (1-8, default 1).
        filename: Optional output filename. If omitted, a timestamped name is used.
            Relative names are written under NANO_BANANA_OUTPUT_DIR. With more than
            one image, a 1-based index is appended.

    Returns the saved path(s) plus each image inline so they are visible.
    """
    if not input_image_paths:
        raise RuntimeError("edit_image requires at least one path in input_image_paths.")
    results = core.generate(
        prompt=prompt,
        input_image_paths=input_image_paths,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        num_images=num_images,
        filename=filename,
    )
    return _to_content(results)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
