"""Local Chinese word boundaries for lettering; never rewrites the translation."""
from functools import lru_cache
import logging
import re


@lru_cache(maxsize=1)
def tokenizer():
    import jieba
    jieba.setLogLevel(logging.ERROR)
    return jieba.Tokenizer()


@lru_cache(maxsize=512)
def word_spans(text):
    from opencc import OpenCC
    # Segment a simplified analysis copy to use the bundled jieba vocabulary.
    # Offsets are used only if character lengths match; original glyphs survive.
    analysis = OpenCC("t2s").convert(text)
    if len(analysis) != len(text):
        analysis = text
    spans = []
    offset = 0
    for word in tokenizer().cut(analysis, HMM=True):
        end = offset + len(word)
        spans.append((offset, end, text[offset:end]))
        offset = end
    return tuple(spans)


@lru_cache(maxsize=512)
def boundary_costs(text, protected_terms=()):
    """None forbids splitting a word/name; lower costs prefer phrase endings."""
    costs = {index: 12.0 for index in range(1, len(text))}
    spans = word_spans(text)
    attach_next = {"把", "被", "讓", "跟", "向", "在", "從", "拿", "用", "替", "給", "與", "和", "及", "的", "就", "才", "又", "也", "還", "不", "很"}
    attach_previous = {"的", "地", "得", "了", "嗎", "呢", "啊", "吧", "啦", "喔", "哦"}
    for start, end, word in spans:
        for boundary in range(start + 1, end):
            costs[boundary] = None
        if end < len(text) and word in attach_next:
            costs[end] = 45.0
        if start and word in attach_previous:
            costs[start] = 35.0
        if end < len(text) and word[-1:] in "，。、；：！？!?…":
            costs[end] = 0.0
    # Keep personal names attached to their title when recognized as two words.
    terms = list(protected_terms)
    for index, (start, end, word) in enumerate(spans):
        if word in {"不", "沒", "未", "無"} and index + 1 < len(spans):
            _, next_end, following = spans[index + 1]
            if re.fullmatch(r"[一-龯]{1,3}", following):
                terms.append(text[start:next_end])
        if index and word in {"著", "了", "過"}:
            a, _, previous = spans[index - 1]
            if re.fullmatch(r"[一-龯]{1,3}", previous):
                terms.append(text[a:end])
        if index and word in {"公主", "王子", "先生", "小姐", "隊長", "博士"}:
            a, b, name = spans[index - 1]
            if 2 <= len(name) <= 4 and name not in {"這位", "那位", "一位", "這個", "那個", "我的", "你的"}:
                terms.append(text[a:end])
    for term in terms:
        if not term:
            continue
        for match in re.finditer(re.escape(term), text):
            for boundary in range(match.start() + 1, match.end()):
                costs[boundary] = None
    return costs
