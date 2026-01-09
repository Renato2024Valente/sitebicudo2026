from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
from sqlalchemy import create_engine, Integer, String, DateTime, Text, ForeignKey, inspect, text as sqltext
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker, scoped_session
import os, json
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# Models
# ----------------------------
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id = mapped_column(Integer, primary_key=True)
    username = mapped_column(String(80), unique=True, nullable=False)
    password_hash = mapped_column(String(255), nullable=False)
    role = mapped_column(String(20), default='professor')
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    tutorias = relationship('Tutoria', back_populates='professor')

class Tutoria(Base):
    __tablename__ = 'tutorias'
    id = mapped_column(Integer, primary_key=True)
    professor_id = mapped_column(Integer, ForeignKey('users.id'), nullable=False)

    nome_tutor = mapped_column(String(120))

    nome_aluno = mapped_column(String(150), nullable=False)
    serie = mapped_column(String(20), nullable=False)
    tel_aluno = mapped_column(String(30))

    tel_resp = mapped_column(String(30))  # legado

    contatos_extra = mapped_column(Text)  # JSON: [{nome, telefone}]
    projeto_vida = mapped_column(Text)
    descricoes = mapped_column(Text)
    ocorrencias = mapped_column(Text)     # CSV
    assinatura = mapped_column(Text)      # base64 PNG

    carimbo_resp = mapped_column(String(120))
    carimbo_inst = mapped_column(String(160))
    carimbo_contato = mapped_column(String(160))
    carimbo_texto = mapped_column(String(80))
    carimbo_obs  = mapped_column(Text)

    criado_em = mapped_column(DateTime, default=datetime.utcnow)
    atualizado_em = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    professor = relationship('User', back_populates='tutorias')

# ----------------------------
# Config / DB
# ----------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key')
GESTAO_PIN = os.getenv('GESTAO_PIN', 'adm123')

def build_database_url():
    """Monta uma URL compatível com SQLAlchemy/Render."""
    db_url = os.getenv("DATABASE_URL")

    # Em produção no Render, SEM DATABASE_URL = ERRO (não deixa cair em SQLite)
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL não configurado. No Render: Web Service > Environment > add DATABASE_URL"
        )

    # Compatibilidade: postgres:// -> postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # Força driver psycopg2 (bem comum no Render)
    if db_url.startswith("postgresql://") and "+psycopg2" not in db_url and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Se for URL externa (render.com), garantir SSL
    if "render.com" in db_url and "sslmode=" not in db_url:
        db_url += ("&" if "?" in db_url else "?") + "sslmode=require"

    return db_url

DATABASE_URL = build_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True
)

Base.metadata.create_all(engine)

def ensure_schema():
    """Garante colunas novas em bancos antigos (migração simples)."""
    insp = inspect(engine)
    try:
        cols = {c['name'] for c in insp.get_columns('tutorias')}
    except Exception:
        Base.metadata.create_all(engine)
        cols = {c['name'] for c in insp.get_columns('tutorias')}

    needed = {
        'contatos_extra': 'TEXT',
        'assinatura': 'TEXT',
        'carimbo_resp': 'TEXT',
        'carimbo_inst': 'TEXT',
        'carimbo_contato': 'TEXT',
        'carimbo_texto': 'TEXT',
        'carimbo_obs': 'TEXT',
        'nome_tutor': 'TEXT',
    }

    with engine.begin() as conn:
        for name, typ in needed.items():
            if name not in cols:
                conn.execute(sqltext(f'ALTER TABLE tutorias ADD COLUMN {name} {typ}'))

ensure_schema()

SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))

# ----------------------------
# App
# ----------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Ajuda com proxy do Render (cookies/scheme/host corretos)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()

SERIES = ['6A','6B','6C','6D','7A','7B','7C','7D','8A','8B','8C','8D','9A','9B','9C','9D','1EM-A','1EM-B','1EM-C','2EM-A','2TEC','3EM-A','3EM-B']
OCORRENCIAS = ['Pessoal','Pedagogico','Familia','Prova paulista','Notas Bimestrais','Conflitos/Bullying','Comportamentos','Desatenção','Desrespeito','Emergencial']

def ensure_seed():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username='gestao').first():
            db.add(User(
                username='gestao',
                password_hash=generate_password_hash(os.getenv('APP_ADMIN_PASS', 'bicudoadmin2526')),
                role='gestao'
            ))
        if not db.query(User).filter_by(username='renato').first():
            db.add(User(
                username='renato',
                password_hash=generate_password_hash(os.getenv('SEED_PROF_PASS', '1234')),
                role='professor'
            ))
        db.commit()
    finally:
        db.close()

ensure_seed()

