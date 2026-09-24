"""Local web UI for Nano Banana 2 (Gemini 3.1 Flash Image) on Vertex AI.

A paper-and-ink studio in the Vedio brand: a big preview on top and one
combined composer at the bottom — prompt, an inline "Image Reference" button
(with thumbnails), compact aspect / resolution / count controls, and Generate.
While generating it shows an animated banana with a 0–100% progress overlay.
Calls the same Vertex AI model as the MCP server via nano_banana_core.

Run:  ./.venv/bin/python app.py
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

# Bill to this project unless the environment already specifies one.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "vedio-444210")
# Don't phone home — we run entirely on your own Vertex AI project.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

import nano_banana_core as core

# Local-static assets (favicon only — the hero brand-mark img was removed).
# Resolved relative to this file so it works whether launched from cwd or as a LaunchAgent.
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_FAVICON_PATH = os.path.join(_ASSETS_DIR, "favicon.png")

# Fonts: Vedio brand — Anton (display, uppercase), Fraunces (lede/serif),
# Inter (body/UI). System fallbacks so nothing breaks if Google Fonts is blocked.
_BRAND_SANS = [
    '"Inter"', "-apple-system", "BlinkMacSystemFont", "SF Pro Display",
    '"Helvetica Neue"', "Arial", "sans-serif",
]

# --- Vedio brand palette (mirrors /brand/index.html v3 tokens) ------------
BG = "#F4F2EE"          # paper — default canvas
CARD = "#FFFFFF"        # white — cards/chips on paper
CARD_BORDER = "#E4E1DA" # line — hairline borders
INPUT = "#FFFFFF"       # white — input fills
INPUT_BORDER = "#E4E1DA"
TEXT = "#0E0E0C"        # ink — primary text
TEXT_MUTED = "#6C6961"  # text soft — secondary copy
PLACEHOLDER = "#98948A" # text faint — captions, hints
ACCENT1 = "#7C3AED"     # violet — the accent (≤ 10% of surface)
ACCENT2 = "#5B21B6"     # violet deep — hover of violet
PREVIEW_BG = "#FBF9F5"  # a whisper darker than paper for preview canvas
VIOLET_SOFT = "#EFE9FB" # tinted violet fill — soft hover / active row
BRICK = "#A33B2A"       # brand's don't-mark color; used only for destructive

THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.violet,
    neutral_hue=gr.themes.colors.stone,
    radius_size=gr.themes.sizes.radius_lg,
    font=_BRAND_SANS,
).set(
    # Force the same values on the .dark class too, so if the user's system
    # is set to dark we still render the Vedio paper palette (the brand is
    # light-mode only, mirroring vedio.dk).
    body_background_fill=BG, body_background_fill_dark=BG,
    body_text_color=TEXT, body_text_color_dark=TEXT,
    body_text_color_subdued=TEXT_MUTED, body_text_color_subdued_dark=TEXT_MUTED,
    background_fill_primary=CARD, background_fill_primary_dark=CARD,
    background_fill_secondary=INPUT, background_fill_secondary_dark=INPUT,
    block_background_fill=CARD, block_background_fill_dark=CARD,
    block_border_width="0px",
    # Vedio's whisper two-layer shadow (mirrors brand/index.html tokens).
    block_shadow="0 1px 2px rgba(14,14,12,0.03), 0 10px 30px rgba(14,14,12,0.05)",
    border_color_primary=CARD_BORDER, border_color_primary_dark=CARD_BORDER,
    input_background_fill=INPUT, input_background_fill_dark=INPUT,
    input_border_color=INPUT_BORDER, input_border_color_dark=INPUT_BORDER,
    input_placeholder_color=PLACEHOLDER, input_placeholder_color_dark=PLACEHOLDER,
    block_title_background_fill="transparent", block_title_background_fill_dark="transparent",
    block_title_text_color=TEXT_MUTED, block_title_text_color_dark=TEXT_MUTED,
    block_label_background_fill="transparent", block_label_background_fill_dark="transparent",
    block_label_text_color=TEXT_MUTED, block_label_text_color_dark=TEXT_MUTED,
)

CUSTOM_CSS = f"""
/* Vedio brand fonts. Google Fonts loads via <link> if allowed by CSP; if
   blocked, the sans/serif/display stacks fall back cleanly. */
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Fraunces:ital,opsz,wght@0,9..144,400..600;1,9..144,400..600&family=Inter:wght@400;500;600;700;800&display=swap');

html, body {{ height: 100%; margin: 0; }}
.gradio-container {{
    background: {BG} !important;
    width: 100% !important; max-width: 1040px !important;
    margin: 0 auto !important; padding: 4px 24px 16px !important;
    height: 100vh !important; display: flex !important; flex-direction: column !important;
}}
.gradio-container .main, .gradio-container .wrap, .gradio-container .contain, .gradio-container .contain > .column {{
    max-width: 100% !important; width: 100% !important;
    height: 100% !important; min-height: 0 !important;
    display: flex !important; flex-direction: column !important;
}}
.gradio-container .contain > .column {{ flex: 1 1 auto !important; }}
.composer {{ flex: 0 0 auto !important; }}
* {{ font-family: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif !important; }}
body, gradio-app {{ background: {BG} !important; color: {TEXT} !important; }}
footer {{ display: none !important; }}

/* Header — Anton headline (uppercase, display) + Inter kicker + Fraunces lede */
.hero {{ position: relative; text-align: center; padding: 22px 0 12px; }}
.hero .badge {{
    display: inline-block;
    background: transparent !important;
    color: {ACCENT1} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 11.5px !important; font-weight: 700 !important;
    letter-spacing: 0.16em !important; text-transform: uppercase !important;
    padding: 0 !important; border-radius: 0 !important;
    box-shadow: none !important; margin-bottom: 10px !important;
}}
.hero h1 {{
    font-family: "Anton", "Arial Narrow", Impact, sans-serif !important;
    font-weight: 400 !important; text-transform: uppercase !important;
    font-size: 54px !important; line-height: 0.95 !important;
    letter-spacing: 0.01em !important;
    color: {TEXT} !important; margin: 8px 0 10px !important;
}}
.hero h1 .v {{ color: {ACCENT1} !important; }}
.hero p {{
    font-family: "Fraunces", Georgia, serif !important;
    color: {TEXT_MUTED} !important;
    font-size: 17px !important; line-height: 1.5 !important;
    margin: 0 auto !important; max-width: 520px !important;
    font-weight: 400 !important;
}}

/* Big preview canvas — paper card lifted by the brand's two-layer whisper shadow */
#preview {{
    flex: 1 1 auto !important; min-height: 220px !important; height: auto !important;
    background: {PREVIEW_BG} !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    border-radius: 24px !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.03), 0 10px 30px rgba(14,14,12,.05) !important;
    overflow: hidden !important;
}}
#preview .empty {{ display: flex !important; align-items: center !important; justify-content: center !important; height: 100% !important; min-height: 0 !important; }}
#preview .empty > * {{ display: none !important; }}
#preview .empty::after {{
    content: "Your image will appear here";
    color: {TEXT_MUTED};
    font-family: "Fraunces", Georgia, serif; font-size: 17px; font-style: italic;
}}
/* Fill the preview and fit the image to its own aspect ratio (no scroll) */
#preview .grid-wrap, #preview .grid-container {{ height: 100% !important; max-height: 100% !important; }}
#preview .preview {{ height: 100% !important; }}
#preview img {{ object-fit: contain !important; max-height: 100% !important; max-width: 100% !important; }}
/* Single-preview big image: don't toggle on click (avoid fullscreen). Toolbar pinned top. */
#preview .media-button {{ pointer-events: none !important; cursor: default !important; flex: 1 1 auto !important; min-height: 0 !important; }}
#preview .icon-button-wrapper.top-panel {{ opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; }}
/* Always hide the inline thumbnails strip — use the grid (← Back) for overview navigation */
#preview .thumbnails {{ display: none !important; }}
/* Restyle the gallery's Close (×) as a clearer "← Back" pill */
#preview button[aria-label="Close"] {{
    display: inline-flex !important; align-items: center !important;
    padding: 8px 16px 8px 13px !important; gap: 6px;
    background: {CARD} !important; border: 1px solid {CARD_BORDER} !important;
    border-radius: 100px !important; color: {TEXT} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 13px !important; font-weight: 600 !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.03), 0 6px 16px rgba(14,14,12,.06) !important;
}}
#preview button[aria-label="Close"] svg {{ display: none !important; }}
#preview button[aria-label="Close"]::before {{ content: "← Back"; }}
#preview button[aria-label="Close"]:hover {{ color: {ACCENT1} !important; }}
/* Grid overview: single-item case spans the full width */
#preview .grid-container {{ gap: 8px !important; }}
#preview .grid-container:has(.gallery-item:only-child) {{ grid-template-columns: 1fr !important; }}
#preview .gallery-item {{ border-radius: 12px !important; overflow: hidden; }}

/* ---- Composer — a raised white card on paper, Vedio surface treatment ---- */
.composer {{
    background: {CARD} !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    border-radius: 24px !important;
    padding: 16px 18px 14px !important;
    margin-top: 12px !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.03), 0 10px 30px rgba(14,14,12,.05) !important;
    gap: 10px !important;
}}
.composer .prompt-input {{
    background: {BG} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 16px !important;
    padding: 4px 10px !important;
    margin-bottom: 6px !important;
    transition: border-color .18s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow .18s cubic-bezier(0.22, 1, 0.36, 1);
}}
.composer .prompt-input:focus-within {{
    border-color: {ACCENT1} !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,.13) !important;
}}
.composer .prompt-input textarea, .composer .prompt-input input {{
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: {TEXT} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 15px !important; font-weight: 400 !important;
    padding: 12px 10px !important; resize: none !important;
    min-height: 56px !important;
}}
.composer .prompt-input textarea::placeholder,
.composer .prompt-input input::placeholder {{
    color: {PLACEHOLDER} !important; font-family: "Fraunces", Georgia, serif !important;
    font-style: italic !important;
}}

