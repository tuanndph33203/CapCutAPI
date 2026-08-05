import logging
import sys

logger = logging.getLogger("TimelineLogger")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[TimelineLogger] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class TimelineLogger:
    """
    TimelineLogger formats timeline operations and configurations into structured columns
    for clear debugging (SEG, SRC, TRIM, SPD, TARGET).
    """
    @staticmethod
    def info(msg: str):
        logger.info(msg)

    @staticmethod
    def log_video_segments(segs: list):
        header = f"{'SEG ID':<10} | {'SRC RANGE':<25} | {'TRIM L/R':<15} | {'SPEED':<6} | {'TARGET RANGE':<25}"
        logger.info(header)
        logger.info("-" * len(header))
        for vs in segs:
            src_str = f"{vs.src_start/1e6:.2f}s -> {(vs.src_start+vs.src_duration)/1e6:.2f}s"
            trim_str = f"{vs.trim_left/1e6:.2f}s / {vs.trim_right/1e6:.2f}s"
            tgt_str = f"{vs.target_start/1e6:.2f}s -> {(vs.target_start+vs.target_duration)/1e6:.2f}s"
            logger.info(f"{vs.id[:8]:<10} | {src_str:<25} | {trim_str:<15} | {vs.speed:<6.3f} | {tgt_str:<25}")
