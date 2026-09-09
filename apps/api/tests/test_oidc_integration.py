"""Real Keycloak authorization-code flow, actual HTTPS API and disposable PG.

Not mocks: browser form submission, code exchange, JWKS verification and RP logout.
Missing SILICON_TEST_KEYCLOAK_HOME is an explicit skip, never a passing integration.
"""
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit,parse_qs,urljoin
import httpx
import pytest
from sqlalchemy import text
from silicon.identity.routes import SESSION, CSRF

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'infra'))
from dev_tls import generate
from keycloak_realm import realm, VERSION


class Form(HTMLParser):
    def __init__(self,body):
        super().__init__();self.action=None;self.inputs={};self.feed(body)
    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag=='form' and self.action is None:self.action=attrs.get('action')
        if tag=='input' and attrs.get('name'):self.inputs[attrs['name']]=attrs.get('value','')


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_http(url,process,tls,seconds=90):
    deadline=time.monotonic()+seconds
    with httpx.Client(verify=tls,timeout=2,trust_env=False) as client:
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('test process exited; inspect captured log')
            try:
                if client.get(url).status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(.2)
    raise TimeoutError('test process startup timeout')


@pytest.fixture
def real_oidc(database,tmp_path):
    configured=os.getenv('SILICON_TEST_KEYCLOAK_HOME')
    if not configured:pytest.skip('not_run: set SILICON_TEST_KEYCLOAK_HOME to Keycloak 26.7.3 distribution; Java 21 required')
    home=tmp_path/'keycloak'
    shutil.copytree(configured,home,ignore=shutil.ignore_patterns('._*','data','log'))
    idp_port,api_port=port(),port()
    origin=f'https://localhost:{api_port}'
    issuer=f'https://127.0.0.1:{idp_port}/realms/silicon-dev'
    imports=home/'data/import';imports.mkdir(parents=True)
    (imports/'silicon-dev-realm.json').write_text(json.dumps(realm(origin)))
    key,cert=generate(tmp_path/'tls')
    tls=ssl.create_default_context(cafile=str(cert))
    assert tls.verify_mode == ssl.CERT_REQUIRED and tls.check_hostname
    env={**database.env,'OIDC_ISSUER':issuer,'OIDC_CLIENT_ID':'silicon-web',
         'OIDC_CLIENT_SECRET':'fictional-dev-client-secret','PUBLIC_ORIGIN':origin,'OIDC_CA_BUNDLE':str(cert)}
    processes=[]
    with (tmp_path/'keycloak.log').open('w') as kc_log,(tmp_path/'api.log').open('w') as api_log:
        try:
            kc=subprocess.Popen([str(home/'bin/kc.sh'),'start-dev','--http-host=127.0.0.1','--http-enabled=false',f'--https-port={idp_port}',
                                 f'--https-certificate-file={cert}',f'--https-certificate-key-file={key}',
                                 '--import-realm','--cache=local'],stdout=kc_log,stderr=subprocess.STDOUT,
                                 env={**os.environ,'JAVA_OPTS_APPEND':'-Xms128m -Xmx512m'})
            processes.append(kc)
            wait_http(issuer+'/.well-known/openid-configuration',kc,tls)
            assert f'Keycloak {VERSION}' in (tmp_path/'keycloak.log').read_text()
            api=subprocess.Popen([sys.executable,'-m','uvicorn','silicon.main:create_app','--factory','--host','127.0.0.1',
                '--port',str(api_port),'--ssl-keyfile',str(key),'--ssl-certfile',str(cert),'--no-access-log'],
                cwd=ROOT,env=env,stdout=api_log,stderr=subprocess.STDOUT)
            processes.append(api)
            wait_http(origin+'/api/v1/ready',api,tls,20)
            yield origin,issuer,tls
        finally:
            for process in reversed(processes):
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            # Only process lifecycle evidence is copied; access logs with codes are disabled.
            if any(p.returncode not in (0,-15,143) for p in processes):
                print('Keycloak/API logs:',tmp_path)
            key.unlink(missing_ok=True)
            cert.unlink(missing_ok=True)
            shutil.rmtree(home)


def begin_login(client,origin):
    response=client.get(origin+'/api/v1/auth/login')
    assert response.status_code==302
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    params=parse_qs(urlsplit(response.headers['location']).query)
    assert params['code_challenge_method']==['S256']
    page=client.get(response.headers['location'])
    assert page.status_code==200
    form=Form(page.text)
    assert form.action
    response=client.post(html.unescape(form.action),data={**form.inputs,'username':'alice','password':'Fictional-alice-17!'})
    assert response.status_code==302, __import__('re').findall(r'<(?:p|span)[^>]*>([^<]+)</(?:p|span)>',response.text)
    callback=response.headers['location']
    assert callback.startswith(origin+'/api/v1/auth/callback?')
    return callback


def test_real_keycloak_code_callback_logout_and_expiry(real_oidc,engine):
    origin,issuer,tls=real_oidc
    with httpx.Client(verify=tls,follow_redirects=False,timeout=10,trust_env=False) as client:
        assert client.get(origin+'/api/v1/session').status_code==401
        callback=begin_login(client,origin)
        # A different browser cannot redeem this callback even with the authentic code/state.
        with httpx.Client(verify=tls,timeout=10,trust_env=False) as stranger:
            assert stranger.get(callback).status_code==401
        response=client.get(callback)
        assert response.status_code==303
        session_cookie=[c for c in response.headers.get_list('set-cookie') if c.startswith(SESSION+'=')][0]
        assert all(v in session_cookie for v in ['HttpOnly','Secure','SameSite=lax','Path=/'])
        assert client.get(callback).status_code==401 # state/code cannot be replayed
        user=client.get(origin+'/api/v1/session')
        assert user.status_code==200 and user.json()['user']['name']
        token=client.cookies.get(SESSION)
        csrf=client.cookies.get(CSRF)
        assert client.post(origin+'/api/v1/auth/logout').status_code==403
        logout=client.post(origin+'/api/v1/auth/logout',headers={'Origin':origin,'X-CSRF-Token':csrf})
        assert logout.status_code==200
        assert client.get(origin+'/api/v1/session').status_code==401
        end=client.get(logout.json()['logout_url'])
        if end.status_code==200:
            form=Form(end.text)
            assert form.action
            end=client.post(urljoin(str(end.url),html.unescape(form.action)),data=form.inputs)
        assert end.status_code in (302,303) and end.headers['location']==origin+'/'
        # IdP SSO session really ended: fresh authorization needs its login form again.
        callback=begin_login(client,origin)
        assert client.get(callback).status_code==303
        with engine.begin() as db:db.execute(text("UPDATE sessions SET expires_at=now()-interval '1 second'"))
        assert client.get(origin+'/api/v1/session').status_code==401
        with httpx.Client(verify=tls,trust_env=False) as stolen:
            stolen.cookies.set(SESSION,token)
            assert stolen.get(origin+'/api/v1/session').status_code==401
        assert client.get(origin+'/api/v1/auth/callback?state=forged&code=forged').status_code==401
    print(f'Real Keycloak {VERSION}: authorization code + PKCE + signed ID token + browser binding + replay rejection + RP logout + session expiry passed')
