from __future__ import annotations

import json
import sys
import textwrap

import pytest
from PyQt6.QtGui import QTextCursor

from lingoflow.config.settings import AppSettings
from lingoflow.core.speech import SpeechRequest
from lingoflow.infrastructure.macos.speech import MacOSSpeechService
from lingoflow.ui.popup import TranslationPopup


@pytest.fixture
def speech(qapp, tmp_path):
    log = tmp_path / "spoken.jsonl"
    program = tmp_path / "fake-say"
    program.write_text(f"#!{sys.executable}\n" + textwrap.dedent(f"""\
        import json, sys, time
        if '?' in sys.argv:
            time.sleep(0.05)
            print('Samantha en_US # Hello')
            print('Daniel en_GB # Hello')
            print('Tingting zh_CN # Hello')
        else:
            text = sys.stdin.read()
            with open({str(log)!r}, 'a') as output:
                output.write(json.dumps({{'text': text, 'args': sys.argv[1:]}}) + '\\n')
            time.sleep(30)
        """))
    program.chmod(0o700)
    service = MacOSSpeechService(program=str(program))
    yield service, log
    service.shutdown()


def entries(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_replacing_and_stopping_speech_uses_only_owned_process(speech, qtbot):
    service, log = speech
    service.speak(SpeechRequest("panel", "source", 'a "quoted" word', "en-US"))
    qtbot.waitUntil(lambda: len(entries(log)) == 1)
    service.speak(SpeechRequest("panel", "translation", "你好", "zh-CN", rate=140))
    qtbot.waitUntil(lambda: len(entries(log)) == 2)
    assert [entry["text"] for entry in entries(log)] == ['a "quoted" word', "你好"]
    assert entries(log)[1]["args"] == ["-v", "Tingting", "-r", "140", "-f", "-"]
    service.stop("panel")
    qtbot.waitUntil(lambda: service._player.processId() == 0)
    assert service.current is None and service.pending is None


def test_stop_during_voice_lookup_never_starts_playback(speech, qtbot):
    service, log = speech
    service.speak(SpeechRequest("panel", "source", "do not speak", "en-US"))
    service.stop("panel")
    qtbot.waitUntil(lambda: bool(service.voices))
    assert not log.exists()


def test_missing_voice_is_reported_without_wrong_language_fallback(speech, qtbot):
    service, log = speech
    with qtbot.waitSignal(service.failed) as failure:
        service.speak(SpeechRequest("panel", "source", "bonjour", "fr-FR"))
    assert failure.args[0] == "panel"
    assert "fr-FR" in failure.args[1]
    assert not log.exists()


def test_popup_speaks_source_selection_in_configured_accent(speech, qtbot, monkeypatch, tmp_path):
    service, log = speech
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    settings = AppSettings()
    settings.ui.hide_on_focus_loss = False
    settings.speech.source_locale = "en-GB"
    popup = TranslationPopup(settings, tmp_path / "geometry.json", service)
    qtbot.addWidget(popup)
    popup.show_with_text("one pronunciation word")
    cursor = popup.source_text.textCursor()
    cursor.setPosition(4)
    cursor.setPosition(17, QTextCursor.MoveMode.KeepAnchor)
    popup.source_text.setTextCursor(cursor)
    popup.start_translation()
    popup.speak_source_btn.click()
    qtbot.waitUntil(lambda: len(entries(log)) == 1)
    assert entries(log)[0]["text"] == "pronunciation"
    assert entries(log)[0]["args"][1] == "Daniel"
    assert popup.source_text.textCursor().selectedText() == "pronunciation"
    popup.append_translation("你好")
    popup.finish_translation()
    popup.speak_translation_btn.click()
    qtbot.waitUntil(lambda: len(entries(log)) == 2)
    assert entries(log)[1]["text"] == "你好"
    assert entries(log)[1]["args"][1] == "Tingting"
    popup.close()
    qtbot.waitUntil(lambda: service._player.processId() == 0)
