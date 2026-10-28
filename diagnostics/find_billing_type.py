import glob, re

for p in glob.glob('/home/sk/isp_v2/*.py') + glob.glob('/home/sk/isp_v2/diagnostics/*.py'):
    try:
        with open(p, 'r', encoding='utf-8') as f:
            txt = f.read()
        lines = txt.split('\n')
        for lno, l in enumerate(lines, 1):
            if 'billing_type' in l and 'postpaid' in l:
                print(f"{p}:{lno} -> {l.strip()}")
    except Exception:
        pass
