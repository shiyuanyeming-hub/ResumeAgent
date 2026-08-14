"""Questionnaire section order and static option tables (zh-first)."""

SECTION_ORDER = ["profile", "target", "education", "experience", "skills", "summary"]

SECTION_LABELS = {
    "profile": "基本信息",
    "target": "求职意向",
    "education": "教育背景",
    "experience": "经历",
    "skills": "技能",
    "summary": "自我评价",
}

PROFILE_STEPS = [
    ("name", "你的姓名是？"),
    ("email", "常用邮箱是？（会出现在简历联系信息里）"),
    ("phone", "联系电话是？"),
    ("location", "目前所在地？（可跳过）"),
    ("links", "个人链接，每行一个，如 GitHub、作品集（可跳过）"),
]

TARGET_STEPS = [
    ("role", "目标岗位是？（例如：数据分析师）"),
    ("city", "目标工作城市？（可跳过）"),
]

DEGREE_OPTIONS = ["高中", "大专", "本科", "硕士", "博士"]

EXPERIENCE_TYPE_OPTIONS = [
    ("internship", "实习"),
    ("work", "工作"),
    ("project", "项目"),
    ("campus", "校园经历"),
]

EXPERIENCE_DONE_OPTION = "经历填写完成"
EDUCATION_DONE_OPTION = "教育填写完成"
