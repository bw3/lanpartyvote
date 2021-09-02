import os,json,urllib,uuid,sqlite3

from flask import (Flask, render_template, request, abort, redirect)

import lanpartyvote.main

def create_app():
    app = Flask(__name__)

    app.register_blueprint(lanpartyvote.main.bp)

    return app

