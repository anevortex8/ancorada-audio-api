"""ANCORADA Audio API — FastAPI application."""
from __future__ import annotations
import base64
import logging
import re
import unicodedata
from datetime import datetime, timezone

import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .models import (
    AudioScriptRequest,
    AudioScriptResponse,
    AudioBlock,
    GenerateAudioRequest,
    GenerateAudioResponse,
)
from .script_generator import generate_audio_script
from .elevenlabs_client import generate_audio_block, concatenate_mp3_blocks

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ancorada-audio")

app = FastAPI(
    title="ANCORADA Audio API",
    description="Gera roteiro de áudio personalizado e MP3 via ElevenLabs para o Diagnóstico ANCORADA.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": config.TEMPLATE_VERSION,
        "model": config.ANTHROPIC_MODEL,
        "elevenlabs_configured": bool(config.ELEVENLABS_API_KEY),
        "supabase_configured": bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY),
    }


@app.post("/generate-audio-script", response_model=AudioScriptResponse)
def generate_script_endpoint(req: AudioScriptRequest):
    """Gera o roteiro de áudio personalizado via Claude."""

    customer_name = req.customer.get_name()

    # Logging detalhado
    logger.info("[audio-script] received payload keys: %s", list(req.model_dump().keys()))
    logger.info("[audio-script] customer: %s", customer_name)
    logger.info("[audio-script] has diagnostic_text: %s", bool(req.diagnostic_text))
    logger.info("[audio-script] diagnostic_text length: %d", len(req.diagnostic_text))
    logger.info("[audio-script] has diagnostic_json: %s", bool(req.diagnostic_json))
    logger.info("[audio-script] has chart_json: %s", bool(req.chart_json))
    logger.info("[audio-script] diagnostic_id: %s", req.diagnostic_id or "(none)")

    # Validação: precisa de pelo menos uma fonte
    has_diagnostic_text = bool(req.diagnostic_text and req.diagnostic_text.strip())
    has_diagnostic_json = bool(req.diagnostic_json)

    if not has_diagnostic_text and not has_diagnostic_json:
        raise HTTPException(
            status_code=422,
            detail="Pelo menos diagnostic_text ou diagnostic_json deve ser fornecido.",
        )

    source = "diagnostic_text" if has_diagnostic_text else "diagnostic_json"
    logger.info("[audio-script] using source: %s", source)
    logger.info("[audio-script] ignored chart_json: %s", not bool(req.chart_json))

    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # Birth profile (opcional)
    birth_profile = req.birth_profile.model_dump() if req.birth_profile else None

    try:
        blocks, full_script = generate_audio_script(
            customer_name=customer_name,
            birth_profile=birth_profile,
            diagnostic_text=req.diagnostic_text,
            diagnostic_json=req.diagnostic_json,
            chart_json=req.chart_json,
        )
    except Exception as e:
        logger.exception("[audio-script] Erro na geração do roteiro de áudio")
        raise HTTPException(status_code=500, detail=str(e))

    word_count = len(full_script.split())
    estimated_minutes = round(word_count / 150, 1)

    return AudioScriptResponse(
        audio_script=full_script,
        audio_blocks=[AudioBlock(label=b["label"], text=b["text"]) for b in blocks],
        estimated_duration_minutes=estimated_minutes,
        metadata={
            "template": config.TEMPLATE_VERSION,
            "tone": "conversacional, íntimo, ritualístico",
            "model": config.ANTHROPIC_MODEL,
            "word_count": word_count,
            "blocks_count": len(blocks),
            "source": source,
            "diagnostic_id": req.diagnostic_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.post("/generate-audio", response_model=GenerateAudioResponse)
def generate_audio_endpoint(req: GenerateAudioRequest):
    """Gera áudio MP3 via ElevenLabs a partir dos blocos de texto."""

    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not configured")

    # Resolver voice_id: payload > env_default > env_legacy
    # Ignorar valores inválidos (nomes como "Sarah", "Mayara", strings curtas)
    INVALID_VOICE_IDS = {"", "sarah", "mayara", "default", "null", "none", "undefined"}
    raw_voice = (req.voice_id or "").strip()
    payload_valid = raw_voice.lower() not in INVALID_VOICE_IDS and len(raw_voice) > 10

    if payload_valid:
        voice_id = raw_voice
        voice_source = "payload"
    elif config.ELEVENLABS_DEFAULT_VOICE_ID:
        voice_id = config.ELEVENLABS_DEFAULT_VOICE_ID
        voice_source = "env_default"
    else:
        voice_id = ""
        voice_source = "none"

    logger.info("[audio] voice_id source: %s", voice_source)
    logger.info("[audio] voice_id configured: %s", bool(voice_id))
    if voice_id:
        logger.info("[audio] voice_id prefix: %s", voice_id[:6])

    if not voice_id:
        raise HTTPException(
            status_code=400,
            detail="voice_id obrigatório. Configure ELEVENLABS_DEFAULT_VOICE_ID no Render ou envie voice_id no body.",
        )

    if not req.audio_blocks:
        raise HTTPException(status_code=400, detail="audio_blocks não pode ser vazio")

    # Gerar áudio para cada bloco
    audio_parts: list[bytes] = []
    for i, block in enumerate(req.audio_blocks):
        logger.info("Gerando áudio bloco %d/%d: %s", i + 1, len(req.audio_blocks), block.label)
        try:
            audio_bytes = generate_audio_block(
                text=block.text,
                voice_id=voice_id,
                model_id=req.model_id,
                stability=req.voice_settings.stability,
                similarity_boost=req.voice_settings.similarity_boost,
                style=req.voice_settings.style,
                use_speaker_boost=req.voice_settings.use_speaker_boost,
                speed=req.speed,
            )
            audio_parts.append(audio_bytes)
        except Exception as e:
            logger.exception("Erro no bloco %d (%s)", i + 1, block.label)
            raise HTTPException(
                status_code=502,
                detail=f"ElevenLabs falhou no bloco {i + 1} ({block.label}): {str(e)}",
            )

    # Concatenar blocos com silêncio entre eles
    logger.info("Concatenando %d blocos de áudio", len(audio_parts))
    try:
        final_audio = concatenate_mp3_blocks(audio_parts)
    except Exception as e:
        logger.exception("Erro na concatenação dos blocos")
        raise HTTPException(status_code=500, detail=f"Erro ao concatenar áudio: {str(e)}")

    # Calcular duração
    duration_seconds = None
    try:
        from pydub import AudioSegment
        import io
        segment = AudioSegment.from_mp3(io.BytesIO(final_audio))
        duration_seconds = round(len(segment) / 1000, 1)
    except Exception:
        pass

    # Gerar filename
    customer_name = req.customer_name or "cliente"
    slug = re.sub(r"[-\s]+", "-", unicodedata.normalize("NFKD", customer_name).encode("ascii", "ignore").decode("ascii").lower().strip())
    filename = f"audio-ancorada-{slug}.mp3"

    # Determinar upload_mode: payload > env > default
    upload_mode = req.upload_mode or config.AUDIO_UPLOAD_MODE or "return_base64"
    logger.info("[audio] upload_mode=%s, file=%s, size=%d bytes, blocks=%d",
                upload_mode, filename, len(final_audio), len(req.audio_blocks))

    # ── Modo: signed_upload (frontend envia signed URL do Supabase) ──
    if upload_mode == "signed_upload":
        if not req.signed_upload or not req.signed_upload.signed_url:
            raise HTTPException(
                status_code=400,
                detail="signed_upload.signed_url é obrigatório no modo signed_upload.",
            )

        signed = req.signed_upload
        upload_url = signed.signed_url
        if signed.token and "?" not in upload_url:
            upload_url = f"{upload_url}?token={signed.token}"
        elif signed.token:
            upload_url = f"{upload_url}&token={signed.token}"

        try:
            resp = requests.put(
                upload_url,
                data=final_audio,
                headers={"Content-Type": "audio/mpeg"},
                timeout=120,
            )
            uploaded = resp.status_code in (200, 201)
            if not uploaded:
                logger.error("[audio] signed upload failed: %d %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.exception("[audio] signed upload error")
            uploaded = False

        logger.info("[audio] uploaded=%s, storage_path=%s", uploaded, signed.path)

        return GenerateAudioResponse(
            uploaded=uploaded,
            storage_path=signed.path,
            filename=filename,
            mime_type="audio/mpeg",
            audio_status="audio_ready" if uploaded else "upload_failed",
            duration_seconds=duration_seconds,
            metadata={
                "template": config.TEMPLATE_VERSION,
                "provider": "elevenlabs",
                "model": req.model_id,
                "voice_id_source": voice_source,
                "voice_id_prefix": voice_id[:6] if voice_id else "",
                "blocks_count": len(req.audio_blocks),
                "file_size_bytes": len(final_audio),
                "upload_mode": "signed_upload",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ── Modo: supabase_upload (legado, requer envs no Render) ──
    if upload_mode == "supabase_upload":
        from .storage import upload_audio_to_supabase
        try:
            audio_url = upload_audio_to_supabase(final_audio, customer_name)
        except Exception as e:
            logger.exception("Erro no upload para Supabase")
            raise HTTPException(status_code=500, detail=f"Erro no upload do áudio: {str(e)}")

        return GenerateAudioResponse(
            audio_url=audio_url,
            filename=filename,
            audio_status="audio_ready",
            duration_seconds=duration_seconds,
            metadata={
                "template": config.TEMPLATE_VERSION,
                "provider": "elevenlabs",
                "model": req.model_id,
                "voice_id_source": voice_source,
                "voice_id_prefix": voice_id[:6] if voice_id else "",
                "blocks_count": len(req.audio_blocks),
                "file_size_bytes": len(final_audio),
                "upload_mode": "supabase_upload",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ── Modo padrão: return_base64 (para testes curtos) ──
    audio_b64 = base64.b64encode(final_audio).decode("utf-8")

    return GenerateAudioResponse(
        audio_base64=audio_b64,
        filename=filename,
        mime_type="audio/mpeg",
        audio_status="audio_ready",
        duration_seconds=duration_seconds,
        metadata={
            "template": config.TEMPLATE_VERSION,
            "provider": "elevenlabs",
            "model": req.model_id,
            "voice_id_source": voice_source,
            "voice_id_prefix": voice_id[:6] if voice_id else "",
            "blocks_count": len(req.audio_blocks),
            "file_size_bytes": len(final_audio),
            "upload_mode": "return_base64",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
