"""
Aethvion Suite — Audio Model Registry
Central registry of all available local audio model classes.
"""
from typing import Dict, Optional, Type
from .base import LocalAudioModel
from .kokoro import KokoroModel
from .xtts import XTTSv2Model
from .whisper_model import WhisperModel

_REGISTRY: Dict[str, Type[LocalAudioModel]] = {
    KokoroModel.MODEL_ID:  KokoroModel,
    XTTSv2Model.MODEL_ID:  XTTSv2Model,
    WhisperModel.MODEL_ID: WhisperModel,
}


def get_all_model_classes() -> Dict[str, Type[LocalAudioModel]]:
    return dict(_REGISTRY)


def get_model_class(model_id: str) -> Optional[Type[LocalAudioModel]]:
    return _REGISTRY.get(model_id)
