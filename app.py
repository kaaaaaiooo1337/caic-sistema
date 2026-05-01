#!/usr/bin/env python3
"""
Sistema CAIC Darcy Ribeiro
Deploy: Render.com
"""

import os, re
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, g
import psycopg2
import psycopg2.extras

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# ── DATABASE ─────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL)
    return g.db

def query(sql, params=None, fetch=False, one=False):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = sql.replace('?', '%s')
    cur.execute(sql, params or [])

    if sql.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        cur.close()
        if one:
            return rows[0] if rows else None
        return rows

    db.commit()
    cur.close()
    return None

# ── INIT DB ─────────────────────────────────────────

def init_db():
    query("""
    CREATE TABLE IF NOT EXISTS turmas (
        id SERIAL PRIMARY KEY,
        nome TEXT UNIQUE NOT NULL,
        turno TEXT
    );
    """)

    query("""
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
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    query("""
    CREATE TABLE IF NOT EXISTS frequencias (
        id SERIAL PRIMARY KEY,
        aluno_id INTEGER REFERENCES alunos(id),
        data TEXT NOT NULL,
        presente INTEGER,
        UNIQUE(aluno_id, data)
    );
    """)

    query("""
    CREATE TABLE IF NOT EXISTS historico (
        id SERIAL PRIMARY KEY,
        aluno_id INTEGER REFERENCES alunos(id),
        tipo TEXT NOT NULL,
        descricao TEXT,
        usuario TEXT,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

# ── ROTAS ─────────────────────────────────────────

@app.route('/api/stats')
def stats():
    agora = datetime.now()
    mes_ini = f"{agora.year}-{agora.month:02d}-01"
    mes_fim = f"{agora.year}-{agora.month:02d}-31"

    return jsonify({
        'total_ativos': query("SELECT COUNT(*) as c FROM alunos WHERE ativo=1", fetch=True)[0]['c'],
        'total_pcd': query("SELECT COUNT(*) as c FROM alunos WHERE ativo=1 AND pcd=1", fetch=True)[0]['c'],
        'total_turmas': query("SELECT COUNT(*) as c FROM turmas", fetch=True)[0]['c'],
        'entradas_mes': query("SELECT COUNT(*) as c FROM historico WHERE tipo='ENTRADA' AND data>=? AND data<=?", [mes_ini, mes_fim], True)[0]['c'],
        'saidas_mes': query("SELECT COUNT(*) as c FROM historico WHERE tipo='SAÍDA' AND data>=? AND data<=?", [mes_ini, mes_fim], True)[0]['c'],
        'matutino': query("SELECT COUNT(*) as c FROM alunos WHERE ativo=1 AND turno ILIKE '%MAT%'", fetch=True)[0]['c'],
        'vespertino': query("SELECT COUNT(*) as c FROM alunos WHERE ativo=1 AND turno ILIKE '%VES%'", fetch=True)[0]['c'],
    })

@app.route('/api/turmas')
def turmas():
    rows = query("""
        SELECT t.*, COUNT(a.id) as total
        FROM turmas t LEFT JOIN alunos a ON a.turma_id=t.id AND a.ativo=1
        GROUP BY t.id ORDER BY t.nome
    """, fetch=True)
    return jsonify(rows)

@app.route('/api/alunos', methods=['GET','POST'])
def alunos():
    if request.method == 'GET':
        rows = query("""
            SELECT a.*, t.nome as turma_nome, t.turno as turma_turno
            FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id
            ORDER BY t.nome, a.nome
        """, fetch=True)
        return jsonify(rows)

    data = request.json

    turma_id = None
    if data.get('turma_nome'):
        t = query("SELECT id FROM turmas WHERE nome=?", [data['turma_nome']], True)
        if t:
            turma_id = t['id']
        else:
            query("INSERT INTO turmas (nome, turno) VALUES (?,?)", [data['turma_nome'], data.get('turno','')])
            t = query("SELECT id FROM turmas WHERE nome=?", [data['turma_nome']], True)
            turma_id = t['id']

    query("""
    INSERT INTO alunos (nome, turma_id, turno, telefone)
    VALUES (?, ?, ?, ?)
    """, [data['nome'], turma_id, data.get('turno'), data.get('telefone')])

    return jsonify({'ok': True})

@app.route('/api/frequencia', methods=['POST'])
def set_freq():
    d = request.json
    query("""
        INSERT INTO frequencias (aluno_id, data, presente)
        VALUES (?, ?, ?)
        ON CONFLICT(aluno_id, data)
        DO UPDATE SET presente=EXCLUDED.presente
    """, [d['aluno_id'], d['data'], d['presente']])
    return jsonify({'ok': True})

@app.route('/api/historico')
def historico():
    rows = query("""
        SELECT h.*, a.nome as aluno_nome FROM historico h
        LEFT JOIN alunos a ON h.aluno_id=a.id
        ORDER BY h.data DESC LIMIT 100
    """, fetch=True)
    return jsonify(rows)

# ── START ─────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)