/* Reference thumbnails — tiny, attached under the prompt */
#ref-thumbs {{ background: transparent !important; border: none !important; box-shadow: none !important; min-height: 0 !important; margin: 0 2px !important; padding: 0 !important; }}
#ref-thumbs .grid-wrap, #ref-thumbs .grid-container, #ref-thumbs .grid {{ display: flex !important; flex-wrap: wrap !important; gap: 6px !important; justify-content: flex-start !important; }}
#ref-thumbs .thumbnail-item, #ref-thumbs button.thumbnail-item {{
    width: 44px !important; height: 44px !important; min-width: 44px !important; max-width: 44px !important;
    flex: 0 0 auto !important;
    border-radius: 12px !important;
    border: 1px solid {CARD_BORDER} !important;
    overflow: hidden !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.04);
}}
#ref-thumbs img {{ width: 100% !important; height: 100% !important; object-fit: cover !important; }}

/* Tools row inside the composer */
.composer-tools {{ display: flex !important; align-items: center !important; gap: 8px !important; flex-wrap: wrap !important; }}
.composer-tools .refine {{ margin-left: auto !important; }}

/* Actions row: Generate (primary) on the left, Refine + Clear next to it */
.composer-actions {{
    display: flex !important; align-items: center !important;
    justify-content: flex-start !important; gap: 8px !important;
    margin-top: 6px !important; flex-wrap: wrap !important;
}}

/* Secondary — white pill with an INSET ring (Vedio: never a bare 1px border) */
.chip {{
    background: {CARD} !important; color: {TEXT} !important;
    border: 1.5px solid transparent !important; border-radius: 100px !important;
    padding: 0 22px !important;
    font-family: "Inter", sans-serif !important;
    font-size: 14px !important; font-weight: 600 !important;
    min-height: 44px !important; white-space: nowrap !important;
    box-shadow: inset 0 0 0 1px rgba(14,14,12,0.10), 0 1px 2px rgba(14,14,12,.03) !important;
    transition: box-shadow .18s cubic-bezier(0.22, 1, 0.36, 1),
                color .18s cubic-bezier(0.22, 1, 0.36, 1);
}}
.chip:hover {{
    color: {ACCENT2} !important;
    box-shadow: inset 0 0 0 1px rgba(124,58,237,0.35), 0 6px 16px rgba(14,14,12,.06) !important;
}}

/* Compact dropdowns for aspect / resolution / count — same secondary treatment.
   IMPORTANT: strip every Gradio wrapper background so only the .wrap pill is
   visible. Otherwise the outer .block / .form containers paint a soft rectangle
   behind each pill (visible on the light Vedio paper). We deliberately DO NOT
   set padding on .wrap — Gradio's internal layout uses it for label + caret. */
.mini,
.mini .block, .mini .form, .mini .container,
.mini > div, .mini > div > div {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    min-width: 140px !important;   /* fits "8 images" + caret comfortably */
}}
.mini .wrap {{
    background: {CARD} !important; border: none !important; border-radius: 100px !important;
    min-height: 44px !important;
    box-shadow: inset 0 0 0 1px rgba(14,14,12,0.10) !important;
}}
.mini .wrap:hover {{
    box-shadow: inset 0 0 0 1px rgba(124,58,237,0.35) !important;
}}
.mini .wrap input, .mini .wrap span {{
    color: {TEXT} !important; font-family: "Inter", sans-serif !important;
    font-size: 14px !important; font-weight: 600 !important;
    background: transparent !important; border: none !important;
}}

/* Primary "Generate" button — ink black gradient, pill, Vedio focus halo */
.cta {{
    border-radius: 100px !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 600 !important; font-size: 15px !important;
    padding: 0 30px !important; min-height: 46px !important;
    color: #fff !important; border: none !important;
    white-space: nowrap !important;
    background: linear-gradient(180deg, #23231F 0%, {TEXT} 100%) !important;
    box-shadow: 0 1px 0 rgba(255,255,255,.14) inset,
                0 8px 22px rgba(14,14,12,.18),
                0 0 0 0 rgba(124,58,237,0) !important;
    transition: transform .12s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow .18s cubic-bezier(0.22, 1, 0.36, 1),
                filter .18s ease;
}}
.cta:hover {{
    filter: brightness(1.06);
    transform: translateY(-2px);
    box-shadow: 0 1px 0 rgba(255,255,255,.14) inset,
                0 12px 28px rgba(14,14,12,.22) !important;
}}
.cta:focus-visible {{
    outline: none !important;
    box-shadow: 0 1px 0 rgba(255,255,255,.14) inset,
                0 8px 22px rgba(14,14,12,.18),
                0 0 0 3px rgba(124,58,237,.13) !important;
}}
.cta:active {{ transform: translateY(0); }}

#status {{
    text-align: center; color: {TEXT_MUTED};
    margin-top: 6px; font-size: 13px; line-height: 1.4;
    font-family: "Inter", sans-serif;
}}
#status p {{ margin: 0 !important; }}

/* Settings gear — moved into the preview-tabs tab list (right of History) via JS */
.gear-btn {{
    width: 40px !important; height: 40px !important; min-width: 40px !important;
    padding: 0 !important;
    background: transparent !important; border: none !important;
    color: {TEXT_MUTED} !important; font-size: 20px !important;
    margin-left: auto !important;
    box-shadow: none !important; border-radius: 8px !important;
    transition: color .15s ease, background .15s ease;
}}
.gear-btn:hover {{ color: {ACCENT2} !important; background: {VIOLET_SOFT} !important; }}

/* Settings modal — dim overlay + light dialog (Vedio's whisper elevation).
   Scrolling lives on the OUTER modal, not the dialog. This lets dropdown
   popovers (Gradio's `position: absolute` option lists) escape the dialog
   card without getting clipped. */
.settings-modal {{
    position: fixed !important; inset: 0 !important; z-index: 100 !important;
    background: rgba(14,14,12,.38) !important;
    backdrop-filter: blur(4px);
    align-items: flex-start !important; justify-content: center !important;
    padding: 40px 24px !important; margin: 0 !important;
    overflow-y: auto !important;
}}
.settings-modal .settings-dialog {{
    background: {CARD} !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    border-radius: 24px !important; padding: 22px 26px 26px !important;
    width: min(920px, 92vw) !important;
    overflow: visible !important;  /* let dropdown popovers escape */
    box-shadow: 0 1px 2px rgba(14,14,12,.06), 0 22px 56px rgba(14,14,12,.16) !important;
    flex: 0 0 auto !important;
    margin: 0 auto !important;
}}
/* Every dropdown popover inside a modal wins the z-index race */
.settings-modal .options,
.settings-modal [role="listbox"],
.settings-modal ul.options {{
    z-index: 200 !important;
    background: {CARD} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.06), 0 12px 32px rgba(14,14,12,.14) !important;
    padding: 4px !important;
}}
.settings-modal .options li,
.settings-modal [role="option"] {{
    border-radius: 10px !important;
    padding: 8px 12px !important;
    font-family: "Inter", sans-serif !important;
    font-size: 14px !important;
    color: {TEXT} !important;
}}
.settings-modal .options li:hover,
.settings-modal [role="option"]:hover {{
    background: {VIOLET_SOFT} !important;
    color: {ACCENT2} !important;
}}
.settings-header {{ align-items: center !important; flex-wrap: nowrap !important; }}
.settings-title {{ flex: 1 1 auto; }}
.settings-title h2 {{
    margin: 0 !important;
    font-family: "Anton", "Arial Narrow", Impact, sans-serif !important;
    font-weight: 400 !important; text-transform: uppercase !important;
    letter-spacing: 0.01em !important;
    font-size: 30px !important; line-height: 1 !important;
    color: {TEXT} !important;
}}
.close-btn {{
    width: 36px !important; min-width: 36px !important; height: 36px !important;
    border-radius: 100px !important; padding: 0 !important;
    background: transparent !important; border: none !important;
    color: {TEXT_MUTED} !important; font-size: 16px !important;
    box-shadow: none !important;
    transition: color .15s ease, background .15s ease;
}}
.close-btn:hover {{ color: {TEXT} !important; background: rgba(14,14,12,0.045) !important; }}

/* Settings pane content */
.settings-pane {{ padding: 14px 4px 8px !important; max-width: 800px; margin: 0 auto; }}
.settings-pane h3 {{
    font-family: "Inter", sans-serif !important;
    font-size: 15px !important; font-weight: 800 !important;
    text-transform: uppercase !important; letter-spacing: 0.10em !important;
    color: {TEXT} !important; margin: 20px 0 10px !important;
}}
.settings-pane .muted, .settings-pane .muted p {{
    color: {TEXT_MUTED} !important; font-size: 14px !important; line-height: 1.5 !important;
}}

/* Rules pane (Settings) — comfortable prose textarea + button row */
#rules-pane textarea {{
    background: {BG} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 16px !important;
    color: {TEXT} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 14.5px !important; line-height: 1.55 !important;
    padding: 14px 16px !important;
    min-height: 220px !important;
}}
#rules-pane textarea:focus {{
    border-color: {ACCENT1} !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,.13) !important;
}}
#rules-pane textarea::placeholder {{
    color: {PLACEHOLDER} !important; font-style: italic !important;
    font-family: "Fraunces", Georgia, serif !important;
}}
.rules-actions {{ margin-top: 14px !important; gap: 10px !important; }}
#rules-status {{
    margin-top: 10px !important;
    font-family: "Inter", sans-serif !important; font-size: 13px !important;
    color: {TEXT_MUTED} !important;
}}

/* Save button — same chip base; the label swaps between "★ Save" and "✓ Saved"
   to signal state. The ★ character stays violet-tinted so it reads as an action. */
.save-btn {{ transition: color .18s ease !important; }}
.save-btn:hover {{ color: {ACCENT2} !important; }}

/* Concept chip — sits in composer-tools; violet accent to signal it's a mode */
.concept-chip {{
    color: {ACCENT2} !important;
    background: {VIOLET_SOFT} !important;
    box-shadow: inset 0 0 0 1px rgba(124,58,237,0.28) !important;
}}
.concept-chip:hover {{
    box-shadow: inset 0 0 0 1px rgba(124,58,237,0.55), 0 6px 16px rgba(124,58,237,.12) !important;
}}

