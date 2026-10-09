import os, re
from pathlib import Path

def run():
    v = set()
    for p in Path('/data').rglob('*'):
        if 'bak' not in p.name.lower() and p.is_file():
            try:
                c = open(p, 'r', encoding='utf-8').read()
                if 'FALCON15:BTCUSDT:SHORT' in c:
                    v.update(re.findall(r'"pnl_r"[^0-9-]+([-0-9.]+)', c))
            except Exception:
                pass
    print("PNL_R_VALUES:", v)

if __name__ == '__main__':
    run()
