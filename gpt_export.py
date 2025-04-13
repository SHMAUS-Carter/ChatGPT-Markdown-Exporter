# gpt_export.py
# Version: 2025.03.30
# Description: Export ChatGPT conversation JSON to Obsidian-compatible Markdown with YAML safety and media logging.
# (Full script goes here...)
import re
import json, os, hashlib, time
from datetime import datetime

# --- CONFIGURATION ---
INPUT_JSON = "conversations.json"
OUTPUT_FOLDER = "gpt_export_markdown"
CONVERSATION_FOLDER = "conversations"
MEDIA_LOG = "media_references.txt"
GENERATE_TOC = True
INCLUDE_SYSTEM_MESSAGES = True
MAX_MESSAGES_PER_FILE = 100
QUIET = False
MANUAL_EDIT_KEY = "manual_edit"
# ----------------------

CONV_PATH = os.path.join(OUTPUT_FOLDER, CONVERSATION_FOLDER)
os.makedirs(CONV_PATH, exist_ok=True)
media_log_path = os.path.join(OUTPUT_FOLDER, MEDIA_LOG)
media_log_entries = []
total_threads = 0
total_messages = 0
start_time = time.time()

def log(msg):
    if not QUIET:
        print(msg)

def slugify(text):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text.strip().lower())

def format_ts(ts):
    try:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        elif isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        else:
            return "unknown"
    except:
        return "unknown"

def make_slug_or_hash(title, ts, idx):
    return slugify(title)[:50] if title else hashlib.sha1(f"{ts}_{idx}".encode()).hexdigest()[:10]

def sanitize_and_log_images(content, title, idx):
    image_urls = re.findall(r'(https://files\.oaiusercontent\.com/[\w\-/]+\.png)', content)
    for count, url in enumerate(image_urls, 1):
        base_name = f"{slugify(title) or 'image'}_{idx:03}_{count:02}.png"
        content = content.replace(url, f"media/{base_name}")
        content += f"\n\n![image](media/{base_name})"
        media_log_entries.append(f"{base_name} — from '{title}'")
    return content

def process_parts(parts, title, idx):
    results = []
    for count, part in enumerate(parts, 1):
        if isinstance(part, str):
            results.append(part)
        elif isinstance(part, dict):
            if part.get("content_type") == "image_asset_pointer":
                asset = part.get("asset_pointer", "")
                if asset.startswith("file-service://file-"):
                    asset_id = asset.split("file-")[-1]
                    name = f"file-{asset_id}.png"
                    media_log_entries.append(f"{name} — from '{title}'")
                    results.append(f"![image](media/{name})")
            elif "text" in part:
                results.append(part["text"])
    return "\n".join(results).strip()

def should_skip_file(filepath):
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            header_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL | re.MULTILINE)
            if header_match and MANUAL_EDIT_KEY in header_match.group(1):
                return MANUAL_EDIT_KEY + ": true" in header_match.group(1)
    except:
        pass
    return False

def write_single_convo(slug, title, timestamp, messages, idx):
    filename = f"{slug}.md"
    filepath = os.path.join(CONV_PATH, filename)
    if should_skip_file(filepath):
        log(f"Skipping manual edit: {filename}")
        return [f"- {title} ({timestamp}) — *manual edit skipped*"]

    with open(filepath, "w", encoding="utf-8") as f:
        # YAML frontmatter
        f.write("---\n")
        f.write(f'title: "{title}"\n')
        f.write(f'created: "{timestamp.split()[0]}"\n')
        f.write("tags:\n  - ai\n")
        f.write('source: "AI"\n')
        f.write("---\n\n")

        f.write(f"# {title}\n")
        f.write(f"_Started: {timestamp}_\n\n")
        for role, content in messages:
            content = sanitize_and_log_images(content, title, idx)
            f.write(f"**[{role}]**:\n{content}\n\n---\n\n")
    return [f"- [{title} ({timestamp})]({CONVERSATION_FOLDER}/{filename})"]

