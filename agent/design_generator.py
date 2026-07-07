"""DESIGN.md generation from a design brief."""

import json
import os

import requests

from .brand_system import BrandSystem, DesignToken


def _load_openrouter_key() -> str:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "OPENROUTER_API_KEY":
                        return v.strip()
    return os.getenv("OPENROUTER_API_KEY", "")


DESIGN_SYSTEM_PROMPT = """You are a design system expert. Given a design brief, generate a complete brand system in JSON format.

Respond ONLY with valid JSON matching this schema:
{
  "name": "Brand name",
  "theme": "light" | "dark" | "warm",
  "colors": [
    {"name": "ColorName", "value": "#hex", "token": "--color-name", "role": "Usage description"}
  ],
  "typography": {
    "font_primary": "font-family",
    "font_heading": "font-family",
    "weights": {"light": 300, "regular": 400, "medium": 500, "bold": 700},
    "scale": {"h1": "48px", "h2": "32px", ...}
  },
  "spacing": {
    "base": 4,
    "scale": [4, 8, 12, 16, 24, 32, 48, 64, 96],
    "card_padding": 24,
    "section_gap": 64,
    "max_width": "1200px"
  },
  "components": {
    "button": {"radius": 8, "padding": "12px 24px"},
    "card": {"radius": 12, "padding": 24}
  },
  "guidelines": ["Do use...", "Don't use..."]
}

Design brief: {brief}

Return ONLY valid JSON, no markdown, no explanation."""


def generate_design_md(brief: str, api_key: str | None = None) -> str | None:
    """
    Generate a complete DESIGN.md from a natural language brief.

    Args:
        brief: Design description (e.g. "Modern agricultural brand, warm earth tones")
        api_key: OpenRouter API key (loaded from env if None)

    Returns:
        DESIGN.md content as string, or None if generation fails
    """
    key = api_key or _load_openrouter_key()
    if not key:
        return None

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "deepseek/deepseek-chat-v3-0324",
                "messages": [{"role": "user", "content": DESIGN_SYSTEM_PROMPT.format(brief=brief)}],
                "max_tokens": 2000,
                "temperature": 0.3,
            },
            timeout=60,
        )
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        data = json.loads(content)
        colors = [DesignToken(**c) for c in data.get("colors", [])]
        brand = BrandSystem(
            name=data.get("name", brief[:30]),
            theme=data.get("theme", "light"),
            colors=colors,
            typography=data.get("typography", {}),
            spacing=data.get("spacing", {}),
            components=data.get("components", {}),
            guidelines=data.get("guidelines", []),
        )
        return render_design_md(brand)
    except Exception:
        return None


def render_design_md(brand: BrandSystem) -> str:
    """Render a BrandSystem into Refero-compatible DESIGN.md format."""
    lines = []
    lines.append(f"# {brand.name} — Design System")
    lines.append(f"> **Theme:** {brand.theme}")
    lines.append("")

    lines.append("## Tokens — Colors")
    lines.append("")
    if brand.colors:
        lines.append("| Name | Value | Token | Role |")
        lines.append("|------|-------|-------|------|")
        for c in brand.colors:
            lines.append(f"| {c.name} | `{c.value}` | `{c.token}` | {c.role} |")
        lines.append("")

    if brand.typography:
        lines.append("## Typography")
        lines.append("")
        pf = brand.typography.get("font_primary", "")
        if pf:
            lines.append(f"**Primary font:** {pf}")
        hf = brand.typography.get("font_heading", "")
        if hf:
            lines.append(f"**Heading font:** {hf}")
        scale = brand.typography.get("scale", {})
        if scale:
            lines.append("")
            lines.append("| Role | Size |")
            lines.append("|------|------|")
            for role, size in scale.items():
                lines.append(f"| {role} | {size} |")
        lines.append("")

    if brand.spacing:
        lines.append("## Spacing")
        lines.append("")
        lines.append(f"**Base unit:** {brand.spacing.get('base', 4)}px")
        lines.append(f"**Max width:** {brand.spacing.get('max_width', '1200px')}")
        if brand.spacing.get("scale"):
            scale_values = ", ".join(f"{s}px" for s in brand.spacing["scale"])
            lines.append(f"**Scale:** {scale_values}")
        lines.append("")

    if brand.components:
        lines.append("## Components")
        lines.append("")
        for name, spec in brand.components.items():
            lines.append(f"### {name.title()}")
            for key, val in spec.items():
                lines.append(f"- **{key}:** {val}")
            lines.append("")

    if brand.guidelines:
        lines.append("## Guidelines")
        lines.append("")
        for g in brand.guidelines:
            lines.append(f"- {g}")
        lines.append("")

    return "\n".join(lines)
