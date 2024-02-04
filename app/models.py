from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login_manager


class Post(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    post_id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)

    # Relationship to get the parent post
    parent = db.relationship('Post', remote_side=[post_id], backref='children')

class User(UserMixin, db.Model):
    user_id = db.Column(db.Integer, primary_key=True, unique=True, autoincrement=True)
    username = db.Column(db.String(100), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    #is_authenricated = db.Column(db.Boolean, default=False)
    #is_active = db.Column(db.Boolean, default=True)
    #is_anonymous = db.Column(db.Boolean, default=False)
    
    #def __init__(self, user_id):
    #    self.user_id = user_id

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
class Footnote(db.Model):
    footnote_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey('source.source_id'), nullable=True)  # new source_id field

    # Relationship to get the associated source
    source = db.relationship('Source', backref='footnotes')


class Source(db.Model):
    source_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    page = db.Column(db.Integer, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    publisher = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))