/* --- Concepts modal — wider than Settings so 5 fields breathe --- */
.settings-modal .concepts-dialog {{
    width: min(980px, 94vw) !important;
}}
#concepts-pane {{ padding-bottom: 14px !important; max-width: 100% !important; }}

/* Load/new row — sits above the editor, must not wrap awkwardly */
.concepts-loadrow {{ gap: 10px !important; align-items: flex-end !important; margin-bottom: 8px !important; }}
.concepts-loadrow > * {{ flex-shrink: 0 !important; }}

/* All textareas inside the concept editor get the same treatment */
#concepts-pane textarea, #concepts-pane input[type="text"] {{
    background: {BG} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 16px !important;
    color: {TEXT} !important; font-family: "Inter", sans-serif !important;
    font-size: 14px !important; line-height: 1.5 !important;
    padding: 12px 14px !important;
}}
#concepts-pane textarea:focus, #concepts-pane input[type="text"]:focus {{
    border-color: {ACCENT1} !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,.13) !important;
}}
#concepts-pane textarea::placeholder, #concepts-pane input::placeholder {{
    color: {PLACEHOLDER} !important; font-style: italic !important;
    font-family: "Fraunces", Georgia, serif !important;
}}
#concepts-pane label > .wrap-inner label {{
    color: {TEXT} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 11.5px !important; font-weight: 700 !important;
    letter-spacing: 0.10em !important; text-transform: uppercase !important;
}}
.editor-label p {{
    color: {TEXT} !important; font-family: "Inter", sans-serif !important;
    font-size: 11.5px !important; font-weight: 700 !important;
    letter-spacing: 0.10em !important; text-transform: uppercase !important;
    margin: 12px 0 4px !important;
}}

/* Editor anchors (thumbnails already attached to the concept) */
#editor-anchors {{ background: transparent !important; border: none !important; box-shadow: none !important; }}
#editor-anchors .thumbnail-item, #editor-anchors button.thumbnail-item {{
    border-radius: 12px !important;
    border: 1.5px solid {ACCENT1} !important;
    box-shadow: 0 0 0 2px rgba(124,58,237,0.10) !important;
    cursor: pointer !important;
}}
#editor-anchors .thumbnail-item:hover {{
    border-color: {BRICK} !important;
    box-shadow: 0 0 0 2px rgba(163,59,42,0.15) !important;
}}

/* Saved-picker: bigger grid, clickable to attach */
#saved-picker {{ background: transparent !important; border: none !important; box-shadow: none !important; }}
#saved-picker .thumbnail-item, #saved-picker button.thumbnail-item {{
    border-radius: 12px !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    cursor: pointer !important;
    transition: transform .12s cubic-bezier(0.22, 1, 0.36, 1),
                border-color .15s ease, box-shadow .18s ease;
}}
#saved-picker .thumbnail-item:hover {{
    border-color: {ACCENT1} !important;
    transform: translateY(-1px) scale(1.02);
    box-shadow: 0 6px 14px rgba(14,14,12,.06) !important;
}}

.anchor-upload-row {{ margin: 10px 0 20px !important; }}
.concepts-actions {{ margin-top: 20px !important; gap: 10px !important; flex-wrap: wrap !important; }}
.concepts-actions .cta {{ min-width: 180px !important; }}
.concepts-actions .clear-studio-btn {{ min-width: 160px !important; margin-left: auto !important; }}
#concept-status {{
    margin-top: 12px !important;
    font-family: "Inter", sans-serif !important; font-size: 13px !important;
    color: {TEXT_MUTED} !important;
}}

/* "🗑 Clear" — ghost tonal button on light (brand's low-emphasis action) */
.clear-studio-btn {{
    background: rgba(14,14,12,0.045) !important;
    border: none !important;
    border-radius: 100px !important;
    color: {TEXT_MUTED} !important;
    padding: 0 18px !important; min-height: 44px !important;
    font-family: "Inter", sans-serif !important;
    font-size: 14px !important; font-weight: 600 !important;
    box-shadow: none !important;
    margin-left: auto !important;
    transition: background .18s ease, color .18s ease;
}}
.clear-studio-btn:hover {{
    color: {BRICK} !important;
    background: rgba(163,59,42,0.09) !important;
}}

/* Preview Tabs (Preview / History) inside Studio — fills its tab pane */
#preview-tabs {{
    flex: 1 1 auto !important; min-height: 0 !important;
    display: flex !important; flex-direction: column !important;
    background: transparent !important; border: none !important;
}}
#preview-tabs > .tab-nav, #preview-tabs > .tab-wrapper {{ flex: 0 0 auto !important; }}
#preview-tabs > .tabitem {{
    flex: 1 1 auto !important; min-height: 0 !important; padding: 0 !important;
    flex-direction: column !important;
}}
#preview-tabs .tabitem > * {{ flex: 1 1 auto !important; min-height: 0 !important; }}
#preview-tabs button[role="tab"] {{
    background: transparent !important; border: none !important;
    color: {TEXT_MUTED} !important;
    font-family: "Inter", sans-serif !important;
    font-size: 12px !important; font-weight: 700 !important;
    letter-spacing: 0.10em !important; text-transform: uppercase !important;
    padding: 10px 14px !important;
}}
#preview-tabs button[role="tab"][aria-selected="true"] {{
    color: {ACCENT1} !important;
    box-shadow: inset 0 -2px 0 {ACCENT1} !important;
}}
#history-gallery {{ background: transparent !important; border: none !important; box-shadow: none !important; }}
#history-gallery .thumbnail-item, #history-gallery button.thumbnail-item {{
    border-radius: 16px !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    cursor: pointer !important; position: relative !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.03), 0 6px 14px rgba(14,14,12,.04) !important;
    transition: transform .18s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow .18s cubic-bezier(0.22, 1, 0.36, 1),
                border-color .15s ease;
}}
#history-gallery .thumbnail-item:hover {{
    border-color: {ACCENT1} !important;
    transform: translateY(-2px) scale(1.015);
    box-shadow: 0 1px 2px rgba(14,14,12,.05), 0 12px 24px rgba(14,14,12,.08) !important;
}}

/* History toolbar (Edit button) */
.history-toolbar {{ display: flex !important; justify-content: flex-end !important; margin-bottom: 8px !important; gap: 8px !important; }}
.history-edit-btn {{ font-size: 13px !important; }}
/* Empty Saved tab: nothing to edit, so hide the toggle and say how to fill it (mirrors the Preview's empty state) */
.history-tab:has(#history-gallery .empty) .history-toolbar {{ display: none !important; }}
#history-gallery .empty {{ display: flex !important; align-items: center !important; justify-content: center !important; }}
#history-gallery .empty > * {{ display: none !important; }}
#history-gallery .empty::after {{
    content: "Nothing saved yet — press ★ Save under an image to keep it here";
    color: {TEXT_MUTED};
    font-family: "Fraunces", Georgia, serif; font-size: 17px; font-style: italic;
}}

/* History edit mode — red border + ✕ overlay, click deletes */
.history-tab.edit-mode #history-gallery .thumbnail-item,
.history-tab.edit-mode #history-gallery button.thumbnail-item {{
    border-color: #ff5470 !important;
    box-shadow: 0 0 0 1px rgba(255,84,112,.25) inset !important;
}}
.history-tab.edit-mode #history-gallery .thumbnail-item::after {{
    content: "✕";
    position: absolute; top: 4px; right: 4px;
    width: 22px; height: 22px;
    background: rgba(255,84,112,.96);
    color: #fff; font-size: 12px; font-weight: 700;
    border-radius: 50%;
    display: flex !important; align-items: center; justify-content: center;
    pointer-events: none;
    box-shadow: 0 2px 6px rgba(0,0,0,.4);
}}
.history-tab.edit-mode #history-gallery .thumbnail-item:hover {{
    border-color: #ff3050 !important;
    transform: scale(.98) !important;
    transition: all .1s ease;
}}
.history-tab.edit-mode #history-gallery .thumbnail-item:hover::after {{
    background: #ff3050;
    transform: scale(1.12);
}}
/* When in edit mode, mark the Edit button as "active" (Done) */
.history-tab.edit-mode .history-edit-btn {{
    background: linear-gradient(135deg, {ACCENT1}, {ACCENT2}) !important;
    color: #fff !important; border-color: transparent !important;
}}

/* ---- Confirm-Clear modal ---- */
/* IMPORTANT: do NOT set `display: flex !important` here. Gradio hides a
   visible=False Column by setting inline `display: none`, and `!important`
   would override that, leaving an invisible click-blocking overlay. */
.confirm-modal {{
    position: fixed !important; inset: 0 !important; z-index: 110 !important;
    background: rgba(14,14,12,.38) !important;
    backdrop-filter: blur(4px);
    align-items: center !important; justify-content: center !important;
    padding: 24px !important; margin: 0 !important;
}}
.confirm-dialog {{
    background: {CARD} !important;
    border: 1px solid rgba(228,225,218,0.55) !important;
    border-radius: 24px !important; padding: 26px 28px !important;
    width: min(460px, 92vw) !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.06), 0 22px 56px rgba(14,14,12,.16) !important;
    flex: 0 0 auto !important;
}}
.confirm-title h3 {{
    margin: 0 0 10px !important;
    font-family: "Anton", "Arial Narrow", Impact, sans-serif !important;
    font-weight: 400 !important; text-transform: uppercase !important;
    letter-spacing: 0.01em !important;
    font-size: 30px !important; line-height: 1 !important;
    color: {TEXT} !important;
}}
.confirm-body p {{
    color: {TEXT_MUTED} !important;
    font-family: "Fraunces", Georgia, serif !important;
    font-size: 16px !important; line-height: 1.5 !important;
    margin: 0 0 22px !important;
}}
.confirm-actions {{ display: flex !important; justify-content: flex-end !important; gap: 12px !important; }}
.cta-danger {{
    border-radius: 100px !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 600 !important; font-size: 14px !important;
    padding: 0 24px !important; min-height: 44px !important;
    color: #fff !important; border: none !important;
    white-space: nowrap !important;
    background: {BRICK} !important;
    box-shadow: 0 1px 2px rgba(14,14,12,.06), 0 8px 22px rgba(163,59,42,.28) !important;
    transition: filter .18s ease, transform .12s cubic-bezier(0.22, 1, 0.36, 1);
}}
.cta-danger:hover {{ filter: brightness(1.05); transform: translateY(-1px); }}

