from resume_agent.domain.course_catalog import catalog_majors, courses_for_major


def test_catalog_has_expected_majors():
    majors = catalog_majors()
    assert "计算机科学与技术" in majors
    assert len(majors) >= 8


def test_courses_for_known_major():
    courses = courses_for_major("计算机科学与技术")
    assert "数据结构" in courses
    assert len(courses) >= 8


def test_courses_for_unknown_major_empty():
    assert courses_for_major("不存在的专业") == []


def test_majors_for_school_prefers_school_category():
    from resume_agent.domain.course_catalog import majors_for_school, school_category
    assert school_category("华中科技大学") == "工科"
    tech = majors_for_school("华中科技大学")
    assert tech[0] == "计算机科学与技术"
    assert school_category("北京师范大学") == "教育"
    edu = majors_for_school("北京师范大学")
    assert "教育学" in edu[:3]
    assert school_category("中央财经大学") == "经管"
    finance = majors_for_school("中央财经大学")
    assert "金融学" in finance[:4]


def test_majors_for_unknown_school_uses_default_order():
    from resume_agent.domain.course_catalog import majors_for_school
    majors = majors_for_school("某某职业技术学院")
    assert majors[0] == "计算机科学与技术"
    assert len(majors) == len(set(majors))


def test_majors_for_overseas_school():
    from resume_agent.domain.course_catalog import majors_for_school, school_category
    assert school_category("哈佛大学") == "综合"
    assert len(majors_for_school("哈佛大学")) >= 30
