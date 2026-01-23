from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):   #회원장부
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.String(50), unique=True, nullable=False) # 아이디 (중복금지)
    password = db.Column(db.String(200), nullable=False)           # 비밀번호 (암호화됨)
    nickname = db.Column(db.String(50), nullable=False)            # 닉네임
    email = db.Column(db.String(100), unique=True, nullable=False) # 이메일 (중복금지)

    def __repr__(self):
        return f'<User {self.userid}>'
    

class Study(db.Model):  #스터디 모집글 장부
    __tablename__ = 'study'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)   # 제목
    category = db.Column(db.String(50), nullable=False) # 카테고리
    member_count = db.Column(db.Integer, nullable=False)# 모집인원
    content = db.Column(db.Text, nullable=False)        # 상세내용
    date = db.Column(db.DateTime, default=datetime.utcnow) # 작성시간(자동)
    
    # 작성자 닉네임 저장
    writer = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Study {self.title}>'