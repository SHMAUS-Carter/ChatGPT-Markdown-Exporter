# gpt_export_mod_v2.py
# Version: 2026.03.12
# Description: Export ChatGPT conversation JSON to Obsidian-compatible Markdown with YAML safety and media logging.

import re
import json
import os
import hashlib
import time
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION ---
INPUT_PATH = r"new_format\run"   # can be a single json file OR a folder containing conversations-*.json
OUTPUT_FOLDER = "gpt_export_markdown_new_format"
CONVERSATION_FOLDER = "conversations"
MEDIA_LOG = "media_references.txt"
GENERATE_TOC = True
INCLUDE_SYSTEM_MESSAGES = True
INCLUDE_HIDDEN_MESSAGES = False
SKIP_IN_PROGRESS_MESSAGES = True
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
loaded_json_files = []


def log(msg):
    if not QUIET:
        print(msg)


def slugify(text):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(text).strip().lower())


def format_ts(ts):
    try:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        elif isinstance(ts, str) and ts:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        else:
            return "unknown"
    except Exception:
        return "unknown"


def make_slug_or_hash(title, ts, idx):
    base = slugify(title)[:50]
    if base and base.strip("_"):
        return base
    return hashlib.sha1(f"{ts}_{idx}".encode()).hexdigest()[:10]


def sanitize_yaml_string(text):
    text = str(text or "").replace('"', '\\"')
    return text.replace("\n", " ").strip()


def sanitize_and_log_images(content, title, idx):
    image_urls = re.findall(r'(https://files\.oaiusercontent\.com/[\w\-/.]+\.png)', content)
    for count, url in enumerate(image_urls, 1):
        base_name = f"{slugify(title) or 'image'}_{idx:03}_{count:02}.png"
        content = content.replace(url, f"media/{base_name}")
        content += f"\n\n![image](media/{base_name})"
        media_log_entries.append(f"{base_name} — from '{title}'")
    return content


def process_parts(parts, title, idx):
    results = []
    for count, part in enumerate(parts or [], 1):
        if isinstance(part, str):
            if part.strip():
                results.append(part)
        elif isinstance(part, dict):
            ctype = part.get("content_type")
            if ctype == "image_asset_pointer":
                asset = part.get("asset_pointer", "")
                if asset.startswith("file-service://file-"):
                    asset_id = asset.split("file-")[-1]
                    name = f"file-{asset_id}.png"
                    media_log_entries.append(f"{name} — from '{title}'")
                    results.append(f"![image](media/{name})")
            elif "text" in part and isinstance(part.get("text"), str):
                text = part["text"].strip()
                if text:
                    results.append(text)
            elif "parts" in part and isinstance(part.get("parts"), list):
                nested = process_parts(part.get("parts"), title, idx)
                if nested:
                    results.append(nested)
    return "\n".join(results).strip()


def extract_content(message, title, idx):
    content_obj = message.get("content") or {}

    # Standard text path
    parts = content_obj.get("parts")
    if isinstance(parts, list):
        text = process_parts(parts, title, idx)
        if text:
            return text

    # Fallbacks for some newer/odd payloads
    if isinstance(content_obj.get("text"), str) and content_obj.get("text").strip():
        return content_obj["text"].strip()

    if isinstance(content_obj.get("result"), str) and content_obj.get("result").strip():
        return content_obj["result"].strip()

    if isinstance(content_obj.get("content"), str) and content_obj.get("content").strip():
        return content_obj["content"].strip()

    return ""


def should_skip_file(filepath):
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            header_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL | re.MULTILINE)
            if header_match and MANUAL_EDIT_KEY in header_match.group(1):
                return MANUAL_EDIT_KEY + ": true" in header_match.group(1)
    except Exception:
        pass
    return False


def write_frontmatter(f, title, timestamp, extra=None):
    extra = extra or {}
    f.write("---\n")
    f.write(f'title: "{sanitize_yaml_string(title)}"\n')
    f.write(f'created: "{timestamp.split()[0] if timestamp != "unknown" else "unknown"}"\n')
    f.write("tags:\n  - ai\n")
    f.write('source: "AI"\n')
    f.write('manual_edit: false\n')
    for key, value in extra.items():
        if isinstance(value, bool):
            f.write(f"{key}: {'true' if value else 'false'}\n")
        elif value is None:
            continue
        else:
            f.write(f'{key}: "{sanitize_yaml_string(value)}"\n')
    f.write("---\n\n")


def write_single_convo(slug, title, timestamp, messages, idx, meta):
    filename = f"{slug}.md"
    filepath = os.path.join(CONV_PATH, filename)
    if should_skip_file(filepath):
        log(f"Skipping manual edit: {filename}")
        return [f"- {title} ({timestamp}) — *manual edit skipped*"]

    with open(filepath, "w", encoding="utf-8") as f:
        write_frontmatter(f, title, timestamp, meta)
        f.write(f"# {title}\n")
        f.write(f"_Started: {timestamp}_\n\n")
        for role, content in messages:
            content = sanitize_and_log_images(content, title, idx)
            f.write(f"**[{role}]**:\n{content}\n\n---\n\n")
    return [f"- [{title} ({timestamp})]({CONVERSATION_FOLDER}/{filename})"]


