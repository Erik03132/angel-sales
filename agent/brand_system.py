"""Brand system data model for Rembrandt."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class DesignToken:
    name: str
    value: str
    token: str
    role: str = ""


@dataclass
class BrandSystem:
    name: str
    theme: str  # "light" | "dark"
    colors: list[DesignToken] = field(default_factory=list)
    typography: dict = field(default_factory=dict)
    spacing: dict = field(default_factory=dict)
    components: dict = field(default_factory=dict)
    guidelines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "theme": self.theme,
            "colors": [asdict(c) for c in self.colors],
            "typography": self.typography,
            "spacing": self.spacing,
            "components": self.components,
            "guidelines": self.guidelines,
        }


def load_brand(path: str) -> BrandSystem:
    with open(path) as f:
        data = json.load(f)
    colors = [DesignToken(**c) for c in data.get("colors", [])]
    return BrandSystem(
        name=data["name"],
        theme=data.get("theme", "light"),
        colors=colors,
        typography=data.get("typography", {}),
        spacing=data.get("spacing", {}),
        components=data.get("components", {}),
        guidelines=data.get("guidelines", []),
    )


INCUBIRD_DEFAULT = BrandSystem(
    name="IncuBird",
    theme="warm",
    colors=[
        DesignToken("Wheat", "#f5e6ca", "--color-wheat", "Page background, warm base"),
        DesignToken("Olive", "#7a9e5a", "--color-olive", "Primary accent, CTAs"),
        DesignToken("Terracotta", "#c4724a", "--color-terracotta", "Secondary accent, highlights"),
        DesignToken("Soil", "#4a3728", "--color-soil", "Body text, headings"),
        DesignToken("Cream", "#faf3e8", "--color-cream", "Card surfaces, elevated backgrounds"),
        DesignToken("Sage", "#b8c9a8", "--color-sage", "Borders, dividers, muted accents"),
        DesignToken("Honey", "#d4a853", "--color-honey", "Warnings, ratings, stars"),
        DesignToken("White", "#ffffff", "--color-white", "Contrast text on dark"),
    ],
    typography={
        "font_primary": "Manrope, sans-serif",
        "font_heading": "PT Serif, serif",
        "font_mono": "JetBrains Mono, monospace",
        "weights": {"light": 300, "regular": 400, "medium": 500, "bold": 700},
        "scale": {
            "display": "72px", "h1": "48px", "h2": "32px",
            "h3": "24px", "body": "16px", "body_sm": "14px", "caption": "12px",
        },
    },
    spacing={
        "base": 4, "scale": [4, 8, 12, 16, 24, 32, 48, 64, 96],
        "card_padding": 24, "section_gap": 64, "element_gap": 8, "max_width": "1200px",
    },
    components={
        "button": {"radius": 8, "padding": "12px 24px", "font_weight": 500},
        "card": {"radius": 12, "padding": 24, "shadow": "0 2px 8px rgba(74, 55, 40, 0.08)"},
        "input": {"radius": 8, "padding": "12px 16px", "border": "1px solid #b8c9a8"},
        "badge": {"radius": 4, "padding": "2px 8px", "font_size": "12px"},
    },
    guidelines=[
        "Use warm earth tones — avoid cold blues and grays",
        "PT Serif for headings, Manrope for body",
        "Generous whitespace — rural brands should feel open, not cramped",
        "Rounded corners (8-12px) for approachability",
        "Subtle shadows with warm undertones (rgba with brown shift)",
    ],
)
