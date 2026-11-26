"""Package-layout and compatibility checks for the animation subsystem."""

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_animation_implementation_is_grouped_under_package():
    modules = (
        "app.animations.rules",
        "app.animations.hints",
        "app.animations.runtime",
        "app.animations.stop",
    )
    for name in modules:
        module = importlib.import_module(name)
        assert Path(module.__file__).is_file()
        assert "app/animations/" in module.__file__.replace("\\", "/")

    root = Path(__file__).resolve().parents[2] / "app" / "animations"
    assert (root / "chooser.py").is_file()
    assert (root / "settings" / "page.py").is_file()
    assert (root / "settings" / "properties.py").is_file()


def test_legacy_import_paths_resolve_to_canonical_implementations():
    from app import anims, anims_hints, anims_rules, anims_runtime, anims_stop
    from app.animations import Rule, Runner, plan
    from app.animations import hints, rules, runtime, stop

    assert anims.Rule is Rule
    assert anims.Runner is Runner
    assert anims.plan is plan
    assert anims_rules.Rule is rules.Rule
    assert anims_runtime.Runner is runtime.Runner
    assert anims_runtime.plan is runtime.plan
    assert anims_hints.suggestions is hints.suggestions
    assert anims_stop.StopWatcher is stop.StopWatcher


def test_legacy_ui_paths_resolve_when_qt_is_available():
    try:
        old_chooser = importlib.import_module("app.animchoice")
        new_chooser = importlib.import_module("app.animations.chooser")
        old_page = importlib.import_module("app.settings_anims_ui")
        new_page = importlib.import_module("app.animations.settings.page")
        old_properties = importlib.import_module("app.settings_anim_props")
        new_properties = importlib.import_module("app.animations.settings.properties")
    except (ImportError, OSError) as error:
        if os.environ.get("RPCHAT_REQUIRE_QT_TESTS") == "1":
            raise
        pytest.skip(f"Qt runtime is unavailable: {error}")

    assert old_chooser.ChoiceWindow is new_chooser.ChoiceWindow
    assert old_page.AnimationsSettingsMixin is new_page.AnimationsSettingsMixin
    assert old_properties.AnimProps is new_properties.AnimProps
    assert old_properties.ask_anim_props is new_properties.ask_anim_props
