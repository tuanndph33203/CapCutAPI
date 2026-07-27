from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class VideoSegment:
    id: str
    material_id: str
    src_start: int
    src_duration: int
    trim_left: int
    trim_right: int
    speed: float
    target_start: int = 0
    target_duration: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    scale_x: float = 1.0
    scale_y: float = 1.0
    color_adjustments: Dict[str, float] = field(default_factory=dict)
    extra_material_refs: list = field(default_factory=list)
    speed_id: Optional[str] = None
    raw_dict: dict = field(default_factory=dict)

    @property
    def effective_source_duration(self) -> int:
        return self.src_duration - self.trim_left - self.trim_right

    @property
    def effective_ratio(self) -> float:
        if self.effective_source_duration <= 0:
            return 1.0
        return self.target_duration / self.effective_source_duration

@dataclass
class MappingResult:
    target: int
    source: int
    ratio: float
    offset: int
    segment: VideoSegment

@dataclass
class SubtitleSegment:
    id: str
    ocr_source_start: int
    ocr_source_duration: int
    target_start: int
    target_duration: int

@dataclass
class AudioSegment:
    id: str
    material_id: str
    src_start: int
    src_duration: int
    target_start: int
    target_duration: int
    speed: float = 1.0
    extra_material_refs: list = field(default_factory=list)
    speed_id: Optional[str] = None
    ocr_source_start: Optional[int] = None
