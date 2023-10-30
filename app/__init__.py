from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SECRET_KEY'] = 'your-secret-key-goes-here'

db = SQLAlchemy(app)
migrate = Migrate(app, db)


from app import models
from app.routes import home, post, new_post


