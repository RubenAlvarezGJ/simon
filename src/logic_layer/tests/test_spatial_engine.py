import json
import math

import numpy as np
import pytest

from logic_layer.spatial_engine import SpatialEngine, GLOBAL_ZONE
 
 
# ===========================================================================
# Minimal ThreatState stub
# ===========================================================================
 
class MockThreatState:
    """Minimal stand-in that satisfies SpatialEngine's mutation contract."""
 
    def __init__(self, tracker_id: int, class_name: str, bbox: list[float]):
        self.tracker_id  = tracker_id
        self.class_name  = class_name
        self.bbox        = np.array(bbox, dtype=float)
        self.active_zones: list[str] = []
 
    def __repr__(self):
        return (
            f"MockThreatState(id={self.tracker_id}, "
            f"cls={self.class_name!r}, zones={self.active_zones})"
        )
 
 
# ===========================================================================
# Shared geometry helpers
# ===========================================================================
 
# A 200×200 square at the top-left corner of a 640×480 frame.
# Bottom-center of a bbox is (cx, y2).  Any bbox whose bottom-centre
# falls inside [0–200, 0–200] should trigger this zone.
SQUARE_ZONE = [[0, 0], [200, 0], [200, 200], [0, 200]]
 
# A non-overlapping zone in the bottom-right corner.
BOTTOM_RIGHT_ZONE = [[440, 280], [640, 280], [640, 480], [440, 480]]
 
 
def write_zones(tmp_path, data: dict) -> str:
    """Write a zones.json file to tmp_path and return its string path."""
    p = tmp_path / "zones.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)
 
 
def inside_threat(tracker_id: int = 1) -> MockThreatState:
    """
    A detection whose bottom-centre lands inside SQUARE_ZONE.
    bbox [10, 10, 90, 190] → bottom-centre = (50, 190) → inside [0–200, 0–200].
    """
    return MockThreatState(tracker_id, "handgun", [10.0, 10.0, 90.0, 190.0])
 
 
def outside_threat(tracker_id: int = 2) -> MockThreatState:
    """
    A detection whose bottom-centre is outside ALL zones in a SQUARE_ZONE config.
    bbox [300, 300, 500, 460] → bottom-centre = (400, 460) → outside [0–200].
    """
    return MockThreatState(tracker_id, "crowbar", [300.0, 300.0, 500.0, 460.0])
 
 
# ===========================================================================
# Bypass Mode Tests
# ===========================================================================
 
class TestBypassMode:
    """Engine behaviour when no valid zones.json exists."""
 
    def test_missing_file_activates_bypass(self, tmp_path):
        engine = SpatialEngine(zones_path=str(tmp_path / "nonexistent.json"))
        assert engine.bypass is True
        assert engine.zone_count == 0
 
    def test_empty_json_object_activates_bypass(self, tmp_path):
        path = write_zones(tmp_path, {})
        engine = SpatialEngine(zones_path=path)
        assert engine.bypass is True
 
    def test_invalid_json_activates_bypass(self, tmp_path):
        p = tmp_path / "zones.json"
        p.write_text("not valid json {{", encoding="utf-8")
        engine = SpatialEngine(zones_path=str(p))
        assert engine.bypass is True
 
    def test_bypass_tags_all_threats_global(self, tmp_path):
        engine = SpatialEngine(zones_path=str(tmp_path / "nonexistent.json"))
        threats = [inside_threat(1), outside_threat(2)]
        engine.evaluate(threats)
        for t in threats:
            assert t.active_zones == [GLOBAL_ZONE]
 
    def test_bypass_clears_stale_zones_before_tagging(self, tmp_path):
        engine = SpatialEngine(zones_path=str(tmp_path / "nonexistent.json"))
        t = inside_threat()
        t.active_zones = ["stale_zone", "another_stale"]
        engine.evaluate([t])
        assert t.active_zones == [GLOBAL_ZONE]
 
    def test_bypass_empty_threat_list_is_safe(self, tmp_path):
        engine = SpatialEngine(zones_path=str(tmp_path / "nonexistent.json"))
        engine.evaluate([])   # Must not raise
 
    def test_json_root_not_dict_activates_bypass(self, tmp_path):
        p = tmp_path / "zones.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        engine = SpatialEngine(zones_path=str(p))
        assert engine.bypass is True
 
 
# ===========================================================================
# Zone Loading & Validation Tests
# ===========================================================================
 
