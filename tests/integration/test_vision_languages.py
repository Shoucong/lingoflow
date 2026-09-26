"""Real Apple Vision recognition of Chinese, mixed and English text (macOS only)."""

import difflib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.macos

FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
SAMPLES = {
    "chinese": [
        "蛋白激酶调控大多数细胞通路，尤其是信号转导。",
        "我们测量了十二种抑制剂的结合亲和力。",
    ],
    "mixed": ["见参考文献 [12] 与图 3 的数据。", "Transformer 模型的等变性分析"],
    "english": [
        "Protein kinases regulate most cellular pathways.",
        "Keep value 12.5 and citation [12].",
    ],
}


@pytest.fixture(scope="module")
def recognize(tmp_path_factory):
    if sys.platform != "darwin" or not FONT.exists():
        pytest.skip("Apple Vision and a system Chinese font are required")
    from PIL import Image, ImageDraw, ImageFont

    from lingoflow.config.settings import AppSettings
    from lingoflow.infrastructure.macos.ocr import OCRService

    settings = AppSettings()  # default OCR language: English + Chinese
    settings.ocr.enhance_image = False
    service = OCRService(settings)
    directory = tmp_path_factory.mktemp("vision")

    def run(lines, size=18):
        font = ImageFont.truetype(str(FONT), size)
        width = 40 + max(int(font.getlength(line)) for line in lines)
        image = Image.new("RGB", (width, 30 + len(lines) * int(size * 1.6)), "white")
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(lines):
            draw.text((20, 15 + index * int(size * 1.6)), line, font=font, fill="black")
        path = directory / f"{abs(hash(tuple(lines)))}.png"
        image.save(path)
        result = service.extract_text(path)
        assert result.success
        truth = "".join(lines).replace(" ", "")
        text = result.text.replace("\n", "").replace(" ", "")
        return difflib.SequenceMatcher(None, truth, text).ratio()

    return run


@pytest.mark.parametrize("kind", ["chinese", "mixed", "english"])
def test_default_ocr_languages_read_chinese_mixed_and_english_text(recognize, kind):
    # With English listed first, Chinese-only text was not recognized at all.
    assert recognize(SAMPLES[kind]) >= 0.9
