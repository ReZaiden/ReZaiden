"""
Telegram Channel Card Generator for GitHub Profile README.

Workflow (single script, no intermediate files):
  1. Fetch channel RSS from RSSHub (with fallback instances).
  2. Parse both channel-level info (name, avatar) and the latest post
     (text, image, link, date).
  3. Download images and embed them as base64 data-URIs so GitHub's
     Content Security Policy does not block them inside SVGs.
  4. Render a premium SVG card and write it to output/telegram-card.svg.
  5. Update the <!-- TELEGRAM_START / END --> block in README.md.

Card layout (900 x 250 px):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  [Channel Avatar]  Channel Name          [Telegram logo]  @handle        │
  │  ──────────────────────────────────────────────────────────────────────  │
  │  📢 Latest Post                                       [Post Thumbnail]   │
  │  Post title / text (wrapped, max 3 lines)             [              ]   │
  │  2026-03-20                                           View Post →        │
  └──────────────────────────────────────────────────────────────────────────┘
"""

import base64
import html
import os
import re
import textwrap
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
import sys

# Force UTF-8 output so Persian / Unicode channel names don't crash on Windows terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Configuration ─────────────────────────────────────────────────────────────
CHANNEL = "ReZaidenCH"

RSS_INSTANCES = [
    "https://rsshub.ktachibana.party",
    "https://rsshub.app",
]
RSS_URL_TEMPLATE = "{instance}/telegram/channel/{channel}"

OUTPUT_SVG = "output/telegram-card.svg"
README_PATH = "README.md"

START_MARKER = "<!-- TELEGRAM_START -->"
END_MARKER = "<!-- TELEGRAM_END -->"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ReZaiden-Profile-Bot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


# ── Network helpers ────────────────────────────────────────────────────────────

def fetch_rss() -> str:
    """Try each RSSHub instance in order; return raw XML on first success."""
    last_error: Exception | None = None
    for instance in RSS_INSTANCES:
        url = RSS_URL_TEMPLATE.format(instance=instance, channel=CHANNEL)
        try:
            print(f"Trying RSS: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            print(f"[OK] {url}")
            return resp.text
        except Exception as exc:
            print(f"[WARN] {url} failed: {exc}")
            last_error = exc
    raise RuntimeError(f"All RSS instances failed. Last error: {last_error}")


def fetch_image_b64(url: str, referer: str = "https://t.me/") -> str | None:
    """
    Download the image at *url* and return a base64 data-URI string.
    Returns None on any network or decoding error.
    """
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": referer},
            timeout=15,
        )
        resp.raise_for_status()
        mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        encoded = base64.b64encode(resp.content).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception as exc:
        print(f"[WARN] Could not fetch image ({exc})")
        return None


# ── RSS Parsing ────────────────────────────────────────────────────────────────

def _first_img_from_description(description_text: str) -> str | None:
    """Extract the first non-emoji <img src> from an HTML description string."""
    decoded = html.unescape(description_text)
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', decoded, re.IGNORECASE):
        candidate = m.group(1)
        if not candidate.startswith("data:"):
            return candidate
    return None


def parse_feed(xml_text: str) -> dict:
    """
    Parse the RSS feed and return a single dict containing:
      channel: { title, avatar_url, link }
      post:    { text, link, img_url, date, post_number }
    """
    root = ET.fromstring(xml_text)
    ch = root.find("channel")
    ns = {"media": "http://search.yahoo.com/mrss/"}

    # ── Channel-level info ────────────────────────────────────────────────────
    ch_title_el = ch.find("title")
    channel_title = (ch_title_el.text or CHANNEL).strip() if ch_title_el is not None else CHANNEL
    # Strip " - Telegram Channel" suffix if present
    channel_title = re.sub(r"\s*-\s*Telegram Channel$", "", channel_title).strip()

    ch_link_el = ch.find("link")
    channel_link = (ch_link_el.text or f"https://t.me/{CHANNEL}").strip() if ch_link_el is not None else f"https://t.me/{CHANNEL}"

    # Channel avatar is inside <image><url>...</url></image>
    avatar_url: str | None = None
    img_el = ch.find("image")
    if img_el is not None:
        url_el = img_el.find("url")
        if url_el is not None and url_el.text:
            avatar_url = url_el.text.strip()

    # ── Latest post ───────────────────────────────────────────────────────────
    items = ch.findall("item")
    if not items:
        raise ValueError("RSS feed contains no items")

    item = items[0]  # first = newest in RSS

    title_el = item.find("title")
    text = (title_el.text or "Media Post").strip() if title_el is not None else "Media Post"
    # Remove leading emoji like "🖼 " that RSSHub adds
    text = re.sub(r"^[\U00010000-\U0010ffff\U00002600-\U000027ff]\s*", "", text).strip()

    link_el = item.find("link")
    link = (link_el.text or f"https://t.me/{CHANNEL}").strip() if link_el is not None else f"https://t.me/{CHANNEL}"

    # Derive approximate post number from URL path (e.g. /306)
    post_number: int | None = None
    m = re.search(r"/(\d+)$", link)
    if m:
        post_number = int(m.group(1))

    # Post image: enclosure → media:content → description HTML
    img_url: str | None = None
    enclosure = item.find("enclosure")
    if enclosure is not None and enclosure.get("type", "").startswith("image"):
        img_url = enclosure.get("url")
    if not img_url:
        for tag in ("media:content", "media:thumbnail"):
            el = item.find(tag, ns)
            if el is not None:
                img_url = el.get("url")
                break
    if not img_url:
        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            img_url = _first_img_from_description(desc_el.text)

    # Post date
    date_str = ""
    pub_date_el = item.find("pubDate")
    if pub_date_el is not None and pub_date_el.text:
        try:
            dt = parsedate_to_datetime(pub_date_el.text.strip())
            date_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date_el.text.strip()[:10]

    return {
        "channel": {
            "title": channel_title,
            "avatar_url": avatar_url,
            "link": channel_link,
        },
        "post": {
            "text": text,
            "link": link,
            "img_url": img_url,
            "date": date_str,
            "post_number": post_number,
        },
    }


