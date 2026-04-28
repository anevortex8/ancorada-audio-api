"""Upload de áudio para Supabase Storage."""
from __future__ import annotations
import logging
import re
import unicodedata

import requests

from . import config

logger = logging.getLogger("ancorada-audio")


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


def upload_audio_to_supabase(audio_bytes: bytes, customer_name: str) -> str:
    """Faz upload do MP3 para Supabase Storage e retorna a URL pública."""

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios")

    bucket = config.SUPABASE_AUDIO_BUCKET
    filename = f"audio-ancorada-{_slugify(customer_name)}.mp3"
    path = f"{filename}"

    upload_url = f"{config.SUPABASE_URL}/storage/v1/object/{bucket}/{path}"

    headers = {
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "Content-Type": "audio/mpeg",
        "x-upsert": "true",
    }

    response = requests.post(upload_url, data=audio_bytes, headers=headers, timeout=60)

    if response.status_code not in (200, 201):
        error_detail = response.text[:500]
        logger.error("Supabase upload erro %d: %s", response.status_code, error_detail)
        raise ValueError(f"Supabase upload falhou ({response.status_code}): {error_detail}")

    public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
    logger.info("Áudio salvo: %s (%d bytes)", public_url, len(audio_bytes))

    return public_url
