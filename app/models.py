from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login_manager


class Post(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    post_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)

class User(UserMixin, db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    #is_authenricated = db.Column(db.Boolean, default=False)
    #is_active = db.Column(db.Boolean, default=True)
    #is_anonymous = db.Column(db.Boolean, default=False)
    
    def __init__(self, user_id):
        self.user_id = user_id

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def get(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))