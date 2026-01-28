from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

db = SQLAlchemy()

# 1. 한국 시간 구하는 함수 (UTC + 9시간)
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

# 2. 댓글 좋아요 연결 테이블
comment_likes = db.Table(
    'comment_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comment_id', db.Integer, db.ForeignKey('comment.id'), primary_key=True)
)

# 3. 신청 내역 관리 (누가, 어떤 스터디에, 어떤 상태인지)
class Enrollment(db.Model):
    __tablename__ = 'enrollment'

    id = db.Column(db.Integer, primary_key=True)

    # 누가 신청했나
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='enrollments')

    # 어떤 스터디에 신청했나
    study_id = db.Column(db.Integer, db.ForeignKey('study.id'), nullable=False)
    study = db.relationship('Study', backref='enrollments')

    # 상태 (0: 대기중, 1: 수락됨, 2: 거절됨)
    status = db.Column(db.Integer, default=0)

    # 신청 시간
    date = db.Column(db.DateTime, default=get_kst_now)

# 4. 회원 정보 (User)
class User(db.Model):   # 회원장부
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.String(50), unique=True, nullable=False)  # 아이디
    password = db.Column(db.String(200), nullable=False)            # 비밀번호
    nickname = db.Column(db.String(50), nullable=False)             # 닉네임
    email = db.Column(db.String(100), unique=True, nullable=False)  # 이메일

    # 한줄 소개 추가! (최대 100자, 비어있어도 됨 nullable=True)
    bio = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f'<User {self.userid}>'

# 5. 스터디 모집글 장부
class Study(db.Model):
    __tablename__ = 'study'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    member_count = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now)
    writer = db.Column(db.String(50), nullable=False)
    chat_link = db.Column(db.String(300), nullable=True)

    # 모집 마감 여부 (False: 모집중, True: 마감)
    is_closed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Study {self.title}>'

# 6. 댓글 장부
class Comment(db.Model):
    __tablename__ = 'comment'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now)
    writer = db.Column(db.String(50), nullable=False)

    study_id = db.Column(db.Integer, db.ForeignKey('study.id'), nullable=False)
    study = db.relationship('Study', backref='comments')

    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)

    replies = db.relationship(
        'Comment',
        backref=db.backref('parent', remote_side=[id]),
        cascade='all, delete',
        lazy=True
    )

    likers = db.relationship(
        'User',
        secondary=comment_likes,
        backref=db.backref('liked_comments', lazy='dynamic')
    )

    def __repr__(self):
        return f'<Comment {self.content[:10]}...>'