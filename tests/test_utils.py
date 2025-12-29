"""Tests for geoguessr.utils module."""
import pytest
from datetime import datetime, timezone

from geoguessr.utils import parse_time, calculate_score


class TestParseTime:
    """Tests for parse_time function."""

    def test_parse_iso_format_with_z_suffix(self):
        result = parse_time("2024-01-15T14:30:00Z")
        expected = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_parse_iso_format_with_timezone(self):
        result = parse_time("2024-06-20T09:15:30+00:00")
        expected = datetime(2024, 6, 20, 9, 15, 30, tzinfo=timezone.utc)
        assert result == expected

    def test_parse_preserves_time_components(self):
        result = parse_time("2024-12-31T23:59:59Z")
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59


class TestCalculateScore:
    """Tests for calculate_score function."""

    def test_perfect_score_at_zero_distance(self):
        assert calculate_score(0) == 5000

    def test_score_decreases_with_distance(self):
        score_near = calculate_score(100)
        score_far = calculate_score(1000)
        assert score_near > score_far

    def test_negative_distance_treated_as_zero(self):
        assert calculate_score(-100) == 5000

    def test_very_large_distance_approaches_zero(self):
        score = calculate_score(50_000_000)
        assert score < 10

    def test_known_distance_values(self):
        # At roughly 1/10 of map size, score should be ~1839
        default_size = 14916862
        distance = default_size / 10
        score = calculate_score(distance)
        assert 1800 <= score <= 1900

    def test_custom_map_size(self):
        # Smaller map = lower scores for same distance
        small_map_score = calculate_score(1000, size=5000)
        large_map_score = calculate_score(1000, size=50000)
        assert small_map_score < large_map_score

    def test_score_is_integer(self):
        score = calculate_score(12345.67)
        assert isinstance(score, int)

    def test_score_never_exceeds_5000(self):
        assert calculate_score(0) == 5000
        assert calculate_score(-1000) == 5000
