#!/usr/bin/env python3
"""
Sistema CAIC Darcy Ribeiro
Banco de dados: Supabase (PostgreSQL)
Deploy: Render.com
"""

import os, json, re
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, g, session, redirect, url_for
import psycopg

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'caic-darcy-ribeiro-2024')

# Senhas — altere nas variáveis de ambiente do Render
SENHA_ADMIN    = os.environ.get('SENHA_ADMIN', 'caic2024')      # secretaria
SENHA_PROFESSOR = os.environ.get('SENHA_PROFESSOR', 'prof2024') # professores

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# ── Database ───────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row, sslmode='require')
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    conn = psycopg.connect(DATABASE_URL, sslmode='require')
    cur  = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS turmas (
        id SERIAL PRIMARY KEY,
        nome TEXT UNIQUE NOT NULL,
        turno TEXT
    );
    CREATE TABLE IF NOT EXISTS alunos (
        id SERIAL PRIMARY KEY,
        id_original TEXT,
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id),
        turno TEXT,
        data_matricula TEXT,
        data_nascimento TEXT,
        cpf TEXT,
        raca TEXT,
        sus TEXT,
        responsavel TEXT,
        telefone TEXT,
        endereco TEXT,
        cidade TEXT,
        cep TEXT,
        obs TEXT,
        pcd INTEGER DEFAULT 0,
        especificidade TEXT,
        apoio TEXT,
        ativo INTEGER DEFAULT 1,
        criado_em TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS frequencias (
        id SERIAL PRIMARY KEY,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        data TEXT NOT NULL,
        presente INTEGER,
        UNIQUE(aluno_id, data)
    );
    CREATE TABLE IF NOT EXISTS historico (
        id SERIAL PRIMARY KEY,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL,
        descricao TEXT,
        usuario TEXT,
        data TIMESTAMP DEFAULT NOW()
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

# ── Helpers ────────────────────────────────────────────────────────────

def q(sql, args=(), one=False, db=None):
    conn = db or get_db()
    cur  = conn.cursor()
    cur.execute(sql, args)
    if sql.strip().upper().startswith('SELECT'):
        rows = cur.fetchone() if one else cur.fetchall()
        return dict(rows) if (one and rows) else ([dict(r) for r in rows] if rows else (None if one else []))
    conn.commit()
    return cur

def get_or_create_turma(db, nome, turno=''):
    row = q("SELECT id FROM turmas WHERE nome=%s", (nome,), one=True, db=db)
    if row:
        return row['id']
    cur = db.cursor()
    cur.execute("INSERT INTO turmas (nome, turno) VALUES (%s, %s) RETURNING id", (nome, turno))
    db.commit()
    return cur.fetchone()[0]

def save_aluno(db, data, aluno_id=None):
    turma_id = None
    if data.get('turma_nome'):
        turma_id = get_or_create_turma(db, data['turma_nome'], data.get('turno',''))

    fields = ['nome','turno','data_nascimento','cpf','raca','sus','telefone',
              'responsavel','endereco','cidade','cep','pcd','especificidade','apoio','obs']
    vals = {f: data.get(f) for f in fields}
    vals['turma_id'] = turma_id

    if aluno_id:
        sets = ', '.join([f"{k}=%s" for k in vals])
        q(f"UPDATE alunos SET {sets} WHERE id=%s", list(vals.values()) + [aluno_id], db=db)
        q("INSERT INTO historico (aluno_id, tipo, descricao) VALUES (%s,%s,%s)",
          (aluno_id, 'EDIÇÃO', 'Dados atualizados'), db=db)
    else:
        vals['ativo'] = data.get('ativo', 1)
        cols = ', '.join(vals.keys())
        phs  = ', '.join(['%s']*len(vals))
        cur  = db.cursor()
        cur.execute(f"INSERT INTO alunos ({cols}) VALUES ({phs}) RETURNING id", list(vals.values()))
        db.commit()
        aluno_id = cur.fetchone()[0]
        q("INSERT INTO historico (aluno_id, tipo, descricao) VALUES (%s,%s,%s)",
          (aluno_id, 'ENTRADA', 'Aluno cadastrado'), db=db)
    return aluno_id

# ── API ────────────────────────────────────────────────────────────────


# ── AUTENTICAÇÃO ───────────────────────────────────────────────────────

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CAIC — Acesso</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1a1614;--ink2:#4a4540;--ink3:#8a847e;--paper:#faf8f5;--paper2:#f2efe9;--paper3:#e8e3da;--accent:#c8602a;--accent-bg:#fdf2ec;--green:#2a6b4a;--radius:14px;--radius-sm:10px}
body{font-family:'DM Sans',sans-serif;background:var(--ink);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem}
.box{background:var(--paper);border-radius:var(--radius);padding:2.5rem 2rem;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.logo{font-family:'DM Serif Display',serif;font-size:26px;color:var(--ink);letter-spacing:-0.5px;margin-bottom:4px}
.logo em{font-style:italic;color:var(--accent)}
.sub{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:2rem}
.tabs{display:flex;gap:4px;background:var(--paper2);border-radius:var(--radius-sm);padding:4px;margin-bottom:1.5rem}
.tab-btn{flex:1;padding:8px;border-radius:8px;border:none;background:transparent;font-size:13px;font-weight:500;cursor:pointer;color:var(--ink3);font-family:'DM Sans',sans-serif;transition:all .15s}
.tab-btn.active{background:var(--paper);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.1)}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:1rem}
label{font-size:11px;font-weight:600;color:var(--ink3);text-transform:uppercase;letter-spacing:0.5px}
input{width:100%;padding:11px 14px;border:1px solid var(--paper3);border-radius:var(--radius-sm);background:var(--paper2);color:var(--ink);font-family:'DM Sans',sans-serif;font-size:14px;outline:none;transition:border-color .15s}
input:focus{border-color:var(--accent);background:var(--paper)}
.btn-login{width:100%;padding:13px;border-radius:var(--radius-sm);background:var(--ink);color:var(--paper);border:none;font-size:14px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;margin-top:.5rem;transition:all .15s}
.btn-login:hover{background:#4a4540}
.btn-login:active{transform:scale(.98)}
.erro{background:#fdf2ec;border:1px solid #c8602a;border-radius:var(--radius-sm);padding:.75rem 1rem;font-size:13px;color:#c8602a;margin-bottom:1rem;display:none}
.erro.show{display:block}
</style>
</head>
<body>
<div class="box">
  <div class="logo">CAIC <em>Darcy Ribeiro</em></div>
  <div class="sub">Ilhéus · Bahia</div>
  <div class="tabs">
    <button class="tab-btn active" onclick="setTipo('admin',this)">Secretaria</button>
    <button class="tab-btn" onclick="setTipo('professor',this)">Professor</button>
  </div>
  <div class="erro" id="erro">Senha incorreta. Tente novamente.</div>
  <form method="POST" action="/login">
    <input type="hidden" name="tipo" id="tipo-input" value="admin"/>
    <div class="fg">
      <label>Senha</label>
      <input type="password" name="senha" placeholder="Digite a senha" autofocus/>
    </div>
    <button type="submit" class="btn-login">Entrar</button>
  </form>
</div>
<script>
function setTipo(tipo,el){
  document.getElementById('tipo-input').value=tipo;
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
}
const p=new URLSearchParams(window.location.search);
if(p.get('erro')==='1'){document.getElementById('erro').classList.add('show');}
if(p.get('tipo')==='professor'){
  document.getElementById('tipo-input').value='professor';
  document.querySelectorAll('.tab-btn').forEach((b,i)=>{b.classList.toggle('active',i===1);});
}
</script>
</body>
</html>"""

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        tipo  = request.form.get('tipo','admin')
        senha = request.form.get('senha','')
        if tipo == 'admin' and senha == SENHA_ADMIN:
            session['perfil'] = 'admin'
            return redirect('/')
        elif tipo == 'professor' and senha == SENHA_PROFESSOR:
            session['perfil'] = 'professor'
            return redirect('/professor')
        else:
            return redirect(f'/login?erro=1&tipo={tipo}')
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

def requer_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('perfil') != 'admin':
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def requer_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('perfil') not in ('admin','professor'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@app.route('/api/stats')
@requer_login
def stats():
    db   = get_db()
    agora = datetime.now()
    mes_ini = f"{agora.year}-{agora.month:02d}-01"
    mes_fim = f"{agora.year}-{agora.month:02d}-31"
    return jsonify({
        'total_ativos': q("SELECT COUNT(*) as n FROM alunos WHERE ativo=1", db=db, one=True)['n'],
        'total_pcd':    q("SELECT COUNT(*) as n FROM alunos WHERE ativo=1 AND pcd=1", db=db, one=True)['n'],
        'total_turmas': q("SELECT COUNT(*) as n FROM turmas", db=db, one=True)['n'],
        'entradas_mes': q("SELECT COUNT(*) as n FROM historico WHERE tipo='ENTRADA' AND data>=%s AND data<=%s", (mes_ini, mes_fim), one=True, db=db)['n'],
        'saidas_mes':   q("SELECT COUNT(*) as n FROM historico WHERE tipo='SAÍDA' AND data>=%s AND data<=%s", (mes_ini, mes_fim), one=True, db=db)['n'],
        'matutino':     q("SELECT COUNT(*) as n FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id WHERE a.ativo=1 AND (a.turno ILIKE '%%MAT%%' OR t.turno ILIKE '%%MAT%%')", db=db, one=True)['n'],
        'vespertino':   q("SELECT COUNT(*) as n FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id WHERE a.ativo=1 AND (a.turno ILIKE '%%VES%%' OR t.turno ILIKE '%%VES%%')", db=db, one=True)['n'],
    })

@app.route('/api/turmas')
@requer_login
def turmas():
    db = get_db()
    return jsonify(q("""
        SELECT t.*, COUNT(a.id) as total
        FROM turmas t LEFT JOIN alunos a ON a.turma_id=t.id AND a.ativo=1
        GROUP BY t.id ORDER BY t.nome
    """, db=db))

@app.route('/api/alunos', methods=['GET','POST'])
@requer_login
def alunos():
    db = get_db()
    if request.method == 'GET':
        params = request.args
        where, args = ["1=1"], []
        if params.get('turma'):
            where.append("t.nome = %s"); args.append(params['turma'])
        if params.get('turno'):
            where.append("(a.turno = %s OR t.turno = %s)"); args += [params['turno']]*2
        if params.get('pcd'):
            where.append("a.pcd = %s"); args.append(int(params['pcd']))
        ativo = params.get('ativo', '1')
        if ativo != 'todos':
            where.append("a.ativo = %s"); args.append(int(ativo))
        if params.get('busca'):
            where.append("(a.nome ILIKE %s OR a.cpf ILIKE %s OR a.sus ILIKE %s)")
            b = f"%{params['busca']}%"; args += [b,b,b]
        return jsonify(q(f"""
            SELECT a.*, t.nome as turma_nome, t.turno as turma_turno
            FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id
            WHERE {' AND '.join(where)}
            ORDER BY t.nome, a.nome
        """, args, db=db))
    else:
        new_id = save_aluno(db, request.json)
        return jsonify({'id': new_id, 'ok': True})

@app.route('/api/alunos/<int:aluno_id>', methods=['GET','PUT'])
@requer_login
def aluno(aluno_id):
    db = get_db()
    if request.method == 'GET':
        row = q("""
            SELECT a.*, t.nome as turma_nome, t.turno as turma_turno
            FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id WHERE a.id=%s
        """, (aluno_id,), one=True, db=db)
        return jsonify(row or {})
    else:
        save_aluno(db, request.json, aluno_id)
        return jsonify({'ok': True})

@app.route('/api/alunos/<int:aluno_id>/saida', methods=['PUT'])
@requer_login
def saida(aluno_id):
    db = get_db()
    q("UPDATE alunos SET ativo=0 WHERE id=%s", (aluno_id,), db=db)
    q("INSERT INTO historico (aluno_id, tipo, descricao) VALUES (%s,%s,%s)",
      (aluno_id, 'SAÍDA', 'Saída registrada'), db=db)
    return jsonify({'ok': True})

@app.route('/api/frequencia/<int:aluno_id>')
@requer_login
def get_freq(aluno_id):
    db  = get_db()
    ano = request.args.get('ano', datetime.now().year)
    mes = request.args.get('mes', datetime.now().month)
    rows = q("""
        SELECT data, presente FROM frequencias
        WHERE aluno_id=%s AND EXTRACT(YEAR FROM data::date)=%s AND EXTRACT(MONTH FROM data::date)=%s
    """, (aluno_id, int(ano), int(mes)), db=db)
    return jsonify({r['data']: r['presente'] for r in rows})

@app.route('/api/frequencia', methods=['POST'])
@requer_login
def set_freq():
    db = get_db()
    d  = request.json
    q("""
        INSERT INTO frequencias (aluno_id, data, presente) VALUES (%s,%s,%s)
        ON CONFLICT(aluno_id, data) DO UPDATE SET presente=EXCLUDED.presente
    """, (d['aluno_id'], d['data'], d['presente']), db=db)
    return jsonify({'ok': True})

@app.route('/api/historico')
@requer_login
def historico():
    db = get_db()
    rows = q("""
        SELECT h.*, a.nome as aluno_nome FROM historico h
        LEFT JOIN alunos a ON h.aluno_id=a.id
        ORDER BY h.data DESC LIMIT 100
    """, db=db)
    return jsonify(rows)

# ── Seed route (run once to import data) ──────────────────────────────

@app.route('/api/seed', methods=['POST'])
def seed():
    secret = request.json.get('secret','')
    if secret != os.environ.get('SEED_SECRET','caic2026'):
        return jsonify({'error': 'Não autorizado'}), 403
    db = get_db()
    data = request.json.get('data', {})

    # Insert turmas
    turma_map = {}
    for t in data.get('turmas', []):
        cur = db.cursor()
        cur.execute("""
            INSERT INTO turmas (nome, turno) VALUES (%s,%s)
            ON CONFLICT (nome) DO UPDATE SET turno=EXCLUDED.turno
            RETURNING id
        """, (t['nome'], t.get('turno') or ''))
        db.commit()
        turma_map[t['id']] = cur.fetchone()[0]

    # Insert alunos
    aluno_map = {}
    for a in data.get('alunos', []):
        turma_id = turma_map.get(a.get('turma_id'))
        cur = db.cursor()
        cur.execute("""
            INSERT INTO alunos
            (id_original, nome, turma_id, turno, data_matricula, data_nascimento,
             cpf, raca, sus, responsavel, telefone, endereco, cidade, cep, obs,
             pcd, especificidade, apoio, ativo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            str(a.get('id','')), a.get('nome',''), turma_id,
            a.get('turno'), a.get('data_matricula'), a.get('data_nascimento'),
            a.get('cpf'), a.get('raca'), a.get('sus'),
            a.get('responsavel'), a.get('telefone'), a.get('endereco'),
            a.get('cidade'), a.get('cep'), a.get('obs'),
            a.get('pcd', 0), a.get('especificidade'), a.get('apoio'),
            a.get('ativo', 1)
        ))
        db.commit()
        aluno_map[a['id']] = cur.fetchone()[0]

    return jsonify({'ok': True, 'alunos': len(aluno_map), 'turmas': len(turma_map)})

# ── HTML (same as before) ──────────────────────────────────────────────

@app.route('/')
@requer_admin
def index():
    return render_template_string(HTML)

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CAIC Darcy Ribeiro — Sistema de Alunos</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#1a1614;--ink2:#4a4540;--ink3:#8a847e;
  --paper:#faf8f5;--paper2:#f2efe9;--paper3:#e8e3da;
  --accent:#c8602a;--accent2:#e8845a;--accent-bg:#fdf2ec;
  --green:#2a6b4a;--green-bg:#edf6f1;
  --blue:#1e4d8c;--blue-bg:#edf2fb;
  --purple:#6b3fa0;--purple-bg:#f3edfb;
  --radius:12px;--radius-sm:8px;
}
body{font-family:'DM Sans',sans-serif;background:var(--paper);color:var(--ink);min-height:100vh}
.app{max-width:960px;margin:0 auto;padding:2rem 1rem 4rem}
.header{margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid var(--paper3)}
.logo-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.logo-title{font-family:'DM Serif Display',serif;font-size:26px;color:var(--ink);letter-spacing:-0.5px}
.logo-title em{font-style:italic}
.logo-sub{font-size:12px;color:var(--ink3);margin-top:3px;text-transform:uppercase;letter-spacing:0.5px}
.logo-sub strong{color:var(--ink2);font-weight:600}
.header-btns{display:flex;gap:8px;flex-wrap:wrap}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:2rem}
@media(max-width:600px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{background:var(--paper2);border:1px solid var(--paper3);border-radius:var(--radius);padding:1rem;position:relative;overflow:hidden;transition:transform .15s}
.stat:hover{transform:translateY(-2px)}
.stat::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%}
.stat.s1::before{background:var(--ink)}.stat.s2::before{background:var(--green)}
.stat.s3::before{background:var(--accent)}.stat.s4::before{background:var(--blue)}.stat.s5::before{background:var(--purple)}
.stat-label{font-size:11px;color:var(--ink3);font-weight:500;letter-spacing:0.4px;text-transform:uppercase;margin-bottom:6px}
.stat-value{font-family:'DM Serif Display',serif;font-size:30px;line-height:1;letter-spacing:-1px}
.s1 .stat-value{color:var(--ink)}.s2 .stat-value{color:var(--green)}
.s3 .stat-value{color:var(--accent)}.s4 .stat-value{color:var(--blue)}.s5 .stat-value{color:var(--purple)}
.tabs{display:flex;gap:2px;background:var(--paper2);border:1px solid var(--paper3);border-radius:var(--radius);padding:4px;margin-bottom:1.5rem;flex-wrap:wrap}
.tab{flex:1;min-width:90px;padding:8px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;border:none;background:transparent;cursor:pointer;color:var(--ink3);transition:all .15s;font-family:'DM Sans',sans-serif}
.tab.active{background:var(--paper);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card{background:var(--paper);border:1px solid var(--paper3);border-radius:var(--radius);padding:1.5rem;margin-bottom:1rem}
.card-title{font-family:'DM Serif Display',serif;font-size:15px;color:var(--ink);margin-bottom:1.25rem;display:flex;align-items:center;gap:8px}
.card-title::after{content:'';flex:1;height:1px;background:var(--paper3)}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:500px){.form-grid{grid-template-columns:1fr}}
.fg{display:flex;flex-direction:column;gap:5px}.fg.full{grid-column:1/-1}
label{font-size:11px;font-weight:600;color:var(--ink3);text-transform:uppercase;letter-spacing:0.5px}
input,select,textarea{width:100%;padding:9px 12px;border:1px solid var(--paper3);border-radius:var(--radius-sm);background:var(--paper2);color:var(--ink);font-family:'DM Sans',sans-serif;font-size:13px;outline:none;transition:border-color .15s}
input:focus,select:focus,textarea:focus{border-color:var(--accent);background:var(--paper)}
textarea{resize:vertical;min-height:64px;line-height:1.5}
select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%238a847e' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
.btn{padding:9px 18px;border-radius:var(--radius-sm);font-size:13px;font-weight:600;cursor:pointer;border:1px solid var(--paper3);background:var(--paper);color:var(--ink);font-family:'DM Sans',sans-serif;transition:all .15s}
.btn:hover{background:var(--paper2)}.btn-primary{background:var(--ink);color:var(--paper);border-color:var(--ink)}.btn-primary:hover{background:var(--ink2)}
.btn-accent{background:var(--accent);color:#fff;border-color:var(--accent)}.btn-accent:hover{background:var(--accent2)}
.btn-ghost{color:var(--ink3);border-color:transparent;background:transparent;padding:4px 10px;font-size:12px}.btn-ghost:hover{background:var(--paper2)}
.btn-danger{color:var(--accent);border-color:var(--paper3);padding:4px 10px;font-size:12px}.btn-danger:hover{background:var(--accent-bg)}
.btn-edit{color:var(--blue);border-color:var(--paper3);padding:4px 10px;font-size:12px}.btn-edit:hover{background:var(--blue-bg)}
.actions{display:flex;gap:8px;justify-content:flex-end;margin-top:1.25rem;padding-top:1rem;border-top:1px solid var(--paper3)}
.filters{display:grid;grid-template-columns:1fr auto auto auto;gap:8px;margin-bottom:12px}
@media(max-width:600px){.filters{grid-template-columns:1fr 1fr}}
.aluno-row{display:flex;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid var(--paper3)}
.aluno-row:last-child{border-bottom:none}
.avatar{width:36px;height:36px;border-radius:50%;background:var(--paper3);display:flex;align-items:center;justify-content:center;font-family:'DM Serif Display',serif;font-size:13px;color:var(--ink2);flex-shrink:0}
.avatar.pcd{background:var(--purple-bg);color:var(--purple)}
.aluno-info{flex:1;min-width:0}
.aluno-nome{font-size:14px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.aluno-det{font-size:12px;color:var(--ink3);margin-top:2px}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:99px;text-transform:uppercase;white-space:nowrap}
.badge-ativo{background:var(--green-bg);color:var(--green)}.badge-inativo{background:var(--accent-bg);color:var(--accent)}.badge-pcd{background:var(--purple-bg);color:var(--purple)}
.aluno-btns{display:flex;gap:4px;flex-shrink:0}
.empty{text-align:center;padding:2.5rem;color:var(--ink3);font-size:14px}
.empty-icon{font-size:32px;margin-bottom:8px;opacity:.4}
.log-row{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid var(--paper3);font-size:13px}
.log-row:last-child{border-bottom:none}
.log-dot{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0}
.log-dot.E{background:var(--green-bg);color:var(--green)}.log-dot.S{background:var(--accent-bg);color:var(--accent)}.log-dot.ED{background:var(--blue-bg);color:var(--blue)}
.log-body{flex:1}.log-name{font-weight:600;color:var(--ink)}.log-meta{font-size:12px;color:var(--ink3);margin-top:1px}
.log-date{font-size:11px;color:var(--ink3);white-space:nowrap;font-weight:500}
.freq-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.dia-btn{cursor:pointer;border-radius:var(--radius-sm);padding:8px 4px;text-align:center;border:1px solid var(--paper3);transition:opacity .15s;user-select:none}
.dia-btn:hover{opacity:.8}
.overlay{display:none;position:fixed;inset:0;background:rgba(26,22,20,.5);z-index:200;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(2px)}
.overlay.open{display:flex}
.modal{background:var(--paper);border-radius:16px;border:1px solid var(--paper3);padding:1.75rem;width:100%;max-width:560px;max-height:88vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.15)}
.modal-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem}
.modal-title{font-family:'DM Serif Display',serif;font-size:20px;color:var(--ink)}
.toast{position:fixed;bottom:2rem;right:2rem;background:var(--ink);color:var(--paper);padding:12px 20px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;z-index:999;opacity:0;transform:translateY(10px);transition:all .3s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}
.sdiv{font-family:'DM Serif Display',serif;font-size:13px;color:var(--ink3);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.sdiv::before,.sdiv::after{content:'';flex:1;height:1px;background:var(--paper3)}
.turma-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:1rem}
@media(max-width:600px){.turma-grid{grid-template-columns:repeat(2,1fr)}}
.turma-card{background:var(--paper2);border:1px solid var(--paper3);border-radius:var(--radius);padding:1rem;cursor:pointer;transition:all .15s}
.turma-card:hover,.turma-card.selected{border-color:var(--accent);background:var(--accent-bg)}
.turma-card-nome{font-weight:600;font-size:13px;color:var(--ink)}
.turma-card-info{font-size:12px;color:var(--ink3);margin-top:3px}
.turma-card-num{font-family:'DM Serif Display',serif;font-size:24px;color:var(--accent);margin-top:4px}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="logo-row">
      <div>
        <div class="logo-title">Controle de <em>Alunos</em></div>
        <div class="logo-sub">Escola CAIC · <strong>Darcy Ribeiro · Ilhéus</strong></div>
      </div>
      <div class="header-btns">
        <button class="btn" onclick="showTab('relatorio',this)">Relatório</button>
        <a href="/logout" class="btn" style="text-decoration:none">Sair</a>
        <button class="btn btn-accent" onclick="exportarExcel()">Exportar Excel ↗</button>
      </div>
    </div>
  </div>
  <div class="stats">
    <div class="stat s1"><div class="stat-label">Alunos ativos</div><div class="stat-value" id="st-total">—</div></div>
    <div class="stat s2"><div class="stat-label">Entradas (mês)</div><div class="stat-value" id="st-entrada">—</div></div>
    <div class="stat s3"><div class="stat-label">Saídas (mês)</div><div class="stat-value" id="st-saida">—</div></div>
    <div class="stat s4"><div class="stat-label">Turmas</div><div class="stat-value" id="st-turmas">—</div></div>
    <div class="stat s5"><div class="stat-label">Alunos PCD</div><div class="stat-value" id="st-pcd">—</div></div>
    <div class="stat s1"><div class="stat-label">Matutino</div><div class="stat-value" id="st-mat">—</div></div>
    <div class="stat s3"><div class="stat-label">Vespertino</div><div class="stat-value" id="st-ves">—</div></div>
  </div>
  <div class="tabs">
    <button class="tab active" onclick="showTab('cadastro',this)">+ Cadastrar</button>
    <button class="tab" onclick="showTab('lista',this)">Lista de alunos</button>
    <button class="tab" onclick="showTab('turmas',this)">Turmas</button>
    <button class="tab" onclick="showTab('frequencia',this)">Frequência</button>
    <button class="tab" onclick="showTab('historico',this)">Histórico</button>
  </div>
  <div id="tab-cadastro">
    <div class="card">
      <div class="card-title">Dados pessoais</div>
      <div class="form-grid">
        <div class="fg full"><label>Nome completo *</label><input id="f-nome" type="text" placeholder="Nome completo do aluno"/></div>
        <div class="fg"><label>Turma *</label><input id="f-turma" type="text" placeholder="Ex: 4º Ano - A" list="turmas-list"/><datalist id="turmas-list"></datalist></div>
        <div class="fg"><label>Turno</label><select id="f-turno"><option value="">Selecione</option><option value="MATUTINO">Matutino</option><option value="VESPERTINO">Vespertino</option></select></div>
        <div class="fg"><label>Data de nascimento</label><input id="f-nasc" type="date"/></div>
        <div class="fg"><label>CPF</label><input id="f-cpf" type="text" placeholder="000.000.000-00" maxlength="14" oninput="maskCPF(this)"/></div>
        <div class="fg"><label>Raça / Cor</label><select id="f-raca"><option value="">Não informado</option><option>Branca</option><option>Preta</option><option>Parda</option><option>Amarela</option><option>Indígena</option></select></div>
        <div class="fg"><label>Cartão SUS</label><input id="f-sus" type="text" placeholder="000 0000 0000 0000" maxlength="18" oninput="maskSUS(this)"/></div>
        <div class="fg"><label>PCD</label><select id="f-pcd" onchange="togglePCD(this)"><option value="0">Não</option><option value="1">Sim</option></select></div>
        <div class="fg full" id="fg-espec" style="display:none"><label>Especificidade / CID</label><input id="f-espec" type="text" placeholder="Ex: TEA, TDAH, F84..."/></div>
        <div class="fg full" id="fg-apoio" style="display:none"><label>Nome do apoio</label><input id="f-apoio" type="text" placeholder="Nome do profissional de apoio"/></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Responsável e contato</div>
      <div class="form-grid">
        <div class="fg"><label>Responsável</label><input id="f-resp" type="text" placeholder="Nome do responsável"/></div>
        <div class="fg"><label>Telefone</label><input id="f-tel" type="text" placeholder="(73) 00000-0000" maxlength="15" oninput="maskTel(this)"/></div>
        <div class="fg full"><label>Endereço</label><input id="f-end" type="text" placeholder="Rua, número, bairro"/></div>
        <div class="fg"><label>Cidade</label><input id="f-cidade" type="text" placeholder="Ex: Ilhéus"/></div>
        <div class="fg"><label>CEP</label><input id="f-cep" type="text" placeholder="00000-000" maxlength="9" oninput="maskCEP(this)"/></div>
        <div class="fg full"><label>Observações</label><textarea id="f-obs" placeholder="Informações adicionais..."></textarea></div>
      </div>
      <div class="actions">
        <button class="btn btn-ghost" onclick="limparForm()">Limpar</button>
        <button class="btn btn-primary" onclick="cadastrar()">Cadastrar aluno</button>
      </div>
    </div>
  </div>
  <div id="tab-lista" style="display:none">
    <div class="filters">
      <input id="busca" type="text" placeholder="Buscar por nome, CPF ou SUS..." oninput="renderLista()"/>
      <select id="fl-turma" onchange="renderLista()"><option value="">Todas as turmas</option></select>
      <select id="fl-turno" onchange="renderLista()"><option value="">Todos os turnos</option><option value="MAT">Matutino</option><option value="VES">Vespertino</option></select>
      <select id="fl-status" onchange="renderLista()"><option value="1">Ativos</option><option value="0">Inativos</option><option value="todos">Todos</option></select>
    </div>
    <div class="card"><div id="lista-container"><div class="empty"><div class="empty-icon">📋</div>Carregando...</div></div></div>
  </div>
  <div id="tab-turmas" style="display:none">
    <div id="turmas-grid" class="turma-grid"></div>
    <div class="card" id="turma-detalhe" style="display:none">
      <div class="card-title" id="turma-detalhe-titulo">Alunos da turma</div>
      <div id="turma-detalhe-lista"></div>
    </div>
  </div>
  <div id="tab-frequencia" style="display:none">
    <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">
      <select id="fq-turma" onchange="renderFreqTurma()" style="flex:1;min-width:140px"><option value="">Selecione uma turma</option></select>
      <select id="fq-mes" onchange="renderFreqTurma()" style="min-width:130px"></select>
      <select id="fq-ano" onchange="renderFreqTurma()" style="min-width:90px"></select>
    </div>
    <div id="freq-container"></div>
  </div>
  <div id="tab-historico" style="display:none">
    <div class="card">
      <div class="card-title">Movimentações recentes</div>
      <div id="hist-container"><div class="empty"><div class="empty-icon">📅</div>Carregando...</div></div>
    </div>
  </div>
  <div id="tab-relatorio" style="display:none"><div id="rel-container"></div></div>
