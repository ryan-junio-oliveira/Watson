from abc import ABC, abstractmethod
from typing import Any, List

from rag.response import AgentResponse, Source


class ResponseFormatter(ABC):

    @abstractmethod
    def format(self, response: AgentResponse) -> Any:
        ...

    def format_error(self, code: str, message: str) -> Any:
        return self._error(code, message)

    @abstractmethod
    def _error(self, code: str, message: str) -> Any:
        ...


class ApiFormatter(ResponseFormatter):

    def format(self, response: AgentResponse) -> dict:
        data = {
            "success": True,
            "answer": response.answer,
            "confidence": round(response.confidence, 2),
            "sources": self._serialize_sources(response.sources),
            "metadata": self._build_metadata(response),
        }
        if response.follow_up:
            data["follow_up"] = response.follow_up
        if response.conclusions:
            data["conclusions"] = response.conclusions
        if response.additional_info:
            data["additional_info"] = response.additional_info
        return data

    def format_error(self, code: str, message: str) -> dict:
        return {
            "success": False,
            "error": {"code": code, "message": message},
        }

    def format_stream_metadata(self, response: AgentResponse) -> dict:
        data = {
            "confidence": round(response.confidence, 2),
            "sources": self._serialize_sources(response.sources),
            "metadata": self._build_metadata(response),
        }
        if response.follow_up:
            data["follow_up"] = response.follow_up
        if response.conclusions:
            data["conclusions"] = response.conclusions
        if response.additional_info:
            data["additional_info"] = response.additional_info
        return data

    def _error(self, code: str, message: str) -> dict:
        return self.format_error(code, message)

    def _serialize_sources(self, sources: List[Source]) -> List[dict]:
        return [s.to_dict() for s in sources]

    def _build_metadata(self, response: AgentResponse) -> dict:
        meta = dict(response.metadata)
        meta["evidence_count"] = response.evidence_count
        meta["execution_time_ms"] = int(response.execution_time * 1000)
        meta["verdict"] = response.verdict
        if response.issues:
            meta["issues"] = response.issues
        return meta


class CliFormatter(ResponseFormatter):

    def format(self, response: AgentResponse) -> str:
        parts = [response.answer]
        if response.sources:
            parts.append("")
            parts.append("Sources")
            parts.append("-------")
            for s in response.sources:
                label = s.title or s.url
                parts.append(f"  \u2022 {label}")
        if response.issues:
            parts.append("")
            parts.append("Notes:")
            for issue in response.issues:
                parts.append(f"  - {issue}")
        return "\n".join(parts)

    def format_compact(self, response: AgentResponse) -> str:
        parts = [response.answer]
        if response.sources:
            parts.append("")
            names = []
            for s in response.sources:
                names.append(s.title or s.url)
            parts.append(f"Sources: {'; '.join(names)}")
        return "\n".join(parts)

    def _error(self, code: str, message: str) -> str:
        return f"Error [{code}]: {message}"
