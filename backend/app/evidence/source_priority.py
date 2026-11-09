"""Source reliability hints for display; conflicts remain unresolved."""
SOURCE_PRIORITY = {'database': 1.0, 'table': .95, 'text': .9, 'chart': .8, 'image': .7}


def priority(source_type: str) -> float:
    return SOURCE_PRIORITY.get(source_type, .5)
