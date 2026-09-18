"""Gunicorn entrypoint for MOD's first 100-user beta."""
import json, time, threading
from contextlib import closing
from collections import defaultdict, deque
from http import HTTPStatus
import server

server.init_db()
limits=defaultdict(deque)
lock=threading.Lock()

def application(environ,start_response):
    code=200
    try:
        method=environ.get('REQUEST_METHOD','GET')
        path=environ.get('PATH_INFO','/')
        if method not in {'GET','POST','DELETE'}:
            raise server.Error(405,'Bu işlem desteklenmiyor.')
        if method=='GET' and path=='/health':
            with closing(server.connect()) as db: db.execute('SELECT 1').fetchone()
            result={'ok':True,'version':'0.1.1-beta'}
        else:
            # One worker; never trust a client-supplied forwarding header.
            key=environ.get('REMOTE_ADDR','unknown')
            stamp=time.monotonic()
            with lock:
                for old in list(limits):
                    if not limits[old] or stamp-limits[old][-1]>60: del limits[old]
                if len(limits)>10000:raise server.Error(503,'Lütfen biraz sonra tekrar dene.')
                bucket=limits[key]
                while bucket and stamp-bucket[0]>60:bucket.popleft()
                if len(bucket)>=120:raise server.Error(429,'Çok fazla istek. Bir dakika sonra tekrar dene.')
                bucket.append(stamp)
            size=int(environ.get('CONTENT_LENGTH') or 0)
            if size<0 or size>16384:raise server.Error(413,'İstek çok büyük.')
            if size and not environ.get('CONTENT_TYPE','').lower().startswith('application/json'):
                raise server.Error(415,'JSON biçiminde istek gerekli.')
            raw=environ['wsgi.input'].read(size) if size else b''
            if len(raw)!=size:raise server.Error(400,'Eksik istek.')
            data=json.loads(raw) if raw else {}
            if not isinstance(data,dict):raise server.Error(400,'Geçersiz istek.')
            with closing(server.connect()) as db, db:
                db.execute('BEGIN IMMEDIATE')
                result=server.dispatch(db,method,path,data,environ.get('HTTP_AUTHORIZATION',''))
    except server.Error as exc:
        code=exc.status;result={'error':exc.message}
    except (ValueError,UnicodeError):
        code=400;result={'error':'Geçersiz istek.'}
    except Exception:
        code=503;result={'error':'Hizmet geçici olarak kullanılamıyor.'}
    payload=json.dumps(result,ensure_ascii=False).encode('utf-8')
    headers=[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(payload))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
    if code==429:headers.append(('Retry-After','60'))
    start_response(f'{code} {HTTPStatus(code).phrase}',headers)
    return [payload]
