from flask import render_template, request
from app.models import db, Post

def home():
    #posts = Post.query.all()
    # place holder for real posts
    posts = ['Hi this is fake', 'This is also fake', 'This is fake too']
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
        db.session.add(post)
        db.session.commit()
    return render_template('new_post.html')