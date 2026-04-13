import os
import queue
import secrets
from collections import defaultdict
from json import dumps
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from sqlalchemy import and_, inspect, or_, text
from sqlalchemy.sql.expression import func
from werkzeug.security import check_password_hash, generate_password_hash

from models import ChatMessage, Comment, Enrollment, Study, User, db

STUDY_CATEGORIES = [
    ("취업 / 커리어", ["취업 준비", "자소서 / 포트폴리오", "면접 준비", "공기업 / 공시"]),
    (
        "자격증",
        [
            "컴퓨터활용능력",
            "한국사능력검정",
            "토익 / 토플",
            "한국어능력시험",
            "정보처리기사",
            "기타 자격증",
        ],
    ),
    (
        "어학 / 외국어",
        ["영어 회화", "토익 / 토플", "오픽 / 스피킹", "일본어", "중국어", "기타 외국어"],
    ),
    ("습관 / 자기관리", ["공부 인증", "루틴 관리", "아침형 인간", "운동 인증", "식단 관리"]),
    ("IT / 개발", ["웹 개발", "앱 개발", "알고리즘 / 코딩테스트", "데이터 분석", "AI / 머신러닝", "보안 / 해킹"]),
    ("취미 / 기타", ["독서", "헬스 / 운동", "러닝 / 마라톤", "요가 / 스트레칭", "악기 연습", "그림 / 드로잉", "사진 / 영상", "재테크 공부", "기타"]),
]

CATEGORY_VALUES = {value for _, values in STUDY_CATEGORIES for value in values}

HOME_SHOWCASE_VISUALS = [
    {
        "image": "images/hero-group-photo.svg",
        "label": "focus room",
        "tone": "light",
        "summary": "함께 공부하는 장면이 먼저 보이는 메인 썸네일",
    },
    {
        "image": "images/hero-study-scene.svg",
        "label": "study board",
        "tone": "dark",
        "summary": "탐색, 모집, 합류 흐름이 화면 안에 자연스럽게 보이는 구도",
    },
    {
        "image": "images/feature-flow.svg",
        "label": "crew flow",
        "tone": "light",
        "summary": "신청과 승인 과정이 한눈에 들어오는 카드형 레이아웃",
    },
    {
        "image": "images/feature-match.svg",
        "label": "curated find",
        "tone": "sage",
        "summary": "카테고리와 필터를 중심으로 스터디를 고르는 탐색 화면",
    },
]

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "STUDYMATE_DB_URI",
    "sqlite:///" + os.path.join(INSTANCE_DIR, "database.db"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db.init_app(app)
chat_subscribers = defaultdict(list)


def get_current_user():
    if hasattr(g, "current_user"):
        return g.current_user

    session_userid = session.get("user_id")
    user = User.query.filter_by(userid=session_userid).first() if session_userid else None

    if session_userid and user is None:
        session.clear()

    g.current_user = user
    return user


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def normalize_text(value):
    return " ".join((value or "").strip().split())


def normalize_optional_text(value):
    value = (value or "").strip()
    return value or None


def normalize_chat_link(value):
    link = normalize_optional_text(value)
    if not link:
        return None

    parsed = urlparse(link)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("채팅방 링크는 http 또는 https 주소만 사용할 수 있습니다.")

    return link


def parse_member_count(value):
    try:
        member_count = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("모집 인원은 숫자로 입력해주세요.") from error

    if member_count < 1:
        raise ValueError("모집 인원은 1명 이상이어야 합니다.")

    return member_count


def validate_category(category):
    normalized = normalize_text(category)
    if normalized not in CATEGORY_VALUES:
        raise ValueError("올바른 카테고리를 선택해주세요.")
    return normalized


def build_study_payload(form):
    title = normalize_text(form.get("title"))
    content = (form.get("content") or "").strip()

    if not title:
        raise ValueError("스터디 제목을 입력해주세요.")
    if not content:
        raise ValueError("상세 내용을 입력해주세요.")

    return {
        "title": title,
        "category": validate_category(form.get("category")),
        "member_count": parse_member_count(form.get("member_count")),
        "content": content,
        "chat_link": normalize_chat_link(form.get("chat_link")),
    }


def is_study_owner(study, user):
    return bool(user) and (
        study.author_id == user.id or (study.author_id is None and study.writer == user.nickname)
    )


def is_comment_owner(comment, user):
    return bool(user) and (
        comment.author_id == user.id or (comment.author_id is None and comment.writer == user.nickname)
    )


def get_author_studies_query(user):
    return Study.query.filter(
        or_(
            Study.author_id == user.id,
            and_(Study.author_id.is_(None), Study.writer == user.nickname),
        )
    )


def approved_member_count(study):
    return sum(1 for enrollment in study.enrollments if enrollment.status == 1)


def sync_closed_state(study):
    if approved_member_count(study) >= study.member_count:
        study.is_closed = True


def serialize_chat_message(message):
    return {
        "id": message.id,
        "content": message.content,
        "date": message.date.strftime("%m-%d %H:%M"),
        "writer": message.user.nickname,
        "user_id": message.user_id,
    }


def broadcast_chat_message(study_id, payload):
    stale_queues = []
    for subscriber in chat_subscribers.get(study_id, []):
        try:
            subscriber.put_nowait(payload)
        except Exception:
            stale_queues.append(subscriber)

    if stale_queues:
        chat_subscribers[study_id] = [
            subscriber for subscriber in chat_subscribers[study_id] if subscriber not in stale_queues
        ]


def can_access_study_chat(study, user):
    if not user:
        return False
    if is_study_owner(study, user):
        return True

    enrollment = Enrollment.query.filter_by(user_id=user.id, study_id=study.id, status=1).first()
    return enrollment is not None


def get_accessible_chat_studies(user):
    if not user:
        return []

    owned_studies = get_author_studies_query(user).all()
    approved_enrollments = (
        Enrollment.query.filter_by(user_id=user.id, status=1)
        .order_by(Enrollment.date.desc())
        .all()
    )

    studies_by_id = {study.id: study for study in owned_studies}
    for enrollment in approved_enrollments:
        studies_by_id.setdefault(enrollment.study.id, enrollment.study)

    studies = list(studies_by_id.values())
    studies.sort(
        key=lambda study: study.chat_messages[-1].date if study.chat_messages else study.date,
        reverse=True,
    )
    return studies


def get_or_404(model, object_id):
    record = db.session.get(model, object_id)
    if record is None:
        abort(404)
    return record


def create_unique_index_if_safe(index_name, table_name, column_name):
    duplicate_check = db.session.execute(
        text(
            f"""
            SELECT {column_name}, COUNT(*)
            FROM {table_name}
            GROUP BY {column_name}
            HAVING COUNT(*) > 1
            """
        )
    ).fetchone()

    if duplicate_check:
        return

    db.session.execute(
        text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})")
    )


