"""Tests for models/button_config.py - Button configuration helpers."""

import pytest
from models.button_config import (
    parse_time_slot,
    validate_program_button_args,
    build_scene_cycle_config,
    build_time_based_config,
    build_single_scene_config,
    build_dimming_config,
    build_long_press_config,
    find_button_rid_for_control_id,
)


class TestParseTimeSlot:
    """Test time slot parsing."""

    def test_valid_time_slot(self):
        """Valid time slot should parse correctly."""
        hour, minute, scene = parse_time_slot("07:30=Morning")
        assert hour == 7
        assert minute == 30
        assert scene == "Morning"

    def test_valid_time_slot_with_spaces(self):
        """Time slot with spaces around scene name should trim."""
        hour, minute, scene = parse_time_slot("14:00=  Afternoon  ")
        assert hour == 14
        assert minute == 0
        assert scene == "Afternoon"

    def test_missing_equals(self):
        """Time slot without equals should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid slot format.*Expected HH:MM=SceneName"):
            parse_time_slot("07:30Morning")

    def test_missing_colon(self):
        """Time slot without colon should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid time format.*Expected HH:MM"):
            parse_time_slot("0730=Morning")

    def test_invalid_hour(self):
        """Hour > 23 should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid hour.*Must be 0-23"):
            parse_time_slot("25:00=Evening")

    def test_negative_hour(self):
        """Negative hour should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid hour.*Must be 0-23"):
            parse_time_slot("-1:00=Night")

    def test_invalid_minute(self):
        """Minute > 59 should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid minute.*Must be 0-59"):
            parse_time_slot("12:60=Noon")

    def test_non_numeric_time(self):
        """Non-numeric time values should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid time values.*must be integers"):
            parse_time_slot("noon:30=Lunch")


class TestValidateProgramButtonArgs:
    """Test argument validation."""

    def test_no_actions_specified(self):
        """No actions should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=False, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert not is_valid
        assert "Must specify at least one action" in msg

    def test_multiple_short_press_actions(self):
        """Multiple short-press actions should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes="A,B", time_based=False, slot=(), scene="C",
            dim_up=False, dim_down=False, long_press=None
        )
        assert not is_valid
        assert "Cannot specify multiple short-press actions" in msg

    def test_time_based_without_slots(self):
        """Time-based without slots should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=True, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert not is_valid
        assert "--time-based requires at least one --slot" in msg

    def test_slots_without_time_based(self):
        """Slots without time-based flag should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=False, slot=("07:00=Morning",), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert not is_valid
        assert "--slot requires --time-based flag" in msg

    def test_scenes_with_only_one_scene(self):
        """Scenes with only one scene should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes="OnlyOne", time_based=False, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert not is_valid
        assert "--scenes requires at least 2" in msg

    def test_both_dim_up_and_dim_down(self):
        """Both dim up and dim down should fail validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=False, slot=(), scene=None,
            dim_up=True, dim_down=True, long_press=None
        )
        assert not is_valid
        assert "Cannot specify both --dim-up and --dim-down" in msg

    def test_valid_scene_cycle(self):
        """Valid scene cycle should pass validation."""
        is_valid, msg = validate_program_button_args(
            scenes="A,B,C", time_based=False, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert is_valid
        assert msg is None

    def test_valid_time_based(self):
        """Valid time-based should pass validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=True, slot=("07:00=A", "12:00=B"), scene=None,
            dim_up=False, dim_down=False, long_press=None
        )
        assert is_valid
        assert msg is None

    def test_valid_single_scene(self):
        """Valid single scene should pass validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=False, slot=(), scene="Relax",
            dim_up=False, dim_down=False, long_press=None
        )
        assert is_valid
        assert msg is None

    def test_valid_long_press_only(self):
        """Valid long press only should pass validation."""
        is_valid, msg = validate_program_button_args(
            scenes=None, time_based=False, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press="All Off"
        )
        assert is_valid
        assert msg is None

    def test_valid_scene_with_long_press(self):
        """Valid scene with long press should pass validation."""
        is_valid, msg = validate_program_button_args(
            scenes="A,B", time_based=False, slot=(), scene=None,
            dim_up=False, dim_down=False, long_press="All Off"
        )
        assert is_valid
        assert msg is None


class TestBuildSceneCycleConfig:
    """Test scene cycle configuration builder."""

    def test_single_scene_cycle(self):
        """Build config for single scene in cycle."""
        config = build_scene_cycle_config(["scene-id-1"])

        assert 'on_short_release' in config
        assert 'scene_cycle_extended' in config['on_short_release']

        cycle = config['on_short_release']['scene_cycle_extended']
        assert cycle['repeat_timeout'] == {'seconds': 3}
        assert len(cycle['slots']) == 1
        assert cycle['slots'][0] == [{'action': {'recall': {'rid': 'scene-id-1', 'rtype': 'scene'}}}]

    def test_multiple_scene_cycle(self):
        """Build config for multiple scenes in cycle."""
        scene_ids = ["scene-1", "scene-2", "scene-3"]
        config = build_scene_cycle_config(scene_ids)

        slots = config['on_short_release']['scene_cycle_extended']['slots']
        assert len(slots) == 3

        # Each slot should be wrapped in a list
        for i, scene_id in enumerate(scene_ids):
            assert slots[i] == [{'action': {'recall': {'rid': scene_id, 'rtype': 'scene'}}}]


