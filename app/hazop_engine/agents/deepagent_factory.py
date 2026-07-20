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
    agent_name: str,
):
    """HAZOP 전용 Deepagent를 생성합니다.

    Deep Agents 직접 의존성은 이 함수에 가둡니다. 이렇게 해두면 패키지 API가 바뀌어도
    FastAPI나 Excel 처리 코드는 흔들리지 않고 이 어댑터만 고치면 됩니다.
    """

    try:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend
    except Exception as exc:  # pragma: no cover - 설치 환경에 따라 달라집니다.
        raise DeepAgentUnavailable("deepagents 패키지를 import할 수 없습니다.") from exc

    _prepare_azure_langchain_env()
    model = _azure_chat_model()

    kwargs: dict[str, Any] = {
        "model": model,
        "tools": tools,
        "system_prompt": system_prompt,
        "response_format": response_format,
        "name": agent_name,
        # 작성/검토/조치 Agent는 workflow에서 각각 별도 LLM 호출로 실행합니다.
        # 내부 task 위임에 기대지 않아 독립 검토 실행 여부가 코드 흐름에서 분명해집니다.
        "subagents": [],
        "skills": _skill_paths(),
        "permissions": _filesystem_permissions(),
        # 기본 StateBackend는 메모리 파일만 보므로 로컬 SKILL.md를 찾을 수 없습니다.
        # 실제 Skill 폴더를 읽되, 아래 permissions로 읽기 범위를 Skill 루트에 제한합니다.
        "backend": FilesystemBackend(root_dir="/", virtual_mode=False),
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


def _skill_paths() -> list[str]:
    """DeepAgents가 하위 Skill 폴더를 탐색할 수 있도록 모음 폴더를 넘깁니다."""

    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
    return [base]


def _filesystem_permissions() -> list[Any]:
    """Agent는 Skill 설명서만 읽을 수 있고 프로젝트 파일은 수정할 수 없습니다."""

    from deepagents.middleware.filesystem import FilesystemPermission

    skill_root = _skill_paths()[0]
    deny_all_patterns = ["/**", "/**/.*", "/**/.*/**", "/**/*.*"]
    return [
        FilesystemPermission(operations=["read"], paths=[f"{skill_root}/**"], mode="allow"),
        FilesystemPermission(operations=["read"], paths=deny_all_patterns, mode="deny"),
        FilesystemPermission(operations=["write"], paths=deny_all_patterns, mode="deny"),
    ]


def _apply_filesystem_lockdown() -> None:
    """Skill 읽기는 남기고 프로젝트 탐색·수정·명령 실행 도구는 숨깁니다.

    DeepAgents Skill은 Agent가 `read_file`로 SKILL.md 전체 본문을 읽어야 동작합니다.
    따라서 `read_file`까지 제외했던 기존 설정은 제거하고, 실제 읽을 수 있는 경로는
    위 `_filesystem_permissions`에서 Skill 모음 폴더로만 제한합니다.
    """

    try:
        from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile

        profile = HarnessProfile(
            excluded_tools=frozenset({"ls", "write_file", "edit_file", "glob", "grep", "execute"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        )
        model_label = connected_model_label()
        for key in {f"azure:{model_label}", f"azure_openai:{model_label}", "azure", "azure_openai"}:
            register_harness_profile(key, profile)
    except Exception:
        return
