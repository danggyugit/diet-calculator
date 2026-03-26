import math

# MET 값 테이블 (운동명, MET, 분류)
EXERCISE_TABLE = [
    {"name": "걷기 (빠른 걸음)", "met": 4.5, "category": "유산소", "icon": "🚶"},
    {"name": "달리기 (6km/h)",   "met": 9.8, "category": "유산소", "icon": "🏃"},
    {"name": "자전거",            "met": 7.5, "category": "유산소", "icon": "🚴"},
    {"name": "수영",              "met": 8.0, "category": "유산소", "icon": "🏊"},
    {"name": "스쿼트",            "met": 5.0, "category": "근력",   "icon": "🏋️"},
    {"name": "플랭크",            "met": 3.8, "category": "근력",   "icon": "💪"},
    {"name": "팔굽혀펴기",        "met": 8.0, "category": "근력",   "icon": "🤸"},
    {"name": "버피",              "met": 10.0,"category": "유산소+근력", "icon": "⚡"},
]

DEFAULT_HEIGHT = {"남성": 170, "여성": 160}


def calc_bmr(weight: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor 공식으로 기초대사량(BMR) 계산"""
    height = DEFAULT_HEIGHT.get(gender, 165)
    if gender == "남성":
        return (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        return (10 * weight) + (6.25 * height) - (5 * age) - 161


def _round_up_5(minutes: float) -> int:
    """5분 단위로 올림"""
    return math.ceil(minutes / 5) * 5


def calc_exercise_plan(total_calories: float, weight: float, age: int, gender: str) -> list:
    """
    총 칼로리를 소모하기 위한 운동별 필요 시간 계산
    - MET × 체중(kg) / 60 = kcal/min
    - 최소 시간: 필요 시간의 80% (5분 단위 올림)
    - 권장 시간: 필요 시간 100% (5분 단위 올림)
    """
    plan = []
    for ex in EXERCISE_TABLE:
        kcal_per_min = ex["met"] * weight / 60
        required_min = total_calories / kcal_per_min
        plan.append({
            "name":     ex["name"],
            "category": ex["category"],
            "icon":     ex["icon"],
            "min_time": _round_up_5(required_min * 0.8),
            "rec_time": _round_up_5(required_min),
        })
    return plan
