import os
import uuid
import base64
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session

# .env 파일에서 환경변수 로드 (override=True: 시스템 환경변수보다 .env 우선)
load_dotenv(Path(__file__).parent / ".env", override=True)

from gemini_service import analyze_food_image
from calorie_service import calc_exercise_plan

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "diet-calculator-secret-2026")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MEDIA_TYPE_MAP = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}

# 이미지를 서버 메모리에 보관하는 캐시
# Flask 세션은 쿠키 기반(4KB 한도)이라 이미지를 직접 저장하면 ERR_RESPONSE_HEADERS_TOO_BIG 발생
# → 이미지는 여기 저장하고, 세션엔 UUID 키만 보관
_image_cache: dict[str, tuple[bytes, str]] = {}


def _validate_file(file) -> tuple:
    """업로드 파일 유효성 검사 (존재 여부 / 확장자 / 크기)"""
    if not file or file.filename == "":
        return False, "파일을 선택해주세요."
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return False, "JPG, PNG 파일만 업로드할 수 있습니다."
    file.seek(0, 2)   # 파일 끝으로 이동해 크기 측정
    size = file.tell()
    file.seek(0)      # 다시 처음으로 되돌림
    if size > MAX_FILE_SIZE:
        return False, "10MB 이하 파일만 업로드할 수 있습니다."
    return True, ""


@app.route("/")
def index():
    """메인 페이지: 사진 업로드 폼"""
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    음식 사진 분석 엔드포인트
    1. 파일 유효성 검사
    2. Claude CLI로 음식 인식 및 칼로리 추정
    3. 이미지는 _image_cache에 저장, 분석 결과는 세션에 저장
    4. 결과 페이지로 리다이렉트
    """
    file = request.files.get("food_image")
    is_valid, err_msg = _validate_file(file)
    if not is_valid:
        return render_template("index.html", error=err_msg)

    weight = float(request.form.get("weight", 70))
    age    = int(request.form.get("age", 30))
    gender = request.form.get("gender", "남성")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    media_type  = MEDIA_TYPE_MAP.get(ext, "image/jpeg")
    image_bytes = file.read()

    try:
        result = analyze_food_image(image_bytes, media_type)
    except Exception as e:
        return render_template("error.html",
                               message="분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                               detail=str(e))

    if result.get("error") or not result.get("foods"):
        return render_template("error.html",
                               message="음식을 인식하지 못했습니다. 음식이 잘 보이는 사진으로 다시 시도해주세요.")

    # 이미지는 메모리 캐시에, 세션엔 UUID 키만 저장
    image_key = str(uuid.uuid4())
    _image_cache[image_key] = (image_bytes, media_type)

    session["image_key"]      = image_key
    session["foods"]          = result["foods"]
    session["total_calories"] = result["total_calories"]
    session["weight"]         = weight
    session["age"]            = age
    session["gender"]         = gender

    return redirect(url_for("result"))


def _get_image_b64(image_key: str | None) -> tuple[str | None, str]:
    """캐시에서 이미지를 꺼내 base64 문자열로 변환 (템플릿에서 <img src> 용도)"""
    if not image_key or image_key not in _image_cache:
        return None, "image/jpeg"
    img_bytes, mime = _image_cache[image_key]
    return base64.b64encode(img_bytes).decode(), mime


@app.route("/result")
def result():
    """
    분석 결과 페이지
    - 인식된 음식 목록 및 칼로리 표시
    - 칼로리 소모를 위한 운동 계획 계산
    """
    if "foods" not in session:
        return redirect(url_for("index"))

    exercise_plan = calc_exercise_plan(
        session["total_calories"],
        session["weight"],
        session["age"],
        session["gender"],
    )
    image_b64, image_mime = _get_image_b64(session.get("image_key"))
    return render_template("result.html",
                           foods=session["foods"],
                           total_calories=session["total_calories"],
                           exercise_plan=exercise_plan,
                           weight=session["weight"],
                           age=session["age"],
                           gender=session["gender"],
                           image_b64=image_b64,
                           image_mime=image_mime)


@app.route("/recalculate", methods=["POST"])
def recalculate():
    """
    음식 수량 조정 / 삭제 후 칼로리 재계산
    - delete_{i} 폼 필드가 있으면 해당 음식 삭제
    - quantity_{i} 폼 필드로 수량 변경 (0.5 ~ 10.0 범위 제한)
    - 변경된 음식 목록으로 운동 계획 재계산
    """
    if "foods" not in session:
        return redirect(url_for("index"))

    foods  = session["foods"]
    weight = session["weight"]
    age    = session["age"]
    gender = session["gender"]

    # 삭제 처리: delete_{인덱스} 키가 있는 항목 제거
    delete_indices = {int(k.split("_")[1]) for k in request.form if k.startswith("delete_")}
    foods = [f for i, f in enumerate(foods) if i not in delete_indices]

    # 수량 반영 및 총 칼로리 재계산
    total_calories = 0
    for i, food in enumerate(foods):
        qty = float(request.form.get(f"quantity_{i}", food.get("quantity", 1.0)))
        qty = max(0.5, min(qty, 10.0))  # 0.5 ~ 10.0 범위 클램프
        food["quantity"] = qty
        total_calories += food["calories"] * qty

    total_calories = round(total_calories)
    session["foods"]          = foods
    session["total_calories"] = total_calories

    image_b64, image_mime = _get_image_b64(session.get("image_key"))
    exercise_plan = calc_exercise_plan(total_calories, weight, age, gender)
    return render_template("result.html",
                           foods=foods,
                           total_calories=total_calories,
                           exercise_plan=exercise_plan,
                           weight=weight,
                           age=age,
                           gender=gender,
                           image_b64=image_b64,
                           image_mime=image_mime)


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
