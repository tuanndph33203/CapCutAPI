import unittest
from timeline.models import VideoSegment
from timeline.exporter import export_draft

class TestExport(unittest.TestCase):
    def test_export_draft(self):
        draft_mock = {
            "materials": {
                "speeds": [],
                "videos": [{"id": "vid_1", "path": "clip.mp4"}]
            },
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "id": "v1",
                            "material_id": "vid_1",
                            "source_timerange": {"start": 0, "duration": 5000},
                            "target_timerange": {"start": 0, "duration": 5000}
                        }
                    ]
                }
            ]
        }
        segs = [
            VideoSegment(
                id="v1",
                material_id="vid_1",
                src_start=0,
                src_duration=5000,
                trim_left=0,
                trim_right=0,
                speed=1.1,
                target_start=0,
                target_duration=4545,
                flip_horizontal=True
            )
        ]
        export_draft(draft_mock, segs, [], [])
        seg_dict = draft_mock["tracks"][0]["segments"][0]
        self.assertEqual(seg_dict["speed"], 1.1)
        self.assertEqual(seg_dict["clip"]["flip"]["horizontal"], True)

if __name__ == "__main__":
    unittest.main()
