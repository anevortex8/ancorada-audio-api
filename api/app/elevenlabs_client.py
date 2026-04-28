"""Cliente ElevenLabs para geração de áudio."""
from __future__ import annotations
import io
import logging
from typing import Optional

import requests

from . import config

logger = logging.getLogger("ancorada-audio")

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def generate_audio_block(
    text: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.8,
    style: float = 0.25,
    use_speaker_boost: bool = True,
    speed: float = 0.97,
) -> bytes:
    """Gera áudio MP3 para um bloco de texto via ElevenLabs."""

    api_key = config.ELEVENLABS_API_KEY
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY não configurada")

    url = f"{ELEVENLABS_TTS_URL}/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost,
        },
        "speed": speed,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)

    if response.status_code != 200:
        error_detail = response.text[:500]
        logger.error("ElevenLabs erro %d: %s", response.status_code, error_detail)
        raise ValueError(
            f"ElevenLabs retornou status {response.status_code}: {error_detail}"
        )

    audio_bytes = response.content
    if len(audio_bytes) < 1000:
        raise ValueError("ElevenLabs retornou áudio muito pequeno, possível erro silencioso")

    logger.info("Áudio gerado: %d bytes", len(audio_bytes))
    return audio_bytes


def concatenate_mp3_blocks(blocks: list[bytes], silence_ms: int = 1500) -> bytes:
    """Concatena blocos MP3 com silêncio entre eles usando pydub."""
    from pydub import AudioSegment

    silence = AudioSegment.silent(duration=silence_ms)
    combined = AudioSegment.empty()

    for i, block_bytes in enumerate(blocks):
        segment = AudioSegment.from_mp3(io.BytesIO(block_bytes))
        if i > 0:
            combined += silence
        combined += segment

    output = io.BytesIO()
    combined.export(output, format="mp3", bitrate="192k")
    return output.getvalue()
