from __future__ import annotations

import os
from typing import Any

import httpx
from langchain_openai import AzureChatOpenAI

from app.services.llm import connected_model_label


class DeepAgentUnavailable(RuntimeError):
    """Deep Agents 패키지나 모델 설정 문제로 실행할 수 없을 때 사용합니다."""


def create_hazop_deep_agent(
    *,
    tools: list,
    system_prompt: str,
    response_format: type,
):
    """HAZOP 전용 Deepagent를 생성합니다.

    Deep Agents 직접 의존성은 이 함수에 가둡니다. 이렇게 해두면 패키지 API가 바뀌어도
    FastAPI나 Excel 처리 코드는 흔들리지 않고 이 어댑터만 고치면 됩니다.
    """

    try:
        from deepagents import create_deep_agent
    except Exception as exc:  # pragma: no cover - 설치 환경에 따라 달라집니다.
        raise DeepAgentUnavailable("deepagents 패키지를 import할 수 없습니다.") from exc

    _prepare_azure_langchain_env()
    model = _azure_chat_model()

    kwargs: dict[str, Any] = {
        "model": model,
        "tools": tools,
        "system_prompt": system_prompt,
        "response_format": response_format,
        "subagents": _hazop_subagents(model),
        "skills": _skill_paths(),
        "permissions": [{"operations": ["read", "write"], "paths": ["**"], "mode": "deny"}],
    }
    _apply_filesystem_lockdown()
    return create_deep_agent(**kwargs)


def _prepare_azure_langchain_env() -> None:
    """기존 `.env` 이름을 LangChain Azure 모델 초기화 이름과 맞춥니다."""

    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    if api_version and not os.getenv("OPENAI_API_VERSION"):
        os.environ["OPENAI_API_VERSION"] = api_version


def _azure_chat_model() -> AzureChatOpenAI:
    """DeepAgent가 사용할 Azure Chat 모델을 직접 만듭니다.

    쉽게 말하면 DeepAgent에게 "이 주소, 이 배포명, 이 SSL 규칙으로 AI를 불러라"라고
    정확한 연결 방법을 쥐여주는 함수입니다. 문자열 모델명만 넘기면 LangChain 기본값에
    맡겨야 해서 사내 게이트웨이 같은 특수 환경에서 `Connection error`가 나기 쉽습니다.
    """

    verify_ssl = os.getenv("AZURE_OPENAI_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
    timeout = float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "120"))
    http_client = httpx.Client(verify=verify_ssl, timeout=timeout)
    http_async_client = httpx.AsyncClient(verify=verify_ssl, timeout=timeout)

    return AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        model=connected_model_label(),
        temperature=0.2,
        timeout=timeout,
        max_retries=1,
        http_client=http_client,
        http_async_client=http_async_client,
    )


def _hazop_subagents(model: AzureChatOpenAI) -> list[dict[str, Any]]:
    """Deep Agents의 task 도구로 호출 가능한 전문 sub-agent 정의입니다."""

    return [
        {
            "name": "risk-draft-agent",
            "description": "#3 위험성평가 초안을 작성하는 HAZOP 작성자입니다.",
            "system_prompt": "입력 Excel의 Node, 변수, Guideword만 사용해 #3 위험성평가 초안을 작성한다.",
            "model": model,
        },
        {
            "name": "risk-review-agent",
            "description": "#3 위험성평가 초안을 검토하고 규칙 위반과 근거 부족을 찾는 검토자입니다.",
            "system_prompt": "HAZOP 초안이 입력 기준, 빈도/강도 범위, 근거 작성 원칙을 지키는지 검토한다.",
            "model": model,
        },
        {
            "name": "action-plan-agent",
            "description": "위험도 9 이상 항목의 #4 조치계획서 초안을 작성하는 담당자입니다.",
            "system_prompt": "고위험 항목에 대해 개선권고사항과 조치 후 빈도/강도 후보 근거를 작성한다.",
            "model": model,
        },
    ]


def _skill_paths() -> list[str]:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
    names = [
        "hazop_risk_draft",
        "hazop_risk_review",
        "hazop_action_plan",
        "incident_history_analysis",
        "standard_hazop_reference",
        "frequency_estimation",
        "standard_hazop_comparison",
    ]
    return [os.path.join(base, name) for name in names]


def _apply_filesystem_lockdown() -> None:
    """Deepagent 기본 파일 도구가 보이더라도 HAZOP 생성에는 쓰지 않게 숨깁니다.

    공식 문서는 tool/sandbox 수준 경계를 강조하므로, 지원되는 버전에서는 파일 도구를
    제외합니다. API가 다른 버전이면 실패하지 않고 custom Tool만 제공하는 구조로 둡니다.
    """

    try:
        from deepagents import HarnessProfile, register_harness_profile

        profile = HarnessProfile(
            excluded_tools=frozenset({"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute"})
        )
        model_label = connected_model_label()
        for key in {f"azure:{model_label}", f"azure_openai:{model_label}", "azure", "azure_openai"}:
            register_harness_profile(key, profile)
    except Exception:
        return
