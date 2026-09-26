"""Render a dictionary lookup as a compact word card (Qt rich text).

Layout, borrowing from reading tools people already know:
- headword and a "form of" note (ran → run), as in macOS Look Up and Eudic;
- a phonetics row with UK/US pronunciation links, as in Bob and Easydict;
- part-of-speech tags, numbered senses, subject labels, one example per sense;
- senses labelled with a science subject are emphasised for paper reading;
- a small, clearly labelled model gloss, and the dictionary name as the source.

Long entries show the first senses of each part of speech with a "more" link.
"""

from __future__ import annotations

from html import escape

from lingoflow.core.dictionary import (
    DictionaryEntry,
    DictionaryResult,
    Pronunciation,
    Sense,
    word_script,
)
from lingoflow.i18n import current_language, tr

# First part of speech of the main entry, later parts, and secondary entries.
SENSES_SHOWN = 3
LATER_PART_SENSES_SHOWN = 2
SECONDARY_SENSES_SHOWN = 2
SCIENCE_DOMAINS = {
    "Anatomy",
    "Astronomy",
    "Biochemistry",
    "Biology",
    "Botany",
    "Chemistry",
    "Computing",
    "Ecology",
    "Electricity",
    "Electronics",
    "Genetics",
    "Geology",
    "Immunology",
    "Mathematics",
    "Medicine",
    "Microbiology",
    "Pharmacology",
    "Pharmacy",
    "Physics",
    "Physiology",
    "Psychology",
    "Statistics",
    "Zoology",
    "Neurology",
    "Pathology",
}
DOMAIN_NAMES = {
    "Anatomy": "解剖",
    "Astronomy": "天文",
    "Biochemistry": "生化",
    "Biology": "生物",
    "Botany": "植物",
    "Chemistry": "化学",
    "Computing": "计算机",
    "Ecology": "生态",
    "Electricity": "电学",
    "Electronics": "电子",
    "Genetics": "遗传",
    "Geology": "地质",
    "Immunology": "免疫",
    "Mathematics": "数学",
    "Medicine": "医学",
    "Microbiology": "微生物",
    "Pharmacology": "药理",
    "Pharmacy": "药学",
    "Physics": "物理",
    "Physiology": "生理",
    "Psychology": "心理",
    "Statistics": "统计",
    "Zoology": "动物",
    "Neurology": "神经",
    "Pathology": "病理",
    "Finance": "金融",
    "Law": "法律",
    "Politics": "政治",
    "Sociology": "社会学",
    "Farming": "农业",
    "Railways": "铁路",
    "Transport": "交通",
    "Aviation": "航空",
    "Telecommunications": "电信",
    "Radio": "广播",
    "Television": "电视",
    "Music": "音乐",
    "Sport": "体育",
    "Military": "军事",
    "Motor Vehicles": "汽车",
}
PART_NAMES = {
    "noun": "名词",
    "verb": "动词",
    "transitive verb": "及物动词",
    "intransitive verb": "不及物动词",
    "adjective": "形容词",
    "adverb": "副词",
    "preposition": "介词",
    "conjunction": "连词",
    "pronoun": "代词",
    "exclamation": "感叹词",
    "abbreviation": "缩写",
    "prefix": "前缀",
    "suffix": "后缀",
    "determiner": "限定词",
    "modal verb": "情态动词",
    "auxiliary verb": "助动词",
    "plural noun": "复数名词",
    "past tense": "过去式",
    "past participle": "过去分词",
    "plural": "复数",
    "present participle": "现在分词",
    "comparative": "比较级",
    "superlative": "最高级",
}


def _domain(name: str) -> str:
    return DOMAIN_NAMES.get(name, name) if current_language() == "zh" else name


def _part(label: str) -> str:
    if current_language() != "zh" or not label:
        return label
    return "，".join(PART_NAMES.get(piece.strip(), piece.strip()) for piece in label.split(","))


def _is_science(sense: Sense) -> bool:
    return any(domain in SCIENCE_DOMAINS for domain in sense.domains)