def create_compound_unique_index_if_safe(index_name, table_name, columns):
    duplicate_check = db.session.execute(
        text(
            f"""
            SELECT {", ".join(columns)}, COUNT(*)
            FROM {table_name}
            GROUP BY {", ".join(columns)}
            HAVING COUNT(*) > 1
            """
        )
    ).fetchone()

    if duplicate_check:
        return

    db.session.execute(
        text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({', '.join(columns)})")
    )


def run_schema_migrations():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    if "study" in table_names:
        study_columns = {column["name"] for column in inspector.get_columns("study")}
        if "author_id" not in study_columns:
            db.session.execute(text("ALTER TABLE study ADD COLUMN author_id INTEGER"))

    if "comment" in table_names:
        comment_columns = {column["name"] for column in inspector.get_columns("comment")}
        if "author_id" not in comment_columns:
            db.session.execute(text("ALTER TABLE comment ADD COLUMN author_id INTEGER"))

    db.session.commit()

    if {"study", "user"} <= table_names:
        db.session.execute(
            text(
                """
                UPDATE study
                SET author_id = (
                    SELECT user.id
                    FROM user
                    WHERE user.nickname = study.writer
                )
                WHERE author_id IS NULL
                """
            )
        )

    if {"comment", "user"} <= table_names:
        db.session.execute(
            text(
                """
                UPDATE comment
                SET author_id = (
                    SELECT user.id
                    FROM user
                    WHERE user.nickname = comment.writer
                )
                WHERE author_id IS NULL
                """
            )
        )

    create_unique_index_if_safe("ix_user_nickname_unique", "user", "nickname")
    create_compound_unique_index_if_safe(
        "ix_enrollment_user_study_unique", "enrollment", ["user_id", "study_id"]
    )
    db.session.commit()


with app.app_context():
    db.create_all()
    run_schema_migrations()


