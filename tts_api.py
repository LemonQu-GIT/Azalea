import os
import json
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn


def load_config():
    config_path = os.path.join(os.path.dirname(
        __file__), "./configs/config.json")
    with open(config_path, "r", encoding="utf8") as f:
        return json.load(f)


config = load_config()
tts_config = config.get("tts", {})

if tts_config.get("genie_data_dir"):
    os.environ["GENIE_DATA_DIR"] = os.path.abspath(
        tts_config["genie_data_dir"])

app = FastAPI(title="TTS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    character_name: Optional[str] = Field(
        None, description="Character name to use, defaults to config value")
    language: Optional[str] = Field(
        None, description="Language override: 'zh', 'en', 'jp', 'kr'")


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    character_name: str
    language: str
    onnx_model_dir: str


class HealthResponse(BaseModel):
    status: str
    character_loaded: bool
    character_name: Optional[str] = None


_genie = None
_character_loaded = False
_loaded_character_name = None


def import_genie():
    import genie_tts as genie
    return genie


def get_genie():
    global _genie, _character_loaded, _loaded_character_name
    if _genie is None:
        try:
            _genie = import_genie()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import genie_tts: {str(e)}"
            )
    if not _character_loaded:
        character_name = tts_config.get("character_name", "WeiHua")
        onnx_model_dir = os.path.abspath(tts_config.get(
            "onnx_model_dir", "./data/onnx_mika"))
        language = tts_config.get("language", "zh")
        ref_audio_path = os.path.abspath(tts_config.get(
            "reference_audio_path", "./data/onnx_mika/reference_audio/mika_normal.wav"))
        ref_audio_text = tts_config.get("reference_audio_text", "")

        try:
            _genie.load_character(
                character_name=character_name,
                onnx_model_dir=onnx_model_dir,
                language=language,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load character '{character_name}': {str(e)}"
            )

        try:
            _genie.set_reference_audio(
                character_name=character_name,
                audio_path=ref_audio_path,
                audio_text=ref_audio_text,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set reference audio: {str(e)}"
            )

        _character_loaded = True
        _loaded_character_name = character_name

    return _genie


def cleanup_temp_file(path: str):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


@app.get("/v1/tts/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        character_loaded=_character_loaded,
        character_name=_loaded_character_name,
    )


@app.get("/v1/tts/models")
async def list_models():
    character_name = tts_config.get("character_name", "WeiHua")
    onnx_model_dir = tts_config.get("onnx_model_dir", "./data/onnx_mika")
    language = tts_config.get("language", "zh")
    return {
        "object": "list",
        "data": [
            {
                "id": character_name,
                "object": "model",
                "character_name": character_name,
                "language": language,
                "onnx_model_dir": onnx_model_dir,
            }
        ]
    }


@app.post("/v1/tts/reload")
async def reload_character():
    global _character_loaded, _loaded_character_name, _genie
    _character_loaded = False
    _loaded_character_name = None
    _genie = None
    try:
        get_genie()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload character: {str(e)}"
        )
    return {
        "success": True,
        "message": f"Character '{_loaded_character_name}' reloaded successfully",
        "character_name": _loaded_character_name,
    }


@app.post("/v1/tts")
async def synthesize(request: TTSRequest, background_tasks: BackgroundTasks):
    try:
        genie = get_genie()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to initialize TTS: {str(e)}")

    character_name = request.character_name or tts_config.get(
        "character_name", "WeiHua")

    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=f"_{uuid.uuid4().hex[:12]}.wav", prefix="tts_")
    os.close(tmp_fd)

    try:
        genie.tts(
            character_name=character_name,
            text=request.text,
            save_path=tmp_path,
        )
    except Exception as e:
        cleanup_temp_file(tmp_path)
        raise HTTPException(
            status_code=500, detail=f"TTS synthesis failed: {str(e)}")

    if not os.path.isfile(tmp_path):
        cleanup_temp_file(tmp_path)
        raise HTTPException(
            status_code=500,
            detail="Audio file was not generated at expected path"
        )

    file_name = f"tts_{uuid.uuid4().hex[:12]}.wav"
    background_tasks.add_task(cleanup_temp_file, tmp_path)

    return FileResponse(
        path=tmp_path,
        media_type="audio/wav",
        filename=file_name,
    )


if __name__ == "__main__":
    host = tts_config.get("host", "127.0.0.1")
    port = int(tts_config.get("port", 8003))
    get_genie()
    uvicorn.run(app, host=host, port=port)
