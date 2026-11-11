"""Genera grafana/dashboards/capstone.json. Uso: python3 make_dashboard.py <uid_datasource>"""
import json, sys
DS = {"type": "influxdb", "uid": sys.argv[1]}
SEL = 'contains(value: r.dispositivo, set: ${dispositivo:json})'
BASE = 'from(bucket: "capstone") |> range(start: v.timeRangeStart, stop: v.timeRangeStop) |> filter(fn: (r) => r._measurement == "capstone" and ' + SEL + ' and %s)'
panels = []

def ts(title, filt, x, y, unit="short", w=12, h=8):
    q = (BASE % filt) + ' |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false) |> yield(name: "mean")'
    panels.append({"id": len(panels) + 1, "type": "timeseries", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "displayName": "${__field.labels.dispositivo}",
                                     "custom": {"lineWidth": 1, "spanNulls": True}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "min"]}},
        "targets": [{"refId": "A", "query": q}]})

# Dispositivos con datos en los ultimos 15 min
panels.append({"id": 1, "type": "stat", "title": "Dispositivos con datos (15 min)", "datasource": DS,
    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 8},
    "fieldConfig": {"defaults": {"thresholds": {"mode": "absolute", "steps": [
        {"color": "red", "value": None}, {"color": "orange", "value": 8}, {"color": "green", "value": 10}]}}, "overrides": []},
    "targets": [{"refId": "A", "query": 'from(bucket: "capstone") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "capstone") |> group(columns: ["dispositivo"]) |> last() |> group() |> count()'}]})

# Resumen: promedio, max, min del rango elegido
resumen = ('d = from(bucket: "capstone") |> range(start: v.timeRangeStart, stop: v.timeRangeStop) '
           '|> filter(fn: (r) => r._measurement == "capstone" and ' + SEL + ' and r._field != "fila") '
           '|> keep(columns: ["dispositivo", "_field", "_value"])\n'
           'a = d |> mean() |> set(key: "stat", value: "promedio")\n'
           'b = d |> max() |> set(key: "stat", value: "maximo")\n'
           'c = d |> min() |> set(key: "stat", value: "minimo")\n'
           'union(tables: [a, b, c]) |> group() |> pivot(rowKey: ["dispositivo", "_field"], columnKey: ["stat"], valueColumn: "_value") '
           '|> sort(columns: ["dispositivo", "_field"])')
panels.append({"id": 2, "type": "table", "title": "Resumen del rango: promedio, máximo y mínimo", "datasource": DS,
    "gridPos": {"x": 6, "y": 0, "w": 18, "h": 8},
    "fieldConfig": {"defaults": {"decimals": 2}, "overrides": []},
    "targets": [{"refId": "A", "query": resumen}]})

ts("PM2.5 (µg/m³)", 'r._field == "pm25"', 0, 8, "conμgm3")
ts("NO2 (µg/m³)", 'r._field == "no2"', 12, 8, "conμgm3")
ts("Temperatura (°C)", 'r._field == "temperature"', 0, 16, "celsius")
ts("Humedad relativa (%)", 'r._field == "humidity"', 12, 16, "percent")
ts("Río: nivel (m)", 'r._field == "nivel_m"', 0, 24, "lengthm")
ts("Río: turbidez (NTU)", 'r._field == "turbidez_ntu"', 12, 24)
ts("Tráfico: incidentes en Bucaramanga", 'r._field == "incidentes"', 0, 32)
ts("Tráfico: retraso total (s)", 'r._field == "retraso_total_s"', 12, 32, "s")
ts("CO del dataset (mg/m³)", 'r._field == "co_gt"', 0, 40)
ts("Índice de calidad del aire AQI (API)", 'r._field == "aqi"', 12, 40)

dash = {"uid": "capstone-resumen", "title": "Capstone UNAB-Ambiental", "schemaVersion": 39, "version": 1,
        "timezone": "browser", "refresh": "1m", "time": {"from": "now-24h", "to": "now"},
        "templating": {"list": [{"name": "dispositivo", "label": "Dispositivo", "type": "query", "datasource": DS,
            "query": 'import "influxdata/influxdb/schema"\nschema.tagValues(bucket: "capstone", tag: "dispositivo")',
            "multi": True, "includeAll": True, "refresh": 2,
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]}}]},
        "panels": panels}
json.dump(dash, open("grafana/dashboards/capstone.json", "w"), indent=1, ensure_ascii=False)
print("ok:", len(panels), "paneles")
