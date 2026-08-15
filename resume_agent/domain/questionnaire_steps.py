"""Questionnaire section order and static option tables (zh-first)."""

SECTION_ORDER = ["profile", "target", "education", "experience", "skills", "summary"]

SECTION_LABELS = {
    "profile": "基本信息",
    "target": "求职意向",
    "education": "教育背景",
    "experience": "实习与项目经历",
    "skills": "技能证书",
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

# 学历优先的新流程：先问最高学历，再自上而下逐段填写
FIRST_DEGREE_OPTIONS = ["博士", "硕士", "本科", "专科", "高中及以下"]
NEXT_DEGREE_OPTIONS = ["博士", "硕士", "本科", "专科"]
HIGH_SCHOOL_OPTION = "高中及以下"

EXPERIENCE_TYPE_OPTIONS = [
    ("internship", "实习"),
    ("work", "工作"),
    ("project", "项目"),
    ("campus", "校园经历"),
]

EXPERIENCE_DONE_OPTION = "经历填写完成"
EDUCATION_DONE_OPTION = "教育填写完成"
