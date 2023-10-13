from flask import Flask
from app.models import db
from app.routes import home, post, new_post
from flask_migrate import Migrate, MigrateCommand

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db.init_app(app)

migrate = Migrate(app, db)

app.cli.add_command(MigrateCommand)

app.route('/')(home)
app.route('/post/<int:id>')(post)
app.route('/new_post', methods=['GET', 'POST'])(new_post)