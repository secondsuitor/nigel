from flask import render_template, request
#from app import app
#from app import db
from app.models import Post

def home():
    #posts = Post.query.all()
    # place holder for real posts
    post1 = Post(title='First Post', content='Content of the first post')
    post2 = Post(title='Second Post', content='Content of the second post')
    post3 = Post(title='Third Post', content='Content of the third post')
    posts = [post1, post2, post3]
    title = "Home"
    return render_template('home.html', title=title, posts=posts)

def post(id):
    post = Post.query.get_or_404(id)
    return render_template('post.html', post=post)

def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post = Post(title=title, content=content)
        #db.session.add(post)
        #db.session.commit()
    return render_template('new_post.html')