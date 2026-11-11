"""Agrega paneles del dispositivo real y de cobertura al dashboard. Se puede repetir sin duplicar."""
import json
RUTA = "grafana/dashboards/capstone.json"
dash = json.load(open(RUTA))
ds = dash["panels"][0]["datasource"]
dash["panels"] = [p for p in dash["panels"] if p.get("id", 0) < 100]

def ts(id_, titulo, campos, x, y, w, h, unidad="short", minimo=None, maximo=None):
    filtro = " or ".join(f'r._field == "{c}"' for c in campos)
    q = ('from(bucket: "capstone") |> range(start: v.timeRangeStart, stop: v.timeRangeStop) '
         f'|> filter(fn: (r) => r._measurement == "capstone" and r.tipo == "real" and ({filtro})) '
         '|> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)')
    d = {"unit": unidad, "displayName": "${__field.labels._field}", "custom": {"lineWidth": 1, "spanNulls": True}}
    if minimo is not None: d["min"] = minimo
    if maximo is not None: d["max"] = maximo
    return {"id": id_, "type": "timeseries", "title": titulo, "datasource": ds,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "min"]}},
            "targets": [{"refId": "A", "query": q}]}

paneles = [
    ts(101, "Dispositivo real (laptop): CPU y memoria (%)", ["cpu_percent", "mem_percent"], 0, 48, 8, 8, "percent", 0, 100),
    ts(102, "Dispositivo real (laptop): batería (%)", ["battery_percent"], 8, 48, 8, 8, "percent", 0, 100),
    ts(103, "Dispositivo real (laptop): red (KiB/s)", ["net_sent_kbps", "net_recv_kbps"], 16, 48, 8, 8, "KBs"),
]
cobertura = ('from(bucket: "capstone") |> range(start: -30d) '
             '|> filter(fn: (r) => r._measurement == "capstone" and r._field != "fila") '
             '|> group(columns: ["dispositivo"]) |> aggregateWindow(every: 1h, fn: count, createEmpty: false) '
             '|> count() |> group() |> rename(columns: {_value: "horas_con_datos"}) '
             '|> keep(columns: ["dispositivo", "horas_con_datos"]) |> sort(columns: ["dispositivo"])')
paneles.append({"id": 104, "type": "table", "title": "Cobertura: horas con datos por dispositivo (últimos 30 días)", "datasource": ds,
                "gridPos": {"x": 0, "y": 56, "w": 16, "h": 8}, "fieldConfig": {"defaults": {}, "overrides": []},
                "targets": [{"refId": "A", "query": cobertura}]})
dias = ('from(bucket: "capstone") |> range(start: -60d) '
        '|> filter(fn: (r) => r._measurement == "capstone" and r._field != "fila") '
        '|> first() |> group() |> sort(columns: ["_time"]) |> limit(n: 1) '
        '|> map(fn: (r) => ({_value: float(v: int(v: now()) - int(v: r._time)) / 86400000000000.0}))')
paneles.append({"id": 105, "type": "stat", "title": "Días de toma de datos (desde el primer dato)", "datasource": ds,
                "gridPos": {"x": 16, "y": 56, "w": 8, "h": 8},
                "fieldConfig": {"defaults": {"unit": "d", "decimals": 2, "displayName": "días"}, "overrides": []},
                "targets": [{"refId": "A", "query": dias}]})
dash["panels"] += paneles
json.dump(dash, open(RUTA, "w"), indent=1, ensure_ascii=False)
print("ok:", len(dash["panels"]), "paneles")
