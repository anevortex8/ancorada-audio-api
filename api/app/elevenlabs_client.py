"""Cliente ElevenLabs para geração de áudio."""
from __future__ import annotations
import io
import logging
import re
from typing import Optional

import requests

from . import config

logger = logging.getLogger("ancorada-audio")

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Regex para remover stage directions entre colchetes ou parênteses
_STAGE_DIRECTION_RE = re.compile(
    r'[\[\(]\s*(?:pausa(?:\s+breve)?|respira|silêncio|silencio)\s*[\]\)]',
    re.IGNORECASE,
)

# Substituições de pronomes (tu/teu/tua → você/seu/sua)
_PRONOUN_REPLACEMENTS = [
    (re.compile(r'\bcontigo\b', re.IGNORECASE), 'com você'),
    (re.compile(r'\bpra ti\b', re.IGNORECASE), 'para você'),
    (re.compile(r'\bpara ti\b', re.IGNORECASE), 'para você'),
    (re.compile(r'\btuas\b', re.IGNORECASE), 'suas'),
    (re.compile(r'\bteus\b', re.IGNORECASE), 'seus'),
    (re.compile(r'\btua\b', re.IGNORECASE), 'sua'),
    (re.compile(r'\bteu\b', re.IGNORECASE), 'seu'),
]

# Dicionário de pronúncia — corrige entonação/fonética de palavras específicas
_PRONUNCIATION_REPLACEMENTS = [
    (re.compile(r'\bQuíron\b'), 'Kíron'),
    (re.compile(r'\bquíron\b'), 'kíron'),
    (re.compile(r'\bmasterclass\b', re.IGNORECASE), 'masterclés'),
    (re.compile(r'\bMasterclass\b'), 'Masterclés'),
]


def sanitize_script_for_tts(text: str, block_label: str = "") -> str:
    """Limpa o texto antes de enviar ao ElevenLabs.

    - Remove stage directions: [pausa], (respira), etc.
    - Normaliza pronomes: teu→seu, tua→sua, contigo→com você, etc.
    """
    # Contar e remover stage directions
    directions_found = len(_STAGE_DIRECTION_RE.findall(text))
    clean = _STAGE_DIRECTION_RE.sub('', text)

    # Normalizar pronomes
    pronoun_applied = False
    for pattern, replacement in _PRONOUN_REPLACEMENTS:
        if pattern.search(clean):
            pronoun_applied = True
            clean = pattern.sub(replacement, clean)

    # Aplicar correções de pronúncia
    for pattern, replacement in _PRONUNCIATION_REPLACEMENTS:
        clean = pattern.sub(replacement, clean)

    # Garantir que o bloco termina com pontuação final forte
    # para que o TTS aplique entonação de encerramento
    clean = re.sub(r'  +', ' ', clean).strip()
    if clean and clean[-1] not in '.!?…':
        clean += '.'

    logger.info("[audio-tts] sanitized block label: %s", block_label)
    logger.info("[audio-tts] removed stage directions: %d", directions_found)
    logger.info("[audio-tts] pronoun normalization applied: %s", pronoun_applied)

    return clean


def generate_audio_block(
    text: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.38,
    similarity_boost: float = 0.78,
    style: float = 0.42,
    use_speaker_boost: bool = True,
    speed: float = 1.05,
    block_label: str = "",
) -> bytes:
    """Gera áudio MP3 para um bloco de texto via ElevenLabs."""

    # Sanitizar texto antes do TTS
    clean_text = sanitize_script_for_tts(text, block_label=block_label)

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
        "text": clean_text,
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


def concatenate_mp3_blocks(blocks: list[bytes], silence_ms: int = 850) -> bytes:
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


def generate_audio_single(
    blocks: list[dict],
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.38,
    similarity_boost: float = 0.76,
    style: float = 0.35,
    use_speaker_boost: bool = True,
    speed: float = 1.035,
) -> bytes:
    """Gera áudio MP3 enviando o roteiro inteiro como uma única chamada ao ElevenLabs.

    Isso garante tom e velocidade consistentes ao longo de todos os blocos.
    Blocos são separados por quebras de parágrafo para pausas naturais.
    """
    # Juntar todos os blocos com separação de parágrafo natural
    full_text_parts = []
    for block in blocks:
        text = block.get("text", "") if isinstance(block, dict) else block.text
        label = block.get("label", "") if isinstance(block, dict) else block.label
        clean = sanitize_script_for_tts(text, block_label=label)
        full_text_parts.append(clean)

    # Separar blocos com dupla quebra de linha — ElevenLabs interpreta como pausa natural
    full_text = "\n\n\n".join(full_text_parts)

    logger.info("[audio-single] Gerando áudio único: %d chars, %d blocos", len(full_text), len(blocks))

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
        "text": full_text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost,
        },
        "speed": speed,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=300)

    if response.status_code != 200:
        error_detail = response.text[:500]
        logger.error("ElevenLabs erro %d: %s", response.status_code, error_detail)
        raise ValueError(
            f"ElevenLabs retornou status {response.status_code}: {error_detail}"
        )

    audio_bytes = response.content
    if len(audio_bytes) < 1000:
        raise ValueError("ElevenLabs retornou áudio muito pequeno, possível erro silencioso")

    # Adicionar silêncio no final para evitar corte abrupto do MP3
    from pydub import AudioSegment
    segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
    segment += AudioSegment.silent(duration=1200)
    output = io.BytesIO()
    segment.export(output, format="mp3", bitrate="192k")
    final_bytes = output.getvalue()

    logger.info("[audio-single] Áudio gerado: %d bytes (com tail pad)", len(final_bytes))
    return final_bytes
