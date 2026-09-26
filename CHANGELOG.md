# Changelog

## 0.4.0 — 2026-09-27

- **Word lookup card.** Selecting one English word (or one Chinese word with an English
  target) shows an offline entry from the Oxford English–Chinese dictionary that ships with
  macOS: UK/US phonetics with pronunciation, parts of speech, numbered senses, subject
  labels with science senses emphasised, and inflections resolved (inhibited → inhibit,
  ran → run). Terms missing from it fall back to English definitions plus the model's term
  translation; words in neither dictionary say so and show the model translation.
  See `docs/DICTIONARY_LOOKUP_2026-09-27.md`.
- **Interface language.** English (default) or Chinese, in Settings → General → Interface.
- Fixes: "&" in tab/menu labels, spare window height going to the source excerpt, and a
  startup crash introduced and fixed during the language change (never released).

## 0.3.0 — 2026-09-26

- Predictable reading window: new windows start unpinned, pinning changes the window level
  in place without flashing, and unpinned windows close on a click in or switch to another
  app in every translation state.
- Reading-first layout, state-dependent actions, explicit edit mode for typed input and OCR
  review, one-click About/Settings, Settings grouped into General / Speech / Model & Advanced.
- Windows open at a standard height; content-free window event trace in the log.
  See `docs/VALIDATION_UI_0.3.0_2026-09-26.md`.

## 0.2.1

- MiLMMT as the default translation model. See `docs/MILMMT_DEFAULT_2026-09-26.md`.