# ── SVG Card Builder ───────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 48, max_lines: int = 3) -> list[str]:
    """Wrap text into at most max_lines lines of width chars each."""
    lines = textwrap.wrap(text, width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def _xml_safe(s: str) -> str:
    """Escape XML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_svg(data: dict) -> str:
    """Build and return the SVG markup for the Telegram channel card."""
    ch = data["channel"]
    post = data["post"]

    W, H = 900, 270
    PAD = 20

    # ── Fetch images ──────────────────────────────────────────────────────────
    print("Fetching channel avatar...")
    avatar_b64 = fetch_image_b64(ch["avatar_url"]) if ch.get("avatar_url") else None

    print("Fetching post thumbnail...")
    post_img_b64 = fetch_image_b64(post["img_url"]) if post.get("img_url") else None

    # ── Channel header section ────────────────────────────────────────────────
    avatar_size = 70
    avatar_x, avatar_y = PAD, PAD

    if avatar_b64:
        avatar_element = f"""\
  <clipPath id="avatarClip">
    <circle cx="{avatar_x + avatar_size // 2}" cy="{avatar_y + avatar_size // 2}" r="{avatar_size // 2}"/>
  </clipPath>
  <circle cx="{avatar_x + avatar_size // 2}" cy="{avatar_y + avatar_size // 2}" r="{avatar_size // 2}" fill="#1e2433"/>
  <image href="{avatar_b64}" x="{avatar_x}" y="{avatar_y}" width="{avatar_size}" height="{avatar_size}" clip-path="url(#avatarClip)" preserveAspectRatio="xMidYMid slice"/>"""
    else:
        # Telegram plane placeholder
        avatar_element = f"""\
  <circle cx="{avatar_x + avatar_size // 2}" cy="{avatar_y + avatar_size // 2}" r="{avatar_size // 2}" fill="#229ED9"/>
  <text x="{avatar_x + avatar_size // 2}" y="{avatar_y + avatar_size // 2 + 14}" fill="white" font-size="36" font-family="Arial" text-anchor="middle">✈</text>'''"""

    ch_name_x = avatar_x + avatar_size + 16
    ch_name_y = avatar_y + 28
    ch_handle_y = ch_name_y + 22

    ch_name_safe = _xml_safe(ch["title"])

    # ── Divider ───────────────────────────────────────────────────────────────
    div_y = avatar_y + avatar_size + 14

    # ── Post thumbnail (left side) ────────────────────────────────────────────
    thumb_size = 130
    thumb_x = PAD
    thumb_y = div_y + 15

    if post_img_b64:
        thumb_element = f"""\
  <clipPath id="thumbClip">
    <rect x="{thumb_x}" y="{thumb_y}" width="{thumb_size}" height="{thumb_size}" rx="12"/>
  </clipPath>
  <rect x="{thumb_x}" y="{thumb_y}" width="{thumb_size}" height="{thumb_size}" rx="12" fill="#1e2433"/>
  <image href="{post_img_b64}" x="{thumb_x}" y="{thumb_y}" width="{thumb_size}" height="{thumb_size}" clip-path="url(#thumbClip)" preserveAspectRatio="xMidYMid slice"/>"""
    else:
        thumb_element = f"""\
  <rect x="{thumb_x}" y="{thumb_y}" width="{thumb_size}" height="{thumb_size}" rx="12" fill="#1e2433"/>
  <text x="{thumb_x + thumb_size // 2}" y="{thumb_y + thumb_size // 2 + 10}" fill="#444" font-size="36" font-family="Arial" text-anchor="middle">📷</text>"""

    # ── Post text (right side) ────────────────────────────────────────────
    text_x = thumb_x + thumb_size + 20
    char_width = 72  # chars per line (with wider space on right)

    label_y = div_y + 28
    text_lines = _wrap(post["text"], width=char_width, max_lines=3)

    text_elements = ""
    for i, line in enumerate(text_lines):
        y = label_y + 26 + i * 24
        text_elements += f'  <text x="{text_x}" y="{y}" fill="#c9d1d9" font-size="14" font-family="Arial, sans-serif">{_xml_safe(line)}</text>\n'

    date_y = H - PAD - 6
    view_y = H - PAD - 6

    # ── Telegram logo (SVG path) ──────────────────────────────────────────────
    tg_logo_x = W - PAD - 24
    tg_logo_y = PAD + 4

    svg = f"""\
<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <!-- Card gradient background -->
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#0a0f1a"/>
    </linearGradient>
  </defs>

  <!-- Card shell -->
  <rect width="{W}" height="{H}" rx="18" fill="url(#bg)" stroke="#00FFAA" stroke-width="1.2"/>

  <!-- Subtle inner glow at top -->
  <rect x="1" y="1" width="{W - 2}" height="80" rx="17" fill="#00FFAA" fill-opacity="0.025"/>

  <!-- ── Channel header ── -->
{avatar_element}

  <!-- Channel name -->
  <text x="{ch_name_x}" y="{ch_name_y}" fill="white" font-size="18" font-family="Arial, sans-serif" font-weight="bold">{ch_name_safe}</text>

  <!-- @handle -->
  <text x="{ch_name_x}" y="{ch_handle_y}" fill="#8b949e" font-size="13" font-family="Arial, sans-serif">@{CHANNEL}</text>

  <!-- Telegram icon (top-right) -->
  <g transform="translate({tg_logo_x},{tg_logo_y})">
    <circle cx="11" cy="11" r="11" fill="#229ED9" fill-opacity="0.9"/>
    <text x="11" y="16" fill="white" font-size="13" font-family="Arial" text-anchor="middle">✈</text>
  </g>

  <!-- Divider -->
  <line x1="{PAD}" y1="{div_y}" x2="{W - PAD}" y2="{div_y}" stroke="#21262d" stroke-width="1"/>

  <!-- ── Latest post section ── -->

  <!-- "Latest Post" label -->
  <text x="{text_x}" y="{label_y}" fill="#00FFAA" font-size="12" font-family="Arial, sans-serif" font-weight="bold" letter-spacing="1">LATEST POST</text>

  <!-- Post body text -->
{text_elements}
  <!-- Date -->
  <text x="{text_x}" y="{date_y}" fill="#8b949e" font-size="12" font-family="Arial, sans-serif">{post["date"]}</text>

  <!-- "View Post →" link-style text -->
  <text x="{W - PAD - 2}" y="{view_y}" fill="#00FFAA" font-size="13" font-family="Arial, sans-serif" text-anchor="end">View Post →</text>

  <!-- Post thumbnail -->
{thumb_element}
</svg>
"""
    return svg


# ── README updater ─────────────────────────────────────────────────────────────

def update_readme(post_data: dict) -> None:
    """Replace the Telegram block between START_MARKER and END_MARKER in README.md."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    post = post_data["post"]
    title = post["text"][:120] + ("..." if len(post["text"]) > 120 else "")
    link = post["link"]
    date = post["date"]

    new_block = (
        f"{START_MARKER}\n"
        f"### 📢 Latest from Telegram\n\n"
        f"[![Telegram Card](https://raw.githubusercontent.com/ReZaiden/ReZaiden/main/output/telegram-card.svg)](https://t.me/{CHANNEL})\n\n"
        f"**[{title}]({link})**  \n"
        f"_{date}_\n\n"
        f"[View Channel →](https://t.me/{CHANNEL})\n"
        f"{END_MARKER}"
    )

    if START_MARKER in content and END_MARKER in content:
        new_content = re.sub(
            re.escape(START_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER),
            new_block,
            content,
        )
    else:
        content = re.sub(
            r"### 📢 Latest from Telegram[\s\S]*?(?=\n---|\Z)",
            "",
            content,
        ).rstrip()
        new_content = content + "\n\n---\n\n" + new_block + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("[OK] README.md updated.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Fetch RSS
    xml_text = fetch_rss()

    # 2. Parse channel + latest post
    data = parse_feed(xml_text)
    post = data["post"]
    ch = data["channel"]
    print(
        f"[OK] Channel: {ch['title']} | "
        f"Post: {post['link']} | "
        f"Date: {post['date']} | "
        f"Has img: {'yes' if post.get('img_url') else 'no'}"
    )

    # 3. Build and save SVG card
    svg = build_svg(data)
    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[OK] SVG card written to {OUTPUT_SVG}")

    # 4. Update README
    update_readme(data)


if __name__ == "__main__":
    main()
