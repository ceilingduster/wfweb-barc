"""Outbound-only Raspberry Pi connector. No browser can reach wfweb directly.
Run: python -m barc_node.agent. Configure with BARC_* environment variables.
"""
import asyncio
import base64
import json
import logging
import os
import ssl
import time
from urllib.parse import urlparse, quote

import requests

from websockets.asyncio.client import connect
from .policy import allowed, safe_asset

log=logging.getLogger('barc.agent')


class Agent:
    def __init__(self, hub, token, radio, ca=None, http_url=None):
        self.hub=hub
        self.token=token
        self.radio=radio
        self.clients={}
        self.http_url=(http_url or radio.replace('wss:','https:',1).replace('ws:','http:',1)).rstrip('/')+'/'
        parsed=urlparse(self.http_url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Configure a local wfweb HTTP(S) URL without credentials or query parameters')
        self.ca=ca
        self.http_tasks=set()
        self.ssl=None
        if radio.startswith('wss:'):
            self.ssl=ssl.create_default_context(cafile=ca)
        if urlparse(hub).scheme!='wss' and os.getenv('BARC_TESTING')!='1':
            raise ValueError('The public gateway must use wss://')

    async def connect_radio(self, headers=None):
        options={'open_timeout':3,'close_timeout':1,'max_size':262144,'max_queue':16}
        if self.ssl:
            options['ssl']=self.ssl
        if headers:options['additional_headers']=headers
        return await connect(self.radio,**options)

    async def proxy_http(self, hub, message):
        rid=message.get('id')
        path=message.get('path','')
        if not isinstance(path,str) or not safe_asset(path):
            await hub.send(json.dumps({'type':'http_error','id':rid}));return
        def fetch():
            with requests.Session() as client:
                client.trust_env=False
                headers={'X-BARC-User':str(message.get('user','')),'X-BARC-Control':'true' if message.get('control') else 'false','X-BARC-TX':'true' if message.get('control') else 'false'}
                with client.get(self.http_url+quote(path,safe='/.-_'),headers=headers,timeout=(3,15),allow_redirects=False,stream=True,verify=self.ca or True) as response:
                    if 300<=response.status_code<400:raise ValueError('Unexpected wfweb redirect')
                    data=bytearray()
                    for chunk in response.iter_content(128*1024):
                        data.extend(chunk)
                        if len(data)>64*1024*1024:raise ValueError('Asset exceeds limit')
                    return response.status_code,response.headers.get('Content-Type','application/octet-stream'),bytes(data)
        try:
            status,content_type,data=await asyncio.to_thread(fetch)
            await hub.send(json.dumps({'type':'http_start','id':rid,'status':status,'headers':{'Content-Type':content_type}}))
            for offset in range(0,len(data),128*1024):
                await hub.send(json.dumps({'type':'http_chunk','id':rid,'data':base64.b64encode(data[offset:offset+128*1024]).decode()}))
            await hub.send(json.dumps({'type':'http_end','id':rid}))
        except Exception:
            await hub.send(json.dumps({'type':'http_error','id':rid}))

    async def stop(self, client):
        # Commands are sent on the original operator socket, never through a
        # listener. Closing also invokes wfweb's pttClient disconnect guard.
        if client['operator']:
            for command in [{'cmd':'setPTT','value':False},{'cmd':'enableMic','value':False}]:
                try:
                    await asyncio.wait_for(client['ws'].send(json.dumps(command)),.3)
                except Exception:
                    pass
        client['operator']=False
        await client['ws'].close()
        client['task'].cancel()
        await asyncio.gather(client['task'], return_exceptions=True)

    def operating(self, client):
        return client['operator'] and time.monotonic()<client['deadline'] and time.time()<client['expires']

    async def forward(self, hub, cid, ws):
        try:
            async for data in ws:
                await hub.send(json.dumps({'type':'binary' if isinstance(data,bytes) else 'text','id':cid,'data':base64.b64encode(data).decode() if isinstance(data,bytes) else data}))
        except Exception:
            pass
        finally:
            try:
                await hub.send(json.dumps({'type':'closed','id':cid}))
            except Exception:
                pass

    async def open(self, hub, cid, user=None):
        if cid in self.clients or len(self.clients)>=12:
            return
        try:
            headers={'X-BARC-User':user,'X-BARC-Control':'false','X-BARC-TX':'false'} if user else None
            ws=await self.connect_radio(headers) if headers else await self.connect_radio()
        except Exception:
            await hub.send(json.dumps({'type':'closed','id':cid}))
            return
        self.clients[cid]={'ws':ws,'operator':False,'deadline':0,'expires':0,'task':asyncio.create_task(self.forward(hub,cid,ws))}

    async def handle(self, hub, message):
        kind=message.get('type');cid=message.get('id')
        if kind=='http':
            if len(self.http_tasks)>=4:
                await hub.send(json.dumps({'type':'http_error','id':cid}));return
            task=asyncio.create_task(self.proxy_http(hub,message));self.http_tasks.add(task)
            task.add_done_callback(self.http_tasks.discard)
            return
        if kind=='welcome':
            if abs(time.time()-message['serverTime'])>1.5:
                raise RuntimeError('Pi clock differs from gateway; enable NTP before operating')
            return
        if kind=='ping':
            await hub.send('{"type":"pong"}');return
        if kind=='open':
            await self.open(hub,cid,message.get('user'));return
        client=self.clients.get(cid)
        if not client:
            return
        if kind=='close':
            del self.clients[cid]
            await self.stop(client)
        elif kind=='lease':
            operator=message.get('operator') is True
            expires=float(message.get('expiresAt',0))
            ttl=min(3,max(0,float(message.get('ttl',0))),max(0,expires-time.time()))
            if client['operator'] and (not operator or ttl<=0):
                # Close rather than reuse a socket that might hold PTT/mic
                # state. The browser reconnects in listener mode.
                del self.clients[cid]
                await self.stop(client)
                return
            if operator and ttl>0:
                # Only one local connection can be an operator, even if the
                # gateway sends conflicting leases.
                if any(c is not client and c['operator'] for c in self.clients.values()):
                    return
            client['operator']=operator and ttl>0
            client['deadline']=time.monotonic()+ttl
            client['expires']=expires
        elif kind in {'text','binary'}:
            operator=self.operating(client)
            if kind=='text':
                data=message.get('data','')
                try:
                    permit=len(data)<=262144 and allowed(json.loads(data),operator)
                except (ValueError,TypeError):
                    permit=False
            else:
                data=base64.b64decode(message['data'],validate=True)
                permit=operator and 6<=len(data)<=262144 and data[0]==3
            if permit:
                await client['ws'].send(data)

    async def watchdog(self):
        while True:
            await asyncio.sleep(.1)
            # This task runs independently of gateway traffic. If the hub or
            # network stalls, the Pi stops TX within the short lease lifetime.
            for cid,client in list(self.clients.items()):
                if client['operator'] and not self.operating(client):
                    self.clients.pop(cid,None)
                    await self.stop(client)

    async def run_once(self):
        async with connect(self.hub,additional_headers={'Authorization':'Bearer '+self.token},max_size=524288,max_queue=16,ping_interval=10,ping_timeout=10,close_timeout=1) as hub:
            await hub.send(json.dumps({'type':'hello','wfweb_url':self.http_url}))
            timer=asyncio.create_task(self.watchdog())
            try:
                async for raw in hub:
                    if not isinstance(raw,str):
                        raise ValueError('Invalid gateway message')
                    await self.handle(hub,json.loads(raw))
            finally:
                timer.cancel()
                tasks=list(self.http_tasks)
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                self.http_tasks.clear()
                clients=list(self.clients.values());self.clients.clear()
                for client in clients:
                    await self.stop(client)

    async def run(self):
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                log.warning('Connector offline (%s); retrying in 5 seconds',type(exc).__name__)
            await asyncio.sleep(5)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    node=os.environ['BARC_NODE_ID']
    agent=Agent(os.getenv('BARC_GATEWAY','wss://remote.barc.ca')+'/ws/nodes/'+node,os.environ['BARC_NODE_TOKEN'],os.environ['BARC_RADIO_WS'],os.getenv('BARC_RADIO_CA'),os.environ['BARC_WFWEB_URL'])
    asyncio.run(agent.run())
