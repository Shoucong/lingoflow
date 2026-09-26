"""Model-specific translation formats, independent of UI and transport."""

from lingoflow.config.constants import MILMMT_MODEL as MILMMT_MODEL
from lingoflow.config.constants import SUPPORTED_LANGUAGES
from lingoflow.core.errors import TranslationError


def is_milmmt_model(model: str) -> bool:
    name = model.rsplit("/", 1)[-1].split(":", 1)[0].casefold()
    return name in {"milmmt-46-4b-v1.0", "milmmt-46-4b-v1.0-gguf"}


def milmmt_prompt(text: str, source: str, target: str) -> str:
    """Use the exact language names and completion format from xiaomi-research/gemmax."""
    names = {
        "Chinese(Simplified)": "Chinese (Simplified)",
        "Chinese(Traditional)": "Chinese (Traditional)",
    }
    if source == "auto" or source not in SUPPORTED_LANGUAGES:
        raise TranslationError("Choose the Text Source language in Settings → Languages.")
    if target == "auto" or target not in SUPPORTED_LANGUAGES:
        raise TranslationError("Choose a supported Translate To language in Settings → Languages.")
    source, target = names.get(source, source), names.get(target, target)
    return f"Translate this from {source} to {target}:\n{source}: {text}\n{target}:"


def milmmt_options() -> dict:
    # Official greedy decoding. Avoid Ollama's implicit repetition penalty and chat stops.
    return {
        "temperature": 0,
        "top_k": 1,
        "repeat_penalty": 1.0,
        "stop": ["<eos>", "<end_of_turn>"],
    }
