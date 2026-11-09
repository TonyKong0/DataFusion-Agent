import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm.deepseek_client import chat

if __name__ == '__main__':
    answer = chat('你是测试助手，请只回复：连接成功', '请确认服务可以正常回答。')
    assert '连接成功' in answer
    print('Phase 3 DeepSeek real chat passed')
