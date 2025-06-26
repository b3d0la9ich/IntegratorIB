from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    projects = db.relationship('Project', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_name = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    industry = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  
    user = db.relationship('User', backref='clients')          

    projects = db.relationship('Project', backref='client', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), default='активный')
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)

    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    services = db.relationship('Service', backref='project', lazy=True)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_type = db.Column(db.String(100))
    status = db.Column(db.String(50), default='в процессе')
    execution_date = db.Column(db.Date)

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
