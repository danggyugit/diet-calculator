# TRD (Technical Requirements Document)
# 음식 사진 칼로리 계산 & 다이어트 운동 추천 앱

**버전**: 1.0
**작성일**: 2026-03-26
**참조 PRD**: PRD.md v1.0

---

## 1. 기술 스택

| 구분 | 기술 | 비고 |
|---|---|---|
| 백엔드 | Flask (Python) | 로컬 실행 |
| AI | Claude Vision API | claude-sonnet-4-6 모델 |
| 프론트엔드 | Jinja2 + Bootstrap 5 | 드래그앤드롭: 순수 JS |
| 칼로리 계산 | Mifflin-St Jeor + MET | BMR × 활동계수 보정 |
| 세션 관리 | Flask session | 분석 결과 임시 저장 |
| 배포 | 로컬 실행 | `python app.py` |

---

## 2. 파일 구조

```
py/diet_calculator/
├── app.py                  # Flask 앱 진입점, 라우팅
├── claude_service.py       # Claude Vision API 호출, JSON 파싱
├── calorie_service.py      # BMR + MET 기반 운동 소모 계산
├── docs/
│   ├── PRD.md
│   └── TRD.md
├── templates/
│   ├── index.html          # 메인 페이지 (업로드 폼 + 사용자 정보)
│   ├── result.html         # 결과 페이지 (수량 수정 + 운동 플랜)
│   └── error.html          # 에러 페이지
└── static/
    └── style.css           # 커스텀 스타일
```

---

## 3. 시스템 아키텍처

```
[브라우저]
    │  POST: 이미지 파일 + {weight, age, gender}
    ▼
[Flask - app.py]
    │
    ├── GET  /              → index.html (업로드 폼)
    ├── POST /analyze       → 파일 검증 → Claude API → 결과 세션 저장 → redirect
    ├── GET  /result        → 세션에서 결과 읽기 → result.html
    ├── POST /recalculate   → 수량 수정 후 재계산 → result.html
    └── GET  /error         → error.html (에러 메시지 표시)
    │
    ├── claude_service.py
    │     └── analyze_food_image(image_bytes) → {"foods": [...], "total_calories": N}
    │
    └── calorie_service.py
          ├── calc_bmr(weight, age, gender) → BMR (kcal/day)
          └── calc_exercise_plan(total_calories, weight, age, gender) → [exercise_plan]
```

---

## 4. Claude Vision API 설계

### 4.1 프롬프트

```
다음 음식 사진을 분석하여 JSON만 반환하세요. 다른 텍스트는 절대 포함하지 마세요.
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
{"foods": [], "total_calories": 0, "error": "음식을 인식할 수 없습니다"}
```

### 4.2 JSON 파싱 방어 로직

API 응답에 Markdown 코드 블록이 포함될 수 있으므로 정규표현식으로 JSON만 추출:

```python
import re, json

def parse_response(raw_text: str) -> dict:
    # ```json ... ``` 또는 ``` ... ``` 블록 제거
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError("JSON을 찾을 수 없습니다")
    return json.loads(match.group())
```

---

## 5. 칼로리 소모 계산 설계

### 5.1 BMR 계산 (Mifflin-St Jeor 공식)

나이·성별을 계산에 반영:

```
남성 BMR = (10 × 체중kg) + (6.25 × 키cm) - (5 × 나이) + 5
여성 BMR = (10 × 체중kg) + (6.25 × 키cm) - (5 × 나이) - 161
```

> 키(cm)는 기본값 170(남) / 160(여) 사용 (입력받지 않음)

### 5.2 운동별 칼로리 소모 계산

```
소모 칼로리(kcal/min) = MET × 체중(kg) × (1/60)
필요 시간(분) = 총 칼로리 / (MET × 체중 / 60)
최소 시간 = 필요 시간 × 0.8  (80% 기준)
권장 시간 = 필요 시간         (100% 기준)
표시 단위 = 5분 단위로 올림
```

### 5.3 운동 MET 테이블

| 운동 | MET | 분류 |
|---|---|---|
| 걷기 (빠른 걸음) | 4.5 | 유산소 |
| 달리기 (6km/h) | 9.8 | 유산소 |
| 자전거 | 7.5 | 유산소 |
| 수영 | 8.0 | 유산소 |
| 스쿼트 | 5.0 | 근력 |
| 플랭크 | 3.8 | 근력 |
| 팔굽혀펴기 | 8.0 | 근력 |
| 버피 | 10.0 | 유산소+근력 |

> 향후 JSON 파일로 분리하여 운동 종목 확장 가능하도록 설계

---

## 6. 파일 업로드 검증

```python
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_file(file) -> tuple[bool, str]:
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "JPG, PNG 파일만 업로드할 수 있습니다."
    file.seek(0, 2)  # 파일 끝으로 이동
    size = file.tell()
    file.seek(0)     # 파일 처음으로 복귀
    if size > MAX_FILE_SIZE:
        return False, "10MB 이하 파일만 업로드할 수 있습니다."
    return True, ""
```

---

## 7. 에러 처리 경로

| 상황 | 처리 방법 |
|---|---|
| 파일 검증 실패 | index.html에 인라인 에러 메시지 표시 |
| Claude API 호출 실패 | error.html로 redirect, 에러 메시지 전달 |
| 음식 인식 0개 | error.html로 redirect, "재시도" 버튼 제공 |
| 세션 없이 /result 접근 | / 로 redirect |

---

## 8. 수량 수정 UI 설계

result.html에서 음식별 수량을 조정 후 `/recalculate` POST:

```html
<!-- 음식 카드 예시 -->
<form action="/recalculate" method="POST">
  <div class="food-card">
    <span>된장찌개</span>
    <input type="number" name="quantity_0" value="1.0" min="0.5" max="5" step="0.5">
    <span>인분 × 450 kcal</span>
  </div>
  <button type="submit">재계산</button>
</form>
```

---

## 9. 환경 변수

```bash
ANTHROPIC_API_KEY=<Claude API 키>
```

`.env` 파일 또는 시스템 환경 변수로 관리. 코드에 하드코딩 금지.

---

## 10. 로딩 스피너 구현

```javascript
// index.html - 폼 제출 시 스피너 표시
document.querySelector('form').addEventListener('submit', function() {
    document.getElementById('spinner').style.display = 'block';
    document.getElementById('submit-btn').disabled = true;
    document.getElementById('submit-btn').textContent = '분석 중...';
});
```

---

## 11. 검증 방법 (End-to-End)

```bash
# 1. 패키지 설치
pip install flask anthropic python-dotenv

# 2. 환경 변수 설정
set ANTHROPIC_API_KEY=<키>

# 3. 서버 실행
python c:/Users/sk15y/claude/py/diet_calculator/app.py

# 4. 브라우저 접속
http://localhost:5000
```

### 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T1 | 한식 단일 음식 사진 업로드 | 음식명, 칼로리, 운동 플랜 정상 출력 |
| T2 | 여러 음식이 담긴 사진 업로드 | 음식별 분리 표시 |
| T3 | 수량 수정 후 재계산 | 칼로리 및 운동 시간 업데이트 |
| T4 | PNG 이외 파일 업로드 시도 | 에러 메시지 출력 |
| T5 | 10MB 초과 파일 업로드 시도 | 에러 메시지 출력 |
| T6 | 음식이 없는 사진 업로드 | 에러 페이지 + 재시도 안내 |
