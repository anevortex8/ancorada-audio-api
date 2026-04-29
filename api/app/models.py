from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional


class Customer(BaseModel):
    full_name: str = ""
    name: str = ""
    email: str = ""

    def get_name(self) -> str:
        return self.full_name or self.name or "Cliente"


class BirthProfile(BaseModel):
    birth_date: str = Field("", description="YYYY-MM-DD")
    birth_time: str = Field("", description="HH:MM")
    birth_city: str = ""
    birth_state: str = ""
    birth_country: str = "Brasil"


class AudioBlock(BaseModel):
    label: str
    text: str


class AudioScriptRequest(BaseModel):
    customer: Customer
    diagnostic_text: str = ""
    diagnostic_json: Any = {}
    diagnostic_id: str = ""
    diagnostic_pdf_url: str = ""
    product: str = "audio"
    birth_profile: Optional[BirthProfile] = None
    chart_json: Any = {}


class AudioScriptResponse(BaseModel):
    audio_script: str
    audio_blocks: list[AudioBlock]
    estimated_duration_minutes: float
    metadata: dict[str, Any] = {}


class VoiceSettings(BaseModel):
    stability: float = 0.5
    similarity_boost: float = 0.8
    style: float = 0.25
    use_speaker_boost: bool = True


class SignedUpload(BaseModel):
    bucket: str = "ancorada-audios"
    path: str = ""
    signed_url: str = ""
    token: str = ""


class GenerateAudioRequest(BaseModel):
    audio_blocks: list[AudioBlock]
    voice_id: str = ""
    model_id: str = "eleven_multilingual_v2"
    voice_settings: VoiceSettings = VoiceSettings()
    speed: float = 0.97
    customer_name: str = ""
    upload_mode: str = ""
    signed_upload: Optional[SignedUpload] = None
    audio_generation_id: str = ""


class GenerateAudioResponse(BaseModel):
    audio_base64: str = ""
    audio_url: str = ""
    uploaded: Optional[bool] = None
    storage_path: str = ""
    filename: str = ""
    mime_type: str = "audio/mpeg"
    audio_status: str = ""
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = {}