</div>
<!-- MODAL EDITAR -->
<div class="overlay" id="modal-editar">
  <div class="modal">
    <div class="modal-hdr"><div class="modal-title">Editar aluno</div><button class="btn btn-ghost" onclick="fecharModal('modal-editar')">Fechar</button></div>
    <input type="hidden" id="e-id"/>
    <div class="form-grid">
      <div class="fg full"><label>Nome *</label><input id="e-nome" type="text"/></div>
      <div class="fg"><label>Turma</label><input id="e-turma" type="text" list="turmas-list"/></div>
      <div class="fg"><label>Turno</label><select id="e-turno"><option value="">Selecione</option><option value="MATUTINO">Matutino</option><option value="VESPERTINO">Vespertino</option></select></div>
      <div class="fg"><label>Nascimento</label><input id="e-nasc" type="date"/></div>
      <div class="fg"><label>CPF</label><input id="e-cpf" type="text" maxlength="14" oninput="maskCPF(this)"/></div>
      <div class="fg"><label>Raça / Cor</label><select id="e-raca"><option value="">Não informado</option><option>Branca</option><option>Preta</option><option>Parda</option><option>Amarela</option><option>Indígena</option></select></div>
      <div class="fg"><label>Cartão SUS</label><input id="e-sus" type="text" maxlength="18" oninput="maskSUS(this)"/></div>
      <div class="fg"><label>PCD</label><select id="e-pcd"><option value="0">Não</option><option value="1">Sim</option></select></div>
      <div class="fg full"><label>Especificidade</label><input id="e-espec" type="text"/></div>
      <div class="fg full"><label>Apoio</label><input id="e-apoio" type="text"/></div>
      <div class="fg"><label>Responsável</label><input id="e-resp" type="text"/></div>
      <div class="fg"><label>Telefone</label><input id="e-tel" type="text" maxlength="15" oninput="maskTel(this)"/></div>
      <div class="fg full"><label>Endereço</label><input id="e-end" type="text"/></div>
      <div class="fg"><label>Cidade</label><input id="e-cidade" type="text"/></div>
      <div class="fg"><label>CEP</label><input id="e-cep" type="text" maxlength="9" oninput="maskCEP(this)"/></div>
      <div class="fg full"><label>Obs</label><textarea id="e-obs"></textarea></div>
    </div>
    <div class="actions">
      <button class="btn btn-ghost" onclick="fecharModal('modal-editar')">Cancelar</button>
      <button class="btn btn-primary" onclick="salvarEdicao()">Salvar</button>
    </div>
  </div>
