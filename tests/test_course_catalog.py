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
