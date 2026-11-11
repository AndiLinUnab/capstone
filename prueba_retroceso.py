"""Prueba de retroceso con duracion visible. Usa la API del panel, registra cada paso en analisis/eventos.txt
y deja anotaciones (tag 'retroceso') en Grafana."""
import base64, json, os, time, urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
for l in open(os.path.join(RAIZ, ".env")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1)
        env[k] = v
AUTH = base64.b64encode(f"operador:{env['PANEL_PASS']}".encode()).decode()
AUTH_G = base64.b64encode(f"admin:{env['GRAFANA_PASSWORD']}".encode()).decode()
EV = os.path.join(RAIZ, "analisis", "eventos.txt")


def api(path, cuerpo=None):
    r = urllib.request.Request("http://127.0.0.1:8000" + path,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Authorization": "Basic " + AUTH, "Content-Type": "application/json"},
        method="POST" if cuerpo is not None else "GET")
    with urllib.request.urlopen(r, timeout=20) as x:
        return json.load(x)


def log(txt):
    linea = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC {txt}"
    open(EV, "a").write(linea + "\n")
    print(linea, flush=True)


def anota(texto, tags, t0, t1=None):
    cuerpo = {"time": int(t0 * 1000), "tags": ["retroceso"] + tags, "text": texto}
    if t1:
        cuerpo["timeEnd"] = int(t1 * 1000)
    try:
        r = urllib.request.Request("http://127.0.0.1:3000/api/annotations", data=json.dumps(cuerpo).encode(),
            headers={"Authorization": "Basic " + AUTH_G, "Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(r, timeout=20).read()
        print("  anotacion creada:", texto, flush=True)
    except Exception as e:
        print("  anotacion NO creada:", type(e).__name__, flush=True)


def cmd(dev, cuerpo, nota):
    cid = api(f"/api/cmd/{dev}", dict(cuerpo))["enviado"]
    time.sleep(4)
    ack = next((a for a in api("/api/state")["acks"] if a.get("id") == cid), None)
    estado = "SIN CONFIRMAR" if ack is None else ("OK" if ack["ok"] else "RECHAZADO: " + str(ack["error"]))
    log(f"{dev} {cuerpo['cmd']} {estado} ({nota})")


log("--- inicio de la prueba de retroceso con duracion ---")

t0 = time.time()
cmd("twin/aire-cabecera", {"cmd": "power", "value": "off"}, "apagado por 3 min")
time.sleep(180)
cmd("twin/aire-cabecera", {"cmd": "power", "value": "on"}, "encendido de nuevo")
anota("aire-cabecera apagado (comando power OFF y luego ON)", ["aire-cabecera"], t0, time.time())

t0 = time.time()
cmd("twin/rio-oro", {"cmd": "calibrate", "variable": "nivel_m", "offset": 1.5}, "offset +1.5 m por 4 min, debe disparar Rio crecido")
time.sleep(240)
cmd("twin/rio-oro", {"cmd": "reset_calibration"}, "fin del offset")
anota("rio-oro: calibracion nivel_m +1.5 m (prueba, no es una crecida natural)", ["rio-oro"], t0, time.time())

t0 = time.time()
cmd("real/laptop-casa", {"cmd": "set_interval", "value": 10}, "dispositivo real: intervalo 10 s por 2 min")
time.sleep(120)
cmd("real/laptop-casa", {"cmd": "set_interval", "value": 30}, "dispositivo real: intervalo de vuelta a 30 s")
anota("laptop-casa: intervalo de muestreo 10 s", ["laptop-casa"], t0, time.time())

t0 = time.time()
cmd("twin/aire-centro", {"cmd": "set_interval", "value": 1}, "valor invalido, debe ser rechazado")
anota("aire-centro: intervalo 1 s rechazado por validacion", ["aire-centro"], t0)
log("--- fin de la prueba ---")
