"""Credential-free first boot, durable per-node identity, and API heartbeats."""
import asyncio
import fcntl
import json
import logging
import os
import platform
import secrets
import socket
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

log=logging.getLogger('barc.node_identity')
AGENT_VERSION='1.0.0'


class NodeIdentity:
    def __init__(self, base_url, state_path, node_id=None, token=None, name=None):
        self.base=base_url.replace('wss://','https://',1).replace('ws://','http://',1).rstrip('/')
        parsed=urlparse(self.base)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme!='https' and not (parsed.scheme=='http' and os.getenv('BARC_TESTING')=='1')):
            raise ValueError('The call-home API must use HTTPS.')
        if bool(node_id)!=bool(token):raise ValueError('Provide both manual node credentials or neither.')
        self.manual=bool(node_id)
        self.name=name or socket.gethostname()
        self.path=Path(state_path)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        lock_fd=os.open(str(self.path)+'.lock',os.O_CREAT|os.O_RDWR,0o600)
        with os.fdopen(lock_fd,'w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if node_id:
                identity={'node_id':node_id,'node_token':token,'manual':True}
            elif self.path.exists():
                identity=json.loads(self.path.read_text())
            else:
                identity={'node_id':'node-'+uuid.uuid4().hex,'node_token':secrets.token_urlsafe(48)}
            if not isinstance(identity.get('node_id'),str) or not isinstance(identity.get('node_token'),str):raise ValueError('Invalid saved node identity.')
            fd,temp=tempfile.mkstemp(prefix='.node-',dir=self.path.parent)
            try:
                with os.fdopen(fd,'w') as stream:
                    json.dump(identity,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
                os.replace(temp,self.path)
            finally:
                if os.path.exists(temp):os.unlink(temp)
        self.node_id=identity['node_id'];self.token=identity['node_token']
        self.manual=identity.get('manual',self.manual)

    @classmethod
    def from_environment(cls):
        path=os.getenv('BARC_NODE_STATE',str(Path.home()/'.local/state/barc-node/identity.json'))
        return cls(os.getenv('BARC_GATEWAY','wss://remote.barc.ca'),path,os.getenv('BARC_NODE_ID'),os.getenv('BARC_NODE_TOKEN'),os.getenv('BARC_NODE_NAME'))

    @property
    def relay_url(self):
        return self.base.replace('https://','wss://',1).replace('http://','ws://',1)+'/ws/nodes/'+self.node_id

    def information(self):
        info={'hostname':socket.gethostname(),'os':platform.system(),'os_release':platform.release(),'architecture':platform.machine(),'python_version':platform.python_version(),'agent_version':AGENT_VERSION}
        try:info['os_name']=platform.freedesktop_os_release().get('PRETTY_NAME',platform.system())
        except OSError:pass
        try:info['model']=Path('/proc/device-tree/model').read_text().strip('\x00\n')[:200]
        except OSError:pass
        try:info['uptime_seconds']=float(Path('/proc/uptime').read_text().split()[0])
        except (OSError,ValueError):pass
        return info

    def request(self, method, path, data=None, authenticated=True):
        headers={'User-Agent':'BARC-Node/'+AGENT_VERSION,'Accept':'application/json'}
        if authenticated:headers['Authorization']='Bearer '+self.token
        with requests.Session() as client:
            client.trust_env=False
            response=client.request(method,self.base+path,json=data,headers=headers,timeout=(5,15),allow_redirects=False)
            response.raise_for_status()
            if response.is_redirect:raise ValueError('Unexpected API redirect.')
            return response.json()

    def register(self, wfweb_url):
        data={'name':self.name,'status':'starting','info':self.information(),'wfweb_url':wfweb_url}
        if self.manual:
            record=self.request('GET','/api/nodes/me')
            if record['node']['id']!=self.node_id:raise ValueError('Manual node identity does not match its credential.')
            return self.request('PATCH','/api/nodes/'+self.node_id,data)
        result=self.request('POST','/api/nodes/register',data|{'node_id':self.node_id,'node_token':self.token},authenticated=False)
        if result['node']['id']!=self.node_id:raise ValueError('API returned a different node identity.')
        return result

    def heartbeat(self, status='ready'):
        return self.request('POST','/api/nodes/'+self.node_id+'/heartbeat',{'status':status,'info':self.information()})

    async def heartbeat_loop(self, connected):
        while True:
            try:await asyncio.to_thread(self.heartbeat,'ready' if connected() else 'degraded')
            except Exception as exc:log.warning('Call-home status update failed (%s)',type(exc).__name__)
            await asyncio.sleep(15)