# ---------- Auth ----------
@app.get('/cadastro')
def cadastro_get():
    if session.get('uid'):
        return redirect(url_for('form'))
    return render_template('cadastro.html')

@app.post('/cadastro')
def cadastro_post():
    username = request.form.get('username','').strip()
    password = request.form.get('password','').strip()
    if not username or not password:
        return render_template('cadastro.html', error='Informe usuário e senha.')

    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=username).first():
            return render_template('cadastro.html', error='Usuário já existe.')
        u = User(username=username, password_hash=generate_password_hash(password), role='professor')
        db.add(u)
        db.commit()
    finally:
        db.close()

    return render_template('login.html', info='Cadastro feito. Entre com suas credenciais.')

@app.get('/login')
def login_get():
    if session.get('uid'):
        return redirect(url_for('form'))
    return render_template('login.html')

@app.post('/login')
def login_post():
    username = request.form.get('username','').strip()
    password = request.form.get('password','')

    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=username).first()
        ok = u and check_password_hash(u.password_hash, password)
        if ok:
            session['uid'] = u.id
            session['role'] = u.role
            session['username'] = u.username
            return redirect(url_for('form'))
    finally:
        db.close()

    return render_template('login.html', error='Usuário ou senha inválidos.')

@app.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_get'))

# ---------- Views ----------
@app.get('/')
def home():
    if session.get('uid'):
        return redirect(url_for('form'))
    return redirect(url_for('login_get'))

@app.get('/form')
def form():
    if not session.get('uid'):
        return redirect(url_for('login_get'))

    db = SessionLocal()
    try:
        tid = request.args.get('id')
        duplicar = request.args.get('duplicar') == '1'
        record = None
        contatos_json = '[]'

        if tid:
            record = db.get(Tutoria, int(tid))
            if not record:
                abort(404)
            if session.get('role') != 'gestao' and record.professor_id != session['uid']:
                abort(403)

            if duplicar:
                class D: pass
                d = D()
                d.id = None
                d.nome_tutor = record.nome_tutor
                d.nome_aluno = record.nome_aluno
                d.serie = record.serie
                d.tel_aluno = record.tel_aluno
                d.contatos_extra = record.contatos_extra
                d.projeto_vida = record.projeto_vida
                d.descricoes = record.descricoes
                d.ocorrencias = record.ocorrencias
                d.assinatura = record.assinatura
                record = d

        if record and getattr(record, "contatos_extra", None):
            contatos_json = record.contatos_extra

        return render_template(
            'form.html',
            SERIES=SERIES,
            OCORRENCIAS=OCORRENCIAS,
            record=record,
            contatos_json=contatos_json
        )
    finally:
        db.close()

@app.get('/lista')
def lista():
    if not session.get('uid'):
        return redirect(url_for('login_get'))

    db = SessionLocal()
    try:
        q = db.query(Tutoria)
        if session.get('role') != 'gestao':
            q = q.filter(Tutoria.professor_id == session['uid'])
        tutorias = q.order_by(Tutoria.criado_em.desc()).all()
        return render_template('lista.html', tutorias=tutorias)
    finally:
        db.close()

# ---------- Gestão com PIN por sessão ----------
@app.get('/gestao')
def gestao_pin():
    if not session.get('uid'):
        return redirect(url_for('login_get'))
    return render_template('gestao_pin.html')

@app.post('/gestao')
def gestao_pin_post():
    if not session.get('uid'):
        return redirect(url_for('login_get'))
    pin = request.form.get('pin','').strip()
    if pin == GESTAO_PIN:
        session['gestao_mode'] = True
        return redirect(url_for('gestao_painel'))
    return render_template('gestao_pin.html', error='PIN incorreto.')

@app.get('/gestao/painel')
def gestao_painel():
    if not session.get('gestao_mode'):
        return redirect(url_for('gestao_pin'))
    return render_template('gestao.html')

@app.post('/gestao/bloquear')
def gestao_bloquear():
    session.pop('gestao_mode', None)
    return redirect(url_for('gestao_pin'))

def require_gestao():
    if not session.get('gestao_mode'):
        abort(403)

# ---------- APIs Gestão ----------
@app.get('/api/gestao/professores')
def api_g_professores():
    require_gestao()
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.username.asc()).all()
        res = [{'id': u.id, 'username': u.username, 'role': u.role} for u in users]
        return jsonify(res)
    finally:
        db.close()

