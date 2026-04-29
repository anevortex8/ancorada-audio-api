"""ANCORADA Audio API — FastAPI application."""
from __future__ import annotations
import base64
import logging
import re
import unicodedata
from datetime import datetime, timezone

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

    voice_id = req.voice_id or config.ELEVENLABS_DEFAULT_VOICE_ID
    logger.info("[audio] voice_id configured: %s", bool(voice_id))
    if not voice_id:
        raise HTTPException(
            status_code=400,
            detail="voice_id é obrigatório. Envie no body ou configure ELEVENLABS_DEFAULT_VOICE_ID ou ELEVENLABS_VOICE_ID no ambiente.",
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

    logger.info("[audio] mode=%s, file=%s, size=%d bytes", config.AUDIO_UPLOAD_MODE, filename, len(final_audio))

    # Modo: supabase_upload (opcional, requer envs)
    if config.AUDIO_UPLOAD_MODE == "supabase_upload":
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
                "voice_id_used": bool(voice_id),
                "blocks_count": len(req.audio_blocks),
                "file_size_bytes": len(final_audio),
                "upload_mode": "supabase_upload",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # Modo padrão: return_base64
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
            "voice_id_used": bool(voice_id),
            "blocks_count": len(req.audio_blocks),
            "file_size_bytes": len(final_audio),
            "upload_mode": "return_base64",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