def _speak_links(entry: DictionaryEntry, colors: dict[str, str]) -> str:
    links = []
    # Variants for the same accent share one link: "/ˈkīˌnās, ˈkiˌnās/".
    grouped: dict[str, list[str]] = {}
    for pronunciation in entry.pronunciations:
        grouped.setdefault(pronunciation.dialect, []).append(pronunciation.ipa)
    for dialect, variants in list(grouped.items())[:2]:
        pronunciation = Pronunciation(dialect, ", ".join(variants[:2]))
        if dialect == "BrE":
            label, locale = tr("UK", "英"), "en-GB"
        elif dialect == "AmE":
            label, locale = tr("US", "美"), "en-US"
        else:
            # No accent given: speak Chinese headwords in Chinese, everything else in English.
            label = ""
            locale = "zh-CN" if word_script(entry.headword) == "cjk" else "en-US"
        target = escape(entry.headword, quote=True)
        links.append(
            f"<span style='color:{colors['muted']}'>{label} </span>"
            f"<span style='color:{colors['source']}'>/{escape(pronunciation.ipa)}/</span> "
            f"<a href='speak:{locale}:{target}' style='text-decoration:none;"
            f"color:{colors['accent']}'>🔊</a>"
        )
    return "&nbsp;&nbsp;&nbsp;".join(links)


def _sense_row(
    sense: Sense, colors: dict[str, str], bilingual: bool, with_example: bool = True
) -> str:
    science = _is_science(sense)
    chips = "".join(
        f"<span style='background-color:{colors['accent_soft'] if science else colors['hover']};"
        f"color:{colors['accent'] if domain in SCIENCE_DOMAINS else colors['muted']}'>"
        f"&nbsp;{escape(_domain(domain))}&nbsp;</span> "
        for domain in sense.domains
    )
    meaning = "；".join(sense.translations) if bilingual else sense.definition
    weight = "600" if science else "normal"
    body = f"{chips}<span style='font-weight:{weight}'>{escape(meaning)}</span>"
    if sense.indicator:
        body += f" <span style='color:{colors['muted']}'>({escape(sense.indicator)})</span>"
    if sense.examples and with_example:
        example = sense.examples[0]
        body += (
            f"<br><span style='color:{colors['muted']}'>▸ {escape(example.source)}"
            f"{'　' + escape(example.translation) if example.translation else ''}</span>"
        )
    number = escape(sense.number) if sense.number else "•"
    return (
        f"<tr><td style='color:{colors['muted']};padding-right:6px' valign='top'>{number}</td>"
        f"<td style='padding-bottom:4px'>{body}</td></tr>"
    )


def _entry_html(
    entry: DictionaryEntry,
    index: int,
    result: DictionaryResult,
    colors: dict[str, str],
    font: int,
    expanded: set[str],
    primary: bool,
    gloss_line: str = "",
) -> str:
    size = font + 8 if primary else font + 2
    html = [
        f"<p style='margin:0'><span style='font-size:{size}px;font-weight:600'>"
        f"{escape(entry.headword)}</span></p>"
    ]
    query = result.query
    if entry.form_of:
        label, form = entry.form_of
        note = tr(
            "{form} is the {label} of {headword}",
            "{form} 是 {headword} 的{label}",
            form=form,
            label=_part(label) or tr("form", "变形"),
            headword=entry.headword,
        )
        html.append(f"<p style='margin:2px 0;color:{colors['muted']}'>{escape(note)}</p>")
    elif primary and entry.headword.casefold() != query.casefold():
        # The dictionary index mapped the selected form to this headword.
        html.append(
            f"<p style='margin:2px 0;color:{colors['muted']}'>"
            f"{escape(query)} → {escape(entry.headword)}</p>"
        )
    phonetics = _speak_links(entry, colors)
    if phonetics:
        html.append(f"<p style='margin:4px 0 6px 0'>{phonetics}</p>")
    html.append(gloss_line)
    for part_index, part in enumerate(entry.parts):
        key = f"{index}:{part_index}"
        if not primary:
            limit = SECONDARY_SENSES_SHOWN
        else:
            limit = SENSES_SHOWN if part_index == 0 else LATER_PART_SENSES_SHOWN
        senses = part.senses if key in expanded else part.senses[:limit]
        if part.label:
            html.append(
                f"<p style='margin:6px 0 2px 0'><span style='color:{colors['accent']};"
                f"font-style:italic'>{escape(_part(part.label))}</span></p>"
            )
        # One example per part of speech keeps long entries (run, set) scannable.
        rows = "".join(
            _sense_row(s, colors, result.bilingual, with_example=i == 0 or key in expanded)
            for i, s in enumerate(senses)
        )
        html.append(f"<table cellspacing='0' cellpadding='0'>{rows}</table>")
        hidden = len(part.senses) - len(senses)
        if hidden > 0:
            html.append(
                f"<p style='margin:0 0 4px 0'><a href='more:{key}' style='text-decoration:none;"
                f"color:{colors['accent']}'>"
                f"{escape(tr('{count} more senses', '另有 {count} 个义项', count=hidden))}</a></p>"
            )
    return "".join(html)