/* ---- Banana loading overlay (0 -> 100%) — light-theme paper backdrop ---- */
#loader {{
    position: fixed; inset: 0; z-index: 90;
    display: flex; align-items: center; justify-content: center;
    background: rgba(244,242,238,0.86);
    backdrop-filter: blur(4px);
}}
.nb-load {{ text-align: center; }}
.nb-banana {{
    font-size: 72px; line-height: 1; display: inline-block;
    filter: drop-shadow(0 4px 12px rgba(14,14,12,.14));
    animation: nb-wobble 1.05s ease-in-out infinite;
}}
.nb-pct {{
    margin-top: 16px;
    font-family: "Anton", "Arial Narrow", Impact, sans-serif !important;
    font-weight: 400 !important;
    font-size: 44px !important; line-height: 1 !important;
    color: {TEXT} !important; letter-spacing: 0.01em !important;
}}
.nb-desc {{
    margin-top: 8px;
    font-family: "Fraunces", Georgia, serif !important;
    font-size: 15px !important; font-style: italic !important;
    color: {TEXT_MUTED} !important;
}}
.nb-track {{
    width: 240px; height: 6px; border-radius: 100px;
    background: {CARD_BORDER}; margin: 18px auto 0; overflow: hidden;
    box-shadow: inset 0 1px 2px rgba(14,14,12,.05);
}}
.nb-fill {{ height: 100%; border-radius: 100px; background: {ACCENT1}; transition: width .25s cubic-bezier(0.22, 1, 0.36, 1); }}
@keyframes nb-wobble {{ 0%, 100% {{ transform: rotate(-22deg) translateY(0); }} 50% {{ transform: rotate(22deg) translateY(-12px); }} }}
"""


_FORCE_LIGHT_JS = """
(() => {
  // Move the gear button into the preview-tabs tab list (right of History).
  // We retry because the tab list may not exist yet at script-injection time.
  const moveGear = () => {
    const tablist = document.querySelector('#preview-tabs .tab-container[role="tablist"]');
    const gear = document.querySelector('.gear-btn');
    if (tablist && gear && gear.parentElement !== tablist) {
      tablist.appendChild(gear);
      return true;
    }
    return false;
  };
  const tryMove = (n) => {
    if (moveGear()) return;
    if (n <= 0) return;
    setTimeout(() => tryMove(n - 1), 300);
  };
  tryMove(40);
  // Force LIGHT theme via URL param — Vedio brand is paper-based, light only.
  const u = new URL(window.location.href);
  if (u.searchParams.get('__theme') !== 'light') {
    u.searchParams.set('__theme', 'light');
    window.location.replace(u.href);
  }
})();
"""


def _loader_html(pct: int, desc: str = "Cooking up your image") -> str:
    pct = max(0, min(100, int(pct)))
    return (
        f'<div class="nb-load"><div class="nb-banana">🍌</div>'
        f'<div class="nb-pct">{pct}%</div>'
        f'<div class="nb-desc">{desc}…</div>'
        f'<div class="nb-track"><div class="nb-fill" style="width:{pct}%"></div></div></div>'
    )


def _paths_from_files(files) -> list[str]:
    """Normalize Gradio file inputs to a list of filesystem paths."""
    if files is None:
        return []
    if not isinstance(files, (list, tuple)):
        files = [files]
    paths = []
    for item in files:
        if isinstance(item, str):
            paths.append(item)
        elif hasattr(item, "name"):
            paths.append(item.name)
    return paths


def on_upload(new_files, existing):
    """Append newly-picked references to the existing list (deduped by path)."""
    new_paths = _paths_from_files(new_files)
    refs = list(existing or [])
    for p in new_paths:
        if p and p not in refs:
            refs.append(p)
    return refs, gr.update(value=refs, visible=bool(refs))


def on_remove_ref(evt: gr.SelectData, refs):
    """Clicking a reference thumbnail removes just that reference."""
    idx = evt.index
    if isinstance(idx, (list, tuple)):
        idx = idx[0] if idx else None
    refs = list(refs or [])
    if isinstance(idx, int) and 0 <= idx < len(refs):
        refs.pop(idx)
    return refs, gr.update(value=refs, visible=bool(refs))


def run_generate(prompt, references, aspect_ratio, resolution, num_images, last_output,
                 rules, active_concept, refine_anchor_in):
    """Generator: streams a banana + 0–100% overlay, then the finished images.

    Yields tuples for (gallery, status, loader, last_output, refine_anchor).

    Anchor logic: if the user clicked Generate with NO references (fresh
    generation), reset the anchor — the next Refine should anchor to the new
    output. If they had references (a chained Refine, or an upload), keep the
    existing anchor. Anchor is preserved during progress ticks.

    Rules (global) + concept rules (per-project) are prepended to every prompt.
    Concept anchors are prepended to references so they weigh in first.
    """
    if not (prompt or "").strip():
        yield gr.update(), "Please enter a prompt to get started.", gr.update(visible=False), last_output, refine_anchor_in
        return

    # Snapshot whether this run started from a "clean" studio (no refs). A fresh
    # generation should reset the anchor so the next Refine anchors to whatever
    # we're about to produce, not to some stale earlier session.
    was_fresh = not bool(references)

    # Compose the actual prompt from four layers, in order:
    #   (1) global rules  → user's Settings.Rules text
    #   (2) concept rules → what the concept says to always do
    #   (3) concept donts → what to never do
    #   (4) concept prompt_prefix → a "concept lead" phrase prepended to the request
    # If a section is empty, it's skipped.
    actual_prompt = prompt
    actual_refs = list(references or [])
    global_rules = (rules or "").strip()
    concept_rules = (active_concept.get("rules") if active_concept else "").strip()
    concept_donts = (active_concept.get("donts") if active_concept else "").strip()
    concept_prefix = (active_concept.get("prompt_prefix") if active_concept else "").strip()
    combined_rules = "\n".join(r for r in [global_rules, concept_rules] if r)

    blocks = []
    if combined_rules:
        blocks.append("Follow these rules for every image you create:\n" + combined_rules)
    if concept_donts:
        blocks.append("Never do any of the following:\n" + concept_donts)
    if concept_prefix:
        blocks.append("Concept context: " + concept_prefix)
    if blocks:
        actual_prompt = "\n\n".join(blocks) + "\n\nNow create: " + actual_prompt

    # Concept anchors go FIRST in references — they define the visual DNA.
    if active_concept:
        anchors = list(active_concept.get("anchors") or [])
        # Filter to files that still exist; dedupe against user refs.
        anchors = [a for a in anchors if Path(a).is_file() and a not in actual_refs]
        actual_refs = anchors + actual_refs

    num_images = int(num_images)
    box: dict = {}

    def work():
        try:
            box["res"] = core.generate(
                prompt=actual_prompt,
                input_image_paths=actual_refs,
                aspect_ratio=aspect_ratio or "",
                resolution=resolution or "",
                num_images=num_images,
            )
        except Exception as exc:  # noqa: BLE001
            box["err"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()

    # Rough time estimate so the bar advances smoothly; it caps at 99% until done.
    # The image model returns 1 image per call, so num_images > 1 fans out to
    # parallel calls (capped at 4) — estimate by # of waves.
    waves = 1 + (num_images - 1) // 4
    estimate = 10.0 + 6.0 * waves
    start = time.time()
    yield gr.update(), "", gr.update(value=_loader_html(0), visible=True), last_output, refine_anchor_in
    while worker.is_alive():
        pct = min(99, int((time.time() - start) / estimate * 100))
        yield gr.update(), "", gr.update(value=_loader_html(pct), visible=True), last_output, refine_anchor_in
        time.sleep(0.25)
    worker.join()

    if "err" in box:
        yield [], f"**Error:** {box['err']}", gr.update(visible=False), last_output, refine_anchor_in
        return

    results = box["res"]
    paths = [str(r.path) for r in results]

    # Write a sidecar .json next to each image so we can reconstruct provenance
    # later (prompt, refs, rules, concept, model, timestamp).
    from datetime import datetime as _dt
    model_name = os.environ.get("NANO_BANANA_MODEL", core.DEFAULT_MODEL)
    meta_base = {
        "prompt": prompt,
        "actual_prompt": actual_prompt,
        "references": list(actual_refs),
        "rules": combined_rules,
        "concept": (
            {"slug": active_concept.get("slug"), "name": active_concept.get("name")}
            if active_concept else None
        ),
        "aspect_ratio": aspect_ratio or "",
        "resolution": resolution or "",
        "model": model_name,
        "created": _dt.now().isoformat(timespec="seconds"),
    }
    for p in paths:
        _write_sidecar(p, meta_base)

    # Briefly show 100%, then reveal the images and hide the overlay.
    yield gr.update(), "", gr.update(value=_loader_html(100, "Done"), visible=True), last_output, refine_anchor_in
    time.sleep(0.35)
    plural = "s" if len(paths) != 1 else ""
    # Single image -> open preview directly; multiple -> stay on grid overview.
    selected = 0 if len(paths) == 1 else None
    note_parts = []
    if combined_rules:
        note_parts.append("**rules**")
    if active_concept:
        note_parts.append(f"concept **{active_concept.get('name', '')[:24]}**")
    note = f"  ·  with {' · '.join(note_parts)}" if note_parts else ""
    # Fresh generation resets the anchor; a chained refine keeps it.
    new_anchor = None if was_fresh else refine_anchor_in
    yield (
        gr.update(value=paths, selected_index=selected),
        f"Saved **{len(paths)}** image{plural}{note}",
        gr.update(visible=False),
        paths,
        new_anchor,
    )


def _saved_dir() -> Path:
    """Subfolder under output_dir where explicitly-saved images live."""
    return core.output_dir() / "saved"


def _list_saved(limit: int = 200) -> list[str]:
    """Return paths of images the user has explicitly saved, newest first."""
    d = _saved_dir()
    if not d.is_dir():
        return []
    files = []
    for ext in ("png", "jpg", "jpeg", "webp"):
        files.extend(d.glob(f"*.{ext}"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in files[:limit]]


def _refresh_saved():
    """Used after every save/un-save to update the state + gallery."""
    paths = _list_saved()
    return paths, paths


def _is_saved(scratch_path: str) -> bool:
    """True if a copy of `scratch_path`'s basename exists in the saved dir."""
    if not scratch_path:
        return False
    return (_saved_dir() / Path(scratch_path).name).is_file()