@app.get('/api/gestao/tutorias')
def api_g_tutorias():
    require_gestao()
    db = SessionLocal()
    try:
        items = db.query(Tutoria).order_by(Tutoria.criado_em.desc()).all()
        res = []
        for t in items:
            res.append({
                'id': t.id,
                'professor_id': t.professor_id,
                'nome_tutor': t.nome_tutor,
                'nome_aluno': t.nome_aluno,
                'serie': t.serie,
                'tel_aluno': t.tel_aluno,
                'contatos_extra': json.loads(t.contatos_extra or '[]'),
                'projeto_vida': t.projeto_vida,
                'descricoes': t.descricoes,
                'ocorrencias': (t.ocorrencias or '').split(',') if t.ocorrencias else [],
                'assinatura': t.assinatura or '',
                'carimbo': {
                    'resp': t.carimbo_resp,
                    'inst': t.carimbo_inst,
                    'contato': t.carimbo_contato,
                    'texto': t.carimbo_texto,
                    'obs': t.carimbo_obs,
                },
                'criado_em': t.criado_em.isoformat(),
            })
        return jsonify(res)
    finally:
        db.close()

@app.post('/api/gestao/carimbo')
def api_g_carimbo_all():
    require_gestao()
    data = request.json or {}
    resp = (data.get('resp') or '').strip()
    inst = (data.get('inst') or '').strip()
    contato = (data.get('contato') or '').strip()
    texto = (data.get('texto') or 'ÊXITO VISTADO').strip()
    obs   = (data.get('obs')   or '').strip()

    db = SessionLocal()
    try:
        n = 0
        for t in db.query(Tutoria).all():
            t.carimbo_resp = resp
            t.carimbo_inst = inst
            t.carimbo_contato = contato
            t.carimbo_texto = texto
            t.carimbo_obs = obs
            n += 1
        db.commit()
        return jsonify({'ok': True, 'aplicados': n})
    finally:
        db.close()

@app.post('/api/gestao/tutorias/<int:tid>/carimbo')
def api_g_carimbo_one(tid):
    require_gestao()
    data = request.json or {}
    db = SessionLocal()
    try:
        t = db.get(Tutoria, tid)
        if not t:
            abort(404)
        t.carimbo_resp = (data.get('resp') or '').strip()
        t.carimbo_inst = (data.get('inst') or '').strip()
        t.carimbo_contato = (data.get('contato') or '').strip()
        t.carimbo_texto = (data.get('texto') or 'ÊXITO VISTADO').strip()
        t.carimbo_obs = (data.get('obs') or '').strip()
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

# ---------- CRUD (professor) ----------
@app.post('/api/tutorias')
def api_create():
    if not session.get('uid'):
        abort(401)

    data = request.json or {}
    db = SessionLocal()
    try:
        t = Tutoria(
            professor_id=session['uid'],
            nome_tutor=(data.get('nome_tutor','') or '').strip(),
            nome_aluno=(data.get('nome_aluno','') or '').strip(),
            serie=(data.get('serie','') or '').strip(),
            tel_aluno=(data.get('tel_aluno','') or '').strip(),
            contatos_extra=json.dumps(data.get('contatos_extra', []), ensure_ascii=False),
            projeto_vida=(data.get('projeto_vida','') or '').strip(),
            descricoes=(data.get('descricoes','') or '').strip(),
            ocorrencias=','.join(data.get('ocorrencias', [])),
            assinatura=data.get('assinatura','') or ''
        )
        db.add(t)
        db.commit()
        return jsonify({'ok': True, 'id': t.id})
    finally:
        db.close()

@app.put('/api/tutorias/<int:tid>')
def api_update(tid):
    if not session.get('uid'):
        abort(401)

    data = request.json or {}
    db = SessionLocal()
    try:
        t = db.get(Tutoria, tid)
        if not t:
            abort(404)
        if session.get('role') != 'gestao' and t.professor_id != session['uid']:
            abort(403)

        t.nome_tutor = (data.get('nome_tutor','') or '').strip()
        t.nome_aluno = (data.get('nome_aluno','') or '').strip()
        t.serie = (data.get('serie','') or '').strip()
        t.tel_aluno = (data.get('tel_aluno','') or '').strip()
        t.contatos_extra = json.dumps(data.get('contatos_extra', []), ensure_ascii=False)
        t.projeto_vida = (data.get('projeto_vida','') or '').strip()
        t.descricoes = (data.get('descricoes','') or '').strip()
        t.ocorrencias = ','.join(data.get('ocorrencias', []))
        t.assinatura = data.get('assinatura','') or ''

        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

@app.delete('/api/tutorias/<int:tid>')
def api_delete(tid):
    if not session.get('uid'):
        abort(401)

    db = SessionLocal()
    try:
        t = db.get(Tutoria, tid)
        if not t:
            abort(404)
        if session.get('role') != 'gestao' and t.professor_id != session['uid']:
            abort(403)
        db.delete(t)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

# ----------------------------
# Main
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", "5000"))
    app.run(host='0.0.0.0', port=port, debug=False)
