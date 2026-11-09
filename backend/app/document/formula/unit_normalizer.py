from app.core.errors import AppError

SCALE = {'元': ('money', 1), '万元': ('money', 10000), '亿元': ('money', 100000000),
         '%': ('ratio', .01), '秒': ('time', 1), '分钟': ('time', 60),
         'KB': ('size', 1), 'MB': ('size', 1024), 'GB': ('size', 1024 * 1024),
         '': ('number', 1)}


def normalize_value(value: float, unit: str) -> tuple[float, str]:
    if unit not in SCALE:
        raise AppError('FORMULA_UNIT_UNKNOWN', f'不支持的单位：{unit}', 422)
    kind, scale = SCALE[unit]
    return value * scale, kind
