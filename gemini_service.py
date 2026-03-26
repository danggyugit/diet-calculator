import os
import re
import json
from google import genai
from google.genai import types

# 무료 티어 기준 하루 500회, 분당 10회 제한
MODEL = "gemini-2.5-flash"

# Claude와 동일한 음식 분석 프롬프트
PROMPT = """다음 음식 사진을 분석하여 JSON만 반환하세요. 다른 텍스트는 절대 포함하지 마세요.
혼합 음식(예: 김밥, 비빔밥)은 하나의 항목으로 처리하세요.
음식의 양은 한국 일반 1인분 기준(Standard serving size)으로 추정하세요.

반환 형식:
{
  "foods": [
    {"name": "음식명", "amount": "추정량(예: 1인분, 200g)", "calories": 숫자, "quantity": 1.0}
  ],
  "total_calories": 숫자
}

음식을 인식할 수 없으면:
{"foods": [], "total_calories": 0, "error": "음식을 인식할 수 없습니다"}"""


def _parse_json(raw_text: str) -> dict:
    """응답에서 JSON 객체만 추출 (Markdown 코드 블록 방어)"""
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError("응답에서 JSON을 찾을 수 없습니다")
    return json.loads(match.group())


def analyze_food_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Gemini Vision API로 음식 사진 분석 (무료 티어 사용).
    Returns: {"foods": [...], "total_calories": N} 또는 {"error": "..."}
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=media_type),
            PROMPT,
        ],
    )

    return _parse_json(response.text)
