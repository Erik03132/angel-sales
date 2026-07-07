#!/usr/bin/env python3
"""
🎨 Rembrandt — Universal Designer Agent

Многофункциональный дизайн-агент для генерации дизайн-систем,
UI-компонентов и изображений.

Использование:
    python3 rembrandt.py --design "Modern agricultural brand"
    python3 rembrandt.py --component "hero section with gradient"
    python3 rembrandt.py --prompt "farm poultry chickens" --output photo.png
    python3 rembrandt.py --brand path/to/brand.json --component "button"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brand_system import BrandSystem, load_brand, INCUBIRD_DEFAULT
from agent.component_generator import generate_component, COMPONENT_TYPES
from agent.design_generator import generate_design_md
from agent.image_generator import leonardo_generate, download_image


def main():
    parser = argparse.ArgumentParser(
        description="🎨 Rembrandt — Universal Designer Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 rembrandt.py --design "Modern agricultural brand, warm earth tones"
  python3 rembrandt.py --component "hero" --spec "Hero section with gradient bg and CTA" --style incubird
  python3 rembrandt.py --prompt "farm poultry chickens" --output photo.png
  python3 rembrandt.py --list-components
        """,
    )

    # Design system generation
    parser.add_argument("--design", "-d", type=str, default=None,
                        help="Generate DESIGN.md from a design brief")

    # Component generation
    parser.add_argument("--component", "-c", type=str, default=None,
                        choices=COMPONENT_TYPES + [None],
                        help=f"Generate a UI component ({', '.join(COMPONENT_TYPES)})")
    parser.add_argument("--spec", "-s", type=str, default="",
                        help="Component specification (natural language)")
    parser.add_argument("--style", type=str, default="incubird",
                        choices=["incubird", "custom"],
                        help="Brand style to use")
    parser.add_argument("--brand", type=str, default=None,
                        help="Path to custom brand JSON file")

    # Image generation (existing)
    parser.add_argument("--prompt", "-p", type=str, default=None,
                        help="Image description for Leonardo.ai generation")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output file path for image")

    # Utility
    parser.add_argument("--list-components", action="store_true",
                        help="List available component types")
    parser.add_argument("--list-brands", action="store_true",
                        help="List available brand systems")

    args = parser.parse_args()

    # --- Load brand ---
    brand: BrandSystem = INCUBIRD_DEFAULT
    if args.brand:
        brand = load_brand(args.brand)
    elif args.style == "custom" and not args.brand:
        print("❌ --style custom requires --brand path/to/brand.json")
        sys.exit(1)

    # --- List components ---
    if args.list_components:
        print("Available component types:")
        for t in COMPONENT_TYPES:
            print(f"  - {t}")
        return

    # --- List brands ---
    if args.list_brands:
        print("Available brand systems:")
        print(f"  - incubird (default): {INCUBIRD_DEFAULT.name}")
        if args.brand:
            print(f"  - custom: {args.brand}")
        return

    # --- DESIGN.md generation ---
    if args.design:
        print(f"🎨 Generating DESIGN.md from brief: {args.design}")
        result = generate_design_md(args.design)
        if result:
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, "design.md")
            with open(path, "w") as f:
                f.write(result)
            print(f"✅ DESIGN.md saved to {path}")
        else:
            print("❌ Failed to generate DESIGN.md")
            sys.exit(1)
        return

    # --- Component generation ---
    if args.component:
        spec = args.spec or f"Generate a {args.component} component in {brand.name} style"
        print(f"🎨 Generating component: {args.component}")
        print(f"   Style: {brand.name}")
        print(f"   Spec: {spec}")
        result = generate_component(args.component, spec, brand)
        if result:
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, f"{args.component}.html")
            with open(path, "w") as f:
                f.write(result)
            print(f"✅ Component saved to {path}")
        else:
            print("❌ Failed to generate component")
            sys.exit(1)
        return

    # --- Image generation ---
    if args.prompt:
        print(f"🎨 Generating image: {args.prompt}")
        image_url = leonardo_generate(args.prompt)
        if image_url:
            output_path = args.output or os.path.join(
                os.path.dirname(__file__), "output", "generated.png"
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            if download_image(image_url, output_path):
                print(f"✅ Image saved to {output_path}")
            else:
                print("❌ Failed to download image")
                sys.exit(1)
        else:
            print("❌ Failed to generate image")
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
