"""Soul Flow Apparel hourly post generator.

Orchestration:
  1. Fetch a selection of live products from soulflowshop.com.
  2. Collect titles of recent blog posts (to avoid topic repeats).
  3. Render a prompt and invoke Claude Code CLI headlessly to:
     - write a new .md file into src/content/blog/ with proper frontmatter
     - invoke publish_to_wp.py to publish the post to VettedView WordPress
  4. Verify the post file was created and the WordPress URL exists in the log.
  5. Log everything.

Invoked by scripts/run_hourly.bat, which is registered as a Windows Task
Scheduler entry.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 SoulFlowBot/1.0"
)


def load_config() -> dict:
    with (HERE / "config.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_products(cfg: dict, limit: int = 40) -> list[dict]:
    """Pull a random-ish selection of live products from soulflowshop.com."""
    shop = cfg["shop_url"].rstrip("/")
    sel: list[dict] = []
    for page in range(1, 6):
        try:
            r = requests.get(
                f"{shop}/products.json",
                params={"limit": 50, "page": page},
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            r.raise_for_status()
            page_products = r.json().get("products", [])
        except Exception as e:
            print(f"!! Failed to fetch products page {page}: {e}")
            break
        if not page_products:
            break
        for p in page_products:
            img = ""
            if p.get("images"):
                img = p["images"][0].get("src", "")
            price = ""
            if p.get("variants"):
                price = f"${p['variants'][0].get('price', '')} USD"
            sel.append({
                "name": p["title"],
                "url": f"{shop}/products/{p['handle']}",
                "image": img,
                "price": price,
                "product_type": p.get("product_type", ""),
            })
        if len(page_products) < 50:
            break
    random.shuffle(sel)
    return sel[:limit]


def recent_titles(cfg: dict, count: int = 20) -> list[str]:
    blog_dir = Path(cfg["blog_content_dir"])
    titles: list[tuple[float, str]] = []
    for f in blog_dir.glob("*.md"):
        try:
            mtime = f.stat().st_mtime
            # Cheap title parse: look for 'title:' in frontmatter.
            head = f.read_text(encoding="utf-8")[:1000]
            m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', head, flags=re.MULTILINE)
            if m:
                titles.append((mtime, m.group(1).strip()))
        except Exception:
            continue
    titles.sort(reverse=True)
    return [t for _, t in titles[:count]]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_prompt(cfg: dict, products: list[dict], recent: list[str], target_path: Path, today_iso: str) -> str:
    products_json = json.dumps(products, indent=2)
    recent_block = "\n".join(f"- {t}" for t in recent) if recent else "(none yet)"

    return f"""You are generating the NEXT post for Soul Flow Apparel's automated fashion blog.

# Brand & goal
- Brand name in copy: "Soul Flow Apparel" (never "Soul Flow Shop").
- Main shop: https://soulflowshop.com
- Goal of every post: drive traffic to https://soulflowshop.com with a warm, elegant, feminine, boho voice that women love to read.

# Today
{today_iso}

# Recent post titles (DO NOT repeat angle or topic):
{recent_block}

# Available products from the live shop (pick 4 to feature at the bottom, and link to the product URLs directly when you mention them specifically):
```json
{products_json}
```

# Your task — do exactly these two steps and NOTHING else:

1. Pick a fresh, traffic-driving topic from women's fashion, boho style, fashion trends, seasonal styling, festival looks, jewelry, kimonos, accessories, etc. Draw topic ideas loosely from Vogue, The Zoe Report, Elle, Business of Fashion, College Fashion, Fashion Magazine — but write fully original copy. Do NOT repeat any angle from the "Recent post titles" list above.

2. Write a single markdown file at exactly this path:
   {target_path.as_posix()}

   The frontmatter MUST match this schema (YAML between --- lines):
   - title: string
   - description: 1-2 sentence hook (string, <=180 chars)
   - pubDate: ISO-8601 datetime (use {today_iso})
   - category: "Fashion"
   - tags: array of 3-6 lowercase strings
   - heroImage: one of the product image URLs from the list above (full https URL)
   - products: an array of exactly 4 product objects chosen from the list above, each with fields: name, url, image, price

   The body (after the closing ---) must be:
   - 600+ words of real, elegant, conversational prose (not listicle fluff).
   - Styled for women — warm, aspirational, boho-feminine.
   - Woven with 3-8 in-body markdown links. When mentioning a specific product from the list above, link to its real product URL. Otherwise link to https://soulflowshop.com or a relevant collection (e.g. https://soulflowshop.com/collections/kimonos).
   - Ends with a clear CTA to shop Soul Flow Apparel.

# STRICT CONSTRAINTS — read carefully:

- DO NOT publish this post. DO NOT call any publisher script. DO NOT make any HTTP requests. DO NOT touch WordPress or vettedview.com. The orchestrator that called you will publish the file; your only job is to write the .md file.
- DO NOT create, modify, or delete any file other than the single target markdown file above.
- DO NOT run curl, wget, python, node, or any other command. Only use your file-writing tool to create the target .md file.
- On the final line of your output, print exactly:
   DONE: {target_path.as_posix()}

That is all. Write the file. Print DONE. Stop."""


def run_claude(prompt: str, log_path: Path) -> int:
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
    ]
    print(f"   invoking: claude -p <prompt {len(prompt)} chars>")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write("\n=== CLAUDE INVOCATION ===\n")
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=600,
        )
        text = proc.stdout.decode("utf-8", errors="replace")
        logf.write(text)
        logf.write(f"\n=== EXIT CODE: {proc.returncode} ===\n")
    print(f"   claude exited {proc.returncode} (see log: {log_path})")
    return proc.returncode


def main() -> int:
    cfg = load_config()
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y-%m-%d-%H%M%S")

    log_dir = HERE / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{stamp}.log"
    latest = log_dir / "latest.log"

    def log(msg: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            latest.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

    log(f"=== Soul Flow hourly run: {stamp} ===")

    log("Fetching live products from soulflowshop.com ...")
    products = fetch_products(cfg, limit=40)
    log(f"  got {len(products)} products")
    if len(products) < 4:
        log("!! Not enough products fetched; aborting.")
        return 1

    recent = recent_titles(cfg, count=20)
    log(f"Recent titles context: {len(recent)} posts")

    blog_dir = Path(cfg["blog_content_dir"])
    target = blog_dir / f"{stamp}-post.md"
    log(f"Target file: {target}")

    prompt = build_prompt(cfg, products, recent, target, now.isoformat(timespec="seconds"))

    exit_code = run_claude(prompt, log_path)
    if exit_code != 0:
        log(f"!! Claude exited with {exit_code}; aborting.")
        return exit_code

    # Give FS a moment if needed
    for _ in range(5):
        if target.exists():
            break
        time.sleep(1)

    if not target.exists():
        log(f"!! Expected file was not created: {target}")
        return 1

    size = target.stat().st_size
    log(f"OK file created: {target.name} ({size} bytes)")

    # Single publishing path — we own this exclusively. Claude is instructed not to publish.
    log("Running WordPress publisher...")
    publisher_log = log_dir / f"publish-{stamp}.log"
    with publisher_log.open("a", encoding="utf-8") as pf:
        proc = subprocess.run(
            ["python", str(HERE / "publish_to_wp.py"), str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
        pf.write(proc.stdout.decode("utf-8", errors="replace"))
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        log(f"  | {line}")
    log(f"  publisher exit code: {proc.returncode}")
    if proc.returncode != 0:
        return proc.returncode

    log(f"=== Soul Flow hourly run complete: {stamp} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