@app.before_request
def load_user_and_protect_forms():
    get_current_user()

    if request.method == "POST":
        session_token = session.get("_csrf_token")
        submitted_token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")

        if not session_token or session_token != submitted_token:
            abort(400, description="잘못된 요청입니다.")


@app.context_processor
def inject_template_globals():
    user = get_current_user()
    return {
        "csrf_token": get_csrf_token(),
        "current_user": user,
        "user_nickname": user.nickname if user else None,
        "study_categories": STUDY_CATEGORIES,
    }


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/")
def home():
    random_studies = Study.query.order_by(func.random()).limit(4).all()
    return render_template(
        "index.html",
        random_studies=random_studies,
        showcase_visuals=HOME_SHOWCASE_VISUALS,
    )


@app.route("/index.html")
def index():
    return redirect(url_for("home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = normalize_text(request.form.get("userid"))
        password = request.form.get("password") or ""
        user = User.query.filter_by(userid=userid).first()

        if not user or not check_password_hash(user.password, password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user.userid
        session["user_nickname"] = user.nickname
        session["_csrf_token"] = secrets.token_hex(32)
        flash("로그인되었습니다.", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("home"))


@app.route("/check-userid")
def check_userid():
    userid = normalize_text(request.args.get("userid"))

    if not userid:
        return jsonify({"available": False, "message": "아이디를 입력하세요."})

    exists = User.query.filter_by(userid=userid).first() is not None
    return jsonify(
        {
            "available": not exists,
            "message": "이미 사용 중인 아이디입니다." if exists else "사용 가능한 아이디입니다.",
        }
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        userid = normalize_text(request.form.get("userid"))
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""
        nickname = normalize_text(request.form.get("nickname"))
        email = normalize_text(request.form.get("email")).lower()

        if len(userid) < 4:
            flash("아이디는 4자 이상으로 입력해주세요.", "error")
            return redirect(url_for("signup"))
        if len(password) < 8:
            flash("비밀번호는 8자 이상이어야 합니다.", "error")
            return redirect(url_for("signup"))
        if password != password_confirm:
            flash("비밀번호 확인이 일치하지 않습니다.", "error")
            return redirect(url_for("signup"))
        if not nickname:
            flash("닉네임을 입력해주세요.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(userid=userid).first():
            flash("이미 존재하는 아이디입니다.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("이미 가입된 이메일입니다.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(nickname=nickname).first():
            flash("이미 사용 중인 닉네임입니다.", "error")
            return redirect(url_for("signup"))

        new_user = User(
            userid=userid,
            password=generate_password_hash(password),
            nickname=nickname,
            email=email,
        )
        db.session.add(new_user)
        db.session.commit()

        flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/study")
def study():
    page = request.args.get("page", 1, type=int)
    keyword = normalize_text(request.args.get("keyword", ""))
    category = normalize_text(request.args.get("category", ""))

    query = Study.query.order_by(Study.date.desc())

    if keyword:
        query = query.filter(or_(Study.title.contains(keyword), Study.content.contains(keyword)))

    if category and category in CATEGORY_VALUES:
        query = query.filter(Study.category == category)
    else:
        category = ""

    pagination = query.paginate(page=page, per_page=9)
    return render_template("study.html", pagination=pagination, keyword=keyword, category=category)


@app.route("/study/write", methods=["GET", "POST"])
def studywrite():
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            payload = build_study_payload(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("studywrite"))

        new_study = Study(writer=user.nickname, author_id=user.id, **payload)
        db.session.add(new_study)
        db.session.commit()

        flash("스터디 모집글이 등록되었습니다.", "success")
        return redirect(url_for("study_detail", study_id=new_study.id))

    return render_template("studywrite.html")


@app.route("/study/<int:study_id>")
def study_detail(study_id):
    study = get_or_404(Study, study_id)
    user = get_current_user()
    enrollment = None
    if user:
        enrollment = Enrollment.query.filter_by(user_id=user.id, study_id=study.id).first()

    root_comments = [comment for comment in study.comments if comment.parent_id is None]
    root_comments.sort(key=lambda comment: comment.date)

    return render_template(
        "study_detail.html",
        study=study,
        enrollment=enrollment,
        approved_count=approved_member_count(study),
        root_comments=root_comments,
        is_owner=is_study_owner(study, user),
        can_access_chat=can_access_study_chat(study, user),
    )


@app.route("/study/<int:study_id>/delete", methods=["POST"])
def study_delete(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)
    if not is_study_owner(study, user):
        flash("삭제 권한이 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    db.session.delete(study)
    db.session.commit()
    flash("스터디가 삭제되었습니다.", "success")
    return redirect(url_for("study"))


@app.route("/study/<int:study_id>/edit", methods=["GET", "POST"])
def study_edit(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)
    if not is_study_owner(study, user):
        flash("수정 권한이 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    if request.method == "POST":
        try:
            payload = build_study_payload(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("study_edit", study_id=study_id))

        study.title = payload["title"]
        study.category = payload["category"]
        study.member_count = payload["member_count"]
        study.content = payload["content"]
        study.chat_link = payload["chat_link"]
        study.writer = user.nickname
        study.author_id = user.id
        sync_closed_state(study)

        db.session.commit()
        flash("스터디가 수정되었습니다.", "success")
        return redirect(url_for("study_detail", study_id=study.id))

    return render_template("study_edit.html", study=study)


@app.route("/myposts")
def my_posts():
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    studies = get_author_studies_query(user).order_by(Study.date.desc()).all()
    return render_template("mypost.html", studies=studies)


@app.route("/comment/write/<int:study_id>", methods=["POST"])
def comment_write(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)
    content = (request.form.get("content") or "").strip()
    parent_id = request.form.get("parent_id", type=int)

    if not content:
        flash("댓글 내용을 입력해주세요.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    parent_comment = None
    if parent_id is not None:
        parent_comment = get_or_404(Comment, parent_id)
        if parent_comment.study_id != study.id:
            abort(400, description="잘못된 댓글 요청입니다.")

    new_comment = Comment(
        content=content,
        writer=user.nickname,
        author_id=user.id,
        study_id=study.id,
        parent_id=parent_comment.id if parent_comment else None,
    )

    db.session.add(new_comment)
    db.session.commit()
    return redirect(url_for("study_detail", study_id=study_id))


@app.route("/comment/delete/<int:comment_id>", methods=["POST"])
def comment_delete(comment_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    comment = get_or_404(Comment, comment_id)
    if not is_comment_owner(comment, user):
        flash("삭제 권한이 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=comment.study_id))

    study_id = comment.study_id
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for("study_detail", study_id=study_id))


@app.route("/comment/like/<int:comment_id>", methods=["POST"])
def comment_like(comment_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    comment = get_or_404(Comment, comment_id)

    if user in comment.likers:
        comment.likers.remove(user)
    else:
        comment.likers.append(user)

    db.session.commit()
    return redirect(url_for("study_detail", study_id=comment.study_id))


@app.route("/study/apply/<int:study_id>", methods=["POST"])
def study_apply(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)

    if is_study_owner(study, user):
        flash("본인 스터디에는 신청할 수 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    if study.is_closed:
        flash("이미 모집이 마감된 스터디입니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    if approved_member_count(study) >= study.member_count:
        study.is_closed = True
        db.session.commit()
        flash("정원이 모두 차서 더 이상 신청할 수 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    existing_apply = Enrollment.query.filter_by(user_id=user.id, study_id=study_id).first()
    if existing_apply:
        messages = {
            0: "이미 신청한 스터디입니다. 승인 결과를 기다려주세요.",
            1: "이미 참여가 승인된 스터디입니다.",
            2: "이미 신청 이력이 있는 스터디입니다.",
        }
        flash(messages.get(existing_apply.status, "이미 신청한 스터디입니다."), "error")
        return redirect(url_for("study_detail", study_id=study_id))

    db.session.add(Enrollment(user_id=user.id, study_id=study_id))
    db.session.commit()
    flash("스터디 신청이 완료되었습니다.", "success")
    return redirect(url_for("study_detail", study_id=study_id))


@app.route("/mypage")
def mypage():
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    my_studies = get_author_studies_query(user).order_by(Study.date.desc()).all()
    my_enrollments = Enrollment.query.filter_by(user_id=user.id).order_by(Enrollment.date.desc()).all()

    return render_template("mypage.html", user=user, my_studies=my_studies, my_enrollments=my_enrollments)


@app.route("/chats")
def chats():
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    studies = get_accessible_chat_studies(user)
    return render_template("chat_list.html", studies=studies, user=user)


@app.route("/study/<int:study_id>/chat", methods=["GET", "POST"])
def study_chat(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)
    if not can_access_study_chat(study, user):
        flash("승인된 참여자만 채팅방에 입장할 수 있습니다.", "error")
        return redirect(url_for("study_detail", study_id=study.id))

    if request.method == "POST":
        payload = request.get_json(silent=True) if request.is_json else request.form
        content = normalize_text(payload.get("content"))
        if not content:
            if request.is_json:
                return jsonify({"ok": False, "message": "메시지를 입력해주세요."}), 400
            flash("메시지를 입력해주세요.", "error")
            return redirect(url_for("study_chat", study_id=study.id))
        if len(content) > 300:
            if request.is_json:
                return jsonify({"ok": False, "message": "메시지는 300자 이내로 입력해주세요."}), 400
            flash("메시지는 300자 이내로 입력해주세요.", "error")
            return redirect(url_for("study_chat", study_id=study.id))

        message = ChatMessage(content=content, study_id=study.id, user_id=user.id)
        db.session.add(message)
        db.session.commit()
        payload = serialize_chat_message(message)
        broadcast_chat_message(study.id, payload)

        if request.is_json:
            return jsonify({"ok": True, "message": payload})
        return redirect(url_for("study_chat", study_id=study.id))

    messages = study.chat_messages[-80:]
    return render_template(
        "study_chat.html",
        study=study,
        messages=messages,
        user=user,
        is_owner=is_study_owner(study, user),
    )


@app.route("/study/<int:study_id>/chat/stream")
def study_chat_stream(study_id):
    user = get_current_user()
    if not user:
        abort(401)

    study = get_or_404(Study, study_id)
    if not can_access_study_chat(study, user):
        abort(403)

    def generate():
        subscriber = queue.Queue()
        chat_subscribers[study.id].append(subscriber)
        try:
            while True:
                try:
                    payload = subscriber.get(timeout=20)
                    yield f"data: {dumps(payload, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            if subscriber in chat_subscribers.get(study.id, []):
                chat_subscribers[study.id].remove(subscriber)

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/update_profile", methods=["POST"])
def update_profile():
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    bio = normalize_optional_text(request.form.get("bio"))
    if bio and len(bio) > 50:
        flash("한줄 소개는 50자 이내로 입력해주세요.", "error")
        return redirect(url_for("mypage"))

    user.bio = bio
    db.session.commit()
    flash("한줄 소개가 업데이트되었습니다.", "success")
    return redirect(url_for("mypage"))


@app.route("/profile/<nickname>")
def profile(nickname):
    user = User.query.filter_by(nickname=nickname).first_or_404()
    studies = Study.query.filter_by(author_id=user.id).order_by(Study.date.desc()).all()
    return render_template("profile.html", target_user=user, studies=studies)


@app.route("/enrollment/<int:enrollment_id>/<action>", methods=["POST"])
def enrollment_action(enrollment_id, action):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    enrollment = get_or_404(Enrollment, enrollment_id)
    study = enrollment.study

    if not is_study_owner(study, user):
        flash("처리 권한이 없습니다.", "error")
        return redirect(url_for("mypage"))

    if action not in {"accept", "reject"}:
        abort(400, description="잘못된 요청입니다.")

    if enrollment.status != 0:
        flash("이미 처리된 신청입니다.", "error")
        return redirect(url_for("mypage"))

    if action == "accept":
        if approved_member_count(study) >= study.member_count:
            study.is_closed = True
            db.session.commit()
            flash("정원이 가득 차 더 이상 승인할 수 없습니다.", "error")
            return redirect(url_for("mypage"))
        enrollment.status = 1
        sync_closed_state(study)
        flash("신청자를 승인했습니다.", "success")
    else:
        enrollment.status = 2
        flash("신청을 거절했습니다.", "success")

    db.session.commit()
    return redirect(url_for("mypage"))


@app.route("/study/<int:study_id>/toggle_close", methods=["POST"])
def study_toggle_close(study_id):
    user = get_current_user()
    if not user:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    study = get_or_404(Study, study_id)
    if not is_study_owner(study, user):
        flash("권한이 없습니다.", "error")
        return redirect(url_for("study_detail", study_id=study_id))

    study.is_closed = not study.is_closed
    db.session.commit()
    flash("모집 상태가 변경되었습니다.", "success")
    return redirect(url_for("study_detail", study_id=study_id))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
