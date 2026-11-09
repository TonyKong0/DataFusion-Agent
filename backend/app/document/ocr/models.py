from dataclasses import dataclass


@dataclass
class ScanDetection:
    is_scanned: bool
    confidence: float
    reason: list[str]

    def to_dict(self):
        return {'is_scanned': self.is_scanned, 'confidence': self.confidence, 'reason': self.reason}
