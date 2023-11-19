from flask import Flask
#print("from flask import Flask")
from flask_sqlalchemy import SQLAlchemy
#print("from flask_sqlalchemy import SQLAlchemy")
from flask_migrate import Migrate
#print("from flask_migrate import Migrate")
from flask_login import LoginManager
#print("from flask_login import LoginManager")

app = Flask(__name__)
#print("app = Flask(__name__)")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
#print("app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'")
app.config['SECRET_KEY'] = 'your-secret-key-goes-here'
#print("app.config['SECRET_KEY'] = 'your-secret-key-goes-here'")

db = SQLAlchemy(app)
#print("db = SQLAlchemy(app)")
migrate = Migrate(app, db)
#print("migrate = Migrate(app, db)")

login_manager = LoginManager()
#print("login = LoginManager()")
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page'

from app import models
print("from app import models")
from app import routes #.routes import home, post, new_post
print("from app import routes #.routes import home, post, new_post")


login_manager.init_app(app)
#print("login.init_app(app)")
