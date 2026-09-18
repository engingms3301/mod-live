"""MOD private-beta API. Python 3.11+, SQLite. Put behind an HTTPS reverse proxy."""
import hashlib,hmac,json,os,re,secrets,sqlite3,time,uuid,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from collections import defaultdict,deque
from contextlib import closing
DB=os.environ.get('MOD_DB','mod.sqlite3')
LIMITS=defaultdict(deque);LOCK=threading.Lock()
class Error(Exception):
 def __init__(self,status,message):self.status=status;self.message=message

def connect():
 db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');return db

def init_db():
 with closing(connect()) as db, db:
  db.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,city TEXT NOT NULL DEFAULT '',salt TEXT NOT NULL,pw TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS follows(follower TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,followed TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(follower,followed),CHECK(follower<>followed));
  CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,type TEXT NOT NULL,place TEXT NOT NULL,starts_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,audience TEXT NOT NULL CHECK(audience IN ('public','followers','private')));
  CREATE TABLE IF NOT EXISTS joins(plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(plan_id,user_id));
  CREATE TABLE IF NOT EXISTS blocks(blocker TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,blocked TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(blocker,blocked),CHECK(blocker<>blocked));
  CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,reporter TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,target_type TEXT NOT NULL,target_id TEXT NOT NULL,reason TEXT NOT NULL,created_at INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending');
  CREATE INDEX IF NOT EXISTS plans_expiry ON plans(expires_at);
  CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
  ''')
  columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
  if 'terms_at' not in columns:db.execute('ALTER TABLE users ADD COLUMN terms_at INTEGER NOT NULL DEFAULT 0')
  if 'suspended' not in columns:db.execute('ALTER TABLE users ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0')


def now():return int(time.time()*1000)
def clean(data,key,minimum=1,maximum=100):
 value=data.get(key)
 if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum:raise Error(400,f'{key}: geçerli bir değer gerekli.')
 return value.strip()
def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def public_user(row):return {k:row[k] for k in ('id','name','city')}
def blocked(db,a,b):
 return db.execute('SELECT 1 FROM blocks WHERE (blocker=? AND blocked=?) OR (blocker=? AND blocked=?)',(a,b,b,a)).fetchone() is not None
def visible(db,p,uid):
 if blocked(db,uid,p['user_id']):return False
 owner=db.execute('SELECT suspended FROM users WHERE id=?',(p['user_id'],)).fetchone()
 if not owner or owner[0]:return False
 return p['user_id']==uid or p['audience']=='public' or (p['audience']=='followers' and db.execute('SELECT 1 FROM follows WHERE follower=? AND followed=?',(uid,p['user_id'])).fetchone() is not None)
def snapshot(db,uid):
 me=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
 following=[r[0] for r in db.execute('SELECT followed FROM follows WHERE follower=?',(uid,))]
 # Bounded private beta: no pagination yet; hard account cap keeps complete state bounded.
 users=[public_user(r) for r in db.execute('SELECT * FROM users WHERE id<>? AND suspended=0 ORDER BY name',(uid,)) if not blocked(db,uid,r['id'])]
 blocked_users=[public_user(r) for r in db.execute('SELECT u.* FROM users u JOIN blocks b ON b.blocked=u.id WHERE b.blocker=?',(uid,))]
 plans=[]
 for row in db.execute('SELECT p.*, (SELECT count(*) FROM joins j WHERE j.plan_id=p.id) AS count FROM plans p WHERE expires_at>? ORDER BY starts_at',(now(),)):
  if visible(db,row,uid):plans.append(dict(row))
 ids={p['id'] for p in plans}
 joined=[r[0] for r in db.execute('SELECT plan_id FROM joins WHERE user_id=?',(uid,)) if r[0] in ids]
 return {'me':dict(public_user(me),terms_accepted=bool(me['terms_at'])),'users':users,'following':following,'joined':joined,'plans':plans,'blocked_users':blocked_users}

def auth(db,authorization):
 if not authorization.startswith('Bearer '):raise Error(401,'Giriş yapmalısın.')
 token=authorization[7:];hashed=hashlib.sha256(token.encode()).hexdigest()
 row=db.execute('SELECT user_id FROM sessions WHERE token_hash=? AND expires>?',(hashed,now())).fetchone()
 if not row:raise Error(401,'Oturumun sona erdi.')
 if db.execute('SELECT suspended FROM users WHERE id=?',(row[0],)).fetchone()[0]:raise Error(403,'Bu hesap askıya alındı.')
 return row[0],hashed

def dispatch(db,method,path,data,authorization=''):
 if method=='GET' and path=='/health':return {'ok':True,'version':'0.1.0'}
 if method=='POST' and path in ('/register','/login'):
  email=clean(data,'email',3,254).lower();password=data.get('password')
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise Error(400,'Geçerli bir e-posta yaz.')
  if not isinstance(password,str) or not 10<=len(password)<=128:raise Error(400,'Parola 10–128 karakter olmalı.')
  if path=='/register':
   if db.execute('SELECT count(*) FROM users').fetchone()[0]>=100:raise Error(403,'Özel beta kullanıcı sınırına ulaşıldı.')
   if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():raise Error(409,'Bu adresle kayıt yapılamadı. Giriş yapmayı dene.')
   uid=str(uuid.uuid4());salt=secrets.token_hex(16);name=clean(data,'name',2,40)
   db.execute('INSERT INTO users(id,email,name,salt,pw) VALUES(?,?,?,?,?)',(uid,email,name,salt,password_hash(password,salt)))
  else:
   row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone();salt=row['salt'] if row else '00'*16
   candidate=password_hash(password,salt)
   if not row or not hmac.compare_digest(candidate,row['pw']):raise Error(401,'E-posta veya parola yanlış.')
   uid=row['id']
  db.execute('DELETE FROM sessions WHERE expires<=?',(now(),))
  token=secrets.token_urlsafe(32);db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,now()+30*86400000))
  return {'token':token,'state':snapshot(db,uid)}
 uid,hashed=auth(db,authorization)
 if method=='GET' and path=='/state':return snapshot(db,uid)
 if method=='POST' and path=='/logout':db.execute('DELETE FROM sessions WHERE token_hash=?',(hashed,));return {'ok':True}
 if method=='DELETE' and path=='/account':db.execute('DELETE FROM users WHERE id=?',(uid,));return {'ok':True}
 if method=='POST' and path=='/profile':
  name=clean(data,'name',2,40);city=clean(data,'city',0,60);db.execute('UPDATE users SET name=?,city=? WHERE id=?',(name,city,uid))
 elif method=='POST' and path=='/follow':
  target=clean(data,'user_id',1,64)
  if uid==target or blocked(db,uid,target) or not db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone():raise Error(400,'Geçerli bir kişi seç.')
  removed=db.execute('DELETE FROM follows WHERE follower=? AND followed=?',(uid,target)).rowcount
  if not removed:db.execute('INSERT INTO follows VALUES(?,?)',(uid,target))
  else:db.execute("DELETE FROM joins WHERE user_id=? AND plan_id IN (SELECT id FROM plans WHERE user_id=? AND audience='followers')",(uid,target))
 elif method=='POST' and path=='/terms/accept':
  if data.get('accepted') is not True:raise Error(400,'Topluluk kurallarını onaylamalısın.')
  db.execute('UPDATE users SET terms_at=? WHERE id=?',(now(),uid))
 elif method=='POST' and path in ('/block','/unblock'):
  target=clean(data,'user_id',1,64)
  if target==uid or not db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone():raise Error(400,'Geçerli bir kullanıcı seç.')
  if path=='/unblock':db.execute('DELETE FROM blocks WHERE blocker=? AND blocked=?',(uid,target))
  else:
   db.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(uid,target))
   db.execute('DELETE FROM follows WHERE (follower=? AND followed=?) OR (follower=? AND followed=?)',(uid,target,target,uid))
   db.execute('DELETE FROM joins WHERE (user_id=? AND plan_id IN (SELECT id FROM plans WHERE user_id=?)) OR (user_id=? AND plan_id IN (SELECT id FROM plans WHERE user_id=?))',(uid,target,target,uid))
 elif method=='POST' and path=='/report':
  kind=clean(data,'target_type',1,10);target=clean(data,'target_id',1,64);reason=clean(data,'reason',3,500)
  if kind=='plan':
   item=db.execute('SELECT * FROM plans WHERE id=?',(target,)).fetchone()
   if not item or not visible(db,item,uid):raise Error(404,'İçerik bulunamadı.')
  elif kind=='user':
   if target==uid or not db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone():raise Error(404,'Kullanıcı bulunamadı.')
  else:raise Error(400,'Geçersiz şikâyet türü.')
  if db.execute('SELECT count(*) FROM reports WHERE reporter=? AND created_at>?',(uid,now()-86400000)).fetchone()[0]>=20:raise Error(429,'Günlük bildirim sınırına ulaştın.')
  db.execute('INSERT INTO reports(id,reporter,target_type,target_id,reason,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),uid,kind,target,reason,now()))
  return {'ok':True}
 elif method=='POST' and path=='/plans':
  if not db.execute('SELECT terms_at FROM users WHERE id=?',(uid,)).fetchone()[0]:raise Error(403,'Önce topluluk kurallarını kabul etmelisin.')
  title=clean(data,'title',1,100);kind=clean(data,'type',1,20);place=clean(data,'place',1,60);audience=clean(data,'audience',1,20);starts=data.get('starts_at')
  if kind not in ('coffee','walk','music','game') or audience not in ('public','followers','private'):raise Error(400,'Geçersiz mod veya görünürlük.')
  if isinstance(starts,bool) or not isinstance(starts,int) or not now()<starts<=now()+86400000:raise Error(400,'Önümüzdeki 24 saat içinde bir zaman seç.')
  if db.execute('SELECT count(*) FROM plans WHERE user_id=? AND expires_at>?',(uid,now())).fetchone()[0]>=10:raise Error(400,'En fazla 10 aktif plan paylaşabilirsin.')
  db.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),uid,title,kind,place,starts,min(now()+86400000,starts+7200000),audience))
 elif method=='POST' and path=='/join':
  pid=clean(data,'plan_id',1,64);p=db.execute('SELECT * FROM plans WHERE id=? AND expires_at>?',(pid,now())).fetchone()
  if not p or not visible(db,p,uid):raise Error(404,'Plan bulunamadı veya artık görünür değil.')
  if p['user_id']==uid:raise Error(400,'Kendi planına zaten ev sahipliği yapıyorsun.')
  removed=db.execute('DELETE FROM joins WHERE plan_id=? AND user_id=?',(pid,uid)).rowcount
  if not removed:db.execute('INSERT INTO joins VALUES(?,?)',(pid,uid))
 elif method=='DELETE' and path.startswith('/plans/'):
  if not db.execute('DELETE FROM plans WHERE id=? AND user_id=?',(path[7:],uid)).rowcount:raise Error(404,'Plan bulunamadı.')
 else:raise Error(404,'İşlem bulunamadı.')
 return snapshot(db,uid)

class Handler(BaseHTTPRequestHandler):
 server_version='MOD/0.1'
 def log_message(self,fmt,*args):pass # No credentials, request bodies or account emails in logs.
 def handle_api(self):
  try:
   self.connection.settimeout(15)
   ip=self.client_address[0]
   with LOCK:
    q=LIMITS[ip];stamp=time.monotonic()
    while q and stamp-q[0]>60:q.popleft()
    if len(q)>=120:raise Error(429,'Çok fazla istek. Bir dakika sonra tekrar dene.')
    q.append(stamp)
    if len(LIMITS)>1000:
     for key in list(LIMITS):
      if not LIMITS[key] or stamp-LIMITS[key][-1]>60:del LIMITS[key]
   size=int(self.headers.get('Content-Length','0'))
   if size<0 or size>16384:raise Error(413,'İstek çok büyük.')
   data=json.loads(self.rfile.read(size)) if size else {}
   if not isinstance(data,dict):raise Error(400,'Geçersiz istek.')
   with closing(connect()) as db, db:
    db.execute('BEGIN IMMEDIATE')
    result=dispatch(db,self.command,self.path,data,self.headers.get('Authorization',''))
   self.reply(200,result)
  except Error as e:self.reply(e.status,{'error':e.message})
  except (ValueError,UnicodeError):self.reply(400,{'error':'Geçersiz istek.'})
  except Exception:self.reply(500,{'error':'Sunucu işlemi tamamlayamadı.'})
 def reply(self,code,data):
  payload=json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
 do_GET=handle_api;do_POST=handle_api;do_DELETE=handle_api

if __name__=='__main__':
 init_db();server=ThreadingHTTPServer((os.environ.get('MOD_BIND','127.0.0.1'),int(os.environ.get('PORT','8080'))),Handler);print('MOD API listening on',server.server_address,flush=True);server.serve_forever()
