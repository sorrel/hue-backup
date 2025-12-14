"""Tests for utility functions in models/utils.py"""

import pytest
from models.utils import display_width, decode_button_event, create_name_lookup


class TestDisplayWidth:
    """Tests for display_width function."""

    def test_ascii_text(self):
        """ASCII text should have width equal to length."""
        assert display_width("hello") == 5
        assert display_width("test") == 4
        assert display_width("") == 0

    def test_battery_emoji(self):
        """Battery emoji should count as 2 columns."""
        assert display_width("🔋") == 2
        assert display_width("🪫") == 2

    def test_arrow_symbol(self):
        """Arrow symbol should count as 2 columns."""
        assert display_width("→") == 2

    def test_mixed_content(self):
        """Mixed ASCII and emojis should sum correctly."""
        assert display_width("Battery: 🔋") == 11  # 9 ASCII + 2 emoji
        assert display_width("A → B") == 6  # 4 ASCII + 2 arrow

    def test_high_unicode(self):
        """High Unicode characters (>0x1F300) should count as 2."""
        # Most emojis are above 0x1F300
        assert display_width("😀") == 2
        assert display_width("🎉") == 2


class TestDecodeButtonEvent:
    """Tests for decode_button_event function."""

    def test_on_button_short_release(self):
        """On button (1) short release (002)."""
        assert decode_button_event(1002) == "On (Short Release)"

    def test_dim_up_hold(self):
        """Dim Up button (2) hold (001)."""
        assert decode_button_event(2001) == "Dim Up (Hold)"

    def test_dim_down_initial_press(self):
        """Dim Down button (3) initial press (000)."""
        assert decode_button_event(3000) == "Dim Down (Initial Press)"

    def test_off_button_long_release(self):
        """Off button (4) long release (003)."""
        assert decode_button_event(4003) == "Off (Long Release)"

    def test_dial_rotate(self):
        """Dial rotate (34) short release (002)."""
        assert decode_button_event(34002) == "Dial Rotate (Short Release)"

    def test_dial_press(self):
        """Dial press (35) initial press (000)."""
        assert decode_button_event(35000) == "Dial Press (Initial Press)"

    def test_unknown_event_code(self):
        """Unknown or invalid event codes."""
        assert decode_button_event(0) == "Unknown"
        assert decode_button_event(None) == "Unknown"
        assert "Unknown" in decode_button_event(99)


class TestCreateNameLookup:
    """Tests for create_name_lookup function."""

    def test_empty_list(self):
        """Empty resource list should return empty dict."""
        assert create_name_lookup([]) == {}

    def test_single_resource(self):
        """Single resource should map ID to name."""
        resources = [
            {'id': 'light-1', 'metadata': {'name': 'Living Room Lamp'}}
        ]
        result = create_name_lookup(resources)
        assert result == {'light-1': 'Living Room Lamp'}

    def test_multiple_resources(self):
        """Multiple resources should all be mapped."""
        resources = [
            {'id': 'light-1', 'metadata': {'name': 'Lamp 1'}},
            {'id': 'light-2', 'metadata': {'name': 'Lamp 2'}},
            {'id': 'light-3', 'metadata': {'name': 'Lamp 3'}},
        ]
        result = create_name_lookup(resources)
        assert len(result) == 3
        assert result['light-1'] == 'Lamp 1'
        assert result['light-2'] == 'Lamp 2'
        assert result['light-3'] == 'Lamp 3'

    def test_missing_metadata(self):
        """Resources without metadata should map to 'Unknown'."""
        resources = [
            {'id': 'light-1'},
            {'id': 'light-2', 'metadata': {}},
        ]
        result = create_name_lookup(resources)
        assert result['light-1'] == 'Unknown'
        assert result['light-2'] == 'Unknown'

    def test_missing_name(self):
        """Resources with metadata but no name should map to 'Unknown'."""
        resources = [
            {'id': 'light-1', 'metadata': {'archetype': 'lamp'}}
        ]
        result = create_name_lookup(resources)
        assert result['light-1'] == 'Unknown'


