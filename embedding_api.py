import os
import json
from typing import List, Union, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


def load_config():
    config_path = os.path.join(os.path.dirname(
        __file__), "./configs/config.json")
    with open(config_path, "r", encoding="utf8") as f:
        return json.load(f)


config = load_config()

app = FastAPI(title="Embedding API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str], List[int], List[List[int]]]
    model: Optional[str] = None
    encoding_format: Optional[str] = "float"


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: UsageInfo


_models_initialized = False
_model = None


def get_model():
    global _models_initialized, _model
    if not _models_initialized:
        from sentence_transformers import SentenceTransformer
        model_path = config["llm"]["embedding_model"]
        _model = SentenceTransformer(model_path)
        _models_initialized = True
    return _model


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "bge-small-zh-v1.5",
                "object": "model",
                "created": 1700000000,
                "owned_by": "embedding-api",
            }
        ]
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    request: EmbeddingRequest,
):
    try:
        model = get_model()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load model: {str(e)}")

    inputs = request.input
    if isinstance(inputs, str):
        texts = [inputs]
    elif isinstance(inputs, list):
        texts = [t if isinstance(t, str) else str(t) for t in inputs]
    else:
        texts = [str(inputs)]

    try:
        embeddings = model.encode(  # type:ignore
            texts, normalize_embeddings=True)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Embedding failed: {str(e)}")

    data = []
    for i, emb in enumerate(embeddings):
        data.append(
            EmbeddingData(
                object="embedding",
                index=i,
                embedding=emb.tolist(),
            )
        )

    return EmbeddingResponse(
        object="list",
        data=data,
        model=request.model or "bge-small-zh-v1.5",
        usage=UsageInfo(prompt_tokens=0, total_tokens=0),
    )


if __name__ == "__main__":
    get_model()  # Load the model at startup
    uvicorn.run(app, host="127.0.0.1", port=8002)
