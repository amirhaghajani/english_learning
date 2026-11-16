from app.audio.stt import SpeechToText, get_stt
from app.audio.tts import SpeechSynth, get_tts
from app.db import get_session
from app.llm.base import TutorLLM
from app.llm.factory import get_llm

get_db = get_session


def get_stt_dep() -> SpeechToText:
    return get_stt()


def get_llm_dep() -> TutorLLM:
    return get_llm()


def get_tts_dep() -> SpeechSynth:
    return get_tts()