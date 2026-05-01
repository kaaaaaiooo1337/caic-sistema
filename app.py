#!/usr/bin/env python3

import os
from flask import Flask, request, jsonify, render_template, g
import psycopg2
import psycopg2.extras

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

# ── DATABASE ─────────────────────────

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(
            DATABASE_URL,
            sslmode='require'  # 🔥 CORREÇÃO AQUI
        )
    return g.db

def query(sql, params=None, one=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        sql = sql.replace('?', '%s')
        cur.execute(sql, params or [])

        if cur.description:
            rows = cur.fetchall()
            return rows[0] if one and rows else rows
        else:
            conn.commit()
            return None

    except Exception as e:
        print("ERRO SQL:", e)
        return None

    finally:
        cur.close()

# ── INIT DB ─────────────────────────

def init_db():
    query("""
    CREATE TABLE IF NOT EXISTS turmas (
        id SERIAL PRIMARY KEY,
        nome TEXT UNIQUE NOT NULL
    );
    """)

    query("""
    CREATE TABLE IF NOT EXISTS alunos (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id),
        telefone TEXT
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

# ── ROTAS ─────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/debug')
def debug():
    return str(DATABASE_URL)

@app.route('/api/alunos', methods=['GET','POST'])
def alunos():
    if request.method == 'GET':
        return jsonify(query("""
            SELECT a.*, t.nome as turma_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id=t.id
            ORDER BY a.nome
        """) or [])

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
    INSERT INTO alunos (nome, turma_id, telefone)
    VALUES (?, ?, ?)
    """, [data['nome'], turma_id, data.get('telefone')])

    return jsonify({'ok': True})

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def deletar_aluno(id):
    query("DELETE FROM alunos WHERE id=?", [id])
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

# ── START ─────────────────────────

if __name__ == '__main__':
    init_db()
    app.run()