from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import app
from app.models import User
from app import db
from app.models import Post

@app.route('/')
def home():
    posts = Post.query.all()
    #place holder for real posts
    #post1 = Post(title='First Post', content='Content of the first post')
    #post2 = Post(title='Second Post', content='Content of the second post')
    #post3 = Post(title='Third Post', content='Content of the third post')
    #posts = [post1, post2, post3]
    title = "Home"
    return render_template('home.html', title=title, posts=posts)

@app.route('/post/<int:id>')
def post(id):
    post = Post.query.get_or_404(id)
    return render_template('post.html', post=post)

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post = Post(title=title, content=content)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('new_post.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
           if user.check_password(password):
                login_user(user)
                flash("Logged in as {}".format(current_user.username))
                return redirect(url_for('home'))
           else:
                flash("Incorrect password")
                return redirect(url_for('login'))
        else:
            flash("User not found")
            return redirect(url_for('login'))   
    return render_template('login.html')

@app.route('/logout')  
def logout():
    #logout_user()
    flash("Logged out")
    return redirect(url_for('home'))

@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password2 = request.form['password2']
        email = request.form['email']

        if not User().check_password_match(password, password2):
            flash("Passwords don't match")
            return redirect(url_for('register_user'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("User registered")
        return redirect(url_for('home'))
    return render_template('register_user.html')
