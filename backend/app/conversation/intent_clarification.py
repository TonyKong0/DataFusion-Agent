"""Persisted clarification for popularity questions with missing semantics."""

import re


POPULARITY = re.compile(r'最流行|最火|最热门|最受欢迎|最爆火')
SALES = re.compile(r'销量|销售量|销售数量|购买数量|购买次数|购买量|售出|卖出')
PLAYS = re.compile(r'播放量|播放次数|收听量|收听次数')
GENRE = re.compile(r'音乐类型|音乐流派|曲风|流派|类型')
TRACK = re.compile(r'歌曲|曲目|歌名|首歌')
NEW_TOPIC = re.compile(r'列出|列举|显示|展示|统计|一共有|多少|为什么|怎么|如何|比较|对比')


def _entity(text: str) -> str | None:
    if GENRE.search(text):
        return 'genre'
    if TRACK.search(text):
        return 'track'
    return None


def _metric(text: str) -> str | None:
    if PLAYS.search(text):
        return 'plays'
    if SALES.search(text):
        return 'sales'
    return None


def needs_clarification(question: str) -> bool:
    return bool(POPULARITY.search(question) and
                (_entity(question) is None or _metric(question) != 'sales'))


def starts_reply(question: str, pending: dict) -> bool:
    text = question.strip()
    if text in {'取消', '算了'}:
        return True
    if POPULARITY.search(text) or NEW_TOPIC.search(text):
        return False
    return len(text) <= 40 and bool(_entity(text) or _metric(text) or text in {'不知道', '不确定'})


def start(question: str) -> dict:
    return {'original_question': question, 'entity': _entity(question),
            'metric': _metric(question)}


def update(pending: dict, answer: str) -> dict:
    return {**pending, 'entity': _entity(answer) or pending.get('entity'),
            'metric': _metric(answer) or pending.get('metric')}


def clarification(pending: dict) -> dict:
    entity, metric = pending.get('entity'), pending.get('metric')
    if metric == 'plays':
        prompt = 'Chinook 数据库没有播放量或收听量记录。是否改用购买数量（销量）衡量？'
        options = ([f'按销量查{"歌曲" if entity == "track" else "音乐类型"}'] if entity else
                   ['按销量查歌曲', '按销量查音乐类型'])
    elif not entity:
        prompt = '你想查最流行的歌曲，还是音乐类型？当前数据库可按购买数量（销量）衡量，没有播放量数据。'
        options = ['按销量查歌曲', '按销量查音乐类型']
    else:
        label = '歌曲' if entity == 'track' else '音乐类型'
        prompt = f'你说的“最流行的{label}”按什么衡量？当前数据库可按购买数量（销量）查询，没有播放量数据。'
        options = [f'按销量查{label}']
    return {'kind': 'single_choice', 'question': prompt,
            'options': [*options, '取消'], 'context': True}


def resolved_question(pending: dict) -> str | None:
    if pending.get('metric') != 'sales':
        return None
    if pending.get('entity') == 'track':
        return '最流行的歌曲按销量衡量是哪首？'
    if pending.get('entity') == 'genre':
        return '销量最高的音乐类型是哪种？'
    return None
