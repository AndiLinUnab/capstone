"""Contact point de Telegram + política raíz. Requiere GRAFANA_PASSWORD en el entorno y TELEGRAM_* en .env."""
import base64, json, os, urllib.request, urllib.error
env = dict(l.strip().split('=', 1) for l in open('.env') if '=' in l and not l.startswith('#'))
A = base64.b64encode(f"admin:{os.environ['GRAFANA_PASSWORD']}".encode()).decode()
H = {"Content-Type": "application/json", "Authorization": f"Basic {A}", "X-Disable-Provenance": "true"}
B = "http://127.0.0.1:3000/api/v1/provisioning/"
def call(path, metodo, cuerpo):
    req = urllib.request.Request(B + path, data=json.dumps(cuerpo).encode(), method=metodo, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("OK", r.status, metodo, path); return True
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, path, e.read().decode()[:250]); return False
if call("contact-points", "POST", {"name": "capstone-telegram", "type": "telegram",
        "settings": {"botToken": env["TELEGRAM_TOKEN"], "chatid": env["TELEGRAM_CHAT"]}}):
    call("policies", "PUT", {"receiver": "capstone-telegram", "group_by": ["grafana_folder", "alertname"],
         "group_wait": "30s", "group_interval": "5m", "repeat_interval": "4h"})