</div>
<!-- MODAL FREQ -->
<div class="overlay" id="modal-freq">
  <div class="modal">
    <div class="modal-hdr"><div class="modal-title" id="mf-nome">Frequência</div><button class="btn btn-ghost" onclick="fecharModal('modal-freq')">Fechar</button></div>
    <div style="display:flex;gap:8px;margin-bottom:1rem">
      <select id="mf-mes" onchange="renderModalFreq()" style="flex:1"></select>
      <select id="mf-ano" onchange="renderModalFreq()" style="min-width:90px"></select>
    </div>
    <div id="mf-conteudo"></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const MESES=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const DSEM=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
let turmasCache=[],mfAlunoId=null;
async function api(method,path,body=null){const opts={method,headers:{'Content-Type':'application/json'}};if(body)opts.body=JSON.stringify(body);const r=await fetch('/api'+path,opts);return r.json();}
function maskCPF(el){let v=el.value.replace(/\D/g,'');if(v.length>3)v=v.slice(0,3)+'.'+v.slice(3);if(v.length>7)v=v.slice(0,7)+'.'+v.slice(7);if(v.length>11)v=v.slice(0,11)+'-'+v.slice(11);el.value=v.slice(0,14)}
function maskTel(el){let v=el.value.replace(/\D/g,'');if(v.length>0)v='('+v;if(v.length>3)v=v.slice(0,3)+') '+v.slice(3);if(v.length>10)v=v.slice(0,10)+'-'+v.slice(10);el.value=v.slice(0,15)}
function maskCEP(el){let v=el.value.replace(/\D/g,'');if(v.length>5)v=v.slice(0,5)+'-'+v.slice(5);el.value=v.slice(0,9)}
function maskSUS(el){let v=el.value.replace(/\D/g,'');if(v.length>3)v=v.slice(0,3)+' '+v.slice(3);if(v.length>8)v=v.slice(0,8)+' '+v.slice(8);if(v.length>13)v=v.slice(0,13)+' '+v.slice(13);el.value=v.slice(0,18)}
function iniciais(n){return n.split(' ').slice(0,2).map(x=>x[0]).join('').toUpperCase()}
function fmtData(d){if(!d)return'—';const p=String(d).split('T')[0].split('-');return`${p[2]}/${p[1]}/${p[0]}`}
function togglePCD(sel){const p=sel.value==='1';document.getElementById('fg-espec').style.display=p?'flex':'none';document.getElementById('fg-apoio').style.display=p?'flex':'none';}
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2800)}
function fecharModal(id){document.getElementById(id).classList.remove('open')}
async function loadStats(){const s=await api('GET','/stats');document.getElementById('st-total').textContent=s.total_ativos;document.getElementById('st-entrada').textContent=s.entradas_mes;document.getElementById('st-saida').textContent=s.saidas_mes;document.getElementById('st-turmas').textContent=s.total_turmas;document.getElementById('st-pcd').textContent=s.total_pcd;document.getElementById('st-mat').textContent=s.matutino;document.getElementById('st-ves').textContent=s.vespertino;}
async function loadTurmasList(){turmasCache=await api('GET','/turmas');const dl=document.getElementById('turmas-list');dl.innerHTML=turmasCache.map(t=>`<option value="${t.nome}">`).join('');['fl-turma','fq-turma'].forEach(id=>{const sel=document.getElementById(id);const val=sel.value;const pre=id==='fl-turma'?'<option value="">Todas as turmas</option>':'<option value="">Selecione uma turma</option>';sel.innerHTML=pre+turmasCache.map(t=>`<option value="${t.nome}"${t.nome===val?'selected':''}>${t.nome} (${t.total})</option>`).join('');});}
function showTab(tab,el){document.querySelectorAll('[id^="tab-"]').forEach(d=>d.style.display='none');document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));document.getElementById('tab-'+tab).style.display='block';if(el)el.classList.add('active');if(tab==='lista'){loadTurmasList();renderLista();}if(tab==='turmas'){loadTurmasList();renderTurmas();}if(tab==='historico')renderHistorico();if(tab==='frequencia'){initFreq();renderFreqTurma();}if(tab==='relatorio')renderRelatorio();}
async function cadastrar(){const nome=document.getElementById('f-nome').value.trim();if(!nome){toast('Informe o nome do aluno.');return;}await api('POST','/alunos',{nome,turma_nome:document.getElementById('f-turma').value.trim(),turno:document.getElementById('f-turno').value,data_nascimento:document.getElementById('f-nasc').value||null,cpf:document.getElementById('f-cpf').value.trim()||null,raca:document.getElementById('f-raca').value||null,sus:document.getElementById('f-sus').value.trim()||null,pcd:parseInt(document.getElementById('f-pcd').value),especificidade:document.getElementById('f-espec').value.trim()||null,apoio:document.getElementById('f-apoio').value.trim()||null,responsavel:document.getElementById('f-resp').value.trim()||null,telefone:document.getElementById('f-tel').value.trim()||null,endereco:document.getElementById('f-end').value.trim()||null,cidade:document.getElementById('f-cidade').value.trim()||null,cep:document.getElementById('f-cep').value.trim()||null,obs:document.getElementById('f-obs').value.trim()||null,ativo:1});toast(`Aluno "${nome}" cadastrado!`);limparForm();loadStats();loadTurmasList();}
function limparForm(){['f-nome','f-turma','f-cpf','f-sus','f-resp','f-tel','f-end','f-cidade','f-cep','f-obs','f-espec','f-apoio'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});['f-turno','f-raca','f-pcd'].forEach(id=>document.getElementById(id).value='');document.getElementById('f-nasc').value='';document.getElementById('fg-espec').style.display='none';document.getElementById('fg-apoio').style.display='none';}
async function renderLista(){const busca=document.getElementById('busca').value;const turma=document.getElementById('fl-turma').value;const turno=document.getElementById('fl-turno').value;const status=document.getElementById('fl-status').value;let url=`/alunos?ativo=${status}`;if(busca)url+=`&busca=${encodeURIComponent(busca)}`;if(turma)url+=`&turma=${encodeURIComponent(turma)}`;if(turno)url+=`&turno=${encodeURIComponent(turno)}`;const alunos=await api('GET',url);const el=document.getElementById('lista-container');if(!alunos.length){el.innerHTML='<div class="empty"><div class="empty-icon">🔍</div>Nenhum aluno encontrado.</div>';return;}el.innerHTML=alunos.map(a=>`<div class="aluno-row"><div class="avatar ${a.pcd?'pcd':''}">${iniciais(a.nome)}</div><div class="aluno-info"><div class="aluno-nome">${a.nome}</div><div class="aluno-det">${a.turma_nome||'Sem turma'} · ${a.turno||a.turma_turno||'—'}${a.telefone?' · '+a.telefone:''}${a.pcd?' · PCD':''}</div></div>${a.pcd?'<span class="badge badge-pcd">PCD</span>':''}<span class="badge ${a.ativo?'badge-ativo':'badge-inativo'}">${a.ativo?'Ativo':'Inativo'}</span><div class="aluno-btns"><button class="btn btn-edit" data-id="${a.id}" onclick="abrirEdicao(parseInt(this.dataset.id))">Editar</button>${a.ativo?`<button class="btn btn-danger" data-id="${a.id}" data-nome="${a.nome.replace(/"/g,'&quot;')}" onclick="registrarSaida(parseInt(this.dataset.id),this.dataset.nome)">Saída</button>`:''}</div></div>`).join('');}
async function registrarSaida(id,nome){if(!confirm(`Confirmar saída de ${nome}?`))return;await api('PUT',`/alunos/${id}/saida`);toast(`Saída de ${nome} registrada.`);renderLista();loadStats();}
async function abrirEdicao(id){const a=await api('GET',`/alunos/${id}`);document.getElementById('e-id').value=id;const map={nome:'e-nome',turma_nome:'e-turma',turno:'e-turno',data_nascimento:'e-nasc',cpf:'e-cpf',raca:'e-raca',sus:'e-sus',especificidade:'e-espec',apoio:'e-apoio',responsavel:'e-resp',telefone:'e-tel',endereco:'e-end',cidade:'e-cidade',cep:'e-cep',obs:'e-obs'};for(const[k,eid] of Object.entries(map)){const el=document.getElementById(eid);if(el)el.value=a[k]!=null?a[k]:'';}document.getElementById('e-pcd').value=a.pcd?'1':'0';const isPcd=a.pcd==1;document.getElementById('fg-espec').style.display=isPcd?'flex':'none';document.getElementById('fg-apoio').style.display=isPcd?'flex':'none';document.getElementById('modal-editar').classList.add('open');}
async function salvarEdicao(){const id=document.getElementById('e-id').value;await api('PUT',`/alunos/${id}`,{nome:document.getElementById('e-nome').value.trim(),turma_nome:document.getElementById('e-turma').value.trim(),turno:document.getElementById('e-turno').value,data_nascimento:document.getElementById('e-nasc').value||null,cpf:document.getElementById('e-cpf').value.trim()||null,raca:document.getElementById('e-raca').value||null,sus:document.getElementById('e-sus').value.trim()||null,pcd:parseInt(document.getElementById('e-pcd').value),especificidade:document.getElementById('e-espec').value.trim()||null,apoio:document.getElementById('e-apoio').value.trim()||null,responsavel:document.getElementById('e-resp').value.trim()||null,telefone:document.getElementById('e-tel').value.trim()||null,endereco:document.getElementById('e-end').value.trim()||null,cidade:document.getElementById('e-cidade').value.trim()||null,cep:document.getElementById('e-cep').value.trim()||null,obs:document.getElementById('e-obs').value.trim()||null});toast('Dados salvos!');fecharModal('modal-editar');renderLista();loadStats();loadTurmasList();}
function renderTurmas(){const grid=document.getElementById('turmas-grid');grid.innerHTML=turmasCache.map((t,i)=>`<div class="turma-card" data-idx="${i}"><div class="turma-card-nome">${t.nome}</div><div class="turma-card-info">${t.turno||'—'}</div><div class="turma-card-num">${t.total}</div></div>`).join('');grid.querySelectorAll('.turma-card').forEach(card=>{card.addEventListener('click',function(){const t=turmasCache[parseInt(this.dataset.idx)];verTurma(t.nome,this);});});document.getElementById('turma-detalhe').style.display='none';}
async function verTurma(nome,card){document.querySelectorAll('.turma-card').forEach(c=>c.classList.remove('selected'));card.classList.add('selected');const alunos=await api('GET',`/alunos?turma=${encodeURIComponent(nome)}&ativo=1`);document.getElementById('turma-detalhe-titulo').textContent=`${nome} — ${alunos.length} aluno(s)`;document.getElementById('turma-detalhe-lista').innerHTML=alunos.map(a=>`<div class="aluno-row"><div class="avatar ${a.pcd?'pcd':''}">${iniciais(a.nome)}</div><div class="aluno-info"><div class="aluno-nome">${a.nome}</div><div class="aluno-det">${a.data_nascimento?'Nasc: '+fmtData(a.data_nascimento):''}${a.telefone?' · '+a.telefone:''}${a.pcd?' · PCD':''}</div></div>${a.pcd?'<span class="badge badge-pcd">PCD</span>':''}</div>`).join('')||'<div class="empty">Nenhum aluno ativo.</div>';const det=document.getElementById('turma-detalhe');det.style.display='block';det.scrollIntoView({behavior:'smooth',block:'nearest'});}
function initFreq(){const agora=new Date();['fq-mes','mf-mes'].forEach(id=>{const sel=document.getElementById(id);if(!sel)return;sel.innerHTML=MESES.map((m,i)=>`<option value="${i}"${i===agora.getMonth()?'selected':''}>${m}</option>`).join('');});const anos=[];for(let y=agora.getFullYear()-1;y<=agora.getFullYear()+1;y++)anos.push(y);['fq-ano','mf-ano'].forEach(id=>{const sel=document.getElementById(id);if(!sel)return;sel.innerHTML=anos.map(y=>`<option value="${y}"${y===agora.getFullYear()?'selected':''}>${y}</option>`).join('');});}
function diasUteis(ano,mes){const dias=[],total=new Date(ano,mes+1,0).getDate();for(let d=1;d<=total;d++){const dow=new Date(ano,mes,d).getDay();if(dow!==0&&dow!==6)dias.push(d);}return dias;}
async function renderFreqTurma(){const turma=document.getElementById('fq-turma').value;const mes=parseInt(document.getElementById('fq-mes').value);const ano=parseInt(document.getElementById('fq-ano').value);const el=document.getElementById('freq-container');if(!turma){el.innerHTML='<div class="card"><div class="empty"><div class="empty-icon">📅</div>Selecione uma turma.</div></div>';return;}const alunos=await api('GET',`/alunos?turma=${encodeURIComponent(turma)}&ativo=1`);if(!alunos.length){el.innerHTML='<div class="card"><div class="empty">Nenhum aluno ativo nesta turma.</div></div>';return;}const dias=diasUteis(ano,mes);const rows=await Promise.all(alunos.map(async a=>{const freq=await api('GET',`/frequencia/${a.id}?ano=${ano}&mes=${mes+1}`);const p=Object.values(freq).filter(v=>v===1).length;const f=Object.values(freq).filter(v=>v===0).length;const pct=dias.length>0?Math.round((p/dias.length)*100):0;const cor=pct>=75?'var(--green)':pct>=50?'var(--blue)':'var(--accent)';return `<div class="aluno-row"><div class="avatar ${a.pcd?'pcd':''}">${iniciais(a.nome)}</div><div class="aluno-info"><div class="aluno-nome">${a.nome}</div><div class="aluno-det"><span style="color:var(--green);font-weight:600">${p}P</span> · <span style="color:var(--accent);font-weight:600">${f}F</span> · ${dias.length-p-f} sem registro</div></div><div style="text-align:right;min-width:48px"><div style="font-family:'DM Serif Display',serif;font-size:20px;color:${cor}">${pct}%</div></div><button class="btn btn-edit" data-id="${a.id}" data-nome="${a.nome.replace(/"/g,'&quot;')}" onclick="abrirFreqAluno(parseInt(this.dataset.id),this.dataset.nome)">Ver dias</button></div>`;}));el.innerHTML=`<div class="card"><div class="card-title">${turma} · ${MESES[mes]} ${ano}</div>${rows.join('')}</div>`;}
async function abrirFreqAluno(id,nome){mfAlunoId=id;document.getElementById('mf-nome').textContent=nome;document.getElementById('mf-mes').value=document.getElementById('fq-mes').value;document.getElementById('mf-ano').value=document.getElementById('fq-ano').value;await renderModalFreq();document.getElementById('modal-freq').classList.add('open');}
async function renderModalFreq(){if(!mfAlunoId)return;const mes=parseInt(document.getElementById('mf-mes').value);const ano=parseInt(document.getElementById('mf-ano').value);const freq=await api('GET',`/frequencia/${mfAlunoId}?ano=${ano}&mes=${mes+1}`);const dias=diasUteis(ano,mes);const p=Object.values(freq).filter(v=>v===1).length;const f=Object.values(freq).filter(v=>v===0).length;const pct=dias.length>0?Math.round((p/dias.length)*100):0;const cor=pct>=75?'var(--green)':pct>=50?'var(--blue)':'var(--accent)';const grid=dias.map(d=>{const ds=`${ano}-${String(mes+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;const v=freq[ds];const bg=v===1?'var(--green-bg)':v===0?'var(--accent-bg)':'var(--paper2)';const lbl=v===1?'P':v===0?'F':'—';const clr=v===1?'var(--green)':v===0?'var(--accent)':'var(--ink3)';return `<div class="dia-btn" style="background:${bg}" onclick="toggleFreq(${mfAlunoId},'${ds}',${v===null||v===undefined?'null':v})"><div style="font-size:10px;color:var(--ink3)">${DSEM[new Date(ano,mes,d).getDay()]}</div><div style="font-size:15px;font-weight:700;color:${clr}">${lbl}</div><div style="font-size:11px;color:var(--ink3)">${d}</div></div>`;}).join('');document.getElementById('mf-conteudo').innerHTML=`<div style="display:flex;gap:8px;margin-bottom:1rem"><div style="flex:1;background:var(--green-bg);border-radius:var(--radius-sm);padding:10px;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:24px;color:var(--green)">${p}</div><div style="font-size:11px;color:var(--green);font-weight:600">Presenças</div></div><div style="flex:1;background:var(--accent-bg);border-radius:var(--radius-sm);padding:10px;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:24px;color:var(--accent)">${f}</div><div style="font-size:11px;color:var(--accent);font-weight:600">Faltas</div></div><div style="flex:1;background:var(--paper2);border-radius:var(--radius-sm);padding:10px;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:24px;color:${cor}">${pct}%</div><div style="font-size:11px;color:var(--ink3);font-weight:600">Frequência</div></div></div><div style="font-size:11px;color:var(--ink3);margin-bottom:8px">Clique num dia: — → P → F → —</div><div class="freq-grid">${grid}</div>`;}
async function toggleFreq(id,ds,atual){let novo;if(atual===null||atual===undefined||atual==='null')novo=1;else if(atual===1||atual==='1')novo=0;else novo=null;await api('POST','/frequencia',{aluno_id:id,data:ds,presente:novo});renderModalFreq();renderFreqTurma();}
async function renderHistorico(){const rows=await api('GET','/historico');const el=document.getElementById('hist-container');if(!rows.length){el.innerHTML='<div class="empty"><div class="empty-icon">📅</div>Sem movimentações.</div>';return;}el.innerHTML=rows.map(h=>`<div class="log-row"><div class="log-dot ${h.tipo==='ENTRADA'?'E':h.tipo==='SAÍDA'?'S':'ED'}">${h.tipo==='ENTRADA'?'E':h.tipo==='SAÍDA'?'S':'ED'}</div><div class="log-body"><div class="log-name">${h.aluno_nome||'—'}</div><div class="log-meta">${h.tipo} · ${h.descricao||''}</div></div><div class="log-date">${fmtData(h.data)}</div></div>`).join('');}
async function renderRelatorio(){const[stats,turmas]=await Promise.all([api('GET','/stats'),api('GET','/turmas')]);const agora=new Date();document.getElementById('rel-container').innerHTML=`<div class="card"><div class="card-title">${MESES[agora.getMonth()]} ${agora.getFullYear()}</div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:1.5rem"><div style="background:var(--paper2);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--ink)">${stats.total_ativos}</div><div style="font-size:11px;color:var(--ink3);font-weight:600;text-transform:uppercase">Alunos ativos</div></div><div style="background:var(--green-bg);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--green)">${stats.matutino}</div><div style="font-size:11px;color:var(--green);font-weight:600;text-transform:uppercase">Matutino</div></div><div style="background:var(--accent-bg);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--accent)">${stats.vespertino}</div><div style="font-size:11px;color:var(--accent);font-weight:600;text-transform:uppercase">Vespertino</div></div><div style="background:var(--purple-bg);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--purple)">${stats.total_pcd}</div><div style="font-size:11px;color:var(--purple);font-weight:600;text-transform:uppercase">Alunos PCD</div></div><div style="background:var(--paper2);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--ink)">${stats.entradas_mes}</div><div style="font-size:11px;color:var(--ink3);font-weight:600;text-transform:uppercase">Entradas no mês</div></div><div style="background:var(--paper2);border-radius:var(--radius-sm);padding:1rem;text-align:center"><div style="font-family:'DM Serif Display',serif;font-size:32px;color:var(--ink)">${stats.saidas_mes}</div><div style="font-size:11px;color:var(--ink3);font-weight:600;text-transform:uppercase">Saídas no mês</div></div></div><div class="sdiv">Alunos por turma</div>${turmas.map(t=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--paper3);font-size:13px"><span style="color:var(--ink2)">${t.nome} <span style="color:var(--ink3)">(${t.turno||'—'})</span></span><span style="font-weight:700;background:var(--paper2);padding:2px 10px;border-radius:99px;font-size:12px">${t.total} aluno${t.total!==1?'s':''}</span></div>`).join('')}</div>`;}
async function exportarExcel(){const alunos=await api('GET','/alunos?ativo=todos');if(!window.XLSX){toast('Biblioteca carregando...');return;}const wb=XLSX.utils.book_new();const data=[['Nome','Turma','Turno','Nascimento','CPF','Raça','SUS','PCD','Especificidade','Apoio','Responsável','Telefone','Endereço','Cidade','CEP','Status','Obs']];alunos.forEach(a=>data.push([a.nome,a.turma_nome||'',a.turno||a.turma_turno||'',fmtData(a.data_nascimento),a.cpf||'',a.raca||'',a.sus||'',a.pcd?'Sim':'Não',a.especificidade||'',a.apoio||'',a.responsavel||'',a.telefone||'',a.endereco||'',a.cidade||'',a.cep||'',a.ativo?'Ativo':'Inativo',a.obs||'']));const ws=XLSX.utils.aoa_to_sheet(data);ws['!cols']=[22,14,12,12,16,10,20,6,16,16,22,16,28,14,10,8,20].map(w=>({wch:w}));XLSX.utils.book_append_sheet(wb,ws,'Alunos');XLSX.writeFile(wb,`Alunos_CAIC_${new Date().toISOString().split('T')[0]}.xlsx`);toast('Excel exportado!');}
loadStats();loadTurmasList();
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
</body></html>"""

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