def on_toggle_save(last_output):
    """Copy the current preview into saved/, or remove it if already there.

    Outputs: (save_btn_label_update, saved_paths_state, saved_gallery_update).
    Copying (not moving) keeps the original in the scratch dir so Refine's
    anchor path stays valid.
    """
    paths = list(last_output or [])
    if not paths:
        return gr.update(value="★ Save"), _list_saved(), gr.update(value=_list_saved())
    src = Path(paths[0])
    if not src.is_file():
        return gr.update(value="★ Save"), _list_saved(), gr.update(value=_list_saved())
    saved_dir = _saved_dir()
    saved_dir.mkdir(parents=True, exist_ok=True)
    dst = saved_dir / src.name
    if dst.is_file():
        # Un-save: remove from saved (scratch untouched). Sidecar too.
        try:
            dst.unlink()
        except Exception:  # noqa: BLE001
            pass
        _delete_sidecar_if_exists(str(dst))
        label = "★ Save"
    else:
        # Save: copy image + sidecar into saved dir.
        try:
            shutil.copy2(src, dst)
            _copy_sidecar_if_exists(str(src), str(dst))
            label = "✓ Saved"
        except Exception:  # noqa: BLE001
            label = "★ Save"
    now = _list_saved()
    return gr.update(value=label), now, gr.update(value=now)


def _save_btn_label_for(last_output) -> str:
    """Return the correct button label for whatever is currently in last_output."""
    paths = list(last_output or [])
    if not paths:
        return "★ Save"
    return "✓ Saved" if _is_saved(paths[0]) else "★ Save"


def on_history_select(evt: gr.SelectData, paths, edit_mode):
    """Click handler for a history thumbnail.

    - Browse mode (edit_mode=False): load it into Preview and switch tabs.
    - Edit mode (edit_mode=True): delete the file from disk and refresh the grid.

    Outputs: gallery, last_output, preview_tabs, saved_paths, saved_gallery, refine_anchor.
    """
    idx = evt.index
    if isinstance(idx, (list, tuple)):
        idx = idx[0] if idx else None
    paths = list(paths or [])
    if not isinstance(idx, int) or idx < 0 or idx >= len(paths):
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
    chosen = paths[idx]

    if edit_mode:
        # Delete from disk (image + its sidecar); missing files just drop out.
        try:
            os.remove(chosen)
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            pass
        _delete_sidecar_if_exists(chosen)
        new_paths = [p for p in paths if p != chosen]
        return (
            gr.update(),                                     # gallery unchanged
            gr.update(),                                     # last_output unchanged
            gr.update(),                                     # stay on History tab
            new_paths,                                       # saved_paths state
            gr.update(value=new_paths),                      # history_gallery
            gr.update(),                                     # refine_anchor unchanged
        )

    # Browse mode: load the chosen image into Preview and switch tabs.
    # Clicking a history image is a fresh-session move — reset the refine
    # anchor so the next Refine anchors to this image (not to some stale one).
    return (
        gr.update(value=[chosen], selected_index=0),         # main gallery
        [chosen],                                             # last_output
        gr.update(selected="prev"),                           # switch to Preview tab
        gr.update(),                                          # saved_paths unchanged
        gr.update(),                                          # history_gallery unchanged
        None,                                                 # refine_anchor -> reset
    )


def on_toggle_edit_history(current):
    """Flip edit mode and update the button label."""
    new = not bool(current)
    label = "✓ Done" if new else "✏️ Edit"
    return new, gr.update(value=label)


_RULES_PATH = os.path.expanduser("~/.cache/nano-banana-rules.txt")


def _load_rules_from_disk() -> str:
    """Read the user's saved rules text, or "" if none saved."""
    if not os.path.isfile(_RULES_PATH):
        return ""
    try:
        with open(_RULES_PATH) as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return ""


def _save_rules_to_disk(text: str) -> None:
    os.makedirs(os.path.dirname(_RULES_PATH), exist_ok=True)
    with open(_RULES_PATH, "w") as f:
        f.write(text or "")


def on_save_rules(text: str):
    """Persist the rules text; returns (rules_state, status)."""
    text = (text or "").strip()
    try:
        _save_rules_to_disk(text)
    except Exception as exc:  # noqa: BLE001
        return text, f"**Save failed:** {exc}"
    if not text:
        return "", "Rules cleared — nothing will be prepended to prompts."
    line_count = len([ln for ln in text.splitlines() if ln.strip()])
    return text, f"✓ Saved {line_count} rule{'s' if line_count != 1 else ''} — applied to every Generate."


def on_clear_rules():
    """Wipe rules from disk; returns (rules_state, rules_textbox, status)."""
    try:
        if os.path.isfile(_RULES_PATH):
            os.remove(_RULES_PATH)
    except Exception:  # noqa: BLE001
        pass
    return "", gr.update(value=""), "Rules cleared."


def _restore_rules_state():
    """Auto-load saved rules on app start; returns (rules_state, rules_textbox, status)."""
    text = _load_rules_from_disk()
    if not text:
        return "", gr.update(), ""
    line_count = len([ln for ln in text.splitlines() if ln.strip()])
    return text, gr.update(value=text), f"📁 Loaded {line_count} saved rule{'s' if line_count != 1 else ''}."


# ============================================================
# Concepts — named bundles of {anchor images, rules} for a
# consistent series (same product/character across N variants).
# ============================================================
import json as _json
import re as _re
import uuid as _uuid

_CONCEPTS_DIR = Path(os.path.expanduser("~/.cache/nano-banana-concepts"))
_ACTIVE_CONCEPT_PATH = os.path.expanduser("~/.cache/nano-banana-active-concept.txt")


def _slugify(text: str) -> str:
    s = _re.sub(r"[^a-z0-9\s-]", "", (text or "").lower()).strip()
    s = _re.sub(r"[\s-]+", "-", s)
    return s[:60] or f"concept-{_uuid.uuid4().hex[:8]}"


def _concept_dir(slug: str) -> Path:
    return _CONCEPTS_DIR / slug


def _concept_json_path(slug: str) -> Path:
    return _CONCEPTS_DIR / f"{slug}.json"


def _load_concept(slug: str) -> dict | None:
    """Read a concept from disk; strips anchors whose files no longer exist."""
    if not slug:
        return None
    p = _concept_json_path(slug)
    if not p.is_file():
        return None
    try:
        d = _json.loads(p.read_text())
        d["anchors"] = [x for x in d.get("anchors", []) if Path(x).is_file()]
        return d
    except Exception:  # noqa: BLE001
        return None


def _list_concepts() -> list[dict]:
    """Return every saved concept, newest first."""
    if not _CONCEPTS_DIR.is_dir():
        return []
    out = []
    for f in _CONCEPTS_DIR.glob("*.json"):
        try:
            d = _json.loads(f.read_text())
            d["anchors"] = [x for x in d.get("anchors", []) if Path(x).is_file()]
            out.append(d)
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda c: c.get("created", 0), reverse=True)
    return out


def _save_concept(name: str, anchor_paths: list, rules: str = "",
                  donts: str = "", prompt_prefix: str = "", notes: str = "") -> dict:
    """Copy anchors into the concept's folder, write JSON, return the dict.

    Copying (not just referencing) means deleting from Saved won't break the concept.
    Anchors already inside the concept's dir are copied in place (idempotent).
    """
    name = (name or "").strip() or "Untitled concept"
    slug = _slugify(name)
    _CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    cdir = _concept_dir(slug)
    cdir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    seen: set[str] = set()
    for i, src in enumerate(anchor_paths or []):
        src_p = Path(src)
        if not src_p.is_file():
            continue
        # If it's already inside this concept's dir, keep it as-is.
        if src_p.parent == cdir:
            copied.append(str(src_p)); seen.add(src_p.name); continue
        # Otherwise copy in with a stable unique name.
        base = f"anchor_{i:02d}{src_p.suffix or '.png'}"
        n = 0
        dst_name = base
        while dst_name in seen or (cdir / dst_name).is_file():
            n += 1
            dst_name = f"anchor_{i:02d}_{n}{src_p.suffix or '.png'}"
        dst = cdir / dst_name
        try:
            shutil.copy2(src_p, dst)
            copied.append(str(dst)); seen.add(dst.name)
        except Exception:  # noqa: BLE001
            continue

    data = {
        "slug": slug, "name": name,
        "anchors": copied,
        "rules": (rules or "").strip(),
        "donts": (donts or "").strip(),
        "prompt_prefix": (prompt_prefix or "").strip(),
        "notes": (notes or "").strip(),
        "created": time.time(),
    }
    _concept_json_path(slug).write_text(_json.dumps(data, indent=2))
    return data


def _delete_concept_from_disk(slug: str) -> None:
    try:
        _concept_json_path(slug).unlink()
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        pass
    cdir = _concept_dir(slug)
    if cdir.is_dir():
        try:
            shutil.rmtree(cdir)
        except Exception:  # noqa: BLE001
            pass


def _save_active_concept_slug(slug: str) -> None:
    try:
        os.makedirs(os.path.dirname(_ACTIVE_CONCEPT_PATH), exist_ok=True)
        with open(_ACTIVE_CONCEPT_PATH, "w") as f:
            f.write(slug or "")
    except Exception:  # noqa: BLE001
        pass


