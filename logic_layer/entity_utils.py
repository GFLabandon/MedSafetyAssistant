# entity_utils.py
import re

DRUG_MAPPING = {
    "泰诺": "泰诺",
    "白加黑": "白加黑",
    "感康": "感康",
    "快克": "快克",
    "维C银翘片": "维C银翘片",
    "连花清瘟": "连花清瘟",
    "布洛芬": "布洛芬缓释胶囊",
    "美林": "美林",
    "阿司匹林": "阿司匹林肠溶片",
    "头孢": "头孢拉定",
    "头孢拉定": "头孢拉定",
    "阿莫西林": "阿莫西林",
    "罗红霉素": "罗红霉素",
    "氯雷他定": "氯雷他定片",
    "西替利嗪": "西替利嗪片",
    "硝苯地平": "硝苯地平"
}

CONDITION_MAPPING = {
    "高血压": "高血压",
    "喝酒": "饮酒状态",
    "饮酒": "饮酒状态",
    "酒": "饮酒状态",
    "怀孕": "妊娠期",
    "开车": "驾驶/高空作业",
    "胃病": "胃溃疡",
    "小孩": "儿童",
    "儿童": "儿童",
    "孩子": "儿童",
    "宝宝": "儿童",
    "老人": "老年患者",
    "老人家": "老年患者",
    "过敏": "青霉素/头孢过敏体质"
}

# entity_utils.py 扩展
DRUG_ALIAS_MAP = {
    "扑热息痛": "对乙酰氨基酚",
    "paracetamol": "对乙酰氨基酚",
    "泰诺": "泰诺",
    "芬必得": "布洛芬缓释胶囊",
    "ibuprofen": "布洛芬缓释胶囊",
    "advil": "布洛芬缓释胶囊",
    "美林": "美林",
    "阿司匹林": "阿司匹林肠溶片",
    "aspirin": "阿司匹林肠溶片"
}

def normalize_entity(text):
    text = text.lower().strip()
    return DRUG_ALIAS_MAP.get(text, text)

def exact_entity_extraction(text):
    found_drugs = set()
    found_conditions = set()

    for keyword, std_name in DRUG_MAPPING.items():
        if keyword in text:
            found_drugs.add(std_name)

    for keyword, std_name in CONDITION_MAPPING.items():
        if keyword in text:
            found_conditions.add(std_name)

    return list(found_drugs), list(found_conditions)