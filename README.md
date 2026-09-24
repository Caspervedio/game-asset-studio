# Nano Banana 2 MCP server

An [MCP](https://modelcontextprotocol.io) server that generates and edits images
with Google's **Nano Banana 2** model (Gemini 3.1 Flash Image,
`gemini-3.1-flash-image`).

It runs against **Vertex AI** using the `google-genai` SDK, so all usage bills
to your Google Cloud project (and is covered by your GCP credits) — not the
AI Studio API.

## Tools

| Tool | What it does |
| --- | --- |
| `generate_image(prompt, aspect_ratio="1:1", resolution="", num_images=1, filename="")` | Text → image(s) |
| `edit_image(prompt, input_image_paths, aspect_ratio="", resolution="", num_images=1, filename="")` | One or more reference images + instruction → image(s) |

Both tools save the result(s) to disk **and** return them inline so they are
visible in the client.

### Parameters

- **prompt** — what to create or how to change the input.
- **input_image_paths** (`edit_image` only) — a list of one or more image paths.
  Pass one to edit it, or several to combine/condition on them (Nano Banana 2
  can fuse multiple references).
- **aspect_ratio** — one of `1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9`.
- **resolution** — output size `1K`, `2K`, or `4K` (default `1K`).
- **num_images** — how many variations to generate, `1`–`8` (default `1`).
  Names get a `_1`, `_2`, … suffix when more than one is produced.
- **filename** — optional output name; relative names land in `NANO_BANANA_OUTPUT_DIR`.

## Configuration (environment variables)

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GOOGLE_CLOUD_PROJECT` | yes | — | GCP project to bill against |
| `GOOGLE_CLOUD_LOCATION` | no | `global` | Vertex AI location |
| `NANO_BANANA_MODEL` | no | `gemini-3.1-flash-image` | Model id |
| `NANO_BANANA_OUTPUT_DIR` | no | `~/nano-banana-images` | Where images are saved |

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

### 2. Enable the Vertex AI API and authenticate (run these yourself)

```bash
# Point gcloud at your project
gcloud config set project YOUR_PROJECT_ID

# Enable Vertex AI
gcloud services enable aiplatform.googleapis.com

# Create application default credentials the SDK will pick up
gcloud auth application-default login
```

### 3. Register the server with Claude Code

```bash
claude mcp add nano-banana \
  --env GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  -- /absolute/path/to/.venv/bin/python /absolute/path/to/server.py
```

Then confirm it is registered:

```bash
claude mcp list
```

**No `claude` CLI? (e.g. the Claude desktop app)** Add the server directly to
`~/.claude.json` instead — this is what `claude mcp add` writes. For a single
project, add it under `projects["<abs-project-dir>"].mcpServers`; for every
project, add it under the top-level `mcpServers`:

```json
"nano-banana": {
  "type": "stdio",
  "command": "/absolute/path/to/.venv/bin/python",
  "args": ["/absolute/path/to/server.py"],
  "env": { "GOOGLE_CLOUD_PROJECT": "YOUR_PROJECT_ID" }
}
```

Back up `~/.claude.json` first, and restart Claude so the new server loads.

## Web UI (optional)

Prefer a visual panel over driving it through chat? There's a small Gradio app
([app.py](app.py)) with a prompt box, reference-image upload (one or many),
aspect-ratio / resolution / count controls, and a result gallery. It calls the
same model via the shared `nano_banana_core` module.

```bash
# Install the UI extra into the same venv
./.venv/bin/pip install -r requirements-ui.txt

# Launch (opens your browser at http://127.0.0.1:7860)
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID ./.venv/bin/python app.py
```

`app.py` defaults `GOOGLE_CLOUD_PROJECT` to the project it was set up with, so
you can usually just run `./.venv/bin/python app.py`. The same gcloud auth and
API steps above apply.

## Files

| File | Purpose |
| --- | --- |
| `nano_banana_core.py` | Shared Vertex AI generation logic (no MCP/UI deps) |
| `server.py` | MCP server exposing `generate_image` / `edit_image` |
| `app.py` | Optional Gradio web UI |
| `requirements.txt` | Core + MCP dependencies |
| `requirements-ui.txt` | Adds Gradio for the web UI |

## Notes

- `gemini-3.1-flash-image` has limited regional availability. If a call
  fails with a **404 / not found**, set
  `GOOGLE_CLOUD_LOCATION=us-central1` and re-register the server.
- If you see an authentication error, re-run
  `gcloud auth application-default login`.
