# ChatGPT-Markdown-Exporter

This Python script converts your exported `conversations.json` from ChatGPT into neatly organized Markdown files compatible with Obsidian or any Markdown-based note system.

## Features

- Converts threads into Markdown files with YAML frontmatter
- Automatically sanitizes image URLs and logs media references
- Splits long threads into multiple parts
- Skips system messages (optional)
- Adds a table of contents (`index.md`)
- Optionally **skips overwriting manually edited files** using the `manual_edit: true` flag in YAML
- Termux-compatible for mobile workflows

## Requirements

- Python 3.6+
- No external dependencies required

## Usage

1. Place your exported `conversations.json` in the script directory.
2. Run the script:
   ```bash
   python3 export_chatgpt.py
   ```
3. Output is saved to:
   ```
   gpt_export_markdown/
     ├── conversations/
     ├── media_references.txt
     └── index.md
   ```

## Manual File Protection

To prevent a file from being overwritten in future exports:

```yaml
---
title: "My Custom Notes"
created: "2024-12-01"
tags:
  - ai
source: "AI"
manual_edit: true
---
```

Files marked with `manual_edit: true` will be skipped during regeneration.

## Notes

- All frontmatter keys are safely quoted to avoid YAML parsing issues.
- Images embedded via Markdown will be referenced by filename in `media/` but must be restored manually if missing from ZIP backups.

## License

MIT – use freely, modify to suit your vault architecture.
