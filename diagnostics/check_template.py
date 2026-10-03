import jinja2
import sys

try:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('/home/tserver/isp_v2/templates'))
    tmpl = env.get_template('customer_edit.html')
    print("SUCCESS: customer_edit.html parsed cleanly with Jinja2!")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