def render_card(
    result: DictionaryResult,
    colors: dict[str, str],
    font: int,
    gloss: str = "",
    gloss_state: str = "none",
    expanded: set[str] | None = None,
) -> str:
    """Return Qt rich text for the card; ``gloss_state`` is none/pending/done/failed."""
    expanded = expanded or set()
    html = [f"<div style='font-size:{font}px;color:{colors['text']}'>"]
    gloss_line = _gloss_html(result, colors, font, gloss, gloss_state)
    for index, entry in enumerate(result.entries):
        if index:
            html.append(f"<hr style='border:none;background-color:{colors['border']}'>")
        # Without a bilingual entry the model's term translation is the answer, so it
        # sits right under the headword; otherwise it is a footnote.
        lead = gloss_line if index == 0 and not result.bilingual else ""
        html.append(
            _entry_html(entry, index, result, colors, font, expanded, index == 0, lead)
        )
    if not result.entries:
        note = tr(
            "Not in the macOS dictionaries; translated by the model.",
            "系统词典未收录此词，以下为模型翻译。",
        )
        html.append(
            f"<p style='margin:0'><span style='font-size:{font + 8}px;font-weight:600'>"
            f"{escape(result.query)}</span></p>"
            f"<p style='margin:2px 0 6px 0;color:{colors['muted']}'>{escape(note)}</p>"
            f"{gloss_line}"
        )
    if result.bilingual and gloss_line:
        html.append(gloss_line)
    if result.source_name:
        html.append(
            f"<p style='margin-top:8px;color:{colors['muted']};font-size:{max(10, font - 3)}px'>"
            f"{escape(tr('Source: {name}', '来源：{name}', name=result.source_name))}</p>"
        )
    html.append("</div>")
    return "".join(html)


def _gloss_html(
    result: DictionaryResult, colors: dict[str, str], font: int, gloss: str, state: str
) -> str:
    if state == "none":
        return ""
    if state == "pending":
        value = tr("translating…", "正在翻译…")
    elif state == "failed" or not gloss.strip():
        value = tr("unavailable", "暂不可用")
    else:
        value = gloss.strip()
    if result.bilingual:
        label = tr("Model gloss (no sentence context)", "模型译法（无上下文，仅供参考）")
        return (
            f"<p style='margin-top:8px;color:{colors['muted']}'>{escape(label)}："
            f"<span style='color:{colors['text']}'>{escape(value)}</span></p>"
        )
    label = tr("Model translation", "模型译名")
    return (
        f"<p style='margin:2px 0 6px 0'>"
        f"<span style='color:{colors['muted']}'>{escape(label)}</span>"
        f"&nbsp;&nbsp;<span style='font-size:{font + 6}px;font-weight:600'>"
        f"{escape(value)}</span></p>"
    )
