"""Dispositivos tipo DataSet (UCI Air Quality) UNAB-Ambiental Capstone, con retroceso.

Reproduce el CSV en bucle. Topics: unab/capstone/dataset/<nombre>/{telemetria,cmd,ack,estado}
Comandos: power, set_interval(2-3600), calibrate(variable, offset), reset_calibration,
          set_speed(1-24 filas por envio), rewind
"""
import csv, json, logging, os, signal, threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "mosquitto")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER, PASS = os.environ["MQTT_USER"], os.environ["MQTT_PASS"]
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "30"))
CSV = os.environ.get("DATASET_CSV", "/data/AirQualityUCI.csv")
BASE = "unab/capstone/dataset"

# nombre de campo -> columna del CSV
DEVICES = {
    "ds-gases": {"co_gt": "CO(GT)", "c6h6_gt": "C6H6(GT)", "nox_gt": "NOx(GT)", "no2_gt": "NO2(GT)"},
    "ds-oxidos": {"s1_co": "PT08.S1(CO)", "s2_nmhc": "PT08.S2(NMHC)", "s3_nox": "PT08.S3(NOx)",
                  "s4_no2": "PT08.S4(NO2)", "s5_o3": "PT08.S5(O3)"},
    "ds-meteo": {"temperature": "T", "humidity": "RH", "abs_humidity": "AH"},
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("replay")
stop = threading.Event()


def num(s):
    try:
        v = float(s.replace(",", "."))
    except (ValueError, AttributeError):
        return None
    return None if v == -200 else v


def cargar():
    with open(CSV, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f, delimiter=";")
        return [r for r in rd if (r.get("Date") or "").strip()]


class Dataset(threading.Thread):
    def __init__(self, nombre, cols, filas):
        super().__init__(daemon=True)
        self.nombre, self.cols, self.filas = nombre, cols, filas
        self.i, self.on, self.intervalo, self.speed, self.offset = 0, True, INTERVAL, 1, {}
        self.wake = threading.Event()
        self.t_tel, self.t_cmd = f"{BASE}/{nombre}/telemetria", f"{BASE}/{nombre}/cmd"
        self.t_ack, self.t_est = f"{BASE}/{nombre}/ack", f"{BASE}/{nombre}/estado"
        c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"ds-{nombre}")
        c.username_pw_set(USER, PASS)
        c.will_set(self.t_est, json.dumps({"online": 0}), qos=1, retain=True)
        c.on_connect, c.on_message = self.on_connect, self.on_message
        c.reconnect_delay_set(1, 30)
        self.c = c

    def estado(self):
        return {"online": 1, "power": "on" if self.on else "off", "intervalo_s": self.intervalo,
                "speed": self.speed, "fila": self.i, "offset": self.offset}

    def publica_estado(self):
        self.c.publish(self.t_est, json.dumps(self.estado()), qos=1, retain=True)

    def on_connect(self, c, u, f, rc, p=None):
        if rc.is_failure:
            log.error("%s: conexión rechazada: %s", self.nombre, rc)
            return
        c.subscribe(self.t_cmd, qos=1)
        self.publica_estado()
        log.info("%s conectado", self.nombre)

    def on_message(self, c, u, msg):
        ok, err, cmd, cid = True, None, None, None
        try:
            o = json.loads(msg.payload.decode("utf-8"))
            cmd, cid = o.get("cmd"), o.get("id")
            if cmd == "power":
                self.on = o["value"] == "on"
            elif cmd == "set_interval":
                v = float(o["value"])
                if not 2 <= v <= 3600:
                    raise ValueError("intervalo fuera de 2-3600 s")
                self.intervalo = v
            elif cmd == "set_speed":
                v = int(o["value"])
                if not 1 <= v <= 24:
                    raise ValueError("speed fuera de 1-24")
                self.speed = v
            elif cmd == "calibrate":
                self.offset[str(o["variable"])] = float(o["offset"])
            elif cmd == "reset_calibration":
                self.offset = {}
            elif cmd == "rewind":
                self.i = 0
            else:
                raise ValueError("comando desconocido")
        except Exception as e:
            ok, err = False, str(e)
        log.warning("%s cmd=%s ok=%s %s", self.nombre, cmd, ok, err or "")
        self.c.publish(self.t_ack, json.dumps({"id": cid, "cmd": cmd, "ok": ok, "error": err,
                       "estado": self.estado(), "ts": int(datetime.now().timestamp() * 1000)}), qos=1)
        self.publica_estado()
        self.wake.set()

    def run(self):
        self.c.connect_async(HOST, PORT, keepalive=60)
        self.c.loop_start()
        while not stop.is_set():
            if self.on:
                fila = self.filas[self.i % len(self.filas)]
                vals = {}
                for campo, col in self.cols.items():
                    v = num(fila.get(col))
                    if v is not None:
                        vals[campo] = round(v + self.offset.get(campo, 0.0), 3)
                if vals:
                    vals["fila"] = self.i % len(self.filas)
                    vals["ts"] = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self.c.publish(self.t_tel, json.dumps(vals), qos=1)
                self.i = (self.i + self.speed) % len(self.filas)
            self.wake.wait(self.intervalo)
            self.wake.clear()
        self.c.publish(self.t_est, json.dumps({"online": 0}), qos=1, retain=True).wait_for_publish(2)
        self.c.loop_stop()
        self.c.disconnect()


def main():
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    filas = cargar()
    log.info("Dataset cargado: %d filas", len(filas))
    ds = [Dataset(n, c, filas) for n, c in DEVICES.items()]
    for d in ds:
        d.start()
    stop.wait()
    for d in ds:
        d.wake.set()
        d.join(5)


if __name__ == "__main__":
    main()
