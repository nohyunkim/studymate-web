from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

db = SQLAlchemy()

# 1. 한국 시간 구하는 함수 (UTC + 9시간)
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

# 2. [필수] 댓글 좋아요 연결 테이블 (이게 없으면 에러 납니다!)
comment_likes = db.Table('comment_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comment_id', db.Integer, db.ForeignKey('comment.id'), primary_key=True)
)

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<User {self.userid}>'

class Study(db.Model):
    __tablename__ = 'study'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    member_count = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now)
    writer = db.Column(db.String(50), nullable=False)

    # 스터디 좋아요(likers)는 삭제했습니다. (댓글 좋아요만 쓰기로 했으므로)

    def __repr__(self):
        return f'<Study {self.title}>'

class Comment(db.Model):
    __tablename__ = 'comment'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now)
    writer = db.Column(db.String(50), nullable=False)
    
    study_id = db.Column(db.Integer, db.ForeignKey('study.id'), nullable=False)
    study = db.relationship('Study', backref='comments') 

    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    
    # 대댓글 삭제 설정 (부모 지우면 자식도 삭제)
    replies = db.relationship('Comment', 
                                backref=db.backref('parent', remote_side=[id]), 
                                cascade='all, delete', 
                                lazy=True)

    # [중요] 이 줄이 있어야 'likers' 에러가 사라집니다!
    likers = db.relationship('User', secondary=comment_likes, backref=db.backref('liked_comments', lazy='dynamic'))

    def __repr__(self):
        return f'<Comment {self.content[:10]}...>'