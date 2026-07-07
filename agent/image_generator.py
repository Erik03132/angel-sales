"""Leonardo.ai image generation wrapper."""

import os
import time

import requests


LEONARDO_BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
LEONARDO_MODELS = {
    "phoenix": "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3",
    "diffusion_xl": "e71a1c2f-3432-4365-aa9a-58804c51051d",
    "absolute_reality": "c61732db-3fac-48d1-9e9e-608fc27e7519",
}


def _load_api_key() -> str:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "LEONARDO_API_KEY":
                        return v.strip()
    return os.getenv("LEONARDO_API_KEY", "")


def leonardo_generate(
    prompt: str,
    model: str = "phoenix",
    width: int = 1024,
    height: int = 1024,
    api_key: str | None = None,
) -> str | None:
    """
    Generate an image via Leonardo.ai API.

    Args:
        prompt: Image description
        model: "phoenix" | "diffusion_xl" | "absolute_reality"
        width, height: Image dimensions
        api_key: Optional key (loaded from env if not provided)

    Returns:
        Image URL or None on failure
    """
    key = api_key or _load_api_key()
    if not key:
        return None

    model_id = LEONARDO_MODELS.get(model, LEONARDO_MODELS["phoenix"])

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "negative_prompt": "text, watermark, signature, blurry, deformed, ugly, duplicate",
        "modelId": model_id,
        "width": width,
        "height": height,
        "num_images": 1,
        "scheduler": "EULER_DISCRETE",
        "sd_version": "SDXL_1_0",
    }

    try:
        response = requests.post(
            f"{LEONARDO_BASE_URL}/generations",
            headers=headers,
            json=payload,
            timeout=60,
        )
        data = response.json()

        if "sdGenerationJob" not in data:
            return None

        generation_id = data["sdGenerationJob"]["generationId"]

        for _ in range(20):
            time.sleep(3)
            status_resp = requests.get(
                f"{LEONARDO_BASE_URL}/generations/{generation_id}",
                headers=headers,
                timeout=30,
            )
            status_data = status_resp.json()
            status = status_data.get("sdGenerationJob", {}).get("status", "PENDING")

            if status == "COMPLETE":
                images = status_data.get("generated_images", [])
                if images:
                    return images[0].get("url")
                return None
            elif status == "FAILED":
                return None

        return None
    except Exception:
        return None


def download_image(url: str, output_path: str, proxy: str = "") -> bool:
    """Download image from URL to local file."""
    proxies = {}
    if proxy:
        proxies = {"https": proxy, "http": proxy}

    try:
        response = requests.get(url, timeout=60, proxies=proxies or None)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        return False
    except Exception:
        return False
