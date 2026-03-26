import os
import re
import json
import base64
import subprocess

# Claude에게 전달할 음식 분석 프롬프트
PROMPT = """다음 음식 사진을 분석하여 JSON만 반환하세요. 다른 텍스트는 절대 포함하지 마세요.
혼합 음식(예: 김밥, 비빔밥)은 하나의 항목으로 처리하세요.
음식의 양은 한국 일반 1인분 기준(Standard serving size)으로 추정하세요.

반환 형식:
{
  "foods": [
    {"name": "음식명", "amount": "추정량(예: 1인분, 200g)", "calories": 숫자, "carbs": 숫자, "protein": 숫자, "fat": 숫자, "quantity": 1.0}
  ],
  "total_calories": 숫자
}

carbs(탄수화물), protein(단백질), fat(지방)은 그램(g) 단위 정수로 추정하세요.

음식을 인식할 수 없으면:
{"foods": [], "total_calories": 0, "error": "음식을 인식할 수 없습니다"}"""


def _parse_json(raw_text: str) -> dict:
    """응답 텍스트에서 JSON 객체만 추출 (Markdown 코드 블록이 붙어도 대응)"""
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError("응답에서 JSON을 찾을 수 없습니다")
    return json.loads(match.group())


def analyze_food_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Claude Code CLI를 subprocess로 호출해 음식 사진을 분석한다 (Max 플랜 활용).

    ANTHROPIC_API_KEY를 환경에서 제거하면 CLI가 API 크레딧 대신
    Max 플랜 OAuth 인증을 사용하므로 별도 크레딧 불필요.

    입력 방식: --input-format stream-json으로 이미지(base64)와 프롬프트를 stdin에 전달
    출력 방식: --output-format stream-json으로 받은 이벤트에서 텍스트 추출 후 JSON 파싱

    Returns: {"foods": [...], "total_calories": N} 또는 {"error": "..."}
    """
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

    # Claude API 메시지 형식: 이미지 + 텍스트 프롬프트를 한 user 메시지로 구성
    message = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {"type": "text", "text": PROMPT},
            ],
        },
    }

    # ANTHROPIC_API_KEY 제거 → CLI가 Max 플랜 OAuth로 인증
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    result = subprocess.run(
        [
            "claude",
            "--print",
            "--input-format", "stream-json",   # stdin으로 JSON 메시지 수신
            "--output-format", "stream-json",  # 응답을 줄 단위 JSON 이벤트로 출력
            "--verbose",                        # stream-json 출력에 필수 플래그
        ],
        input=json.dumps(message).encode("utf-8"),
        capture_output=True,
        timeout=60,
        env=env,
    )

    # bytes로 받아 utf-8 디코딩 (Windows 기본 인코딩 cp949 깨짐 방지)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")

    if result.returncode != 0:
        raise RuntimeError(stderr.strip() or "claude CLI 오류")

    # stream-json 이벤트를 순회해 assistant 텍스트 추출
    text_parts = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        # result 이벤트: 최종 응답 텍스트 (있으면 바로 반환)
        if event.get("type") == "result":
            raw = event.get("result", "")
            if raw:
                return _parse_json(raw)

        # assistant 이벤트: 스트리밍 텍스트 조각 수집
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])

    return _parse_json("".join(text_parts))
