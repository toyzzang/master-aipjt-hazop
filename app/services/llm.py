from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncAzureOpenAI, DefaultAsyncHttpxClient


AZURE_OPENAI_REQUIRED_ENV = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]


def azure_openai_configured() -> bool:
    """Azure OpenAI 호출에 필요한 환경 변수가 모두 있는지 확인합니다."""

    return not missing_azure_openai_env()


def missing_azure_openai_env() -> list[str]:
    """값을 노출하지 않고 비어 있는 Azure OpenAI 설정 키 이름만 반환합니다."""

    return [name for name in AZURE_OPENAI_REQUIRED_ENV if not os.getenv(name)]


def connected_model_label() -> str:
    """화면 로그에 보여줄 연결 모델 이름을 반환합니다.

    Azure에서는 `AZURE_OPENAI_DEPLOYMENT`가 실제 모델명일 수도 있고,
    회사에서 정한 배포 이름일 수도 있습니다. 사용자가 보기에는
    "지금 연결된 모델" 정도로 이해하면 충분합니다.
    """

    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt")


async def generate_json_with_azure(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Azure OpenAI에 JSON 생성을 요청합니다.

    이 함수는 PoC에서 한 곳만 Azure OpenAI SDK를 사용하게 만든 얇은 래퍼입니다.
    나중에 모델이나 프롬프트 전략을 바꾸더라도 다른 서비스 코드는 크게 흔들리지 않습니다.
    """

    verify_ssl = os.getenv("AZURE_OPENAI_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
    http_client = None
    if not verify_ssl:
        # 사내 프록시/게이트웨이형 Azure OpenAI endpoint는 환경에 따라
        # self-signed certificate chain 오류가 날 수 있습니다.
        # PoC에서는 `AZURE_OPENAI_VERIFY_SSL=false`일 때만 검증을 끕니다.
        # 운영에서는 사내 CA 인증서를 컨테이너에 설치하는 방식이 더 안전합니다.
        http_client = DefaultAsyncHttpxClient(verify=False)

    client = AsyncAzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        http_client=http_client,
    )
    response = await client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
