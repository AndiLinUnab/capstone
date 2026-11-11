"""Analisis con IA de las series del Capstone. Uso:
  python3 analisis/ia.py --list-models
  python3 analisis/ia.py [horas]        (por defecto 24)
Lee de ../.env: INFLUX_TOKEN, INFLUX_ORG, AI_API_KEY, AI_BASE_URL, AI_MODEL. Nunca imprime las claves."""
import csv, io, json, os, statistics, sys, urllib.request, urllib.error
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
for l in open(os.path.join(RAIZ, ".env")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1)
        env[k] = v


def http(url, datos=None, cabeceras=None):
    import time
    for intento in range(8):
        req = urllib.request.Request(url, data=datos, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and intento < 7:
                try:
                    espera = int(e.headers.get("Retry-After", "30"))
                except ValueError:
                    espera = 30
                print(f"servicio ocupado ({e.code}), reintento {intento + 1}/7 en {espera}s", flush=True)
                time.sleep(min(max(espera, 5), 120))
                continue
            sys.exit(f"ERROR HTTP {e.code}: {e.read().decode()[:300]}")
        except Exception as e:
            sys.exit(f"ERROR de conexion: {type(e).__name__}")


BASE = env.get("AI_BASE_URL", "").rstrip("/")
AI = {"Authorization": "Bearer " + env.get("AI_API_KEY", ""), "Content-Type": "application/json",
      "User-Agent": "capstone-ia/1.0"}

if "--list-models" in sys.argv:
    d = json.loads(http(BASE + "/models", cabeceras=AI))
    print("\n".join(sorted(m["id"] for m in d["data"])))
    sys.exit()

modelo = env.get("AI_MODEL")
if not modelo or not BASE:
    sys.exit("Falta AI_BASE_URL o AI_MODEL en .env (usa --list-models para ver los modelos)")
horas = int(sys.argv[1]) if len(sys.argv) > 1 else 24

flux = (f'from(bucket:"capstone") |> range(start:-{horas}h) |> filter(fn:(r) => r._measurement=="capstone" and r._field!="fila") '
        '|> aggregateWindow(every: 10m, fn: mean, createEmpty: false) |> keep(columns:["_time","_value","_field","dispositivo"])')
txt = http("http://127.0.0.1:8086/api/v2/query?org=" + env["INFLUX_ORG"], flux.encode(),
           {"Authorization": "Token " + env["INFLUX_TOKEN"], "Content-Type": "application/vnd.flux", "Accept": "application/csv"})

series, cols = {}, None
for fila in csv.reader(io.StringIO(txt)):
    if not fila or fila[0].startswith("#"):
        continue
    if "_time" in fila:
        cols = {n: i for i, n in enumerate(fila)}
        continue
    if cols and len(fila) > cols["_value"]:
        try:
            series.setdefault((fila[cols["dispositivo"]], fila[cols["_field"]]), []).append((fila[cols["_time"]], float(fila[cols["_value"]])))
        except ValueError:
            pass

res = {}
for (d, c), pts in sorted(series.items()):
    v = [x[1] for x in pts]
    imax, imin = v.index(max(v)), v.index(min(v))
    q = max(1, len(v) // 4)
    res[f"{d}/{c}"] = {"n": len(v), "media": round(statistics.mean(v), 2), "desv": round(statistics.pstdev(v), 2),
                      "min": round(min(v), 2), "hora_min_utc": pts[imin][0][:16],
                      "max": round(max(v), 2), "hora_max_utc": pts[imax][0][:16],
                      "inicio": round(statistics.mean(v[:q]), 2), "fin": round(statistics.mean(v[-q:]), 2)}

ev = os.path.join(RAIZ, "analisis", "eventos.txt")
eventos = open(ev).read().strip() if os.path.exists(ev) else "(sin eventos registrados)"
prompt = ("Eres analista de datos IoT. Describe en espanol, para un informe academico, el comportamiento de las series de las ultimas "
          f"{horas} horas en Bucaramanga. Usa SOLO las cifras dadas (medias de 10 min, horas en UTC; hora local = UTC-5); no inventes valores. "
          "Cubre: patron diario, picos y valles con su hora, relaciones entre dispositivos, anomalias y que eventos explican las pruebas listadas. "
          "Aclara que los gemelos digitales y el dataset son simulados o historicos, las APIs son datos reales de Azure Maps y el dispositivo "
          "'real' mide el propio equipo. Termina con 3 observaciones y posibles reglas de alerta.\n\n"
          f"EVENTOS DE PRUEBA (no son fenomenos naturales):\n{eventos}\n\nESTADISTICAS:\n{json.dumps(res, ensure_ascii=False)}")
r = json.loads(http(BASE + "/chat/completions",
                    json.dumps({"model": modelo, "messages": [{"role": "user", "content": prompt}]}).encode(), AI))
texto = r["choices"][0]["message"]["content"]

ahora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
os.makedirs(os.path.join(RAIZ, "analisis", "salidas"), exist_ok=True)
base = os.path.join(RAIZ, "analisis", "salidas", f"analisis-{ahora}")
open(base + ".md", "w").write(f"# Analisis IA ({horas} h hasta {ahora} UTC, modelo {modelo})\n\n{texto}\n")
json.dump(res, open(base + ".json", "w"), ensure_ascii=False, indent=1)
print(texto)
print("\nGuardado en", base + ".md")