def _load_active_concept_slug() -> str:
    if not os.path.isfile(_ACTIVE_CONCEPT_PATH):
        return ""
    try:
        with open(_ACTIVE_CONCEPT_PATH) as f:
            return f.read().strip()
    except Exception:  # noqa: BLE001
        return ""


def _concept_chip_label(concept: dict | None) -> str:
    """Compact label for the composer's concept chip."""
    if not concept:
        return "🎬 New concept"
    name = concept.get("name") or concept.get("slug") or "concept"
    if len(name) > 24:
        name = name[:23] + "…"
    return f"🎬 {name}"


def _concept_choices() -> list[tuple[str, str]]:
    """(label, slug) pairs for a Dropdown."""
    return [(c["name"], c["slug"]) for c in _list_concepts()]


# ---------- Concept handlers ----------
# Editor fields are exposed as a tuple, in a fixed order used by every handler that
# populates or reads the editor:
#   (name, editor_anchors_state, editor_anchors_gallery, rules, donts, prompt_prefix, notes)


def _editor_from_concept(concept: dict | None) -> tuple:
    """Populate all editor fields from a concept dict (or clear them)."""
    if not concept:
        return (
            gr.update(value=""),        # concept_name
            [],                         # editor_anchors state
            gr.update(value=[]),        # editor_anchors_gallery
            gr.update(value=""),        # rules
            gr.update(value=""),        # donts
            gr.update(value=""),        # prompt_prefix
            gr.update(value=""),        # notes
        )
    anchors = list(concept.get("anchors") or [])
    return (
        gr.update(value=concept.get("name", "")),
        anchors,
        gr.update(value=anchors),
        gr.update(value=concept.get("rules", "")),
        gr.update(value=concept.get("donts", "")),
        gr.update(value=concept.get("prompt_prefix", "")),
        gr.update(value=concept.get("notes", "")),
    )


def on_new_blank_concept():
    """Clear the editor for a fresh new concept (doesn't touch active yet)."""
    return _editor_from_concept(None) + (
        "Editor cleared — set a name, attach anchors from Saved (or upload), "
        "fill the fields, then Save concept.",
    )


def on_load_concept_into_editor(slug):
    """Load an existing concept's fields into the editor AND activate it."""
    if not slug:
        return _editor_from_concept(None) + (
            None,                                       # active_concept
            gr.update(value=_concept_chip_label(None)), # chip
            "Pick a concept from the list first.",
        )
    concept = _load_concept(slug)
    if not concept:
        return _editor_from_concept(None) + (
            None, gr.update(value=_concept_chip_label(None)),
            "Concept not found on disk.",
        )
    _save_active_concept_slug(slug)
    fields = _editor_from_concept(concept)
    return fields + (
        concept,
        gr.update(value=_concept_chip_label(concept)),
        f"📁 Loaded **{concept['name']}** into the editor — active for generation. "
        f"Edit fields and hit Save to persist.",
    )


def on_save_editor_concept(name, editor_anchors, rules, donts, prompt_prefix, notes):
    """Persist the editor as a concept (create OR update by slugified name), activate it.

    Outputs: (active_concept, chip, concepts_picker, concept_status,
              editor_anchors_state, editor_anchors_gallery)
    """
    if not (name or "").strip():
        return (
            gr.update(), gr.update(), gr.update(),
            "Give the concept a name first.",
            gr.update(), gr.update(),
        )
    if not (editor_anchors or []):
        return (
            gr.update(), gr.update(), gr.update(),
            "Attach at least one anchor image (from Saved or upload) — "
            "anchors are the DNA that keeps a series consistent.",
            gr.update(), gr.update(),
        )
    data = _save_concept(
        name=name, anchor_paths=editor_anchors,
        rules=rules or "", donts=donts or "",
        prompt_prefix=prompt_prefix or "", notes=notes or "",
    )
    _save_active_concept_slug(data["slug"])
    choices = _concept_choices()
    # The anchors list on disk may have new paths (copied into the concept dir)
    # — reflect that in the editor state so subsequent saves are idempotent.
    return (
        data,
        gr.update(value=_concept_chip_label(data)),
        gr.update(choices=choices, value=data["slug"]),
        f"✓ Saved concept **{data['name']}** with {len(data['anchors'])} "
        f"anchor{'s' if len(data['anchors']) != 1 else ''}. Active for generation.",
        data["anchors"],
        gr.update(value=data["anchors"]),
    )


def on_attach_anchor_from_saved(evt: gr.SelectData, saved_paths_list, editor_anchors):
    """Clicking a Saved thumbnail attaches (or de-attaches) it to the editor."""
    idx = evt.index
    if isinstance(idx, (list, tuple)):
        idx = idx[0] if idx else None
    saved = list(saved_paths_list or [])
    if not isinstance(idx, int) or idx < 0 or idx >= len(saved):
        return editor_anchors, gr.update(value=editor_anchors), gr.update()
    chosen = saved[idx]
    anchors = list(editor_anchors or [])
    if chosen in anchors:
        anchors.remove(chosen)
        msg = f"Removed from editor anchors ({len(anchors)} left)."
    else:
        anchors.append(chosen)
        msg = f"Attached to editor anchors ({len(anchors)} total) — Save concept to persist."
    return anchors, gr.update(value=anchors), gr.update(value=msg)


def on_remove_editor_anchor(evt: gr.SelectData, editor_anchors):
    """Click a thumbnail in the editor's anchor strip to remove it."""
    idx = evt.index
    if isinstance(idx, (list, tuple)):
        idx = idx[0] if idx else None
    anchors = list(editor_anchors or [])
    if isinstance(idx, int) and 0 <= idx < len(anchors):
        removed = anchors.pop(idx)
        msg = f"Removed {Path(removed).name} from editor anchors — Save concept to persist."
    else:
        msg = gr.update()
    return anchors, gr.update(value=anchors), gr.update(value=msg) if not isinstance(msg, dict) else msg


def on_upload_editor_anchor(new_files, editor_anchors):
    """Add uploaded image files to the editor's anchor list."""
    anchors = list(editor_anchors or [])
    for p in _paths_from_files(new_files):
        if p and p not in anchors:
            anchors.append(p)
    msg = f"Added {len(anchors)} anchor{'s' if len(anchors) != 1 else ''} — Save concept to persist."
    return anchors, gr.update(value=anchors), gr.update(value=msg)


def on_deactivate_concept():
    """Clear the active concept — freestyle mode."""
    _save_active_concept_slug("")
    return (
        None,
        gr.update(value=_concept_chip_label(None)),
        "Freestyle — no concept active. Your generations use only current refs + global rules.",
        gr.update(value=None),
    )


def on_delete_concept(slug, current_active):
    """Delete a concept from disk. Deactivates it if it was active.

    Outputs: (active_concept, chip_label, concepts_picker, status).
    """
    if not slug:
        return current_active, gr.update(), gr.update(), "Nothing to delete."
    concept = _load_concept(slug)
    name = concept.get("name") if concept else slug
    _delete_concept_from_disk(slug)
    # If we deleted the active concept, deactivate.
    new_active = current_active
    chip = gr.update()
    if current_active and current_active.get("slug") == slug:
        new_active = None
        chip = gr.update(value=_concept_chip_label(None))
        _save_active_concept_slug("")
    choices = _concept_choices()
    return (
        new_active, chip,
        gr.update(choices=choices, value=None),
        f"🗑 Deleted concept **{name}**.",
    )


def _restore_active_concept():
    """On app start, restore whichever concept was last active.

    Outputs: (active_concept_state, chip_label_update, concepts_picker).
    """
    slug = _load_active_concept_slug()
    choices = _concept_choices()
    if not slug:
        return None, gr.update(value=_concept_chip_label(None)), gr.update(choices=choices, value=None)
    concept = _load_concept(slug)
    if not concept:
        _save_active_concept_slug("")
        return None, gr.update(value=_concept_chip_label(None)), gr.update(choices=choices, value=None)
    return (
        concept,
        gr.update(value=_concept_chip_label(concept)),
        gr.update(choices=choices, value=slug),
    )


# ============================================================
# Sidecar metadata — a JSON next to every generated image so
# you can come back weeks later and see exactly how it was made.
# ============================================================

def _sidecar_path(image_path: str) -> Path:
    return Path(image_path).with_suffix(".json")


def _write_sidecar(image_path: str, meta: dict) -> None:
    try:
        _sidecar_path(image_path).write_text(_json.dumps(meta, indent=2))
    except Exception:  # noqa: BLE001
        pass


def _copy_sidecar_if_exists(src_image: str, dst_image: str) -> None:
    sc = _sidecar_path(src_image)
    if sc.is_file():
        try:
            shutil.copy2(sc, _sidecar_path(dst_image))
        except Exception:  # noqa: BLE001
            pass


def _delete_sidecar_if_exists(image_path: str) -> None:
    p = _sidecar_path(image_path)
    if p.is_file():
        try:
            p.unlink()
        except Exception:  # noqa: BLE001
            pass


def on_confirm_clear_studio():
    """Wipe the Studio AND close the confirmation modal — atomic, single round-trip.

    A chained `.click().then()` was causing the click to appear to freeze for some
    users; collapsing into one return value is more reliable.
    """
    return (
        gr.update(value=""),                              # prompt
        [],                                               # references state
        gr.update(value=[], visible=False),               # ref_thumbs gallery
        gr.update(value=[], selected_index=None),         # main gallery
        [],                                               # last_output state
        "",                                               # status
        gr.update(visible=False),                         # confirm_clear_modal -> closed
        None,                                             # refine_anchor -> reset
    )


def on_refine(last_output, current_anchor):
    """Load the ORIGINAL of this refine session as the reference.

    First Refine of a session: anchor to the current preview (last_output[0]).
    Subsequent Refines in the same session: reuse the same anchor image.

    Anchoring like this stops the "each refine looks worse" quality drift you
    get when you feed the previous refined output back to the model — every
    round-trip loses a tiny bit of sharpness, and it compounds fast.

    Returns updates for (references, ref_thumbs, refine_anchor, status).
    """
    paths = list(last_output or [])
    if not paths:
        return (
            [], gr.update(visible=False), current_anchor,
            "Generate an image first, then Refine to iterate on it.",
        )
    is_first_refine = current_anchor is None
    anchor = current_anchor or paths[0]
    msg = (
        "Locked in your image as the source — tweak the prompt and click **Generate**. "
        "Every Refine will re-run from this original so quality doesn't drift."
        if is_first_refine else
        "Still refining from your original — same source image, new prompt."
    )
    return (
        [anchor],                                    # references state
        gr.update(value=[anchor], visible=True),     # ref_thumbs
        anchor,                                       # refine_anchor state (persist)
        msg,                                          # status
    )


