"""References that point to the material selection supplied with this turn."""

import re


SELECTED_MATERIAL_REFERENCE = re.compile(
    r'(?:这(?:篇|份|本)(?:文档|文件|PDF|文章|课件|书|材料)?'
    r'|这个(?:文档|文件|PDF|文章|课件|书|材料)'
    r'|这(?:[一二两三四五六七八九十\d]+|几|些)(?:篇|份|个)'
    r'(?:文档|文件|PDF|文章|课件|材料|资料)?'
    r'|(?:这些|那几)(?:文档|文件|PDF|文章|课件|材料|资料)'
    r'|(?:所选|选中)(?:的)?(?:[一二两三四五六七八九十\d]+|几|些)?'
    r'(?:篇|份|个)?(?:文档|文件|PDF|文章|课件|材料|资料)'
    r'|当前(?:文档|文件|PDF|文章|课件|材料|资料))',
    re.IGNORECASE,
)
