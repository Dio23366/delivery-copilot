from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.prompt_builder import build_issue_analysis_prompt
from app.ai.providers.base import BaseIssueAnalysisProvider
from app.ai.providers.rule_based import RuleBasedIssueAnalysisProvider
from app.ai.schemas import IssueAnalysisContext, IssueAnalysisResult
from app.core.config import settings


class LLMIssueAnalysisProvider(BaseIssueAnalysisProvider):
    name = 'llm'

    def __init__(self) -> None:
        self.api_key = settings.ai_llm_api_key
        self.model = settings.ai_llm_model
        self.base_url = settings.ai_llm_base_url
        self.timeout_seconds = settings.ai_llm_timeout_seconds
        self.fallback_provider = RuleBasedIssueAnalysisProvider()
        self.last_provider_name = self.fallback_provider.name
        self.last_model_name = None
        self.last_fallback_reason: str | None = None

    def analyze_issue(self, context: IssueAnalysisContext) -> IssueAnalysisResult:
        if not self.api_key:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'missing_api_key'
            print('LLM fallback reason=missing_api_key')
            return self.fallback_provider.analyze_issue(context)

        try:
            prompt = build_issue_analysis_prompt(context)
            raw_output = self._call_llm(prompt)
            parsed = self._parse_and_validate(raw_output)
            self.last_provider_name = 'llm'
            self.last_model_name = self.model
            self.last_fallback_reason = None
            return IssueAnalysisResult(**parsed)
        except httpx.TimeoutException:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'timeout'
            print('LLM fallback reason=timeout')
            return self.fallback_provider.analyze_issue(context)
        except httpx.HTTPStatusError as exc:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'http_error'
            status_code = exc.response.status_code if exc.response is not None else 'unknown'
            print(f'LLM fallback reason=http_error status={status_code}')
            return self.fallback_provider.analyze_issue(context)
        except httpx.RequestError:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'request_error'
            print('LLM fallback reason=request_error')
            return self.fallback_provider.analyze_issue(context)
        except json.JSONDecodeError:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'invalid_json'
            print('LLM fallback reason=invalid_json')
            return self.fallback_provider.analyze_issue(context)
        except ValueError as exc:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'schema_validation_error'
            print(f'LLM fallback reason=schema_validation_error error={exc!s}')
            return self.fallback_provider.analyze_issue(context)
        except (KeyError, TypeError):
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'response_structure_error'
            print('LLM fallback reason=response_structure_error')
            return self.fallback_provider.analyze_issue(context)
        except Exception as exc:
            self.last_provider_name = self.fallback_provider.name
            self.last_model_name = None
            self.last_fallback_reason = 'unexpected_error'
            print(f'LLM fallback reason=unexpected_error exception_type={type(exc).__name__}')
            return self.fallback_provider.analyze_issue(context)

    def _call_llm(self, prompt: str) -> str:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload: dict[str, Any] = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': 'Return only valid JSON.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data['choices'][0]['message']['content']

    def _parse_and_validate(self, raw_output: str) -> dict[str, Any]:
        data = json.loads(raw_output)
        required_keys = {
            'issue_summary',
            'possible_root_cause',
            'recommended_actions',
            'customer_update_draft',
            'risk_level',
            'project_impact',
        }
        if not isinstance(data, dict) or not required_keys.issubset(data):
            raise ValueError('LLM output schema invalid')
        if data['risk_level'] not in {'low', 'medium', 'high', 'critical'}:
            raise ValueError('Invalid risk level')
        if not isinstance(data['recommended_actions'], list):
            raise ValueError('recommended_actions must be a list')
        return data