class TestBuildTimeBasedConfig:
    """Test time-based configuration builder."""

    def test_single_time_slot(self):
        """Build config for single time slot."""
        config = build_time_based_config([(7, 30, "scene-morning")])

        assert 'on_short_release' in config
        assert 'time_based_extended' in config['on_short_release']

        time_based = config['on_short_release']['time_based_extended']
        assert time_based['repeat_timeout'] == {'seconds': 3}
        assert len(time_based['slots']) == 1

        slot = time_based['slots'][0]
        assert slot['start_time'] == {'hour': 7, 'minute': 30}
        assert slot['actions'] == [{'action': {'recall': {'rid': 'scene-morning', 'rtype': 'scene'}}}]

    def test_multiple_time_slots_sorted(self):
        """Build config for multiple time slots, should be sorted by time."""
        slots = [(17, 0, "scene-evening"), (7, 0, "scene-morning"), (12, 30, "scene-afternoon")]
        config = build_time_based_config(slots)

        result_slots = config['on_short_release']['time_based_extended']['slots']
        assert len(result_slots) == 3

        # Should be sorted by time
        assert result_slots[0]['start_time'] == {'hour': 7, 'minute': 0}
        assert result_slots[1]['start_time'] == {'hour': 12, 'minute': 30}
        assert result_slots[2]['start_time'] == {'hour': 17, 'minute': 0}


class TestBuildSingleSceneConfig:
    """Test single scene configuration builder."""

    def test_single_scene(self):
        """Build config for single scene activation."""
        config = build_single_scene_config("scene-relax")

        assert 'on_short_release' in config
        assert 'recall_single_extended' in config['on_short_release']

        actions = config['on_short_release']['recall_single_extended']['actions']
        assert actions == [{'action': {'recall': {'rid': 'scene-relax', 'rtype': 'scene'}}}]


class TestBuildDimmingConfig:
    """Test dimming configuration builder."""

    def test_dim_up(self):
        """Build config for dim up."""
        config = build_dimming_config('dim_up')

        assert 'on_repeat' in config
        assert config['on_repeat'] == {'action': 'dim_up'}

    def test_dim_down(self):
        """Build config for dim down."""
        config = build_dimming_config('dim_down')

        assert 'on_repeat' in config
        assert config['on_repeat'] == {'action': 'dim_down'}


class TestBuildLongPressConfig:
    """Test long press configuration builder."""

    def test_all_off_action(self):
        """Build config for all off action."""
        config = build_long_press_config('all_off', None)

        assert 'on_long_press' in config
        assert config['on_long_press'] == {'action': 'all_off'}

    def test_all_off_with_space(self):
        """Build config for 'all off' (with space)."""
        config = build_long_press_config('all off', None)

        assert 'on_long_press' in config
        assert config['on_long_press'] == {'action': 'all_off'}

    def test_scene_recall(self):
        """Build config for scene recall on long press."""
        config = build_long_press_config('Relax', 'scene-relax-id')

        assert 'on_long_press' in config
        assert config['on_long_press'] == {'recall': {'rid': 'scene-relax-id', 'rtype': 'scene'}}


class TestFindButtonRidForControlId:
    """Test button RID lookup for new format."""

    def test_old_format_returns_none(self):
        """Old format (button1/button2) should return None."""
        behaviour = {
            'configuration': {
                'button1': {'on_short_release': {}},
                'button2': {'on_short_release': {}},
                'device': {'rid': 'device-id', 'rtype': 'device'}
            }
        }
        button_lookup = {}

        result = find_button_rid_for_control_id(behaviour, 1, button_lookup)
        assert result is None

    def test_new_format_finds_button(self):
        """New format should find button by control_id."""
        behaviour = {
            'configuration': {
                'buttons': {
                    'button-rid-1': {'on_short_release': {}},
                    'button-rid-2': {'on_short_release': {}}
                },
                'device': {'rid': 'device-id', 'rtype': 'device'}
            }
        }
        button_lookup = {
            'button-rid-1': {'metadata': {'control_id': 1}},
            'button-rid-2': {'metadata': {'control_id': 2}}
        }

        result = find_button_rid_for_control_id(behaviour, 1, button_lookup)
        assert result == 'button-rid-1'

        result = find_button_rid_for_control_id(behaviour, 2, button_lookup)
        assert result == 'button-rid-2'

    def test_new_format_button_not_found(self):
        """New format with non-existent control_id should return None."""
        behaviour = {
            'configuration': {
                'buttons': {
                    'button-rid-1': {'on_short_release': {}}
                },
                'device': {'rid': 'device-id', 'rtype': 'device'}
            }
        }
        button_lookup = {
            'button-rid-1': {'metadata': {'control_id': 1}}
        }

        result = find_button_rid_for_control_id(behaviour, 99, button_lookup)
        assert result is None
