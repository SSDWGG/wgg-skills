---
name: codexzh-image-generation
description: Generate and download images through the CodexZH AI Hub image generation API. Use when Codex needs to create bitmap images from prompts using CodexZH/XBai/OpenAI-compatible image endpoints, save generated images locally, inspect image-generation API responses, or automate repeatable image generation workflows with CodexZH API keys.
---

# CodexZH Image Generation

## Quick Start

Use `scripts/generate_image.py` for API calls. It uses the OpenAI-compatible CodexZH AI Hub image endpoint and downloads the generated image when the API returns a URL.

Set an API key in the environment when possible:

```bash
export CODEXZH_API_KEY="..."
```

Run:

```bash
python3 /Users/renshuaiweidemac/.codex/skills/codexzh-image-generation/scripts/generate_image.py \
  --prompt "isometric 3D miniature game world under a lifted keyboard keycap" \
  --filename keycap-micro-game-world.jpg
```

If the user provides a key directly for a one-off request, pass it with `--api-key`; do not write that key into the skill files.

## Workflow

1. Read `references/api.md` if endpoint details, model defaults, or response fields are needed.
2. Create a concrete prompt that states subject, composition, style, lighting, and output constraints.
3. Run `scripts/generate_image.py` with `--prompt`; pass `--filename` for a stable name. Only pass `--output` when the user explicitly requests a path.
4. Inspect the saved image with `file`, `sips`, or a visual viewer when quality matters.
5. Report the saved path and any API response path to the user.

## Output Location Rule

Always save generated images into the corresponding project folder when one can be found. The script detects a project root from the current directory by looking for markers such as `.git`, `package.json`, `pyproject.toml`, `pom.xml`, or `go.mod`.

When a project root is found, save image assets under the first existing project asset directory from this order: `src/assets/images`, `src/assets`, `assets/images`, `assets`, `public/images`, `public`, `static/images`, `static`, `images`. If none exists, create `assets/images` under the project root.

If no corresponding project folder is found, save image assets directly on the user's Desktop. To force a specific project, pass `--project-dir /path/to/project`.

## Script Notes

- Default base URL: `https://api.xbai.top/v1`
- Default endpoint: `/images/generations`
- Default model: `nano-banana-2`
- Default size: `1024x1024`
- Default quality: `standard`
- Supported key env vars, in order: `CODEXZH_API_KEY`, `XBAI_API_KEY`, `OPENAI_API_KEY`
- `--output` is optional. If omitted, the script uses the Output Location Rule.
- Use `--response-json` to save the raw API response for debugging or provenance.

## Safety

Treat API keys as secrets. Do not commit, display, or store user-provided keys unless the user explicitly asks for persistent credential storage.
