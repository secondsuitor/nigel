from flask import render_template, request, redirect, url_for
from app import app, db
from app.models import Post, User

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
        #password = request.form['password']
        #user = User.query.filter_by(username=username).first()
        #if user:
        #    user.logged_in = True
        #    db.session.commit()
        #    return redirect(url_for('home'))
        #else:
        #    return redirect(url_for('login'))
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/logout')  
def logout():
    #user = User.query.filter_by(logged_in=True).first()
    #if user:
    #    user.logged_in = False
    #    db.session.commit()
    return redirect(url_for('home'))

@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password2 = request.form['password2']
        email = request.form['email']
        user = User(username=username, password=password, password2=password2, email=email)
        #db.session.add(user)
        #db.session.commit()
        return redirect(url_for('home'))
    return render_template('register.html')
