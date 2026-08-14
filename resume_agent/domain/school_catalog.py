"""学校目录：支持名称、全拼、首字母模糊搜索（中文简历优先）。"""

import re
from typing import Dict, List, Optional

try:
    from pypinyin import Style, lazy_pinyin
    _HAS_PYPINYIN = True
except Exception:  # 缺依赖时降级为纯名称匹配
    _HAS_PYPINYIN = False

SCHOOLS: List[Dict[str, str]] = [
    # 北京
    {"name": "清华大学", "province": "北京", "tags": "985 211"},
    {"name": "北京大学", "province": "北京", "tags": "985 211"},
    {"name": "中国人民大学", "province": "北京", "tags": "985 211"},
    {"name": "北京航空航天大学", "province": "北京", "tags": "985 211"},
    {"name": "北京理工大学", "province": "北京", "tags": "985 211"},
    {"name": "北京师范大学", "province": "北京", "tags": "985 211"},
    {"name": "中国农业大学", "province": "北京", "tags": "985 211"},
    {"name": "中央民族大学", "province": "北京", "tags": "985 211"},
    {"name": "北京交通大学", "province": "北京", "tags": "211"},
    {"name": "北京工业大学", "province": "北京", "tags": "211"},
    {"name": "北京科技大学", "province": "北京", "tags": "211"},
    {"name": "北京化工大学", "province": "北京", "tags": "211"},
    {"name": "北京邮电大学", "province": "北京", "tags": "211"},
    {"name": "北京林业大学", "province": "北京", "tags": "211"},
    {"name": "北京中医药大学", "province": "北京", "tags": "211"},
    {"name": "首都师范大学", "province": "北京", "tags": "双一流"},
    {"name": "中央财经大学", "province": "北京", "tags": "211"},
    {"name": "对外经济贸易大学", "province": "北京", "tags": "211"},
    {"name": "北京外国语大学", "province": "北京", "tags": "211"},
    {"name": "中国政法大学", "province": "北京", "tags": "211"},
    {"name": "华北电力大学", "province": "北京", "tags": "211"},
    {"name": "中国传媒大学", "province": "北京", "tags": "211"},
    {"name": "中国石油大学", "province": "北京", "tags": "211"},
    {"name": "中国地质大学", "province": "北京", "tags": "211"},
    {"name": "中国矿业大学", "province": "北京", "tags": "211"},
    {"name": "中央音乐学院", "province": "北京", "tags": "211"},
    {"name": "北京体育大学", "province": "北京", "tags": "211"},
    {"name": "首都医科大学", "province": "北京", "tags": ""},
    {"name": "首都经济贸易大学", "province": "北京", "tags": ""},
    {"name": "北京语言大学", "province": "北京", "tags": ""},
    # 天津
    {"name": "南开大学", "province": "天津", "tags": "985 211"},
    {"name": "天津大学", "province": "天津", "tags": "985 211"},
    {"name": "天津医科大学", "province": "天津", "tags": "211"},
    {"name": "天津财经大学", "province": "天津", "tags": ""},
    {"name": "天津工业大学", "province": "天津", "tags": "双一流"},
    # 河北
    {"name": "河北工业大学", "province": "天津", "tags": "211"},
    {"name": "燕山大学", "province": "河北", "tags": ""},
    {"name": "河北大学", "province": "河北", "tags": ""},
    # 山西
    {"name": "太原理工大学", "province": "山西", "tags": "211"},
    {"name": "山西大学", "province": "山西", "tags": "双一流"},
    # 内蒙古
    {"name": "内蒙古大学", "province": "内蒙古", "tags": "211"},
    # 辽宁
    {"name": "大连理工大学", "province": "辽宁", "tags": "985 211"},
    {"name": "东北大学", "province": "辽宁", "tags": "985 211"},
    {"name": "大连海事大学", "province": "辽宁", "tags": "211"},
    {"name": "辽宁大学", "province": "辽宁", "tags": "211"},
    {"name": "中国医科大学", "province": "辽宁", "tags": ""},
    {"name": "东北财经大学", "province": "辽宁", "tags": ""},
    # 吉林
    {"name": "吉林大学", "province": "吉林", "tags": "985 211"},
    {"name": "东北师范大学", "province": "吉林", "tags": "211"},
    {"name": "延边大学", "province": "吉林", "tags": "211"},
    # 黑龙江
    {"name": "哈尔滨工业大学", "province": "黑龙江", "tags": "985 211"},
    {"name": "哈尔滨工程大学", "province": "黑龙江", "tags": "211"},
    {"name": "东北林业大学", "province": "黑龙江", "tags": "211"},
    {"name": "东北农业大学", "province": "黑龙江", "tags": "211"},
    {"name": "黑龙江大学", "province": "黑龙江", "tags": ""},
    {"name": "哈尔滨医科大学", "province": "黑龙江", "tags": ""},
    # 上海
    {"name": "复旦大学", "province": "上海", "tags": "985 211"},
    {"name": "上海交通大学", "province": "上海", "tags": "985 211"},
    {"name": "同济大学", "province": "上海", "tags": "985 211"},
    {"name": "华东师范大学", "province": "上海", "tags": "985 211"},
    {"name": "华东理工大学", "province": "上海", "tags": "211"},
    {"name": "东华大学", "province": "上海", "tags": "211"},
    {"name": "上海大学", "province": "上海", "tags": "211"},
    {"name": "上海财经大学", "province": "上海", "tags": "211"},
    {"name": "上海外国语大学", "province": "上海", "tags": "211"},
    {"name": "上海理工大学", "province": "上海", "tags": ""},
    {"name": "华东政法大学", "province": "上海", "tags": ""},
    {"name": "上海对外经贸大学", "province": "上海", "tags": ""},
    # 江苏
    {"name": "南京大学", "province": "江苏", "tags": "985 211"},
    {"name": "东南大学", "province": "江苏", "tags": "985 211"},
    {"name": "南京航空航天大学", "province": "江苏", "tags": "211"},
    {"name": "南京理工大学", "province": "江苏", "tags": "211"},
    {"name": "河海大学", "province": "江苏", "tags": "211"},
    {"name": "南京农业大学", "province": "江苏", "tags": "211"},
    {"name": "中国药科大学", "province": "江苏", "tags": "211"},
    {"name": "南京师范大学", "province": "江苏", "tags": "211"},
    {"name": "苏州大学", "province": "江苏", "tags": "211"},
    {"name": "江南大学", "province": "江苏", "tags": "211"},
    {"name": "南京邮电大学", "province": "江苏", "tags": "双一流"},
    {"name": "南京信息工程大学", "province": "江苏", "tags": "双一流"},
    {"name": "扬州大学", "province": "江苏", "tags": ""},
    {"name": "江苏大学", "province": "江苏", "tags": ""},
    {"name": "南京工业大学", "province": "江苏", "tags": ""},
    {"name": "南京审计大学", "province": "江苏", "tags": ""},
    # 浙江
    {"name": "浙江大学", "province": "浙江", "tags": "985 211"},
    {"name": "浙江工业大学", "province": "浙江", "tags": ""},
    {"name": "宁波大学", "province": "浙江", "tags": "双一流"},
    {"name": "杭州电子科技大学", "province": "浙江", "tags": ""},
    {"name": "浙江师范大学", "province": "浙江", "tags": ""},
    {"name": "温州医科大学", "province": "浙江", "tags": ""},
    {"name": "浙江工商大学", "province": "浙江", "tags": ""},
    # 安徽
    {"name": "中国科学技术大学", "province": "安徽", "tags": "985 211"},
    {"name": "合肥工业大学", "province": "安徽", "tags": "211"},
    {"name": "安徽大学", "province": "安徽", "tags": "211"},
    # 福建
    {"name": "厦门大学", "province": "福建", "tags": "985 211"},
    {"name": "福州大学", "province": "福建", "tags": "211"},
    {"name": "福建师范大学", "province": "福建", "tags": ""},
    # 江西
    {"name": "南昌大学", "province": "江西", "tags": "211"},
    {"name": "江西财经大学", "province": "江西", "tags": ""},
    # 山东
    {"name": "山东大学", "province": "山东", "tags": "985 211"},
    {"name": "中国海洋大学", "province": "山东", "tags": "985 211"},
    {"name": "青岛大学", "province": "山东", "tags": ""},
    {"name": "山东师范大学", "province": "山东", "tags": ""},
    {"name": "济南大学", "province": "山东", "tags": ""},
    # 河南
    {"name": "郑州大学", "province": "河南", "tags": "211"},
    {"name": "河南大学", "province": "河南", "tags": "双一流"},
    # 湖北
    {"name": "武汉大学", "province": "湖北", "tags": "985 211"},
    {"name": "华中科技大学", "province": "湖北", "tags": "985 211"},
    {"name": "武汉理工大学", "province": "湖北", "tags": "211"},
    {"name": "华中师范大学", "province": "湖北", "tags": "211"},
    {"name": "华中农业大学", "province": "湖北", "tags": "211"},
    {"name": "中南财经政法大学", "province": "湖北", "tags": "211"},
    {"name": "湖北大学", "province": "湖北", "tags": ""},
    {"name": "武汉科技大学", "province": "湖北", "tags": ""},
    # 湖南
    {"name": "湖南大学", "province": "湖南", "tags": "985 211"},
    {"name": "中南大学", "province": "湖南", "tags": "985 211"},
    {"name": "湖南师范大学", "province": "湖南", "tags": "211"},
    {"name": "湘潭大学", "province": "湖南", "tags": "双一流"},
    {"name": "长沙理工大学", "province": "湖南", "tags": ""},
    # 广东
    {"name": "中山大学", "province": "广东", "tags": "985 211"},
    {"name": "华南理工大学", "province": "广东", "tags": "985 211"},
    {"name": "暨南大学", "province": "广东", "tags": "211"},
    {"name": "华南师范大学", "province": "广东", "tags": "211"},
    {"name": "深圳大学", "province": "广东", "tags": ""},
    {"name": "广东工业大学", "province": "广东", "tags": ""},
    {"name": "南方医科大学", "province": "广东", "tags": ""},
    {"name": "广州大学", "province": "广东", "tags": ""},
    {"name": "华南农业大学", "province": "广东", "tags": "双一流"},
    {"name": "广东外语外贸大学", "province": "广东", "tags": ""},
    {"name": "南方科技大学", "province": "广东", "tags": "双一流"},
    # 广西
    {"name": "广西大学", "province": "广西", "tags": "211"},
    # 海南
    {"name": "海南大学", "province": "海南", "tags": "211"},
    # 重庆
    {"name": "重庆大学", "province": "重庆", "tags": "985 211"},
    {"name": "西南大学", "province": "重庆", "tags": "211"},
    {"name": "重庆邮电大学", "province": "重庆", "tags": ""},
    {"name": "西南政法大学", "province": "重庆", "tags": ""},
    {"name": "重庆医科大学", "province": "重庆", "tags": ""},
    # 四川
    {"name": "四川大学", "province": "四川", "tags": "985 211"},
    {"name": "电子科技大学", "province": "四川", "tags": "985 211"},
    {"name": "西南交通大学", "province": "四川", "tags": "211"},
    {"name": "西南财经大学", "province": "四川", "tags": "211"},
    {"name": "四川农业大学", "province": "四川", "tags": "211"},
    {"name": "成都理工大学", "province": "四川", "tags": "双一流"},
    {"name": "西南石油大学", "province": "四川", "tags": "双一流"},
    # 贵州
    {"name": "贵州大学", "province": "贵州", "tags": "211"},
    # 云南
    {"name": "云南大学", "province": "云南", "tags": "211"},
    {"name": "昆明理工大学", "province": "云南", "tags": ""},
    # 西藏
    {"name": "西藏大学", "province": "西藏", "tags": "211"},
    # 陕西
    {"name": "西安交通大学", "province": "陕西", "tags": "985 211"},
    {"name": "西北工业大学", "province": "陕西", "tags": "985 211"},
    {"name": "西北农林科技大学", "province": "陕西", "tags": "985 211"},
    {"name": "西安电子科技大学", "province": "陕西", "tags": "211"},
    {"name": "陕西师范大学", "province": "陕西", "tags": "211"},
    {"name": "长安大学", "province": "陕西", "tags": "211"},
    {"name": "西北大学", "province": "陕西", "tags": "211"},
    {"name": "西安建筑科技大学", "province": "陕西", "tags": ""},
    # 甘肃
    {"name": "兰州大学", "province": "甘肃", "tags": "985 211"},
    # 青海
    {"name": "青海大学", "province": "青海", "tags": "211"},
    # 宁夏
    {"name": "宁夏大学", "province": "宁夏", "tags": "211"},
    # 新疆
    {"name": "新疆大学", "province": "新疆", "tags": "211"},
    {"name": "石河子大学", "province": "新疆", "tags": "211"},
    # 港澳台（常见）
    {"name": "香港大学", "province": "香港", "tags": ""},
    {"name": "香港中文大学", "province": "香港", "tags": ""},
    {"name": "香港科技大学", "province": "香港", "tags": ""},
    {"name": "香港城市大学", "province": "香港", "tags": ""},
    {"name": "香港理工大学", "province": "香港", "tags": ""},
    {"name": "澳门大学", "province": "澳门", "tags": ""},
    {"name": "台湾大学", "province": "台湾", "tags": ""},
]

