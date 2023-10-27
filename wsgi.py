from app import app as application

from app import db
#from app.routes import home, post, new_post

if __name__ == '__main__':
    application.run(name='application')