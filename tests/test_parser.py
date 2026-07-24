import unittest
from timeline.parser import parse_draft

class TestParser(unittest.TestCase):
    def test_parse_draft(self):
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
        video_segs, subtitle_segs, audio_segs = parse_draft(draft_mock)
        self.assertEqual(len(video_segs), 1)
        self.assertEqual(video_segs[0].id, "v1")
        self.assertEqual(len(subtitle_segs), 0)
        self.assertEqual(len(audio_segs), 0)

if __name__ == "__main__":
    unittest.main()
