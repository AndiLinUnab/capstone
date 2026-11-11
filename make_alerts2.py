"""Alertas adicionales. Reemplaza la regla de 10 dispositivos por una de 11 y agrega 4 reglas. Seguro de repetir."""
import base64, json, os, urllib.request, urllib.error
env = dict(l.strip().split('=', 1) for l in open('.env') if '=' in l and not l.startswith('#'))
A = base64.b64encode(f"admin:{env['GRAFANA_PASSWORD']}".encode()).decode()
H = {"Authorization": f"Basic {A}", "Content-Type": "application/json", "X-Disable-Provenance": "true"}
G = "http://127.0.0.1:3000"

def llamar(ruta, metodo="GET", cuerpo=None):
    req = urllib.request.Request(G + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, headers=H, method=metodo)
    with urllib.request.urlopen(req, timeout=20) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip() else {}

DS = llamar("/api/datasources")[0]["uid"]
FOLDER = [x["uid"] for x in llamar("/api/search?query=Capstone") if x["type"] == "dash-folder"][0]

def regla(titulo, flux, op, umbral, espera, resumen, rango=900, sin_datos="NoData", reducer="max"):
    return {"title": titulo, "ruleGroup": "capstone", "folderUID": FOLDER, "orgID": 1, "condition": "C", "for": espera,
            "noDataState": sin_datos, "execErrState": "Error", "labels": {"proyecto": "capstone"}, "annotations": {"summary": resumen},
            "data": [{"refId": "A", "relativeTimeRange": {"from": rango, "to": 0}, "datasourceUid": DS,
                      "model": {"refId": "A", "query": flux, "intervalMs": 1000, "maxDataPoints": 43200}},
                     {"refId": "B", "datasourceUid": "__expr__", "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": reducer, "settings": {"mode": "dropNN"}}},
                     {"refId": "C", "datasourceUid": "__expr__", "model": {"refId": "C", "type": "threshold", "expression": "B", "conditions": [{"evaluator": {"type": op, "params": [umbral]}}]}}]}

B = 'from(bucket: "capstone") |> range(start: -%s) |> filter(fn: (r) => r._measurement == "capstone" and %s)'
cuenta = ('from(bucket: "capstone") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "capstone") '
          '|> group(columns: ["dispositivo"]) |> last() |> group() |> count()')
laptop = ('from(bucket: "capstone") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "capstone" and r.tipo == "real" and r._field == "cpu_percent") '
          '|> group() |> count()')
nuevas = [
    regla("Menos de 11 dispositivos con datos", cuenta, "lt", 11, "5m", "Hay dispositivos sin enviar datos en los últimos 15 minutos", 900, "Alerting", "last"),
    regla("UV alto (>8)", B % ("10m", 'r._field == "uv_index"'), "gt", 8, "5m", "Índice UV por encima de 8 en algún dispositivo", 600),
    regla("AQI alto (>100)", B % ("30m", 'r._field == "aqi"'), "gt", 100, "5m", "Índice de calidad del aire por encima de 100", 1800),
    regla("Turbidez del río alta (>80 NTU)", B % ("5m", 'r._field == "turbidez_ntu"'), "gt", 80, "2m", "Turbidez del río por encima de 80 NTU", 300),
    regla("Dispositivo real sin datos", laptop, "lt", 1, "5m", "La laptop no envía datos en los últimos 10 minutos", 600, "Alerting", "last"),
]
for r in llamar("/api/v1/provisioning/alert-rules"):
    if r["title"].startswith("Menos de 10 dispositivos"):
        llamar(f"/api/v1/provisioning/alert-rules/{r['uid']}", "DELETE")
        print("borrada la regla antigua:", r["title"])
existentes = {r["title"] for r in llamar("/api/v1/provisioning/alert-rules")}
for r in nuevas:
    if r["title"] in existentes:
        print("ya existe:", r["title"]); continue
    try:
        llamar("/api/v1/provisioning/alert-rules", "POST", r); print("OK", r["title"])
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, r["title"], e.read().decode()[:250])
