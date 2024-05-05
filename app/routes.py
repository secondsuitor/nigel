from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import app
from app.models import User
from app import db
from app.models import Post, Footnote, Source
from app.forms import LoginForm, PostForm
import bleach # for sanitizing html

# bleach settings
allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br','blockquote','aside','del','template','sup']
allowed_attrs = {'*': ['class']}

@app.route('/')
def home():
    posts = Post.query.all()
    title = "Home"
    return render_template('home.html', title=title, posts=posts)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, user_id=current_user.user_id)
        post.content = bleach.clean(post.content, tags=allowed_tags, attributes=allowed_attrs)
        db.session.add(post)
        db.session.commit()
        if post.content.find('<sup>'):
            print(post.content.count('<sup>'), 'superscript(s) found')
            return redirect(url_for('edit_post', post_id=post.post_id))
        return redirect(url_for('home'))
    return render_template('new_post.html', title='New Post', form=form)

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    footnotes = Footnote.query.filter_by(post_id=post_id).all()
    if post.user_id != current_user.user_id:
        print('oops')
        #abort(403)
    form = PostForm()
    print('Makiing a form')
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = bleach.clean(form.content.data, tags=allowed_tags, attributes=allowed_attrs)
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('post', post_id=post.post_id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('edit_post.html', title='Edit Post', form=form)

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


