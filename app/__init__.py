from flask import Flask
from models import db
from routes import home, post, new_post

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db.init_app(app)

app.route('/')(home)
app.route('/post/<int:id>')(post)
app.route('/new_post', methods=['GET', 'POST'])(new_post)