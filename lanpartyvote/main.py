import functools, traceback, json, threading, sqlite3

import markdown, bleach, bleach

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, abort, jsonify, make_response, Response
)

class DB:

    def __init__(self):
        self.thread_local = threading.local()
        cur = self.get_conn().cursor()
        queries = """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username text UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                name text UNIQUE NOT NULL,
                disk_usage TEXT NOT NULL DEFAULT '',
                info TEXT NOT NULL DEFAULT '',
                players TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS votes (
                uid INTEGER,
                gameid INTEGER,
                value INTEGER,
                FOREIGN KEY(uid) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(gameid) REFERENCES games(id) ON DELETE CASCADE,
                UNIQUE(uid,gameid)
            );
        """
        for query in queries.split(';'):
            cur.execute(query)
        self.get_conn().commit()


    def get_conn(self):
        if not hasattr(self.thread_local, 'conn'):
            self.thread_local.conn = sqlite3.connect('db')
        self.thread_local.conn.cursor().execute('PRAGMA foreign_keys = ON')
        return self.thread_local.conn

db=DB()
bp = Blueprint('main', __name__, url_prefix='/')

@bp.route('/', methods=['GET'])
def index():
    with bp.open_resource('static/index.html') as file:
        return file.read()

@bp.route('/user/', methods=['GET'])
def list_users():
    cur = db.get_conn().cursor()
    cur.execute('SELECT id, username FROM users')
    return {"users":cur.fetchall()}

@bp.route('/user/', methods=['POST'])
def create_user():
    json = request.get_json()
    cur = db.get_conn().cursor()
    cur.execute('SELECT id FROM users WHERE username = ?', (json["username"],))
    result = cur.fetchone()
    if result is not None:
        return {"id":result[0]}
    try:
        cur.execute('INSERT INTO users (username) VALUES (?)', (json["username"],))
        db.get_conn().commit()
    except:
        db.get_conn().rollback()
    cur.execute('SELECT id FROM users WHERE username = ?', (json["username"],))
    return {"id":cur.fetchone()[0]}

@bp.route('/user/<uid>', methods=['POST'])
def change_username(uid):
    json = request.get_json()
    cur = db.get_conn().cursor()
    cur.execute('UPDATE users SET username = ? WHERE id = ?', (json["username"],uid))
    db.get_conn().commit()
    return {}

@bp.route('/user/<uid>', methods=['DELETE'])
def delete_user(uid):
    json = request.get_json()
    cur = db.get_conn().cursor()
    cur.execute('DELETE FROM users WHERE id = ?', (uid,))
    db.get_conn().commit()
    return {}


@bp.route('/game/', methods=['POST'])
def save_game():
    json = request.get_json()
    cur = db.get_conn().cursor()
    if len(json.get("name","")) == 0:
        abort(400)
    game_id = json.get("id", None)
    delete = json.get("delete", False)
    try:
        if game_id is None:
            cur.execute('INSERT INTO games (name,disk_usage,info,players) VALUES (?,?,?,?)', (json["name"],json.get("disk_usage",""),json.get("info",""),json.get("players")))
        elif delete:
            cur.execute('DELETE FROM games WHERE id = ?', (game_id,))
        else:
            cur.execute('UPDATE games SET name = ?, disk_usage = ?,info = ?,players=? WHERE id = ?', (json["name"],json.get("disk_usage",""),json.get("info",""),json.get("players",""), game_id))
        db.get_conn().commit()
    except sqlite3.IntegrityError:
        db.get_conn().rollback()
        abort(409)
    if delete:
        return {}
    else:
        cur.execute('SELECT id FROM games WHERE name = ?', (json["name"],))
        return {"id":cur.fetchone()[0]}

@bp.route('/game/', methods=['GET'])
def list_games(uid=None):
    cur = db.get_conn().cursor()
    if uid is None:
        uid = request.args.get('uid',None)
    if request.args.get('sort_order',None) == 'score':
        order_by = ' ORDER BY score DESC, name ASC'
    elif request.args.get('sort_order',None) == 'upvotes':
        order_by = ' ORDER BY upvotes DESC, name ASC'
    else:
        order_by = ' ORDER BY name ASC'
    cur.execute("""
        SELECT 
            (SELECT COUNT(*) FROM votes WHERE votes.gameid = games.id AND VALUE=1) AS upvotes,
            (SELECT COUNT(*) FROM votes WHERE votes.gameid = games.id AND VALUE=-1), 
            (SELECT TOTAL(value) FROM votes WHERE votes.gameid = games.id) AS score,
            (SELECT TOTAL(value) FROM votes WHERE votes.gameid = games.id AND votes.uid = ?),
            games.id,
            games.name,
            games.disk_usage,
            games.players
        FROM games LEFT OUTER JOIN votes ON votes.gameid == games.id 
        GROUP BY games.id
    """ + order_by, (uid,) )
    games = cur.fetchall()
    cur.execute("SELECT username FROM users")
    users = []
    for user in cur.fetchall():
        users.append(user[0])
    return {"games":games, "users":users}

@bp.route('/game/<game_id>', methods=['GET'])
def get_game(game_id):
    cur = db.get_conn().cursor()
    cur.execute('SELECT name,disk_usage,info,players FROM games WHERE id = ?', (game_id,))
    row = cur.fetchone()
    response = {
        "name":row[0], 
        "disk_usage":row[1], 
        "info":row[2], 
        "info_html":markdown.markdown(bleach.clean(row[2])), 
        "id":game_id, 
        "upvotes":[], 
        "downvotes":[],
        "players":row[3]
    }
    cur.execute('SELECT users.username,value FROM votes INNER JOIN users ON users.id == uid WHERE gameid = ?', (game_id,))
    for row in cur.fetchall():
        if row[1] == 1:
            response["upvotes"] += [row[0]]
        elif row[1] == -1:
            response["downvotes"] += [row[0]]
    return response
    
@bp.route('/vote/', methods=['POST'])
def vote():
    json = request.get_json()
    cur = db.get_conn().cursor()
    try:
        uid = int(json["uid"])
        cur.execute('SELECT username FROM users WHERE id = ?', (uid,))
        if cur.fetchone()[0] != json["username"]:
            abort(403)
    except:
        abort(403)
    gameid = int(json["gameid"])
    value = int(json["value"])
    try:
        cur.execute('DELETE FROM votes WHERE uid = ? AND gameid = ?', (uid, gameid))
        if value == 1 or value == -1:
            cur.execute('INSERT INTO votes (uid,gameid,value) VALUES (?,?,?)', (uid,gameid,value))
        db.get_conn().commit()
    except:
        db.get_conn().rollback()
    return list_games(uid)
