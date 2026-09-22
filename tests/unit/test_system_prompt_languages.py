import json
from dataclasses import asdict
from pathlib import Path

from shotmill.application.application_settings import ApplicationSettingsStore
from shotmill.domain.application_settings import DEFAULT_SYSTEM_PROMPT_PRESETS
from shotmill.prompt_skills.minimax_h3_system_prompt import (
    CHINESE_H3_SYSTEM_PROMPT,
    DEFAULT_H3_SYSTEM_PROMPT,
    H3_CHINESE_LANGUAGE_REPLACEMENTS,
    LEGACY_CHINESE_H3_SYSTEM_PROMPT,
    LEGACY_H3_SYSTEM_PROMPT,
)


def test_language_variants_only_change_language_requirements():
    restored = CHINESE_H3_SYSTEM_PROMPT
    for english, chinese in reversed(H3_CHINESE_LANGUAGE_REPLACEMENTS):
        assert english in DEFAULT_H3_SYSTEM_PROMPT
        assert chinese in restored
        restored = restored.replace(chinese, english)
    assert restored == DEFAULT_H3_SYSTEM_PROMPT
    assert len(DEFAULT_SYSTEM_PROMPT_PRESETS) == 2
    frontend = Path(__file__).parents[2] / "frontend/src/features/settings/systemPromptPresets.json"
    assert json.loads(frontend.read_text(encoding="utf-8")) == [
        asdict(p) for p in DEFAULT_SYSTEM_PROMPT_PRESETS
    ]


def test_old_default_migrates_without_changing_active_prompt(tmp_path):
    path = tmp_path / "settings.json"
    legacy = asdict(DEFAULT_SYSTEM_PROMPT_PRESETS[0])
    legacy["name"] = "MiniMax H3 默认"
    path.write_text(
        json.dumps(
            {
                "prompt_system": {
                    "system_prompt": "custom active prompt",
                    "system_prompt_presets": [legacy],
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = ApplicationSettingsStore(path).get_prompt_system()
    assert loaded.system_prompt_presets == DEFAULT_SYSTEM_PROMPT_PRESETS
    assert loaded.system_prompt == "custom active prompt"
    legacy["prompt"] = "user edited preset"
    path.write_text(
        json.dumps({"prompt_system": {"system_prompt_presets": [legacy]}}), encoding="utf-8"
    )
    loaded = ApplicationSettingsStore(path).get_prompt_system()
    assert len(loaded.system_prompt_presets) == 1
    assert loaded.system_prompt_presets[0].prompt == "user edited preset"


def test_director_upgrade_preserves_h3_protocol_and_migrates_only_untouched_defaults(tmp_path):
    for old, new in (
        (LEGACY_H3_SYSTEM_PROMPT, DEFAULT_H3_SYSTEM_PROMPT),
        (LEGACY_CHINESE_H3_SYSTEM_PROMPT, CHINESE_H3_SYSTEM_PROMPT),
    ):
        assert old in new
        assert "W.分镜脚本大师" in new
        assert "cause -> physical process -> outcome" in " ".join(new.split())
        assert "15 seconds" in new
        assert "driver's seat" in new
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"prompt_system": {"system_prompt": old}}), encoding="utf-8")
        assert ApplicationSettingsStore(path).get_prompt_system().system_prompt == new
        path.write_text(json.dumps({"prompt_system": {"system_prompt": old + " CUSTOM"}}),
                        encoding="utf-8")
        assert ApplicationSettingsStore(path).get_prompt_system().system_prompt == old + " CUSTOM"


def test_director_preset_upgrade_keeps_user_edits_and_custom_presets(tmp_path):
    path = tmp_path / "settings.json"
    presets = [
        {"id": "minimax-h3-default", "name": "英文", "prompt": LEGACY_H3_SYSTEM_PROMPT},
        {"id": "minimax-h3-chinese", "name": "中文", "prompt": "我的修改"},
        {"id": "my-copy", "name": "保留的副本", "prompt": LEGACY_H3_SYSTEM_PROMPT},
    ]
    path.write_text(json.dumps({"prompt_system": {
        "system_prompt": "我当前的规则", "system_prompt_presets": presets,
    }}), encoding="utf-8")
    loaded = ApplicationSettingsStore(path).get_prompt_system()
    assert loaded.system_prompt == "我当前的规则"
    assert [p.prompt for p in loaded.system_prompt_presets] == [
        DEFAULT_H3_SYSTEM_PROMPT, "我的修改", LEGACY_H3_SYSTEM_PROMPT,
    ]
