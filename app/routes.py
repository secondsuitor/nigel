from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import app
from app.models import User
from app import db
from app.models import Post
from app.forms import LoginForm
import bleach # for sanitizing html

# bleach settings
allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br','blockquote','aside','del','template','sup']
allowed_attrs = {'*': ['class']}

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

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = bleach.clean(request.form['content'], tags=allowed_tags, attributes=allowed_attrs)
        post = Post(user_id=current_user.user_id, title=title, content=content)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('new_post.html')

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    if request.method == 'POST':
        title = request.form['title']
        content = bleach.clean(request.form['content'], tags=allowed_tags, attributes=allowed_attrs)
        post_id = request.form['post_id']
        post = Post.query.get_or_404(post_id)
        post.title = title
        post.content = content
        db.session.commit()
        return redirect(url_for('home'))
    post = Post.query.get_or_404(post_id)
    return render_template('edit_post.html', post=post)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Here we use a class of some kind to represent and validate our
    # client-side form data. For example, WTForms is a library that will
    # handle this for us, and we use a custom LoginForm to validate.
    form = LoginForm()
    flash('logging in')
    if form.validate_on_submit() or request.method == 'POST':
        user = User.query.filter_by(username=form.username.data).first()
        # Login and validate the user.
        # user should be an instance of your `User` class
        login_user(user)

        #next = request.args.get('next')
        # url_has_allowed_host_and_scheme should check if the url is safe
        # for redirects, meaning it matches the request host.
        # See Django's url_has_allowed_host_and_scheme for an example.
        #if not url_has_allowed_host_and_scheme(next, request.host):
        #    return flask.abort(400)

        #return redirect(next or url_for('index'))
        flash("Logged in as {}".format(current_user.username))
        return redirect(url_for('home'))
    flash("or not")
    return render_template('login.html', title="Login here", form=form)

@app.route('/logout')
@login_required  
def logout():
    flash("Logged out as {}".format(current_user.username))
    logout_user()
    return redirect(url_for('home'))

@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        #if not User().check_password_match(password):
        #    flash("Passwords don't match")
        #    return redirect(url_for('register_user'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("User registered")
        return redirect(url_for('home'))
    return render_template('register_user.html')


