"""Crea 3 reglas de alerta en Grafana. Requiere GRAFANA_PASSWORD, DSUID y FOLDER en el entorno."""
import base64, json, os, urllib.request, urllib.error
AUTH = base64.b64encode(f"admin:{os.environ['GRAFANA_PASSWORD']}".encode()).decode()
DS, FOLDER = os.environ["DSUID"], os.environ["FOLDER"]
URL = "http://127.0.0.1:3000/api/v1/provisioning/alert-rules"

def regla(titulo, flux, op, umbral, espera, resumen, rango=900, sin_datos="NoData", reducer="max"):
    return {"title": titulo, "ruleGroup": "capstone", "folderUID": FOLDER, "orgID": 1,
            "condition": "C", "for": espera, "noDataState": sin_datos, "execErrState": "Error",
            "labels": {"proyecto": "capstone"}, "annotations": {"summary": resumen},
            "data": [
                {"refId": "A", "relativeTimeRange": {"from": rango, "to": 0}, "datasourceUid": DS,
                 "model": {"refId": "A", "query": flux, "intervalMs": 1000, "maxDataPoints": 43200}},
                {"refId": "B", "datasourceUid": "__expr__",
                 "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": reducer,
                           "settings": {"mode": "dropNN"}}},
                {"refId": "C", "datasourceUid": "__expr__",
                 "model": {"refId": "C", "type": "threshold", "expression": "B",
                           "conditions": [{"evaluator": {"type": op, "params": [umbral]}}]}}]}

BASE = 'from(bucket: "capstone") |> range(start: -%s) |> filter(fn: (r) => r._measurement == "capstone" and %s)'
reglas = [
    regla("PM2.5 alto (>25 ug/m3)", BASE % ("10m", 'r._field == "pm25"'), "gt", 25, "5m",
          "PM2.5 por encima de 25 ug/m3 en algún dispositivo", 600),
    regla("Rio crecido (>1.8 m)", BASE % ("5m", 'r._field == "nivel_m"'), "gt", 1.8, "1m",
          "Nivel del río por encima de 1.8 m", 300),
    regla("Menos de 10 dispositivos con datos",
          'from(bucket: "capstone") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "capstone") '
          '|> group(columns: ["dispositivo"]) |> last() |> group() |> count()',
          "lt", 10, "5m", "Hay dispositivos sin enviar datos en los últimos 15 minutos", 900,
          sin_datos="Alerting", reducer="last"),
]
for r in reglas:
    req = urllib.request.Request(URL, data=json.dumps(r).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Basic {AUTH}",
                 "X-Disable-Provenance": "true"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print("OK", resp.status, r["title"])
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, r["title"], e.read().decode()[:300])
