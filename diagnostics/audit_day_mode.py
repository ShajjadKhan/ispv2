import os
import glob
import re
import sys

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
if not os.path.exists(TEMPLATE_DIR):
    TEMPLATE_DIR = '/home/tserver/isp_v2/templates'

files = sorted(glob.glob(os.path.join(TEMPLATE_DIR, '*.html')))

target_file = sys.argv[1] if len(sys.argv) > 1 else None

for fpath in files:
    bname = os.path.basename(fpath)
    if target_file and target_file != bname:
        continue

    with open(fpath, 'r', encoding='utf-8') as fp:
        lines = fp.readlines()

    findings = []
    for idx, line in enumerate(lines, 1):
        has_white = re.search(r'style=["\'][^"\']*color:\s*(?:#fff\b|#ffffff\b|white\b)', line, re.I)
        has_dark = re.search(r'style=["\'][^"\']*background(?:-color)?:\s*(?:#070a12|#0b1120|#0f172a|#090e1a|#111827|#111a2e|#131d36|#17233f|rgba\(\s*15,\s*23,\s*42)', line, re.I)
        
        if has_white or has_dark:
            kind = []
            if has_white:
                kind.append('WHITE')
            if has_dark:
                kind.append('DARK_BG')
            findings.append((idx, '+'.join(kind), line.strip()))

    if findings:
        print(f"\n==================== {bname} ({len(findings)} findings) ====================")
        for ln, k, text in findings:
            print(f"  L{ln:4d} [{k:12s}]: {text[:120]}")
