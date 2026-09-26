#!/usr/bin/env python3
"""Compare Apple Vision language settings on rendered Chinese, mixed and English text.

Usage: probe_ocr_languages.py OUTPUT_DIR FONT_PATH
Prints character accuracy against the rendered text for each configuration.
"""

import difflib
import sys
from pathlib import Path

import Vision
from Cocoa import NSURL
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

out = Path(sys.argv[1])
out.mkdir(exist_ok=True)
FONT = sys.argv[2]
samples = {
    "zh": ["蛋白激酶调控大多数细胞通路，尤其是信号转导。", "我们测量了十二种抑制剂的结合亲和力。"],
    "mixed": [
        "图 3：IC50 = 12.5 ± 0.3 nM，见参考文献 [12]。",
        "Transformer 模型的等变性（equivariance）分析",
    ],
    "en": [
        "Protein kinases regulate most cellular pathways.",
        "Keep value 12.5 and citation [12].",
    ],
}


def render(lines, size):
    font = ImageFont.truetype(FONT, size)
    img = Image.new(
        "RGB",
        (40 + max(int(font.getlength(line)) for line in lines), 30 + len(lines) * int(size * 1.6)),
        "white",
    )
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((20, 15 + i * int(size * 1.6)), line, font=font, fill="black")
    return img


def enhance(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = img.filter(ImageFilter.SHARPEN)
    if min(img.size) < 300:
        s = 300 / min(img.size)
        img = img.resize((int(img.size[0] * s), int(img.size[1] * s)), Image.Resampling.LANCZOS)
    return img


def ocr(path, langs, auto=False):
    h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        NSURL.fileURLWithPath_(str(path)), None
    )
    r = Vision.VNRecognizeTextRequest.alloc().init()
    r.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    r.setUsesLanguageCorrection_(True)
    if langs:
        r.setRecognitionLanguages_(langs)
    if auto:
        r.setAutomaticallyDetectsLanguage_(True)
    h.performRequests_error_([r], None)
    obs = r.results() or []
    return "\n".join(o.topCandidates_(1)[0].string() for o in obs), (
        sum(o.topCandidates_(1)[0].confidence() for o in obs) / len(obs) if obs else 0
    )


configs = [
    ("en,zh (0.4.0)", ["en-US", "zh-Hans"], False),
    ("zh,en", ["zh-Hans", "en-US"], False),
    ("auto", [], True),
    ("zh,en+auto", ["zh-Hans", "en-US"], True),
]
print(
    "supported:",
    list(
        Vision.VNRecognizeTextRequest.alloc()
        .init()
        .supportedRecognitionLanguagesAndReturnError_(None)[0]
    )[:12],
)
for name, lines in samples.items():
    for size in (28, 16):
        img = render(lines, size)
        p = out / f"{name}-{size}.png"
        img.save(p)
        pe = out / f"{name}-{size}-enh.png"
        enhance(img).save(pe)
        truth = "\n".join(lines)
        for cname, langs, auto in configs:
            for label, path in (("original", p), ("enhanced", pe)):
                text, conf = ocr(path, langs, auto)
                acc = difflib.SequenceMatcher(
                    None, truth.replace(" ", ""), text.replace(" ", "")
                ).ratio()
                print(
                    f"{name:5} {size}px {cname:12} {label} accuracy {acc:5.0%} "
                    f"confidence {conf:4.0%} | {text.replace(chr(10), ' / ')[:60]}"
                )
