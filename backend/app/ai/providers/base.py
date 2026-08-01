from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.schemas import IssueAnalysisContext, IssueAnalysisResult


class BaseIssueAnalysisProvider(ABC):
    name: str

    @abstractmethod
    def analyze_issue(self, context: IssueAnalysisContext) -> IssueAnalysisResult:
        raise NotImplementedError
