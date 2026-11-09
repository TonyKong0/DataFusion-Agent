"""Download official BGE-M3 weights with resumable verified HTTP ranges."""
import sys
import concurrent.futures
from pathlib import Path
import httpx

DESTINATION = Path(__file__).resolve().parents[1] / 'data/models/bge-m3'
BASE = 'https://huggingface.co/BAAI/bge-m3/resolve/main/'
FILES = ['config.json', 'config_sentence_transformers.json', 'modules.json', 'sentence_bert_config.json',
         'sentencepiece.bpe.model', 'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', '1_Pooling/config.json']


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        for filename in FILES:
            path = DESTINATION / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                response = client.get(BASE + filename)
                response.raise_for_status()
                path.write_bytes(response.content)
        response = client.head(BASE + 'pytorch_model.bin')
        response.raise_for_status()
        size = int(response.headers['content-length'])
    target = DESTINATION / 'pytorch_model.bin'
    if target.exists() and target.stat().st_size == size:
        print('BGE-M3 already downloaded', flush=True)
        return
    block = 32 * 1024 * 1024

    def download(index: int) -> Path:
        begin = index * block
        end = min(size-1, begin+block-1)
        path = DESTINATION / f'weights.part{index:03}'
        if path.exists() and path.stat().st_size == end-begin+1:
            return path
        for attempt in range(3):
            try:
                with httpx.Client(follow_redirects=True, timeout=180) as client:
                    with client.stream('GET', BASE+'pytorch_model.bin', headers={'Range': f'bytes={begin}-{end}'}) as result:
                        result.raise_for_status()
                        if result.status_code != 206 or result.headers.get('content-range') != f'bytes {begin}-{end}/{size}':
                            raise RuntimeError('Invalid HTTP range')
                        with path.open('wb') as output:
                            for chunk in result.iter_bytes(1024*1024):
                                output.write(chunk)
                if path.stat().st_size != end-begin+1:
                    raise RuntimeError('Incomplete range')
                return path
            except Exception:
                if attempt == 2:
                    raise
        return path

    count = (size+block-1)//block
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(download, index) for index in range(count)]
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if done % 5 == 0 or done == count:
                print(f'BGE-M3 download {done}/{count}', flush=True)
    with target.open('wb') as output:
        for index in range(count):
            path = DESTINATION / f'weights.part{index:03}'
            with path.open('rb') as source:
                while chunk := source.read(1024*1024):
                    output.write(chunk)
            path.unlink()
    assert target.stat().st_size == size
    print('Official BGE-M3 download complete', flush=True)


if __name__ == '__main__':
    main()