_HAN_RE = re.compile(r"[\u4e00-\u9fff]+")

_INDEX_CACHE: Optional[List[Dict[str, str]]] = None


def _han_part(name: str) -> str:
    return "".join(_HAN_RE.findall(name))


def _build_index() -> List[Dict[str, str]]:
    entries = []
    for school in SCHOOLS:
        entry = dict(school)
        han = _han_part(school["name"])
        if _HAS_PYPINYIN:
            entry["pinyin"] = "".join(lazy_pinyin(han))
            entry["initials"] = "".join(
                lazy_pinyin(han, style=Style.FIRST_LETTER)
            )
        else:
            entry["pinyin"] = ""
            entry["initials"] = ""
        entries.append(entry)
    return entries


def _school_index() -> List[Dict[str, str]]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = _build_index()
    return _INDEX_CACHE


def search_schools(query: str, limit: int = 8) -> List[Dict[str, str]]:
    """名称、全拼、首字母模糊搜索；返回 {name, province, tags}。"""
    q = (query or "").strip().lower()
    if not q:
        return []
    results = []
    for entry in _school_index():
        if (
            q in entry["name"].lower()
            or q in entry["pinyin"]
            or entry["initials"].startswith(q)
        ):
            results.append(
                {
                    "name": entry["name"],
                    "province": entry["province"],
                    "tags": entry["tags"],
                }
            )
    return results[: max(1, min(limit, 20))]
