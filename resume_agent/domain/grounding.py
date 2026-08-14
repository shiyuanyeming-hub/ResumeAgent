"""Grounding checks for generated self-summary options."""

import re

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_numbers(text: str):
    return set(NUMBER_RE.findall(text))


def collect_fact_texts(base, version):
    texts = []
    selected = set(version.selected_experience_ids or [])
    for experience in base.experiences:
        if selected and experience.id not in selected:
            continue
        for values in experience.statements.values():
            texts.extend(value.text for value in values)
    return texts