def build() -> gr.Blocks:
    with gr.Blocks(title="Nano Banana 2 — Image Studio", fill_width=True) as demo:
        gr.HTML(
            """
            <div class="hero">
              <span class="badge">Vertex AI · Nano Banana 2</span>
              <h1>Image <span class="v">Studio.</span></h1>
              <p>Describe what you want, or drop a reference to remix.</p>
            </div>
            """
        )

        # Shared state lives outside tabs so handlers in any tab can read/write.
        references = gr.State([])
        last_output = gr.State([])
        saved_paths = gr.State([])
        edit_saved = gr.State(False)     # True = clicking a saved thumb deletes it
        refine_anchor = gr.State(None)   # first image of current refine session — reused, never overwritten by drift
        rules_state = gr.State("")       # user's saved rules text, prepended to every prompt
        active_concept = gr.State(None)  # dict of the currently-active concept, or None (freestyle)

        # ============== MAIN UI ==============
        with gr.Tabs(elem_id="preview-tabs") as preview_tabs:
            with gr.Tab("Preview", id="prev"):
                gallery = gr.Gallery(
                    show_label=False, columns=4, object_fit="contain", preview=False,
                    allow_preview=True, selected_index=None, elem_id="preview",
                )
            with gr.Tab("Saved", id="saved"):
                with gr.Column(elem_id="history-tab-wrap", elem_classes="history-tab"):
                    with gr.Row(elem_classes="history-toolbar"):
                        edit_saved_btn = gr.Button(
                            "✏️ Edit", scale=0, min_width=110,
                            elem_classes="chip history-edit-btn", elem_id="edit-history-btn",
                        )
                    saved_gallery = gr.Gallery(
                        show_label=False, columns=8, object_fit="cover", allow_preview=False,
                        elem_id="history-gallery",
                    )

        with gr.Column(elem_classes="composer"):
            prompt = gr.Textbox(
                show_label=False, placeholder="Describe the image you want to create",
                lines=2, max_lines=6, container=False, elem_classes="prompt-input",
            )
            ref_thumbs = gr.Gallery(
                visible=False, show_label=False, columns=10, height=56,
                object_fit="cover", allow_preview=False, elem_id="ref-thumbs",
            )
            with gr.Row(elem_classes="composer-tools"):
                upload_btn = gr.UploadButton(
                    "＋  Image Reference", file_count="multiple", file_types=["image"],
                    type="filepath", size="sm", scale=0, min_width=170, elem_classes="chip",
                )
                concept_chip_btn = gr.Button(
                    "🎬 New concept", scale=0, min_width=160,
                    elem_classes="chip concept-chip",
                )
                aspect_ratio = gr.Dropdown(
                    choices=list(core.VALID_ASPECT_RATIOS), value="1:1",
                    show_label=False, container=False, scale=0, min_width=104, elem_classes="mini",
                )
                resolution = gr.Dropdown(
                    choices=list(core.VALID_RESOLUTIONS), value="1K",
                    show_label=False, container=False, scale=0, min_width=92, elem_classes="mini",
                )
                num_images = gr.Dropdown(
                    choices=[(f"{i} image" if i == 1 else f"{i} images", i)
                             for i in range(1, core.MAX_IMAGES + 1)],
                    value=1, show_label=False, container=False, scale=0, min_width=120, elem_classes="mini",
                )
            with gr.Row(elem_classes="composer-actions"):
                generate_btn = gr.Button(
                    "Generate", variant="primary", scale=0, min_width=140, elem_classes="cta",
                )
                refine_btn = gr.Button(
                    "↻ Refine", scale=0, min_width=104, elem_classes="chip refine",
                )
                save_btn = gr.Button(
                    "★ Save", scale=0, min_width=104, elem_classes="chip save-btn",
                )
                clear_btn = gr.Button(
                    "🗑  Clear", scale=0, min_width=98, elem_classes="clear-studio-btn",
                )
            status = gr.Markdown(elem_id="status")

        # Floating gear icon (top-right) — opens the Settings modal
        gear_btn = gr.Button("⚙", elem_classes="gear-btn", elem_id="gear-btn", min_width=44)

        # ============== SETTINGS MODAL (Rules) ==============
        with gr.Column(visible=False, elem_classes="settings-modal") as settings_modal:
            with gr.Column(elem_classes="settings-dialog"):
                with gr.Row(elem_classes="settings-header"):
                    gr.Markdown("## ⚙  Settings", elem_classes="settings-title")
                    close_settings_btn = gr.Button("✕", scale=0, min_width=44, elem_classes="close-btn")
                with gr.Column(elem_classes="settings-pane", elem_id="rules-pane"):
                    gr.Markdown("### Rules & instructions")
                    gr.Markdown(
                        "Fundamental instructions that get prepended to **every** prompt. "
                        "Use it for house style, subject rules, framing preferences, "
                        "things the model should always avoid.",
                        elem_classes="muted",
                    )
                    rules_textbox = gr.Textbox(
                        show_label=False,
                        placeholder=(
                            "e.g.\n"
                            "• Always use natural daylight, no harsh flash.\n"
                            "• Real people only — never AI avatars.\n"
                            "• Never include readable text or logos.\n"
                            "• 9:16 vertical framing, subject centered."
                        ),
                        lines=10, max_lines=24, container=False,
                        elem_id="rules-textbox",
                    )
                    with gr.Row(elem_classes="rules-actions"):
                        rules_save_btn = gr.Button("Save rules", elem_classes="cta", scale=2)
                        rules_clear_btn = gr.Button("Clear rules", scale=1, elem_classes="chip")
                    rules_status = gr.Markdown(elem_id="rules-status")

        # ============== CONCEPTS MODAL ==============
        # Editor state — anchors currently in the editor (may differ from active
        # concept until user hits Save). Stays in sync with editor_anchors_gallery.
        editor_anchors_state = gr.State([])

        with gr.Column(visible=False, elem_classes="settings-modal") as concepts_modal:
            with gr.Column(elem_classes="settings-dialog concepts-dialog"):
                with gr.Row(elem_classes="settings-header"):
                    gr.Markdown("## 🎬  Concepts", elem_classes="settings-title")
                    close_concepts_btn = gr.Button("✕", scale=0, min_width=44, elem_classes="close-btn")
                with gr.Column(elem_classes="settings-pane", elem_id="concepts-pane"):
                    gr.Markdown(
                        "A **concept** locks in your visual DNA — anchor images + rules — "
                        "so a whole series stays consistent while each variant differs. "
                        "Load an existing concept to edit it, or start blank.",
                        elem_classes="muted",
                    )

                    # ---- LOAD / NEW row ----
                    gr.Markdown("### Load or start fresh")
                    with gr.Row(elem_classes="concepts-loadrow"):
                        concepts_picker = gr.Dropdown(
                            choices=[], value=None, label="Existing concepts",
                            allow_custom_value=False, scale=8, min_width=280,
                        )
                        load_concept_btn = gr.Button(
                            "Load & activate", scale=0, min_width=170, elem_classes="chip",
                        )
                        new_blank_btn = gr.Button(
                            "New blank", scale=0, min_width=130, elem_classes="chip",
                        )
                        deactivate_concept_btn = gr.Button(
                            "Freestyle", scale=0, min_width=130, elem_classes="chip",
                        )

                    # ---- EDITOR ----
                    gr.Markdown("### Edit concept")
                    concept_name = gr.Textbox(
                        label="Name", placeholder="e.g. Peter · founder shoot",
                        elem_id="concept-name-input",
                    )

                    gr.Markdown("**Anchor images**", elem_classes="editor-label")
                    gr.Markdown(
                        "Click a thumbnail here to remove it from this concept.",
                        elem_classes="muted",
                    )
                    editor_anchors_gallery = gr.Gallery(
                        value=[], show_label=False, columns=6, height=110,
                        object_fit="cover", allow_preview=False,
                        elem_id="editor-anchors",
                    )
                    with gr.Row(elem_classes="anchor-upload-row"):
                        upload_editor_anchor_btn = gr.UploadButton(
                            "＋  Attach uploaded image", file_count="multiple",
                            file_types=["image"], type="filepath",
                            scale=0, min_width=210, elem_classes="chip",
                        )

                    concept_rules_edit = gr.Textbox(
                        label="Rules — the do's",
                        placeholder=(
                            "One per line. Always-do instructions.\n"
                            "e.g. Natural daylight only.\n"
                            "     Warm cinematic grade.\n"
                            "     Subject centered in frame."
                        ),
                        lines=5, max_lines=15,
                    )
                    concept_donts_edit = gr.Textbox(
                        label="Don'ts — the never's",
                        placeholder=(
                            "One per line. Never-do instructions.\n"
                            "e.g. Never include readable text.\n"
                            "     Never use AI-avatar faces.\n"
                            "     Never harsh flash / studio lighting."
                        ),
                        lines=5, max_lines=15,
                    )
                    concept_prompt_prefix_edit = gr.Textbox(
                        label="Prompt lead — always prepended to your variant prompt",
                        placeholder=(
                            "A short phrase that leads every generation.\n"
                            "e.g. Editorial photograph of Peter Trebbien, founder of Vedio, "
                            "office setting, warm afternoon light."
                        ),
                        lines=3, max_lines=8,
                    )
                    concept_notes_edit = gr.Textbox(
                        label="Notes (private — never sent to the model)",
                        placeholder="For your own reference.",
                        lines=2, max_lines=6,
                    )

                    with gr.Row(elem_classes="concepts-actions"):
                        save_concept_btn = gr.Button(
                            "Save concept", elem_classes="cta", scale=2,
                        )
                        delete_concept_btn = gr.Button(
                            "Delete concept", scale=1, elem_classes="clear-studio-btn",
                        )
                    concept_status = gr.Markdown(elem_id="concept-status")

                    # ---- ATTACH FROM SAVED ----
                    gr.Markdown("### Attach anchors from Saved")
                    gr.Markdown(
                        "Click any thumbnail below to attach it to the editor's anchors "
                        "(click again to remove). Reflects your Saved tab.",
                        elem_classes="muted",
                    )
                    saved_picker_gallery = gr.Gallery(
                        value=[], show_label=False, columns=8, height=180,
                        object_fit="cover", allow_preview=False,
                        elem_id="saved-picker",
                    )

        # ============== CONFIRM-CLEAR MODAL ==============
        with gr.Column(visible=False, elem_classes="confirm-modal") as confirm_clear_modal:
            with gr.Column(elem_classes="confirm-dialog"):
                gr.Markdown("### Start over?", elem_classes="confirm-title")
                gr.Markdown(
                    "This will clear your prompt, reference images, and the current "
                    "preview. Your saved Rules and saved images are kept.",
                    elem_classes="confirm-body",
                )
                with gr.Row(elem_classes="confirm-actions"):
                    confirm_cancel_btn = gr.Button("Cancel", scale=0, min_width=120, elem_classes="chip")
                    confirm_clear_btn = gr.Button(
                        "Yes, start over", scale=0, min_width=160, elem_classes="cta-danger",
                    )

        loader = gr.HTML(visible=False, elem_id="loader")

        # ---------- Wiring ----------
        # References upload + remove
        upload_btn.upload(
            fn=on_upload, inputs=[upload_btn, references], outputs=[references, ref_thumbs],
            show_progress="hidden",
        )
        ref_thumbs.select(
            fn=on_remove_ref, inputs=[references], outputs=[references, ref_thumbs],
            show_progress="hidden",
        )

        # ---------- Generate wiring ----------
        # Fresh generation resets the Save button (the new image is not yet saved).
        gen_inputs = [prompt, references, aspect_ratio, resolution, num_images, last_output,
                      rules_state, active_concept, refine_anchor]
        gen_outputs = [gallery, status, loader, last_output, refine_anchor]
        (generate_btn.click(fn=run_generate, inputs=gen_inputs, outputs=gen_outputs, show_progress="hidden")
            .then(fn=lambda: gr.update(value="★ Save"), inputs=None, outputs=save_btn, show_progress="hidden"))
        (prompt.submit(fn=run_generate, inputs=gen_inputs, outputs=gen_outputs, show_progress="hidden")
            .then(fn=lambda: gr.update(value="★ Save"), inputs=None, outputs=save_btn, show_progress="hidden"))

        # ---------- Saved tab ----------
        # Clicking a thumb in browse mode loads it into Preview; in edit mode, deletes it.
        # After loading into Preview, refresh the Save button label for the newly-shown image.
        (saved_gallery.select(
            fn=on_history_select, inputs=[saved_paths, edit_saved],
            outputs=[gallery, last_output, preview_tabs, saved_paths, saved_gallery, refine_anchor],
            show_progress="hidden",
        ).then(
            fn=lambda lo: gr.update(value=_save_btn_label_for(lo)),
            inputs=[last_output], outputs=save_btn, show_progress="hidden",
        ))
        edit_saved_btn.click(
            fn=on_toggle_edit_history, inputs=[edit_saved],
            outputs=[edit_saved, edit_saved_btn],
            js=(
                "(s) => { "
                "  document.getElementById('history-tab-wrap')"
                "    ?.classList.toggle('edit-mode'); "
                "  return [s]; "
                "}"
            ),
            show_progress="hidden",
        )
        # Save button: toggle scratch->saved copy, refresh the Saved tab.
        save_btn.click(
            fn=on_toggle_save, inputs=[last_output],
            outputs=[save_btn, saved_paths, saved_gallery], show_progress="hidden",
        )

        # ---------- Refine + Clear ----------
        refine_btn.click(
            fn=on_refine, inputs=[last_output, refine_anchor],
            outputs=[references, ref_thumbs, refine_anchor, status],
            show_progress="hidden",
        )
        clear_btn.click(
            fn=lambda: gr.update(visible=True), inputs=None, outputs=confirm_clear_modal,
            show_progress="hidden",
        )
        confirm_cancel_btn.click(
            fn=lambda: gr.update(visible=False), inputs=None, outputs=confirm_clear_modal,
            show_progress="hidden",
        )
        (confirm_clear_btn.click(
            fn=on_confirm_clear_studio, inputs=None,
            outputs=[prompt, references, ref_thumbs, gallery, last_output, status,
                     confirm_clear_modal, refine_anchor],
            show_progress="hidden",
        ).then(fn=lambda: gr.update(value="★ Save"), inputs=None, outputs=save_btn, show_progress="hidden"))

        # ---------- Rules (Settings modal) ----------
        rules_save_btn.click(
            fn=on_save_rules, inputs=[rules_textbox],
            outputs=[rules_state, rules_status], show_progress="hidden",
        )
        rules_clear_btn.click(
            fn=on_clear_rules, inputs=None,
            outputs=[rules_state, rules_textbox, rules_status], show_progress="hidden",
        )

        # ---------- Concepts (chip + editor modal) ----------
        # The editor's field list, always in this exact order:
        editor_fields = [concept_name, editor_anchors_state, editor_anchors_gallery,
                         concept_rules_edit, concept_donts_edit,
                         concept_prompt_prefix_edit, concept_notes_edit]

        # Chip opens the concepts modal AND refreshes the Saved picker snapshot
        # (so anchors reflect whatever's saved right now).
        (concept_chip_btn.click(
            fn=lambda: gr.update(visible=True), inputs=None, outputs=concepts_modal,
            show_progress="hidden",
        ).then(
            fn=lambda: gr.update(value=_list_saved()), inputs=None,
            outputs=saved_picker_gallery, show_progress="hidden",
        ))
        close_concepts_btn.click(
            fn=lambda: gr.update(visible=False), inputs=None, outputs=concepts_modal,
            show_progress="hidden",
        )

        # Load an existing concept into the editor (and activate).
        load_concept_btn.click(
            fn=on_load_concept_into_editor,
            inputs=[concepts_picker],
            outputs=editor_fields + [active_concept, concept_chip_btn, concept_status],
            show_progress="hidden",
        )
        # Start a blank concept in the editor.
        new_blank_btn.click(
            fn=on_new_blank_concept, inputs=None,
            outputs=editor_fields + [concept_status],
            show_progress="hidden",
        )
        # Save the editor's fields as the concept (create OR update by name).
        save_concept_btn.click(
            fn=on_save_editor_concept,
            inputs=[concept_name, editor_anchors_state,
                    concept_rules_edit, concept_donts_edit,
                    concept_prompt_prefix_edit, concept_notes_edit],
            outputs=[active_concept, concept_chip_btn, concepts_picker,
                     concept_status, editor_anchors_state, editor_anchors_gallery],
            show_progress="hidden",
        )
        # Freestyle (deactivate).
        deactivate_concept_btn.click(
            fn=on_deactivate_concept, inputs=None,
            outputs=[active_concept, concept_chip_btn, concept_status, concepts_picker],
            show_progress="hidden",
        )
        # Delete the concept currently in the picker (or the active one if same).
        delete_concept_btn.click(
            fn=on_delete_concept,
            inputs=[concepts_picker, active_concept],
            outputs=[active_concept, concept_chip_btn, concepts_picker, concept_status],
            show_progress="hidden",
        )
        # Click a Saved thumbnail → attach/detach it from the editor.
        saved_picker_gallery.select(
            fn=on_attach_anchor_from_saved,
            inputs=[saved_paths, editor_anchors_state],
            outputs=[editor_anchors_state, editor_anchors_gallery, concept_status],
            show_progress="hidden",
        )
        # Click an editor-anchor thumbnail → remove it from the editor.
        editor_anchors_gallery.select(
            fn=on_remove_editor_anchor,
            inputs=[editor_anchors_state],
            outputs=[editor_anchors_state, editor_anchors_gallery, concept_status],
            show_progress="hidden",
        )
        # Upload one or more images directly into the editor's anchors.
        upload_editor_anchor_btn.upload(
            fn=on_upload_editor_anchor,
            inputs=[upload_editor_anchor_btn, editor_anchors_state],
            outputs=[editor_anchors_state, editor_anchors_gallery, concept_status],
            show_progress="hidden",
        )

        # ---------- Startup: load saved gallery + restore rules + restore active concept ----------
        demo.load(fn=_refresh_saved, inputs=None, outputs=[saved_paths, saved_gallery])
        demo.load(
            fn=_restore_rules_state, inputs=None,
            outputs=[rules_state, rules_textbox, rules_status],
        )
        demo.load(
            fn=_restore_active_concept, inputs=None,
            outputs=[active_concept, concept_chip_btn, concepts_picker],
        )
        # If a concept auto-restored on startup, seed the editor with its fields too.
        demo.load(
            fn=lambda: _editor_from_concept(_load_concept(_load_active_concept_slug())),
            inputs=None, outputs=editor_fields,
        )

        # ---------- Settings modal open/close ----------
        gear_btn.click(
            fn=lambda: gr.update(visible=True), inputs=None, outputs=settings_modal,
            show_progress="hidden",
        )
        close_settings_btn.click(
            fn=lambda: gr.update(visible=False), inputs=None, outputs=settings_modal,
            show_progress="hidden",
        )

    return demo


if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT", os.environ.get("PORT", "7860")))
    inbrowser = os.environ.get("NB_OPEN_BROWSER", "1") not in ("0", "false", "False")
    out_dir = core.output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    build().launch(
        server_name="127.0.0.1", server_port=port, inbrowser=inbrowser,
        theme=THEME, css=CUSTOM_CSS, js=_FORCE_LIGHT_JS, quiet=True,
        favicon_path=_FAVICON_PATH,
        # Serve generated images and the static assets dir (logo).
        allowed_paths=[str(out_dir), _ASSETS_DIR],
    )
