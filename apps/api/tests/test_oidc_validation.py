"""Cryptographic claim validation with an explicit HTTP substitute; NOT real IdP evidence."""
import base64
import time
from dataclasses import replace
from unittest.mock import MagicMock
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from silicon.identity.oidc import OIDC
from silicon.settings import Settings


@pytest.mark.parametrize('change',[
    {'exp':0}, {'iss':'https://wrong.invalid'}, {'aud':'wrong'}, {'nonce':'wrong'},
    {'azp':'wrong'}, {'iat':4102444800}, {'sub':None}, {'nonce':None},
    {'aud':['silicon-web','other']}, {'__bad_signature':True}, {'__algorithm':'HS256'},
    {'__missing':'exp'}, {'__missing':'nonce'},
])
def test_invalid_claims_rejected_with_http_substitute(monkeypatch,change):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuer='http://127.0.0.1:8080/realms/silicon-dev'
    oidc=OIDC(Settings('postgresql+psycopg://unused/unused','test',issuer))
    claims=dict(iss=issuer,sub='fictional',aud='silicon-web',iat=int(time.time()),exp=int(time.time())+60,nonce='expected')
    claims.update({k:v for k,v in change.items() if not k.startswith('__')})
    if '__missing' in change: claims.pop(change['__missing'])
    signing_key=rsa.generate_private_key(public_exponent=65537,key_size=2048) if change.get('__bad_signature') else key
    algorithm=change.get('__algorithm','RS256')
    token=jwt.encode(claims,signing_key if algorithm=='RS256' else 'test-only-secret-not-production-32bytes',algorithm=algorithm,headers={'kid':'test'})
    jwk=jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(),as_dict=True);jwk['kid']='test'
    metadata={k:issuer+'/protocol/openid-connect/'+v for k,v in [('authorization_endpoint','auth'),('token_endpoint','token'),('jwks_uri','certs'),('end_session_endpoint','logout')]}
    metadata['issuer']=issuer
    def response(data):
        return httpx.Response(200,json=data,request=httpx.Request('GET',issuer))
    client=MagicMock()
    client.__enter__.return_value=client
    client.get.side_effect=lambda url:response(metadata if url.endswith('configuration') else {'keys':[jwk]})
    client.post.return_value=response({'id_token':token})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:client)
    with pytest.raises((ValueError,jwt.PyJWTError)):oidc.exchange('test-code','test-verifier','expected')


def test_secure_configuration_and_no_production_bypass():
    settings=Settings('postgresql+psycopg://unused/unused','test')
    with pytest.raises(ValueError):replace(settings,public_origin='http://localhost:5173')
    with pytest.raises(ValueError):replace(settings,oidc_issuer='http://idp.example.invalid/realm')
    with pytest.raises(ValueError):replace(settings,environment='production')
