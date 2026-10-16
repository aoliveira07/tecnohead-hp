"""Ingress web UI and JSON API."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from settings import SettingsError
from service import MonitorService


HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TecnoHead HP</title>
<style>
:root{color-scheme:dark;--bg:#10141b;--panel:#171e28;--line:#2c3948;--text:#eef4fa;--muted:#9db0c3;--accent:#48b8a5;--warn:#f1bb62;--bad:#ef766c}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#0d1218,#182330);color:var(--text);font:15px system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1080px;margin:auto;padding:24px 16px 60px}header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}h1,h2{margin:0 0 10px}h1{font-size:clamp(24px,5vw,38px)}h2{font-size:19px}.sub,.muted{color:var(--muted)}.badge{border:1px solid var(--line);border-radius:999px;padding:7px 11px;color:var(--muted)}.badge.ok{color:var(--accent);border-color:#2b756b}.badge.bad{color:var(--bad);border-color:#82423f}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}.card{background:rgba(23,30,40,.92);border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:0 12px 30px #05080c44;margin-bottom:14px}.wide{grid-column:1/-1}.supply{display:flex;flex-direction:column;gap:7px}.bar{height:9px;background:#2a3542;border-radius:8px;overflow:hidden}.fill{height:100%;background:var(--accent);width:0%;transition:width .3s}.fill.low{background:var(--warn)}.fill.empty{background:var(--bad)}.row{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:7px 0}.row strong{font-size:18px}label{display:block;margin:13px 0 6px;color:var(--muted)}input,select{width:100%;border:1px solid var(--line);border-radius:9px;padding:11px;background:#0f151d;color:var(--text);font:inherit}button{border:0;border-radius:9px;padding:11px 14px;background:var(--accent);color:#071512;font-weight:700;cursor:pointer;margin:7px 6px 0 0}button.secondary{background:#2d3c4c;color:var(--text)}button.danger{background:#7d3f42;color:#fff}button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap}.notice{padding:12px 14px;border-radius:10px;background:#1d2d36;border:1px solid #315663;color:#cce9e4}.notice.warn{background:#342c1e;border-color:#6d5832;color:#f7dfae}.status-line{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.small{font-size:13px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}.hidden{display:none}.source{font-size:12px;color:var(--muted)}details summary{cursor:pointer;color:var(--accent)}@media(max-width:600px){main{padding:18px 11px 45px}header{align-items:flex-start;flex-direction:column}.card{padding:15px}}
</style>
</head>
<body><main>
<header><div><h1>TecnoHead HP</h1><div class="sub">HP Color LaserJet Pro MFP M176n · monitoramento local</div></div><div id="appBadge" class="badge">Carregando</div></header>
<section id="waiting" class="card notice warn hidden">Configure o endereço IP da impressora para iniciar o monitoramento. A interface permanece disponível sem IP.</section>
<section class="grid">
<div class="card wide"><h2>Visão geral</h2><div class="status-line"><strong id="printerState">Desconhecida</strong><span id="printerOnline" class="badge">offline</span><span id="configuredIp" class="muted">IP não configurado</span></div><p id="message" class="muted">Aguardando leitura.</p><div class="actions"><button id="refresh">Atualizar agora</button><button id="openHp" class="secondary">Abrir administração HP</button></div></div>
<div class="card"><h2>Suprimentos</h2><div id="supplies"><p class="muted">Nenhuma leitura disponível.</p></div></div>
<div class="card"><h2>Conexões</h2><div class="row"><span>SNMPv1</span><strong id="snmpState">—</strong></div><div class="row"><span>EWS</span><strong id="ewsState">—</strong></div><div class="row"><span>MQTT</span><strong id="mqttState">—</strong></div><div class="row"><span>Última leitura</span><span id="lastRead" class="small muted">—</span></div></div>
</section>
<section class="card"><h2>Configurações</h2><p class="muted">O IP é a fonte única da coleta. Salvar um novo IP invalida imediatamente o estado anterior e preserva os mesmos identificadores no Home Assistant.</p><form id="configForm"><div class="grid"><div><label for="printer_name">Nome amigável</label><input id="printer_name" name="printer_name" required><label for="ip">Endereço IP da impressora</label><input id="ip" name="ip" inputmode="decimal" placeholder="192.168.X.Y"><label for="snmp_community">Comunidade SNMPv1 de leitura</label><input id="snmp_community" name="snmp_community" type="password" autocomplete="new-password" placeholder="Não exibida após salvar"></div><div><label for="snmp_timeout">Timeout SNMP (segundos)</label><input id="snmp_timeout" name="snmp_timeout" type="number" min="0.1" max="30" step="0.1"><label for="poll_interval">Intervalo de consulta (segundos)</label><input id="poll_interval" name="poll_interval" type="number" min="30" max="86400"><label for="ews_port">Porta EWS</label><input id="ews_port" name="ews_port" type="number" min="1" max="65535"><label><input id="use_ews" name="use_ews" type="checkbox"> Usar EWS somente leitura</label></div><div><label for="mqtt_host">Broker MQTT manual (opcional)</label><input id="mqtt_host" name="mqtt_host" placeholder="vazio = serviço MQTT do HA"><label for="mqtt_port">Porta MQTT</label><input id="mqtt_port" name="mqtt_port" type="number" min="1" max="65535"><label for="mqtt_username">Usuário MQTT (opcional)</label><input id="mqtt_username" name="mqtt_username" autocomplete="off"><label for="mqtt_password">Senha MQTT (opcional)</label><input id="mqtt_password" name="mqtt_password" type="password" autocomplete="new-password"><label><input id="mqtt_auto" name="mqtt_auto" type="checkbox"> Descobrir broker pelo Supervisor</label></div></div><div class="actions"><button type="submit">Salvar configurações</button><button type="button" class="secondary" data-test="connection">Testar conexão com a impressora</button><button type="button" class="secondary" data-test="snmp">Testar comunicação SNMP</button><button type="button" class="secondary" data-test="ews">Testar EWS</button><button type="button" class="secondary" data-test="mqtt">Testar MQTT</button><button type="button" class="secondary" data-test="discover">Descobrir recursos</button></div><p id="formMessage" class="muted"></p></form></section>
<section class="card"><h2>Controles remotos</h2><div class="notice warn">Reiniciar e Acordar estão indisponíveis. Nenhum SNMP SET, Wake-on-LAN ou comando administrativo é emitido pela V1. Só poderão aparecer após homologação presencial e autorização explícita.</div></section>
<section class="card"><details><summary>Diagnóstico e homologação</summary><div class="actions"><button id="export" class="secondary">Exportar diagnóstico anonimizado</button></div><pre id="diagnostic" class="mono small muted"></pre></details></section>
</main>
<script>
const $=id=>document.getElementById(id);let current={};
function setText(id,value){$(id).textContent=value??'—'}
function badge(el,ok){el.className='badge '+(ok?'ok':'bad');el.textContent=ok?'online':'offline'}
function fillForm(cfg){for(const id of ['printer_name','ip','snmp_timeout','poll_interval','ews_port','mqtt_host','mqtt_port','mqtt_username']){if(cfg[id]!==undefined)$(id).value=cfg[id]??''}for(const id of ['use_ews','mqtt_auto'])$(id).checked=!!cfg[id];$('snmp_community').value='';$('mqtt_password').value='';$('snmp_community').placeholder=cfg.snmp_community?.configured?'Configurada (deixe vazio para manter)':'Informe a comunidade de leitura'}
function render(state){current=state;const cfg=state.settings||{};$('waiting').classList.toggle('hidden',!!cfg.ip);$('configuredIp').textContent=cfg.ip?`IP configurado: ${cfg.ip}`:'IP não configurado';setText('printerState',state.state_label);badge($('printerOnline'),!!state.online);setText('message',state.message||'');setText('snmpState',state.sources?.state?'conectado':'indisponível');setText('ewsState',state.ews?.reachable?'conectado':'indisponível');setText('mqttState',state.mqtt_connected?'conectado':'indisponível');setText('lastRead',state.collected_at||'—');$('openHp').disabled=!cfg.ip;$('openHp').onclick=()=>{if(cfg.ip)window.open(`http://${cfg.ip}:${cfg.ews_port||80}/`,'_blank','noopener')};const box=$('supplies');box.innerHTML='';const entries=Object.entries(state.supplies||{});if(!entries.length){box.innerHTML='<p class="muted">Indisponível até uma leitura real.</p>'}for(const [key,item] of entries){const p=item.percent;const value=p==null?'Indisponível':`${p}%`;const width=p==null?0:Math.max(0,Math.min(100,p));const cls=p!=null&&p<20?' low':p===0?' empty':'';box.insertAdjacentHTML('beforeend',`<div class="supply"><div class="row"><span>${item.name||key}</span><strong>${value}</strong></div><div class="bar"><div class="fill${cls}" style="width:${width}%"></div></div><span class="source">Origem: ${item.source||'Não disponível'}</span></div>`)}fillForm(cfg);$('appBadge').className='badge ok';$('appBadge').textContent='App online'}
async function api(path,options={}){const ingressPath='./'+path.replace(/^\\/+/,"");const r=await fetch(ingressPath,{headers:{'Content-Type':'application/json'},...options});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.message||'Falha na API');return data}
async function load(){try{render(await api('/api/status'))}catch(e){$('appBadge').textContent='Falha';$('appBadge').className='badge bad';$('formMessage').textContent=e.message}}
$('configForm').addEventListener('submit',async e=>{e.preventDefault();const data={};for(const id of ['printer_name','ip','snmp_timeout','poll_interval','ews_port','mqtt_host','mqtt_port','mqtt_username'])data[id]=$(id).value;for(const id of ['use_ews','mqtt_auto'])data[id]=$(id).checked;if($('snmp_community').value)data.snmp_community=$('snmp_community').value;if($('mqtt_password').value)data.mqtt_password=$('mqtt_password').value;try{const s=await api('/api/config',{method:'POST',body:JSON.stringify(data)});render(s);$('formMessage').textContent='Configurações salvas. A coleta será reconectada automaticamente.'}catch(e){$('formMessage').textContent=e.message}});
$('refresh').onclick=async()=>{try{render(await api('/api/refresh',{method:'POST'}))}catch(e){$('formMessage').textContent=e.message}};
for(const button of document.querySelectorAll('[data-test]'))button.onclick=async()=>{try{const d=await api('/api/test/'+button.dataset.test,{method:'POST'});$('formMessage').textContent=d.message||JSON.stringify(d);if(d.result) $('diagnostic').textContent=JSON.stringify(d.result,null,2)}catch(e){$('formMessage').textContent=e.message}};
$('export').onclick=async()=>{const d=await api('/api/diagnostics');$('diagnostic').textContent=JSON.stringify(d,null,2)};load();setInterval(load,15000);
</script></body></html>'''


def _safe_remote(remote: str) -> bool:
    # The production ingress gateway is the only allowed source. Localhost is
    # opt-in for development tests and never enabled by the app image.
    return remote == "172.30.32.2" or (os.environ.get("TECNHEAD_ALLOW_LOCALHOST") == "1" and remote in {"127.0.0.1", "::1"})


class Handler(BaseHTTPRequestHandler):
    service: MonitorService

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0")), 512 * 1024)
        data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        return data if isinstance(data, dict) else {}

    def _handle(self, method: str) -> None:
        if not _safe_remote(self.client_address[0]):
            self._send(403, {"message": "Acesso permitido somente pelo Ingress do Home Assistant."})
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        if method == "GET" and path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif method == "GET" and path == "/api/config":
            self._send(200, {"config": self.service.store.public()})
        elif method == "GET" and path in {"/api/status", "/api/health"}:
            self._send(200, self.service.status())
        elif method == "GET" and path == "/api/diagnostics":
            self._send(200, self.service.export_diagnostics())
        elif method == "POST" and path == "/api/config":
            try:
                self._send(200, self.service.save(self._json()))
            except (SettingsError, ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"message": str(exc)})
        elif method == "POST" and path == "/api/refresh":
            self._send(200, self.service.refresh())
        elif method == "POST" and path == "/api/test-connection":
            self._send(200, self.service.test_connection())
        elif method == "POST" and path.startswith("/api/test/"):
            action = path.rsplit("/", 1)[-1]
            actions = {"connection": self.service.test_connection, "snmp": self.service.test_snmp, "ews": self.service.test_ews, "mqtt": self.service.test_mqtt, "discover": self.service.discover}
            if action not in actions:
                self._send(404, {"message": "Teste desconhecido."})
            else:
                self._send(200, actions[action]())
        else:
            self._send(404, {"message": "Rota não encontrada."})

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")


def serve(service: MonitorService, host: str = "0.0.0.0", port: int = 8099) -> ThreadingHTTPServer:
    Handler.service = service
    server = ThreadingHTTPServer((host, port), Handler)
    return server
