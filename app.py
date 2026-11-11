"""API de control + panel web del retroceso (UNAB-Ambiental Capstone)."""
import json, os, re, secrets, threading, time, uuid
from collections import deque
import paho.mqtt.client as mqtt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

PANEL_USER, PANEL_PASS = os.environ["PANEL_USER"], os.environ["PANEL_PASS"]
CMDS = {"power", "set_interval", "calibrate", "reset_calibration", "poll_now", "set_speed", "rewind"}
estado, acks, lock = {}, deque(maxlen=60), threading.Lock()

c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="control-api")
c.username_pw_set("control", os.environ["MQTT_CONTROL_PASS"])
c.reconnect_delay_set(1, 30)

def on_connect(cl, u, f, rc, p=None):
    if not rc.is_failure:
        cl.subscribe([("unab/capstone/+/+/estado", 1), ("unab/capstone/+/+/ack", 1)])

def on_message(cl, u, msg):
    parts = msg.topic.split("/")
    if len(parts) != 5:
        return
    _, _, tipo, nombre, kind = parts
    try:
        d = json.loads(msg.payload.decode())
    except Exception:
        return
    with lock:
        if kind == "estado":
            estado[f"{tipo}/{nombre}"] = {**d, "visto": int(time.time())}
        else:
            acks.appendleft({"dispositivo": f"{tipo}/{nombre}", **d})

c.on_connect, c.on_message = on_connect, on_message
c.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), 1883, keepalive=60)
c.loop_start()

app = FastAPI(title="Capstone control")
sec = HTTPBasic()

def auth(cr: HTTPBasicCredentials = Depends(sec)):
    ok = secrets.compare_digest(cr.username, PANEL_USER) & secrets.compare_digest(cr.password, PANEL_PASS)
    if not ok:
        raise HTTPException(401, "credenciales", headers={"WWW-Authenticate": "Basic"})

@app.get("/api/state", dependencies=[Depends(auth)])
def get_state():
    with lock:
        return {"dispositivos": estado, "acks": list(acks)[:15]}

@app.post("/api/cmd/{tipo}/{nombre}", dependencies=[Depends(auth)])
def post_cmd(tipo: str, nombre: str, body: dict):
    if not re.fullmatch(r"[a-z0-9-]{1,40}", tipo) or not re.fullmatch(r"[a-z0-9-]{1,40}", nombre):
        raise HTTPException(400, "nombre inválido")
    with lock:
        if f"{tipo}/{nombre}" not in estado:
            raise HTTPException(404, "dispositivo desconocido")
    if body.get("cmd") not in CMDS:
        raise HTTPException(400, "comando no permitido")
    body["id"] = uuid.uuid4().hex[:8]
    c.publish(f"unab/capstone/{tipo}/{nombre}/cmd", json.dumps(body), qos=1)
    return {"enviado": body["id"]}

PAGE = """<!doctype html><meta charset=utf-8><title>Capstone: control</title>
<style>body{font:14px system-ui;margin:20px;background:#111;color:#eee}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #333;padding:6px 8px;text-align:left}th{background:#222}.on{color:#4c4}.off{color:#e55}
button,input{background:#222;color:#eee;border:1px solid #555;border-radius:4px;padding:3px 7px;margin:1px}input{width:70px}
#acks{font:12px monospace;white-space:pre-wrap;background:#1a1a1a;padding:8px;margin-top:14px}</style>
<h2>Capstone UNAB-Ambiental: control de dispositivos</h2><table id=t></table><h3>Últimas respuestas (ack)</h3><div id=acks></div>
<script>
const T=document.getElementById('t'),A=document.getElementById('acks');
async function send(k,body){const r=await fetch('/api/cmd/'+k,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok)alert('Error '+r.status);setTimeout(load,1200)}
function el(tag,txt,cls){const e=document.createElement(tag);if(txt!==undefined)e.textContent=txt;if(cls)e.className=cls;return e}
function btn(txt,fn){const b=el('button',txt);b.onclick=fn;return b}
function inp(ph,val){const i=el('input');i.placeholder=ph;if(val!==undefined)i.value=val;return i}
function fila(k,d){const r=el('tr'),tipo=k.split('/')[0];
 r.append(el('td',k),el('td',d.online?'online':'offline',d.online?'on':'off'),el('td',d.power||'-'),el('td',d.intervalo_s??'-'),
  el('td',JSON.stringify(d.offset||{})));const c=el('td');
 if(d.online){c.append(btn('ON',()=>send(k,{cmd:'power',value:'on'})),btn('OFF',()=>send(k,{cmd:'power',value:'off'})));
  const iv=inp('seg');c.append(iv,btn('intervalo',()=>send(k,{cmd:'set_interval',value:+iv.value})));
  const v=inp('variable'),o=inp('offset');c.append(v,o,btn('calibrar',()=>send(k,{cmd:'calibrate',variable:v.value,offset:+o.value})),
   btn('reset calib.',()=>send(k,{cmd:'reset_calibration'})));
  if(tipo==='api')c.append(btn('consultar ya',()=>send(k,{cmd:'poll_now'})));
  if(tipo==='dataset'){const s=inp('1-24');c.append(s,btn('velocidad',()=>send(k,{cmd:'set_speed',value:+s.value})),btn('rewind',()=>send(k,{cmd:'rewind'})))}}
 r.append(c);return r}
async function load(){const r=await fetch('/api/state');if(!r.ok)return;const j=await r.json();
 T.replaceChildren();const h=el('tr');['Dispositivo','Estado','Power','Intervalo (s)','Calibración','Comandos'].forEach(x=>h.append(el('th',x)));T.append(h);
 Object.keys(j.dispositivos).sort().forEach(k=>T.append(fila(k,j.dispositivos[k])));
 A.textContent=j.acks.map(a=>[a.dispositivo,a.cmd,a.ok?'OK':'ERROR '+a.error,a.id].join('  ')).join('\\n')}
load();setInterval(load,4000);
</script>"""

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index():
    return PAGE
