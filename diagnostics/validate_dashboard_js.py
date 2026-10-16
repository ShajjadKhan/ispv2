import re
import sys

def check_html_js(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL)
    print(f"Total script blocks in {filepath}: {len(scripts)}")

    errors = []
    for s_idx, script in enumerate(scripts):
        # Strip Jinja2 expressions and blocks so they don't break JS brace/paren matching
        clean_script = re.sub(r'\{#.*?#\}', '', script, flags=re.DOTALL)
        clean_script = re.sub(r'\{\{.*?\}\}', '""', clean_script, flags=re.DOTALL)
        clean_script = re.sub(r'\{%.*?%\}', '', clean_script, flags=re.DOTALL)

        lines = clean_script.split('\n')
        brace_level = 0
        paren_level = 0
        in_multiline_comment = False
        in_str = None
        top_scope_declarations = {}

        for l_idx, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check comments
            if not in_str:
                if '/*' in stripped and '*/' not in stripped:
                    in_multiline_comment = True
                    continue
                if '*/' in stripped:
                    in_multiline_comment = False
                    continue
                if in_multiline_comment or stripped.startswith('//'):
                    continue

            # Strip single line comment at end (if not inside string)
            clean = line
            if not in_str:
                clean = re.sub(r'//.*$', '', line)

            # Check if declaring let/const at top-level
            if brace_level == 0 and not in_str:
                m = re.match(r'^\s*(let|const)\s+([a-zA-Z0-9_$]+)', clean)
                if m:
                    kind = m.group(1)
                    var_name = m.group(2)
                    if var_name in top_scope_declarations:
                        err = f"SyntaxError in script #{s_idx} line {l_idx}: Identifier '{var_name}' has already been declared ({top_scope_declarations[var_name]})"
                        print("ERROR:", err)
                        errors.append(err)
                    else:
                        top_scope_declarations[var_name] = f"{kind} at line {l_idx}"

            # Track braces and strings with escape awareness
            i = 0
            n = len(clean)
            while i < n:
                ch = clean[i]
                if in_str:
                    if ch == '\\':
                        i += 2  # Skip escaped character
                        continue
                    elif ch == in_str:
                        in_str = None
                else:
                    if ch in ("'", '"', '`'):
                        in_str = ch
                    elif ch == '{':
                        brace_level += 1
                    elif ch == '}':
                        brace_level = max(0, brace_level - 1)
                    elif ch == '(':
                        paren_level += 1
                    elif ch == ')':
                        paren_level = max(0, paren_level - 1)
                i += 1

        if brace_level != 0:
            err = f"SyntaxError in script #{s_idx}: Unclosed brace at EOF (depth {brace_level})"
            print("ERROR:", err)
            errors.append(err)
        if paren_level != 0:
            err = f"SyntaxError in script #{s_idx}: Unclosed parenthesis at EOF (depth {paren_level})"
            print("ERROR:", err)
            errors.append(err)

    print(f"Validation complete. Found {len(errors)} error(s).")
    return errors

if __name__ == '__main__':
    import glob
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = sorted(glob.glob('templates/*.html'))
    total_errors = 0
    for fpath in files:
        errs = check_html_js(fpath)
        total_errors += len(errs)
    if total_errors > 0:
        print(f"\nFAILED with {total_errors} total error(s).")
        sys.exit(1)
    else:
        print("\nALL TEMPLATES PASSED JS VALIDATION.")
        sys.exit(0)
