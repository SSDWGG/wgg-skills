# CodexZH AI Hub Image API Reference

Source documentation: https://docs.codexzh.com/ai-hub-api/image-tutorial

## Endpoint

Use the OpenAI-compatible image generation route:

```text
POST https://api.xbai.top/v1/images/generations
```

Headers:

```text
Content-Type: application/json
Authorization: Bearer <api-key>
```

Common request body:

```json
{
  "model": "nano-banana-2",
  "prompt": "Describe the image to generate",
  "n": 1,
  "size": "1024x1024",
  "quality": "standard",
  "response_format": "url"
}
```

Common response shape:

```json
{
  "created": 1777256336,
  "data": [
    {
      "url": "https://...",
      "b64_json": "",
      "revised_prompt": ""
    }
  ]
}
```

Prefer `response_format: "url"` for local download workflows. If the API returns `b64_json`, decode it and write the bytes directly.
