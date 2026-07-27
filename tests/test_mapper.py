import unittest
from timeline.models import VideoSegment
from timeline.mapper import map_source_to_target, map_target_to_source

class TestMapper(unittest.TestCase):
    def test_bidirectional_mapping(self):
        segs = [
            VideoSegment(
                id="v1",
                material_id="mat1",
                src_start=0,
                src_duration=5000,
                trim_left=0,
                trim_right=1000,
                speed=1.0,
                target_start=0,
                target_duration=4000
            )
        ]
        mapped_tgt = map_source_to_target(2000, segs)
        self.assertEqual(mapped_tgt.target, 2000)
        self.assertEqual(mapped_tgt.ratio, 1.0)

        mapped_src = map_target_to_source(2000, segs)
        self.assertEqual(mapped_src.source, 2000)
        self.assertEqual(mapped_src.ratio, 1.0)

if __name__ == "__main__":
    unittest.main()