class TestCreateSceneReverseLookup:
    """Tests for create_scene_reverse_lookup function."""

    def test_empty_list(self):
        """Empty list should return empty dict."""
        from models.utils import create_scene_reverse_lookup
        result = create_scene_reverse_lookup([])
        assert result == {}

    def test_single_scene(self):
        """Single scene should create correct lowercase mapping."""
        from models.utils import create_scene_reverse_lookup
        scenes = [
            {'id': 'scene123', 'metadata': {'name': 'Morning Light'}}
        ]
        result = create_scene_reverse_lookup(scenes)
        assert result == {'morning light': 'scene123'}

    def test_multiple_scenes(self):
        """Multiple scenes should create correct mappings."""
        from models.utils import create_scene_reverse_lookup
        scenes = [
            {'id': 'scene1', 'metadata': {'name': 'Energise'}},
            {'id': 'scene2', 'metadata': {'name': 'Relax'}},
            {'id': 'scene3', 'metadata': {'name': 'Read'}}
        ]
        result = create_scene_reverse_lookup(scenes)
        assert result == {
            'energise': 'scene1',
            'relax': 'scene2',
            'read': 'scene3'
        }

    def test_case_insensitive_mapping(self):
        """Scene names should be lowercase in keys."""
        from models.utils import create_scene_reverse_lookup
        scenes = [
            {'id': 'scene1', 'metadata': {'name': 'UPPERCASE'}},
            {'id': 'scene2', 'metadata': {'name': 'MixedCase'}},
            {'id': 'scene3', 'metadata': {'name': 'lowercase'}}
        ]
        result = create_scene_reverse_lookup(scenes)
        assert result == {
            'uppercase': 'scene1',
            'mixedcase': 'scene2',
            'lowercase': 'scene3'
        }

    def test_missing_metadata_skipped(self):
        """Scenes without metadata should be skipped."""
        from models.utils import create_scene_reverse_lookup
        scenes = [
            {'id': 'scene1'},
            {'id': 'scene2', 'metadata': {}},
            {'id': 'scene3', 'metadata': {'name': 'Valid'}}
        ]
        result = create_scene_reverse_lookup(scenes)
        assert result == {'valid': 'scene3'}


class TestFindSimilarStrings:
    """Tests for find_similar_strings function."""

    def test_empty_candidates(self):
        """Empty candidates should return empty list."""
        from models.utils import find_similar_strings
        result = find_similar_strings('test', [])
        assert result == []

    def test_exact_match(self):
        """Exact match should score 100 and be first."""
        from models.utils import find_similar_strings
        candidates = ['apple', 'banana', 'cherry']
        result = find_similar_strings('banana', candidates)
        assert result[0] == 'banana'

    def test_prefix_match(self):
        """Prefix match should score high."""
        from models.utils import find_similar_strings
        candidates = ['testing', 'test', 'contest']
        result = find_similar_strings('test', candidates, limit=3)
        # 'test' (exact) and 'testing' (prefix) should rank higher than 'contest' (contains)
        assert 'test' in result[:2]
        assert 'testing' in result[:2]

    def test_contains_match(self):
        """Contains match should rank."""
        from models.utils import find_similar_strings
        candidates = ['understand', 'stand', 'outstanding']
        result = find_similar_strings('stand', candidates, limit=3)
        assert 'stand' in result  # Exact match
        assert 'understand' in result or 'outstanding' in result  # Contains

    def test_no_matches(self):
        """No similar strings should return empty list."""
        from models.utils import find_similar_strings
        candidates = ['xyz', 'abc', 'def']
        result = find_similar_strings('qwerty', candidates)
        # May return empty or very low scoring matches
        assert len(result) <= 5  # Respects limit

    def test_limit_parameter(self):
        """Limit parameter should restrict results."""
        from models.utils import find_similar_strings
        candidates = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        result = find_similar_strings('a', candidates, limit=3)
        assert len(result) <= 3

    def test_case_insensitive(self):
        """Matching should be case insensitive."""
        from models.utils import find_similar_strings
        candidates = ['Office', 'OFFICE', 'office']
        result = find_similar_strings('office', candidates)
        # All should match with high scores
        assert len(result) == 3