def write_chunked_convo(slug, title, timestamp, messages, idx, meta):
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
            part_meta = dict(meta)
            part_meta["part"] = f"{i+1}/{len(parts)}"
            write_frontmatter(f, f"{title} (Part {i+1})", timestamp, part_meta)
            f.write(f"# {title} (Part {i+1} of {len(parts)})\n")
            f.write(f"_Started: {timestamp}_\n\n")
            for role, content in part:
                content = sanitize_and_log_images(content, title, idx)
                f.write(f"**[{role}]**:\n{content}\n\n")
        toc_entries.append(f"  - [Part {i+1} of {len(parts)}]({CONVERSATION_FOLDER}/{slug}/{partname})")

    return toc_entries


def find_active_path(thread):
    mapping = thread.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        return []

    current_id = thread.get("current_node")
    if not current_id or current_id not in mapping:
        # fallback for older exports: find a leaf node and walk upward
        leaves = [node_id for node_id, node in mapping.items() if not node.get("children")]
        current_id = leaves[0] if leaves else next(iter(mapping.keys()))

    path = []
    seen = set()
    while current_id and current_id not in seen and current_id in mapping:
        seen.add(current_id)
        node = mapping[current_id]
        path.append(node)
        current_id = node.get("parent")

    path.reverse()
    return path


def flatten_messages(thread, title, idx):
    global total_messages
    messages = []

    for node in find_active_path(thread):
        msg = node.get("message")
        if not msg:
            continue

        role = msg.get("author", {}).get("role", "unknown")
        metadata = msg.get("metadata") or {}
        status = msg.get("status")

        if role == "system" and not INCLUDE_SYSTEM_MESSAGES:
            continue
        if metadata.get("is_visually_hidden_from_conversation") and not INCLUDE_HIDDEN_MESSAGES:
            continue
        if SKIP_IN_PROGRESS_MESSAGES and status == "in_progress":
            continue

        content = extract_content(msg, title, idx)
        if content:
            messages.append((role, content))
            total_messages += 1

    return messages


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "conversations" in data:
        return data["conversations"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unrecognized format in {path}")


def load_conversations(input_path):
    path = Path(input_path)
    conversations = []

    if path.is_dir():
        json_files = sorted(path.glob("conversations*.json"))
        if not json_files:
            raise FileNotFoundError(f"No conversations*.json files found in folder: {input_path}")
        for json_file in json_files:
            log(f"Loading {json_file.name}")
            loaded_json_files.append(str(json_file))
            conversations.extend(load_json_file(json_file))
        return conversations

    if path.is_file():
        loaded_json_files.append(str(path))
        return load_json_file(path)

    # legacy behavior: plain filename maybe in cwd
    if os.path.exists(input_path):
        loaded_json_files.append(input_path)
        return load_json_file(input_path)

    raise FileNotFoundError(f"Input path not found: {input_path}")


def get_input_size_mb(paths):
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total / (1024 * 1024)


# --- LOAD JSON / FOLDER ---
conversations = load_conversations(INPUT_PATH)

toc = ["# ChatGPT Conversation Index\n"]

for idx, thread in enumerate(conversations):
    title = thread.get("title") or "Untitled"
    create_time = thread.get("create_time", "")
    timestamp = format_ts(create_time)
    slug = make_slug_or_hash(title, timestamp, idx)
    log(f"Processing thread {idx + 1}/{len(conversations)}: {title}")

    messages = flatten_messages(thread, title, idx)
    if not messages:
        continue

    meta = {
        "thread_id": thread.get("id", ""),
        "message_count": str(len(messages)),
        "update_time": format_ts(thread.get("update_time", "")),
        "active_branch_only": True,
    }

    total_threads += 1
    if len(messages) > MAX_MESSAGES_PER_FILE:
        toc.append(f"- {title} ({timestamp})")
        toc.extend(write_chunked_convo(slug, title, timestamp, messages, idx, meta))
    else:
        toc.extend(write_single_convo(slug, title, timestamp, messages, idx, meta))

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
            try:
                size += os.path.getsize(os.path.join(root, file))
            except OSError:
                pass
    return size / (1024 * 1024)


original_size = get_input_size_mb(loaded_json_files)
exported_size = get_dir_size_mb(CONV_PATH)

print(
    f"""
Conversion complete.
Threads processed: {total_threads}
Messages exported: {total_messages}
Markdown size: {exported_size:.1f} MB
Input JSON size: {original_size:.1f} MB
JSON files loaded: {len(loaded_json_files)}
Elapsed time: {elapsed:.1f} seconds
""".strip()
)
