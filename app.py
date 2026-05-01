#!/usr/bin/env python3

import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g
import psycopg2
import psycopg2.extras

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# ── DATABASE ─────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL)
    return g.db

def query(sql, params=None, one=False):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = sql.replace('?', '%s')
    cur.execute(sql, params or [])

    if sql.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        cur.close()
        return rows[0] if one and rows else rows

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
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id),
        turno TEXT,
        telefone TEXT,
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

# ── ROTAS ─────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/alunos', methods=['GET','POST'])
def alunos():
    if request.method == 'GET':
        rows = query("""
            SELECT a.*, t.nome as turma_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id=t.id
            ORDER BY a.nome
        """)
        return jsonify(rows)

    data = request.json

    turma_id = None
    if data.get('turma_nome'):
        t = query("SELECT id FROM turmas WHERE nome=?", [data['turma_nome']], one=True)
        if t:
            turma_id = t['id']
        else:
            query("INSERT INTO turmas (nome) VALUES (?)", [data['turma_nome']])
            t = query("SELECT id FROM turmas WHERE nome=?", [data['turma_nome']], one=True)
            turma_id = t['id']

    query("""
    INSERT INTO alunos (nome, turma_id, turno, telefone)
    VALUES (?, ?, ?, ?)
    """, [data['nome'], turma_id, data.get('turno'), data.get('telefone')])

    return jsonify({'ok': True})

# ── START ─────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)