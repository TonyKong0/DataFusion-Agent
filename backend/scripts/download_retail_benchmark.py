"""Download the pinned UCI Online Retail II workbook outside the Git tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data' / 'benchmarks'
WORKBOOK = DATA_DIR / 'online-retail-ii.xlsx'
SOURCE_URL = (
    'https://hf-mirror.com/datasets/michaelmallari/online-retail-ii/resolve/'
    '433602ba287f8dc687f4ded85148827eeb4b0c68/online-retail-ii.xlsx'
)
EXPECTED_SIZE = 45_622_278
EXPECTED_SHA256 = 'bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=WORKBOOK,
                        help='destination must be the local ignored benchmark cache')
    args = parser.parse_args()
    output = args.output.resolve()
    if output != WORKBOOK.resolve():
        parser.error(f'output is fixed at {WORKBOOK}')

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if output.is_file() and output.stat().st_size == EXPECTED_SIZE \
            and sha256_file(output) == EXPECTED_SHA256:
        print(json.dumps({'status': 'already_verified', 'path': str(output),
                          'size_bytes': EXPECTED_SIZE, 'sha256': EXPECTED_SHA256}, indent=2))
        return 0

    partial = output.with_suffix(output.suffix + '.part')
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'DataFusion-Evaluation/1.5'})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as target:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > EXPECTED_SIZE:
                    raise RuntimeError('download exceeds pinned dataset size')
                digest.update(block)
                target.write(block)
                print(json.dumps({'progress_bytes': size, 'expected_bytes': EXPECTED_SIZE}), flush=True)
        actual_hash = digest.hexdigest()
        if size != EXPECTED_SIZE or actual_hash != EXPECTED_SHA256:
            raise RuntimeError(f'dataset verification failed: size={size}, sha256={actual_hash}')
        os.replace(partial, output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    print(json.dumps({'status': 'downloaded_and_verified', 'path': str(output),
                      'size_bytes': size, 'sha256': digest.hexdigest()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
