from abc import ABC, abstractmethod
from typing import Any
from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.qc_report import QCReport

class ConsistencyJudgePort(ABC):
    @abstractmethod
    async def judge(self, shot_contract: ShotContract, video_asset: Any) -> QCReport:
        pass