def write_chunked_convo(slug, title, timestamp, messages, idx):
    subfolder = os.path.join(CONV_PATH, slug)
    os.makedirs(subfolder, exist_ok=True)
    parts = [messages[i:i + MAX_MESSAGES_PER_FILE] for i in range(0, len(messages), MAX_MESSAGES_PER_FILE)]
    toc_entries = []

    for i, part in enumerate(parts):
        partname = f"{slug}_part_{i+1}_of_{len(parts)}.md"
        filepath = os.path.join(subfolder, partname)
        if should_skip_file(filepath):
            log(f"Skipping manual edit: {partname}")
            toc_entries.append(f"  - [Part {i+1} of {len(parts)}] — *manual edit skipped*")
            continue

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f'title: "{title} (Part {i+1})"\n')
            f.write(f'created: "{timestamp.split()[0]}"\n')
            f.write("tags:\n  - ai\n")
            f.write('source: "AI"\n')
            f.write("---\n\n")

            f.write(f"# {title} (Part {i+1} of {len(parts)})\n")
            f.write(f"_Started: {timestamp}_\n\n")
            for role, content in part:
                content = sanitize_and_log_images(content, title, idx)
                f.write(f"**[{role}]**:\n{content}\n\n")
        toc_entries.append(f"  - [Part {i+1} of {len(parts)}]({CONVERSATION_FOLDER}/{slug}/{partname})")

    return toc_entries

# --- LOAD JSON AND DETECT FORMAT ---
with open(INPUT_JSON, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

if isinstance(raw_data, dict) and "conversations" in raw_data:
    conversations = raw_data["conversations"]
elif isinstance(raw_data, list):
    conversations = raw_data
else:
    raise ValueError("Unrecognized format in conversations.json")

toc = ["# ChatGPT Conversation Index\n"]

for idx, thread in enumerate(conversations):
    title = thread.get("title", "Untitled")
    create_time = thread.get("create_time", "")
    timestamp = format_ts(create_time)
    slug = make_slug_or_hash(title, timestamp, idx)
    log(f"Processing thread {idx + 1}/{len(conversations)}: {title}")

    messages = []
    for node in thread.get("mapping", {}).values():
        msg = node.get("message")
        if not msg:
            continue
        role = msg.get("author", {}).get("role", "unknown")
        if role == "system" and not INCLUDE_SYSTEM_MESSAGES:
            continue
        parts = msg.get("content", {}).get("parts", [])
        content = process_parts(parts, title, idx)
        if content:
            messages.append((role, content))
            total_messages += 1

    total_threads += 1
    if len(messages) > MAX_MESSAGES_PER_FILE:
        toc.append(f"- {title} ({timestamp})")
        toc.extend(write_chunked_convo(slug, title, timestamp, messages, idx))
    else:
        toc.extend(write_single_convo(slug, title, timestamp, messages, idx))

if GENERATE_TOC:
    with open(os.path.join(OUTPUT_FOLDER, "index.md"), "w", encoding="utf-8") as toc_f:
        toc_f.write("\n".join(toc))

if media_log_entries:
    with open(media_log_path, "w", encoding="utf-8") as log_f:
        log_f.write("\n".join(media_log_entries))

# --- FINAL SUMMARY ---
elapsed = time.time() - start_time

def get_dir_size_mb(path):
    size = 0
    for root, _, files in os.walk(path):
        for file in files:
            size += os.path.getsize(os.path.join(root, file))
    return size / (1024 * 1024)

original_size = os.path.getsize(INPUT_JSON) / (1024 * 1024)
exported_size = get_dir_size_mb(CONV_PATH)

print(f"""
Conversion complete.
Threads processed: {total_threads}
Messages exported: {total_messages}
Markdown size: {exported_size:.1f} MB
Original JSON size: {original_size:.1f} MB
Elapsed time: {elapsed:.1f} seconds
""".strip())
