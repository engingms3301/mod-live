"""Gunicorn entrypoint for MOD's first 100-user beta."""
import json, time, threading
from contextlib import closing
from collections import defaultdict, deque
from http import HTTPStatus
import server

server.init_db()
limits=defaultdict(deque)
lock=threading.Lock()

SUPPORT_EMAIL = 'engingms3301@gmail.com'

def policy_page(title, body):
    return ("<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title} | MOD</title><style>body{{font-family:system-ui,-apple-system,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6;color:#172033}}h1{{color:#5b3df5}}a{{color:#4b32c3}}</style></head><body>"
            f"<h1>{title}</h1>{body}<p><a href='/privacy'>Gizlilik Politikası</a> · <a href='/terms'>Topluluk Kuralları</a></p></body></html>").encode('utf-8')

PRIVACY_PAGE = policy_page('MOD Gizlilik Politikası', f"""
<p>Son güncelleme: 18 Eylül 2026</p>
<p>MOD, günlük hayattaki planları ve arkadaş takibini kolaylaştıran bir sosyal uygulamadır. Bu politika, uygulamayı kullandığınızda hangi verileri işlediğimizi açıklar.</p>
<h2>Topladığımız veriler</h2><p>Hesap oluştururken e-posta adresi, ad, parola ve isteğe bağlı şehir bilgisi; oluşturduğunuz planlar, takip ilişkileri, katılımlar, engellemeler ve bildirimler işlenir. Parolalar geri döndürülemez biçimde özetlenerek saklanır.</p>
<h2>Veriyi neden kullanırız</h2><p>Hesabınızı yönetmek, planları göstermek, takip ve katılım özelliklerini çalıştırmak, güvenliği sağlamak ve kötüye kullanım bildirimlerini incelemek için kullanırız. Verinizi satmayız.</p>
<h2>Paylaşım ve görünürlük</h2><p>Herkese açık planlar uygulama kullanıcılarına görünür. Takipçi ve özel planlar yalnızca seçtiğiniz hedef kitleye görünür. Konum izni, rehber, kamera veya hassas cihaz verisi toplamıyoruz.</p>
<h2>Saklama ve silme</h2><p>Hesabınızı uygulamadaki hesap silme seçeneğiyle kalıcı olarak silebilirsiniz. Silme, hesabınıza bağlı profil, oturum, takip ve plan verilerini kaldırır. Yasal olarak gerekli olmadıkça veriyi saklamayız.</p>
<h2>İletişim</h2><p>Gizlilik veya hesap silme talepleri için <a href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a> adresine yazabilirsiniz.</p>""")

TERMS_PAGE = policy_page('MOD Topluluk Kuralları', f"""
<p>MOD, 13 yaş ve üzerindeki kullanıcılar için tasarlanmıştır. Başkalarına zarar verme, taciz, nefret söylemi, yasa dışı içerik, kişisel bilgilerin izinsiz paylaşımı ve spam yasaktır.</p>
<p>Uygulama içinden kullanıcı veya plan bildirebilir, kullanıcıları engelleyebilirsiniz. Bildirimler incelenir; kuralları ihlal eden içerik kaldırılabilir ve hesaplar kısıtlanabilir.</p>
<p>Yardım için <a href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a> adresine ulaşabilirsiniz.</p>""")

def application(environ,start_response):
    code=200
    content_type='application/json; charset=utf-8'
    try:
        method=environ.get('REQUEST_METHOD','GET')
        path=environ.get('PATH_INFO','/')
        if method not in {'GET','POST','DELETE'}:
            raise server.Error(405,'Bu işlem desteklenmiyor.')
        if method=='GET' and path=='/privacy':
            payload=PRIVACY_PAGE
            content_type='text/html; charset=utf-8'
        elif method=='GET' and path=='/terms':
            payload=TERMS_PAGE
            content_type='text/html; charset=utf-8'
        elif method=='GET' and path=='/health':
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
    if content_type.startswith('application/json'):
        payload=json.dumps(result,ensure_ascii=False).encode('utf-8')
    headers=[('Content-Type',content_type),('Content-Length',str(len(payload))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
    if code==429:headers.append(('Retry-After','60'))
    start_response(f'{code} {HTTPStatus(code).phrase}',headers)
    return [payload]
