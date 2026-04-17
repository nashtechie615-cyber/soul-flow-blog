"""Publish a Soul Flow blog post (markdown + frontmatter) to VettedView WordPress.

Usage:
    python publish_to_wp.py <path-to-post.md>

Reads config.json from the same directory. Uploads the hero image as a media
attachment, ensures the "Fashion" category exists, renders markdown + product
grid to HTML, and publishes the post.
"""
from __future__ import annotations

import json
import sys
import os
import re
import io
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests
import frontmatter
import markdown as md_lib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 SoulFlowPublisher/1.0"
)

def load_config() -> dict:
    with (HERE / "config.json").open("r", encoding="utf-8") as f:
        return json.load(f)

def wp_api(cfg: dict, path: str) -> str:
    return cfg["wp_site"].rstrip("/") + "/wp-json/wp/v2" + path

def make_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.auth = (cfg["wp_user"], cfg["wp_app_password"])
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    return s

def auth(cfg: dict) -> tuple[str, str]:
    return (cfg["wp_user"], cfg["wp_app_password"])

def ensure_category(cfg: dict, session: requests.Session, name: str) -> int:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    r = session.get(wp_api(cfg, "/categories"), params={"slug": slug}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data:
        return data[0]["id"]
    r = session.post(
        wp_api(cfg, "/categories"),
        json={"name": name, "slug": slug},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]

def ensure_tags(cfg: dict, session: requests.Session, names: list[str]) -> list[int]:
    ids: list[int] = []
    for name in names:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not slug:
            continue
        r = session.get(wp_api(cfg, "/tags"), params={"slug": slug}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data:
            ids.append(data[0]["id"])
            continue
        r = session.post(
            wp_api(cfg, "/tags"),
            json={"name": name, "slug": slug},
            timeout=30,
        )
        r.raise_for_status()
        ids.append(r.json()["id"])
    return ids

def upload_media(cfg: dict, session: requests.Session, image_url: str, title: str) -> int | None:
    """Download an image from its URL and upload it to WP media library. Returns media ID."""
    if not image_url:
        return None
    try:
        img_resp = requests.get(image_url, timeout=60, headers={"User-Agent": USER_AGENT})
        img_resp.raise_for_status()
    except Exception as e:
        print(f"  ! Failed to download image: {e}", file=sys.stderr)
        return None

    content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    filename = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:80] + ext

    r = session.post(
        wp_api(cfg, "/media"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        },
        data=img_resp.content,
        timeout=120,
    )
    if r.status_code >= 400:
        print(f"  ! Media upload failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return None
    return r.json()["id"]

def render_products_html(products: list[dict]) -> str:
    if not products:
        return ""
    cards: list[str] = []
    for p in products:
        name = p.get("name", "")
        url = p.get("url", "#")
        image = p.get("image", "")
        price = p.get("price", "")
        price_html = f'<p style="color:#8a5f47;font-size:14px;margin:4px 0 0;">{price}</p>' if price else ""
        cards.append(
            f'<a href="{url}" target="_blank" rel="noopener" '
            f'style="display:block;text-decoration:none;color:inherit;">'
            f'<img src="{image}" alt="{name}" loading="lazy" '
            f'style="width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:12px;background:#f1e9df;" />'
            f'<h4 style="font-family:\'Libre Bodoni\',Georgia,serif;font-size:17px;margin:12px 0 0;'
            f'color:#2a2420;line-height:1.35;">{name}</h4>'
            f'{price_html}'
            f'</a>'
        )
    return (
        '<hr />'
        '<section style="margin-top:40px;">'
        '<div style="text-align:center;margin-bottom:24px;">'
        '<p style="text-transform:uppercase;letter-spacing:0.28em;color:#b28267;font-size:12px;margin:0;">Soul Flow Apparel</p>'
        '<h3 style="font-family:\'Libre Bodoni\',Georgia,serif;font-size:30px;color:#2a2420;margin:10px 0 6px;">Shop the Story</h3>'
        '<p style="color:#5b4f47;margin:0;">Hand-picked pieces from Soul Flow Apparel to bring the look home.</p>'
        '</div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px;">'
        + "".join(cards) +
        '</div>'
        '<p style="text-align:center;margin-top:28px;">'
        '<a href="https://soulflowshop.com" target="_blank" rel="noopener" '
        'style="display:inline-block;background:#2a2420;color:#faf6f1;padding:12px 28px;border-radius:999px;'
        'text-decoration:none;font-size:13px;letter-spacing:0.2em;text-transform:uppercase;">'
        'Shop All at Soul Flow Apparel</a></p>'
        '</section>'
    )

def render_post_html(post: frontmatter.Post) -> str:
    body_html = md_lib.markdown(post.content, extensions=["extra", "sane_lists"])
    description = (post.get("description") or "").strip()
    lead = (
        f'<p style="font-size:19px;color:#5b4f47;font-style:italic;margin:0 0 28px;">'
        f'{description}</p>'
        if description else ""
    )
    products_html = render_products_html(post.get("products") or [])
    return lead + body_html + products_html

def find_existing_post(cfg: dict, session: requests.Session, title: str) -> dict | None:
    """Look up an existing post by exact title match (across all statuses).

    Idempotency guard: if a post with this title already exists, we refuse to
    create a duplicate. Returns the post dict, or None if no match found.
    """
    r = session.get(
        wp_api(cfg, "/posts"),
        params={
            "search": title,
            "per_page": 20,
            "status": "publish,draft,pending,private,future",
        },
        timeout=30,
    )
    if r.status_code >= 400:
        return None
    for p in r.json():
        rendered = (p.get("title") or {}).get("rendered", "").strip()
        # WP renders HTML entities; strip a few common ones for comparison.
        rendered = (
            rendered.replace("&#8217;", "'").replace("&#8216;", "'")
                    .replace("&#8220;", '"').replace("&#8221;", '"')
                    .replace("&amp;", "&")
        )
        if rendered == title.strip():
            return p
    return None


def publish(md_path: Path) -> dict:
    cfg = load_config()
    session = make_session(cfg)
    post = frontmatter.load(md_path)
    title = post["title"]
    description = post.get("description", "")
    hero_image = post.get("heroImage")
    category_name = post.get("category") or cfg["wp_category_name"]
    tags = post.get("tags") or []

    print(f"-> Publishing: {title}")

    existing = find_existing_post(cfg, session, title)
    if existing:
        print(
            f"   SKIP: post already exists on WP (id={existing['id']}, "
            f"status={existing.get('status')}, link={existing.get('link')})"
        )
        return existing

    category_id = ensure_category(cfg, session, category_name)
    tag_ids = ensure_tags(cfg, session, tags)
    print(f"   category={category_name} (id={category_id}), tags={tag_ids}")

    media_id = upload_media(cfg, session, hero_image, title) if hero_image else None
    if media_id:
        print(f"   featured_media id={media_id}")

    html = render_post_html(post)

    payload: dict[str, Any] = {
        "title": title,
        "excerpt": description,
        "content": html,
        "status": "publish",
        "categories": [category_id],
        "tags": tag_ids,
    }
    if media_id:
        payload["featured_media"] = media_id

    r = session.post(wp_api(cfg, "/posts"), json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    print(f"   OK Published: {data['link']}")
    return data

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python publish_to_wp.py <path-to-post.md>", file=sys.stderr)
        return 2
    md_path = Path(sys.argv[1]).resolve()
    if not md_path.exists():
        print(f"Post not found: {md_path}", file=sys.stderr)
        return 1
    try:
        publish(md_path)
    except requests.HTTPError as e:
        body = e.response.text[:500] if e.response is not None else ""
        print(f"HTTP error: {e}\nBody: {body}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
