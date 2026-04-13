from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)


comment_likes = db.Table(
    "comment_likes",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("comment_id", db.Integer, db.ForeignKey("comment.id"), primary_key=True),
)


class Enrollment(db.Model):
    __tablename__ = "enrollment"
    __table_args__ = (
        UniqueConstraint("user_id", "study_id", name="uq_enrollment_user_study"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    study_id = db.Column(db.Integer, db.ForeignKey("study.id"), nullable=False)
    status = db.Column(db.Integer, default=0, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now, nullable=False)

    user = db.relationship("User", back_populates="enrollments")
    study = db.relationship("Study", back_populates="enrollments")


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    bio = db.Column(db.String(100), nullable=True)

    studies = db.relationship("Study", back_populates="author", lazy=True)
    comments = db.relationship("Comment", back_populates="author", lazy=True)
    enrollments = db.relationship("Enrollment", back_populates="user", lazy=True)
    chat_messages = db.relationship("ChatMessage", back_populates="user", lazy=True)

    def __repr__(self):
        return f"<User {self.userid}>"


class Study(db.Model):
    __tablename__ = "study"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    member_count = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now, nullable=False)
    writer = db.Column(db.String(50), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    chat_link = db.Column(db.String(300), nullable=True)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)

    author = db.relationship("User", back_populates="studies")
    comments = db.relationship(
        "Comment",
        back_populates="study",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="Comment.date.asc()",
    )
    enrollments = db.relationship(
        "Enrollment",
        back_populates="study",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="Enrollment.date.desc()",
    )
    chat_messages = db.relationship(
        "ChatMessage",
        back_populates="study",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="ChatMessage.date.asc()",
    )

    def __repr__(self):
        return f"<Study {self.title}>"


class Comment(db.Model):
    __tablename__ = "comment"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now, nullable=False)
    writer = db.Column(db.String(50), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    study_id = db.Column(db.Integer, db.ForeignKey("study.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)

    author = db.relationship("User", back_populates="comments")
    study = db.relationship("Study", back_populates="comments")
    replies = db.relationship(
        "Comment",
        backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True,
        lazy=True,
        order_by="Comment.date.asc()",
    )
    likers = db.relationship(
        "User",
        secondary=comment_likes,
        backref=db.backref("liked_comments", lazy="dynamic"),
    )

    def __repr__(self):
        return f"<Comment {self.content[:10]}...>"


class ChatMessage(db.Model):
    __tablename__ = "chat_message"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=get_kst_now, nullable=False)
    study_id = db.Column(db.Integer, db.ForeignKey("study.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    study = db.relationship("Study", back_populates="chat_messages")
    user = db.relationship("User", back_populates="chat_messages")

    def __repr__(self):
        return f"<ChatMessage {self.study_id}:{self.user_id}>"