class TestZoneLoading:
    """Zone compilation from JSON including edge-case validation."""
 
    def test_valid_zones_loaded_correctly(self, tmp_path):
        path = write_zones(tmp_path, {
            "driveway": SQUARE_ZONE,
            "porch":    BOTTOM_RIGHT_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        assert engine.bypass is False
        assert engine.zone_count == 2
 
    def test_zone_names_preserved(self, tmp_path):
        path = write_zones(tmp_path, {"my_zone_42": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        names = [z.name for z in engine._zones]
        assert "my_zone_42" in names
 
    def test_zone_with_fewer_than_3_vertices_skipped(self, tmp_path):
        path = write_zones(tmp_path, {
            "bad":  [[0, 0], [100, 0]],
            "good": SQUARE_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        assert engine.zone_count == 1
        assert engine._zones[0].name == "good"
 
    def test_zone_with_non_list_vertices_skipped(self, tmp_path):
        path = write_zones(tmp_path, {
            "bad":  "not a list",
            "good": SQUARE_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        assert engine.zone_count == 1
 
    def test_zone_with_malformed_point_skipped(self, tmp_path):
        path = write_zones(tmp_path, {
            "bad":  [[0, 0], [100, 0], "oops"],
            "good": SQUARE_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        assert engine.zone_count == 1
 
    def test_zone_with_3_point_tuple_accepted(self, tmp_path):
        """Minimum viable polygon: exactly 3 vertices."""
        triangle = [[0, 0], [200, 0], [100, 200]]
        path = write_zones(tmp_path, {"triangle": triangle})
        engine = SpatialEngine(zones_path=path)
        assert engine.zone_count == 1
 
    def test_all_zones_invalid_triggers_bypass(self, tmp_path):
        path = write_zones(tmp_path, {
            "bad1": [[0, 0]],
            "bad2": "string",
        })
        engine = SpatialEngine(zones_path=path)
        assert engine.bypass is True
 
    def test_vertex_count_stored_correctly(self, tmp_path):
        path = write_zones(tmp_path, {"zone": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        assert engine._zones[0].vertex_count == 4
 
 
# ===========================================================================
# Spatial Evaluation Tests — Core Geometry
# ===========================================================================
 
class TestEvaluateSingleZone:
    """Point-in-polygon correctness with a single zone."""
 
    def test_threat_inside_zone_tagged(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        assert "square" in t.active_zones
 
    def test_threat_outside_zone_not_tagged(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = outside_threat()
        engine.evaluate([t])
        assert "square" not in t.active_zones
 
    def test_threat_outside_receives_global_fallback(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = outside_threat()
        engine.evaluate([t])
        assert t.active_zones == [GLOBAL_ZONE]
 
    def test_threat_inside_does_not_receive_global(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        assert GLOBAL_ZONE not in t.active_zones
 
    def test_empty_threat_list_is_safe(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        engine.evaluate([])   # Must not raise
 
 
class TestBottomCenterAnchor:
    """
    Explicit verification that BOTTOM_CENTER is the active anchor.
 
    Strategy: construct a bbox whose *centroid* is outside the zone but
    whose *bottom-centre* falls inside it, and a bbox where it is reversed.
    Only the bottom-centre result should match the expected zone membership.
    """
 
    def test_bottom_center_inside_centroid_outside(self, tmp_path):
        """
        Zone: narrow horizontal strip at y=[150, 200].
        bbox: [40, 0, 160, 199]
          - centroid (cx=100, cy=99.5) → OUTSIDE the strip.
          - bottom-centre (cx=100, cy=199) → INSIDE the strip.
        Expected: zone IS triggered.
        """
        strip_zone = [[0, 150], [200, 150], [200, 200], [0, 200]]
        path = write_zones(tmp_path, {"strip": strip_zone})
        engine = SpatialEngine(zones_path=path)
 
        t = MockThreatState(1, "knife", [40.0, 0.0, 160.0, 199.0])
        engine.evaluate([t])
        assert "strip" in t.active_zones, (
            "Bottom-centre (100, 199) should be inside strip zone [y:150–200]"
        )
 
    def test_centroid_inside_bottom_center_outside(self, tmp_path):
        """
        Zone: narrow horizontal strip at y=[0, 50].
        bbox: [40, 0, 160, 199]
          - centroid (cx=100, cy=99.5) → OUTSIDE the strip [y:0–50].
          - bottom-centre (cx=100, cy=199) → OUTSIDE the strip.
        Expected: zone is NOT triggered, threat receives global.
        """
        top_strip = [[0, 0], [200, 0], [200, 50], [0, 50]]
        path = write_zones(tmp_path, {"top_strip": top_strip})
        engine = SpatialEngine(zones_path=path)
 
        t = MockThreatState(1, "knife", [40.0, 0.0, 160.0, 199.0])
        engine.evaluate([t])
        assert "top_strip" not in t.active_zones
 
 
class TestEvaluateMultipleZones:
    """Behaviour with two or more loaded zones."""
 
    def test_threat_inside_one_zone_only(self, tmp_path):
        path = write_zones(tmp_path, {
            "zone_a": SQUARE_ZONE,
            "zone_b": BOTTOM_RIGHT_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        assert "zone_a" in t.active_zones
        assert "zone_b" not in t.active_zones
 
    def test_threat_in_overlapping_zones_receives_both(self, tmp_path):
        """
        An object at the overlap of two zones must receive both zone names.
        Both zone_a and zone_b cover [0–200, 0–200]; inside_threat lands there.
        """
        path = write_zones(tmp_path, {
            "zone_a": SQUARE_ZONE,
            "zone_b": SQUARE_ZONE,   # Identical polygon — guaranteed overlap.
        })
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        assert "zone_a" in t.active_zones
        assert "zone_b" in t.active_zones
        assert len(t.active_zones) == 2
 
    def test_multiple_threats_evaluated_independently(self, tmp_path):
        path = write_zones(tmp_path, {
            "square":       SQUARE_ZONE,
            "bottom_right": BOTTOM_RIGHT_ZONE,
        })
        engine = SpatialEngine(zones_path=path)
        t_in  = inside_threat(1)
        t_out = outside_threat(2)
        # t_out bbox [300,300,500,460] → bottom-centre=(400,460) → inside BOTTOM_RIGHT_ZONE
        t_out_br = MockThreatState(3, "flashlight", [480.0, 300.0, 600.0, 460.0])
        engine.evaluate([t_in, t_out, t_out_br])
 
        assert "square" in t_in.active_zones
        assert "square" not in t_out.active_zones
        assert "bottom_right" in t_out_br.active_zones
 
 
# ===========================================================================
# State Mutation Contract Tests
# ===========================================================================
 
class TestStateMutation:
    """Guarantees about how active_zones is mutated per frame."""
 
    def test_stale_zones_cleared_before_evaluation(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        t.active_zones = ["stale_zone_from_last_frame"]
        engine.evaluate([t])
        assert "stale_zone_from_last_frame" not in t.active_zones
        assert "square" in t.active_zones
 
    def test_zone_list_cleared_when_object_leaves_zone(self, tmp_path):
        """
        Simulate an object moving out of a zone between frames.
        Frame 1: object inside → tagged.
        Frame 2: object outside → previous tag cleared, receives global.
        """
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
 
        engine.evaluate([t])
        assert "square" in t.active_zones
 
        # Move the bbox outside the zone
        t.bbox = np.array([300.0, 300.0, 500.0, 460.0])
        engine.evaluate([t])
        assert "square" not in t.active_zones
        assert t.active_zones == [GLOBAL_ZONE]
 
    def test_active_zones_is_list_not_set(self, tmp_path):
        """active_zones must remain a list to preserve insertion order."""
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        assert isinstance(t.active_zones, list)
 
    def test_multiple_calls_do_not_accumulate_zones(self, tmp_path):
        """Calling evaluate() twice must not double-append zone names."""
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        t = inside_threat()
        engine.evaluate([t])
        engine.evaluate([t])
        assert t.active_zones.count("square") == 1
 
 
# ===========================================================================
# Diagnostics & Hot-reload Tests
# ===========================================================================
 
class TestDiagnostics:
 
    def test_diagnostics_bypass_mode(self, tmp_path):
        engine = SpatialEngine(zones_path=str(tmp_path / "missing.json"))
        d = engine.diagnostics()
        assert d["bypass"] is True
        assert d["zone_count"] == 0
        assert d["zones"] == []
 
    def test_diagnostics_loaded_mode(self, tmp_path):
        path = write_zones(tmp_path, {"driveway": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        d = engine.diagnostics()
        assert d["bypass"] is False
        assert d["zone_count"] == 1
        assert d["zones"][0]["name"] == "driveway"
        assert d["zones"][0]["vertices"] == 4
 
    def test_diagnostics_is_json_serialisable(self, tmp_path):
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        import json
        json.dumps(engine.diagnostics())   # Must not raise
 
 
class TestHotReload:
 
    def test_reload_picks_up_new_zones(self, tmp_path):
        zones_file = tmp_path / "zones.json"
 
        # Start with no file → bypass
        engine = SpatialEngine(zones_path=str(zones_file))
        assert engine.bypass is True
 
        # Write valid config and reload
        zones_file.write_text(
            json.dumps({"driveway": SQUARE_ZONE}), encoding="utf-8"
        )
        result = engine.reload()
        assert result is True
        assert engine.bypass is False
        assert engine.zone_count == 1
 
    def test_reload_returns_false_on_missing_file(self, tmp_path):
        # Load a valid config first
        path = write_zones(tmp_path, {"square": SQUARE_ZONE})
        engine = SpatialEngine(zones_path=path)
        assert engine.zone_count == 1
 
        # Delete the file and reload
        (tmp_path / "zones.json").unlink()
        result = engine.reload()
        assert result is False
        assert engine.bypass is True
 
    def test_reload_replaces_old_zones(self, tmp_path):
        zones_file = tmp_path / "zones.json"
        zones_file.write_text(
            json.dumps({"old_zone": SQUARE_ZONE}), encoding="utf-8"
        )
        engine = SpatialEngine(zones_path=str(zones_file))
        assert engine._zones[0].name == "old_zone"
 
        # Replace with a new zone definition
        zones_file.write_text(
            json.dumps({"new_zone": BOTTOM_RIGHT_ZONE}), encoding="utf-8"
        )
        engine.reload()
        assert engine._zones[0].name == "new_zone"
        assert engine.zone_count == 1
 
 
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])