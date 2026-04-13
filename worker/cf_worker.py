import base64
import hashlib
import hmac
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlencode, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from js import Request as JsRequest
from js import URL
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from workers import Response, WorkerEntrypoint

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

SESSION_COOKIE_NAME = "studymate_session"
DEFAULT_SECRET = "dev-secret-change-me"
TEMPLATES_DIR = Path(__file__).parent / "templates"

ROUTE_PATTERNS = [
    ("home", ["GET"], re.compile(r"^/$")),
    ("index", ["GET"], re.compile(r"^/index\.html$")),
    ("login", ["GET", "POST"], re.compile(r"^/login$")),
    ("logout", ["POST"], re.compile(r"^/logout$")),
    ("check_userid", ["GET"], re.compile(r"^/check-userid$")),
    ("signup", ["GET", "POST"], re.compile(r"^/signup$")),
    ("study", ["GET"], re.compile(r"^/study$")),
    ("studywrite", ["GET", "POST"], re.compile(r"^/study/write$")),
    ("study_detail", ["GET"], re.compile(r"^/study/(?P<study_id>\d+)$")),
    ("study_delete", ["POST"], re.compile(r"^/study/(?P<study_id>\d+)/delete$")),
    ("study_edit", ["GET", "POST"], re.compile(r"^/study/(?P<study_id>\d+)/edit$")),
    ("study_apply", ["POST"], re.compile(r"^/study/apply/(?P<study_id>\d+)$")),
    ("study_chat", ["GET", "POST"], re.compile(r"^/study/(?P<study_id>\d+)/chat$")),
    ("study_chat_messages", ["GET"], re.compile(r"^/study/(?P<study_id>\d+)/chat/messages$")),
    ("study_toggle_close", ["POST"], re.compile(r"^/study/(?P<study_id>\d+)/toggle_close$")),
    ("mypage", ["GET"], re.compile(r"^/mypage$")),
    ("my_posts", ["GET"], re.compile(r"^/myposts$")),
    ("comment_write", ["POST"], re.compile(r"^/comment/write/(?P<study_id>\d+)$")),
    ("comment_delete", ["POST"], re.compile(r"^/comment/delete/(?P<comment_id>\d+)$")),
    ("comment_like", ["POST"], re.compile(r"^/comment/like/(?P<comment_id>\d+)$")),
    ("chats", ["GET"], re.compile(r"^/chats$")),
    ("update_profile", ["POST"], re.compile(r"^/update_profile$")),
    ("profile", ["GET"], re.compile(r"^/profile/(?P<nickname>[^/]+)$")),
    ("enrollment_action", ["POST"], re.compile(r"^/enrollment/(?P<enrollment_id>\d+)/(?P<action>accept|reject)$")),
]

URL_RULES = {
    "home": "/",
    "index": "/index.html",
    "login": "/login",
    "logout": "/logout",
    "check_userid": "/check-userid",
    "signup": "/signup",
    "study": "/study",
    "studywrite": "/study/write",
    "study_detail": "/study/{study_id}",
    "study_delete": "/study/{study_id}/delete",
    "study_edit": "/study/{study_id}/edit",
    "study_apply": "/study/apply/{study_id}",
    "study_chat": "/study/{study_id}/chat",
    "study_chat_messages": "/study/{study_id}/chat/messages",
    "study_toggle_close": "/study/{study_id}/toggle_close",
    "mypage": "/mypage",
    "my_posts": "/myposts",
    "comment_write": "/comment/write/{study_id}",
    "comment_delete": "/comment/delete/{comment_id}",
    "comment_like": "/comment/like/{comment_id}",
    "chats": "/chats",
    "update_profile": "/update_profile",
    "profile": "/profile/{nickname}",
    "enrollment_action": "/enrollment/{enrollment_id}/{action}",
}

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
jinja_env.filters["tojson"] = lambda value: Markup(json.dumps(value, ensure_ascii=False))


class HTTPError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total

    @property
    def pages(self):
        return max(1, math.ceil(self.total / self.per_page)) if self.total else 0

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def prev_num(self):
        return self.page - 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=2, right_edge=2):
        last = 0
        for number in range(1, self.pages + 1):
            if (
                number <= left_edge
                or (self.page - left_current - 1 < number < self.page + right_current)
                or number > self.pages - right_edge
            ):
                if last + 1 != number:
                    yield None
                yield number
                last = number


def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)


def now_iso():
    return get_kst_now().replace(microsecond=0).isoformat()


def parse_db_datetime(value):
    if not value:
        return get_kst_now()
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return get_kst_now()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


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


def build_user(row, prefix=""):
    if not row:
        return None
    return {
        "id": row[f"{prefix}id"],
        "userid": row[f"{prefix}userid"],
        "nickname": row[f"{prefix}nickname"],
        "email": row.get(f"{prefix}email"),
        "bio": row.get(f"{prefix}bio"),
    }


def build_study(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "member_count": int(row["member_count"]),
        "content": row["content"],
        "date": parse_db_datetime(row["date"]),
        "writer": row["writer"],
        "author_id": row.get("author_id"),
        "chat_link": row.get("chat_link"),
        "is_closed": bool(row.get("is_closed", 0)),
    }


def build_comment(row):
    return {
        "id": row["id"],
        "content": row["content"],
        "date": parse_db_datetime(row["date"]),
        "writer": row["writer"],
        "author_id": row.get("author_id"),
        "study_id": row["study_id"],
        "parent_id": row.get("parent_id"),
        "replies": [],
        "likers": [],
    }


def build_enrollment(row):
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "study_id": row["study_id"],
        "status": int(row["status"]),
        "date": parse_db_datetime(row["date"]),
    }


def build_chat_message(row):
    return {
        "id": row["id"],
        "content": row["content"],
        "date": parse_db_datetime(row["date"]),
        "study_id": row["study_id"],
        "user_id": row["message_user_id"],
        "user": build_user(row, "user_"),
    }


def approved_member_count(study):
    return sum(1 for enrollment in study.get("enrollments", []) if enrollment["status"] == 1)


def is_study_owner(study, user):
    return bool(user) and (
        study.get("author_id") == user["id"] or (study.get("author_id") is None and study.get("writer") == user["nickname"])
    )


def is_comment_owner(comment, user):
    return bool(user) and (
        comment.get("author_id") == user["id"] or (comment.get("author_id") is None and comment.get("writer") == user["nickname"])
    )


def serialize_chat_message(message):
    return {
        "id": message["id"],
        "content": message["content"],
        "date": message["date"].strftime("%m-%d %H:%M"),
        "writer": message["user"]["nickname"],
        "user_id": message["user_id"],
    }


def sign_session(payload, secret):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def unsign_session(token, secret):
    if not token or "." not in token:
        return {}
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return {}
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def parse_cookie_header(header_value):
    cookies = {}
    if not header_value:
        return cookies
    for chunk in header_value.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def build_set_cookie(name, value, secure=False):
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def delete_cookie(name, secure=False):
    parts = [f"{name}=", "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def js_to_py(value):
    if value is None:
        return None
    if hasattr(value, "to_py"):
        return value.to_py()
    return value


async def d1_run(env, sql, params=None):
    statement = env.DB.prepare(sql)
    if params:
        statement = statement.bind(*params)
    return js_to_py(await statement.run())


async def d1_rows(env, sql, params=None):
    result = await d1_run(env, sql, params)
    if isinstance(result, dict):
        return result.get("results", []) or []
    return []


async def d1_first(env, sql, params=None):
    rows = await d1_rows(env, sql, params)
    return rows[0] if rows else None


async def d1_execute(env, sql, params=None):
    result = await d1_run(env, sql, params)
    if isinstance(result, dict):
        meta = result.get("meta") or {}
        if meta.get("last_row_id") is not None:
            return meta.get("last_row_id")
        rows = result.get("results") or []
        if rows and isinstance(rows[0], dict) and "id" in rows[0]:
            return rows[0]["id"]
    return None


async def fetch_user_by_userid(env, userid):
    row = await d1_first(
        env,
        "SELECT id, userid, nickname, email, bio, password FROM user WHERE userid = ?",
        [userid],
    )
    return row


async def fetch_user_by_id(env, user_id):
    row = await d1_first(
        env,
        "SELECT id, userid, nickname, email, bio FROM user WHERE id = ?",
        [user_id],
    )
    return build_user(row)


async def fetch_user_by_nickname(env, nickname):
    row = await d1_first(
        env,
        "SELECT id, userid, nickname, email, bio FROM user WHERE nickname = ?",
        [nickname],
    )
    return build_user(row)


async def fetch_study_by_id(env, study_id):
    row = await d1_first(env, "SELECT * FROM study WHERE id = ?", [study_id])
    return build_study(row)


async def fetch_enrollment(env, user_id, study_id):
    row = await d1_first(
        env,
        "SELECT id, user_id, study_id, status, date FROM enrollment WHERE user_id = ? AND study_id = ?",
        [user_id, study_id],
    )
    return build_enrollment(row) if row else None


async def fetch_study_enrollments(env, study_id):
    rows = await d1_rows(
        env,
        """
        SELECT e.id, e.user_id AS member_user_id, e.study_id, e.status, e.date,
               u.id AS user_id, u.userid AS user_userid, u.nickname AS user_nickname,
               u.email AS user_email, u.bio AS user_bio
        FROM enrollment e
        JOIN user u ON u.id = e.user_id
        WHERE e.study_id = ?
        ORDER BY e.date DESC
        """,
        [study_id],
    )
    enrollments = []
    for row in rows:
        enrollment = {
            "id": row["id"],
            "user_id": row["member_user_id"],
            "study_id": row["study_id"],
            "status": int(row["status"]),
            "date": parse_db_datetime(row["date"]),
            "user": build_user(row, "user_"),
        }
        enrollments.append(enrollment)
    return enrollments


async def fetch_study_comments(env, study_id):
    rows = await d1_rows(
        env,
        "SELECT id, content, date, writer, author_id, study_id, parent_id FROM comment WHERE study_id = ? ORDER BY date ASC, id ASC",
        [study_id],
    )
    comments = {row["id"]: build_comment(row) for row in rows}
    if not comments:
        return []

    placeholders = ", ".join(["?"] * len(comments))
    like_rows = await d1_rows(
        env,
        f"""
        SELECT cl.comment_id,
               u.id, u.userid, u.nickname, u.email, u.bio
        FROM comment_likes cl
        JOIN user u ON u.id = cl.user_id
        WHERE cl.comment_id IN ({placeholders})
        ORDER BY cl.comment_id ASC
        """,
        list(comments.keys()),
    )
    for row in like_rows:
        comments[row["comment_id"]]["likers"].append(build_user(row))

    root_comments = []
    for comment in comments.values():
        parent_id = comment.get("parent_id")
        if parent_id and parent_id in comments:
            comments[parent_id]["replies"].append(comment)
        else:
            root_comments.append(comment)
    root_comments.sort(key=lambda item: (item["date"], item["id"]))
    for comment in comments.values():
        comment["replies"].sort(key=lambda item: (item["date"], item["id"]))
    return root_comments


async def fetch_chat_messages(env, study_id, limit=80, after_id=None):
    params = [study_id]
    sql = """
        SELECT cm.id, cm.content, cm.date, cm.study_id, cm.user_id AS message_user_id,
               u.id AS user_id, u.userid AS user_userid, u.nickname AS user_nickname,
               u.email AS user_email, u.bio AS user_bio
        FROM chat_message cm
        JOIN user u ON u.id = cm.user_id
        WHERE cm.study_id = ?
    """
    if after_id is not None:
        sql += " AND cm.id > ?"
        params.append(after_id)
    sql += " ORDER BY cm.date ASC, cm.id ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = await d1_rows(env, sql, params)
    return [build_chat_message(row) for row in rows]


async def fetch_current_user(env, session_data):
    userid = session_data.get("user_id")
    if not userid:
        return None
    row = await d1_first(env, "SELECT id, userid, nickname, email, bio FROM user WHERE userid = ?", [userid])
    return build_user(row)


async def fetch_author_studies(env, user):
    rows = await d1_rows(
        env,
        """
        SELECT *
        FROM study
        WHERE author_id = ? OR (author_id IS NULL AND writer = ?)
        ORDER BY date DESC, id DESC
        """,
        [user["id"], user["nickname"]],
    )
    return [build_study(row) for row in rows]


async def sync_closed_state(env, study_id):
    row = await d1_first(
        env,
        """
        SELECT s.member_count, COUNT(e.id) AS approved_count
        FROM study s
        LEFT JOIN enrollment e ON e.study_id = s.id AND e.status = 1
        WHERE s.id = ?
        GROUP BY s.id, s.member_count
        """,
        [study_id],
    )
    if not row:
        return
    should_close = int(row["approved_count"] or 0) >= int(row["member_count"])
    await d1_execute(env, "UPDATE study SET is_closed = ? WHERE id = ?", [1 if should_close else 0, study_id])


def url_for(endpoint, **values):
    if endpoint == "static":
        filename = values.pop("filename", "")
        path = "/static/" + quote(str(filename).lstrip("/"))
        if values:
            path += "?" + urlencode(values, doseq=True)
        return path
    if endpoint not in URL_RULES:
        raise KeyError(f"Unknown endpoint: {endpoint}")
    path = URL_RULES[endpoint]
    consumed = set()
    for key, value in values.items():
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, quote(str(value), safe=""))
            consumed.add(key)
    query_values = {key: value for key, value in values.items() if key not in consumed and value not in (None, "")}
    if query_values:
        path += "?" + urlencode(query_values, doseq=True)
    return path


class RequestContext:
    def __init__(self, env, request, endpoint, route_params):
        self.env = env
        self.request = request
        self.endpoint = endpoint
        self.route_params = route_params
        self.url = urlparse(request.url)
        self.query = {key: values[0] for key, values in parse_qs(self.url.query).items()}
        self.secret = env.SECRET_KEY if hasattr(env, "SECRET_KEY") and env.SECRET_KEY else DEFAULT_SECRET
        cookies = parse_cookie_header(request.headers.get("Cookie"))
        self.session = unsign_session(cookies.get(SESSION_COOKIE_NAME), self.secret)
        if not isinstance(self.session, dict):
            self.session = {}
        self.session.setdefault("flashes", [])
        self.mutated = False
        self._flashes_consumed = False
        self.current_user = None

    async def load_user(self):
        self.current_user = await fetch_current_user(self.env, self.session)
        if self.session.get("user_id") and self.current_user is None:
            self.session.clear()
            self.session["flashes"] = []
            self.mutated = True

    def flash(self, message, category="message"):
        self.session.setdefault("flashes", []).append([category, message])
        self.mutated = True

    def get_flashed_messages(self, with_categories=False):
        messages = self.session.get("flashes", []) if not self._flashes_consumed else []
        self.session["flashes"] = []
        self._flashes_consumed = True
        self.mutated = True
        if with_categories:
            return messages
        return [message for _, message in messages]

    def get_csrf_token(self):
        token = self.session.get("_csrf_token")
        if not token:
            token = hashlib.sha256(f"{self.url.path}:{now_iso()}".encode("utf-8")).hexdigest()
            self.session["_csrf_token"] = token
            self.mutated = True
        return token

    async def get_form(self):
        form_data = await self.request.formData()
        data = {}
        for key in form_data.keys():
            value = form_data.get(key)
            data[str(key)] = None if value is None else str(value)
        return data

    async def get_json(self):
        payload = js_to_py(await self.request.json())
        return payload if isinstance(payload, dict) else {}

    def require_login(self):
        if self.current_user:
            return None
        self.flash("로그인이 필요합니다.", "error")
        return self.redirect(url_for("login"))

    def redirect(self, location, status=302):
        response = Response("", status=status, headers={"Location": location})
        return self.finalize(response)

    def render(self, template_name, **context):
        template = jinja_env.get_template(template_name)
        rendered = template.render(
            url_for=url_for,
            request=SimpleNamespace(endpoint=self.endpoint, path=self.url.path),
            current_user=self.current_user,
            user_nickname=self.current_user["nickname"] if self.current_user else None,
            csrf_token=self.get_csrf_token(),
            study_categories=STUDY_CATEGORIES,
            showcase_visuals=HOME_SHOWCASE_VISUALS,
            get_flashed_messages=self.get_flashed_messages,
            **context,
        )
        response = Response(rendered, headers={"Content-Type": "text/html; charset=utf-8"})
        return self.finalize(response)

    def json(self, payload, status=200):
        response = Response.json(payload, status=status)
        return self.finalize(response)

    def text(self, text, status=200):
        response = Response(text, status=status, headers={"Content-Type": "text/plain; charset=utf-8"})
        return self.finalize(response)

    def finalize(self, response):
        secure = self.url.scheme == "https"
        if self.session.get("user_id") or self.session.get("_csrf_token") or self.session.get("flashes"):
            token = sign_session(self.session, self.secret)
            response.headers["Set-Cookie"] = build_set_cookie(SESSION_COOKIE_NAME, token, secure=secure)
        elif self.mutated:
            response.headers["Set-Cookie"] = delete_cookie(SESSION_COOKIE_NAME, secure=secure)
        return response


async def validate_csrf(ctx, form=None):
    if ctx.request.method != "POST":
        return
    session_token = ctx.session.get("_csrf_token")
    submitted_token = None
    if form is not None:
        submitted_token = form.get("_csrf_token")
    if submitted_token is None:
        submitted_token = ctx.request.headers.get("X-CSRFToken")
    if not session_token or session_token != submitted_token:
        raise HTTPError(400, "잘못된 요청입니다.")


def ensure_path_int(route_params, key):
    return int(route_params[key])


async def handle_home(ctx):
    rows = await d1_rows(ctx.env, "SELECT * FROM study ORDER BY RANDOM() LIMIT 4")
    studies = [build_study(row) for row in rows]
    return ctx.render("index.html", random_studies=studies)


async def handle_index(ctx):
    return ctx.redirect(url_for("home"))


async def handle_login(ctx):
    if ctx.request.method == "POST":
        form = await ctx.get_form()
        await validate_csrf(ctx, form)
        userid = normalize_text(form.get("userid"))
        password = form.get("password") or ""
        user_row = await fetch_user_by_userid(ctx.env, userid)
        if not user_row or not check_password_hash(user_row["password"], password):
            ctx.flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return ctx.redirect(url_for("login"))

        ctx.session = {
            "user_id": user_row["userid"],
            "user_nickname": user_row["nickname"],
            "_csrf_token": hashlib.sha256(f"{user_row['userid']}:{now_iso()}".encode("utf-8")).hexdigest(),
            "flashes": [["success", "로그인되었습니다."]],
        }
        ctx.mutated = True
        return ctx.redirect(url_for("home"))
    return ctx.render("login.html")


async def handle_logout(ctx):
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    ctx.session = {"flashes": [["success", "로그아웃되었습니다."]]}
    ctx.mutated = True
    return ctx.redirect(url_for("home"))


async def handle_check_userid(ctx):
    userid = normalize_text(ctx.query.get("userid", ""))
    if not userid:
        return ctx.json({"available": False, "message": "아이디를 입력하세요."})
    exists = await d1_first(ctx.env, "SELECT id FROM user WHERE userid = ?", [userid]) is not None
    return ctx.json(
        {
            "available": not exists,
            "message": "이미 사용 중인 아이디입니다." if exists else "사용 가능한 아이디입니다.",
        }
    )


async def handle_signup(ctx):
    if ctx.request.method == "POST":
        form = await ctx.get_form()
        await validate_csrf(ctx, form)
        userid = normalize_text(form.get("userid"))
        password = form.get("password") or ""
        password_confirm = form.get("password_confirm") or ""
        nickname = normalize_text(form.get("nickname"))
        email = normalize_text(form.get("email")).lower()

        if len(userid) < 4:
            ctx.flash("아이디는 4자 이상으로 입력해주세요.", "error")
            return ctx.redirect(url_for("signup"))
        if len(password) < 8:
            ctx.flash("비밀번호는 8자 이상이어야 합니다.", "error")
            return ctx.redirect(url_for("signup"))
        if password != password_confirm:
            ctx.flash("비밀번호 확인이 일치하지 않습니다.", "error")
            return ctx.redirect(url_for("signup"))
        if not nickname:
            ctx.flash("닉네임을 입력해주세요.", "error")
            return ctx.redirect(url_for("signup"))
        if await d1_first(ctx.env, "SELECT id FROM user WHERE userid = ?", [userid]):
            ctx.flash("이미 존재하는 아이디입니다.", "error")
            return ctx.redirect(url_for("signup"))
        if await d1_first(ctx.env, "SELECT id FROM user WHERE email = ?", [email]):
            ctx.flash("이미 가입된 이메일입니다.", "error")
            return ctx.redirect(url_for("signup"))
        if await d1_first(ctx.env, "SELECT id FROM user WHERE nickname = ?", [nickname]):
            ctx.flash("이미 사용 중인 닉네임입니다.", "error")
            return ctx.redirect(url_for("signup"))

        await d1_execute(
            ctx.env,
            "INSERT INTO user (userid, password, nickname, email, bio) VALUES (?, ?, ?, ?, NULL)",
            [userid, generate_password_hash(password), nickname, email],
        )
        ctx.flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return ctx.redirect(url_for("login"))
    return ctx.render("signup.html")


async def handle_study(ctx):
    page = int(ctx.query.get("page", "1") or "1")
    keyword = normalize_text(ctx.query.get("keyword", ""))
    category = normalize_text(ctx.query.get("category", ""))
    where_clauses = []
    params = []
    if keyword:
        where_clauses.append("(title LIKE ? OR content LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like])
    if category and category in CATEGORY_VALUES:
        where_clauses.append("category = ?")
        params.append(category)
    else:
        category = ""

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    count_row = await d1_first(ctx.env, f"SELECT COUNT(*) AS total FROM study {where_sql}", params)
    total = int(count_row["total"] if count_row else 0)
    per_page = 9
    offset = (page - 1) * per_page
    rows = await d1_rows(
        ctx.env,
        f"SELECT * FROM study {where_sql} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
        [*params, per_page, offset],
    )
    pagination = Pagination([build_study(row) for row in rows], page, per_page, total)
    return ctx.render("study.html", pagination=pagination, keyword=keyword, category=category)


async def handle_studywrite(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response

    if ctx.request.method == "POST":
        form = await ctx.get_form()
        await validate_csrf(ctx, form)
        try:
            payload = build_study_payload(form)
        except ValueError as error:
            ctx.flash(str(error), "error")
            return ctx.redirect(url_for("studywrite"))

        study_id = await d1_execute(
            ctx.env,
            """
            INSERT INTO study (title, category, member_count, content, date, writer, author_id, chat_link, is_closed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            RETURNING id
            """,
            [
                payload["title"],
                payload["category"],
                payload["member_count"],
                payload["content"],
                now_iso(),
                ctx.current_user["nickname"],
                ctx.current_user["id"],
                payload["chat_link"],
            ],
        )
        ctx.flash("스터디 모집글이 등록되었습니다.", "success")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    return ctx.render("studywrite.html")


async def load_study_bundle(ctx, study_id):
    study = await fetch_study_by_id(ctx.env, study_id)
    if not study:
        raise HTTPError(404, "스터디를 찾을 수 없습니다.")
    study["enrollments"] = await fetch_study_enrollments(ctx.env, study_id)
    study["chat_messages"] = await fetch_chat_messages(ctx.env, study_id, limit=80)
    return study


async def handle_study_detail(ctx):
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await load_study_bundle(ctx, study_id)
    enrollment = None
    if ctx.current_user:
        enrollment = await fetch_enrollment(ctx.env, ctx.current_user["id"], study_id)
    root_comments = await fetch_study_comments(ctx.env, study_id)
    approved_count = approved_member_count(study)
    return ctx.render(
        "study_detail.html",
        study=study,
        enrollment=enrollment,
        approved_count=approved_count,
        root_comments=root_comments,
        is_owner=is_study_owner(study, ctx.current_user),
        can_access_chat=can_access_study_chat(study, ctx.current_user),
    )


def can_access_study_chat(study, user):
    if not user:
        return False
    if is_study_owner(study, user):
        return True
    return any(enrollment["user_id"] == user["id"] and enrollment["status"] == 1 for enrollment in study.get("enrollments", []))


async def handle_study_delete(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await fetch_study_by_id(ctx.env, study_id)
    if not study:
        raise HTTPError(404, "스터디를 찾을 수 없습니다.")
    if not is_study_owner(study, ctx.current_user):
        ctx.flash("삭제 권한이 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))
    await d1_execute(ctx.env, "DELETE FROM study WHERE id = ?", [study_id])
    ctx.flash("스터디가 삭제되었습니다.", "success")
    return ctx.redirect(url_for("study"))


async def handle_study_edit(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await fetch_study_by_id(ctx.env, study_id)
    if not study:
        raise HTTPError(404, "스터디를 찾을 수 없습니다.")
    if not is_study_owner(study, ctx.current_user):
        ctx.flash("수정 권한이 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    if ctx.request.method == "POST":
        form = await ctx.get_form()
        await validate_csrf(ctx, form)
        try:
            payload = build_study_payload(form)
        except ValueError as error:
            ctx.flash(str(error), "error")
            return ctx.redirect(url_for("study_edit", study_id=study_id))

        await d1_execute(
            ctx.env,
            """
            UPDATE study
            SET title = ?, category = ?, member_count = ?, content = ?, chat_link = ?, writer = ?, author_id = ?
            WHERE id = ?
            """,
            [
                payload["title"],
                payload["category"],
                payload["member_count"],
                payload["content"],
                payload["chat_link"],
                ctx.current_user["nickname"],
                ctx.current_user["id"],
                study_id,
            ],
        )
        await sync_closed_state(ctx.env, study_id)
        ctx.flash("스터디가 수정되었습니다.", "success")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    return ctx.render("study_edit.html", study=study)


async def handle_my_posts(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    studies = await fetch_author_studies(ctx.env, ctx.current_user)
    return ctx.render("mypost.html", studies=studies)


async def handle_comment_write(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await fetch_study_by_id(ctx.env, study_id)
    if not study:
        raise HTTPError(404, "스터디를 찾을 수 없습니다.")
    content = (form.get("content") or "").strip()
    parent_id = form.get("parent_id")
    if not content:
        ctx.flash("댓글 내용을 입력해주세요.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))
    parent_comment_id = None
    if parent_id:
        parent_comment = await d1_first(ctx.env, "SELECT id, study_id FROM comment WHERE id = ?", [int(parent_id)])
        if not parent_comment or int(parent_comment["study_id"]) != study_id:
            raise HTTPError(400, "잘못된 댓글 요청입니다.")
        parent_comment_id = int(parent_comment["id"])

    await d1_execute(
        ctx.env,
        """
        INSERT INTO comment (content, date, writer, author_id, study_id, parent_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [content, now_iso(), ctx.current_user["nickname"], ctx.current_user["id"], study_id, parent_comment_id],
    )
    return ctx.redirect(url_for("study_detail", study_id=study_id))


async def handle_comment_delete(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    comment_id = ensure_path_int(ctx.route_params, "comment_id")
    row = await d1_first(
        ctx.env,
        "SELECT id, writer, author_id, study_id FROM comment WHERE id = ?",
        [comment_id],
    )
    if not row:
        raise HTTPError(404, "댓글을 찾을 수 없습니다.")
    comment = {"id": row["id"], "writer": row["writer"], "author_id": row.get("author_id"), "study_id": row["study_id"]}
    if not is_comment_owner(comment, ctx.current_user):
        ctx.flash("삭제 권한이 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=row["study_id"]))
    await d1_execute(ctx.env, "DELETE FROM comment WHERE id = ?", [comment_id])
    return ctx.redirect(url_for("study_detail", study_id=row["study_id"]))


async def handle_comment_like(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    comment_id = ensure_path_int(ctx.route_params, "comment_id")
    comment = await d1_first(ctx.env, "SELECT id, study_id FROM comment WHERE id = ?", [comment_id])
    if not comment:
        raise HTTPError(404, "댓글을 찾을 수 없습니다.")
    existing = await d1_first(
        ctx.env,
        "SELECT 1 AS present FROM comment_likes WHERE user_id = ? AND comment_id = ?",
        [ctx.current_user["id"], comment_id],
    )
    if existing:
        await d1_execute(ctx.env, "DELETE FROM comment_likes WHERE user_id = ? AND comment_id = ?", [ctx.current_user["id"], comment_id])
    else:
        await d1_execute(ctx.env, "INSERT INTO comment_likes (user_id, comment_id) VALUES (?, ?)", [ctx.current_user["id"], comment_id])
    return ctx.redirect(url_for("study_detail", study_id=comment["study_id"]))


async def handle_study_apply(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await load_study_bundle(ctx, study_id)
    if is_study_owner(study, ctx.current_user):
        ctx.flash("본인 스터디에는 신청할 수 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))
    if study["is_closed"]:
        ctx.flash("이미 모집이 마감된 스터디입니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))
    if approved_member_count(study) >= study["member_count"]:
        await d1_execute(ctx.env, "UPDATE study SET is_closed = 1 WHERE id = ?", [study_id])
        ctx.flash("정원이 모두 차서 더 이상 신청할 수 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    existing = await fetch_enrollment(ctx.env, ctx.current_user["id"], study_id)
    if existing:
        messages = {
            0: "이미 신청한 스터디입니다. 승인 결과를 기다려주세요.",
            1: "이미 참여가 승인된 스터디입니다.",
            2: "이미 신청 이력이 있는 스터디입니다.",
        }
        ctx.flash(messages.get(existing["status"], "이미 신청한 스터디입니다."), "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    await d1_execute(
        ctx.env,
        "INSERT INTO enrollment (user_id, study_id, status, date) VALUES (?, ?, 0, ?)",
        [ctx.current_user["id"], study_id, now_iso()],
    )
    ctx.flash("스터디 신청이 완료되었습니다.", "success")
    return ctx.redirect(url_for("study_detail", study_id=study_id))


async def handle_mypage(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response

    my_studies = await fetch_author_studies(ctx.env, ctx.current_user)
    for study in my_studies:
        study["enrollments"] = await fetch_study_enrollments(ctx.env, study["id"])

    enrollment_rows = await d1_rows(
        ctx.env,
        """
        SELECT e.id, e.user_id, e.study_id, e.status, e.date,
               s.title, s.category, s.member_count, s.content, s.date AS study_date,
               s.writer, s.author_id, s.chat_link, s.is_closed
        FROM enrollment e
        JOIN study s ON s.id = e.study_id
        WHERE e.user_id = ?
        ORDER BY e.date DESC, e.id DESC
        """,
        [ctx.current_user["id"]],
    )
    my_enrollments = []
    for row in enrollment_rows:
        enrollment = build_enrollment(row)
        study = build_study(
            {
                "id": row["study_id"],
                "title": row["title"],
                "category": row["category"],
                "member_count": row["member_count"],
                "content": row["content"],
                "date": row["study_date"],
                "writer": row["writer"],
                "author_id": row["author_id"],
                "chat_link": row["chat_link"],
                "is_closed": row["is_closed"],
            }
        )
        enrollment["study"] = study
        my_enrollments.append(enrollment)

    return ctx.render("mypage.html", user=ctx.current_user, my_studies=my_studies, my_enrollments=my_enrollments)


async def handle_chats(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response

    owned_rows = await d1_rows(
        ctx.env,
        "SELECT id FROM study WHERE author_id = ? OR (author_id IS NULL AND writer = ?)",
        [ctx.current_user["id"], ctx.current_user["nickname"]],
    )
    approved_rows = await d1_rows(
        ctx.env,
        "SELECT study_id AS id FROM enrollment WHERE user_id = ? AND status = 1",
        [ctx.current_user["id"]],
    )
    study_ids = sorted({int(row["id"]) for row in owned_rows + approved_rows})
    studies = []
    for study_id in study_ids:
        study = await fetch_study_by_id(ctx.env, study_id)
        if not study:
            continue
        messages = await fetch_chat_messages(ctx.env, study_id, limit=None)
        study["chat_messages"] = messages[-1:] if messages else []
        studies.append(study)
    studies.sort(key=lambda study: study["chat_messages"][-1]["date"] if study["chat_messages"] else study["date"], reverse=True)
    return ctx.render("chat_list.html", studies=studies, user=ctx.current_user)


async def handle_study_chat(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response

    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await load_study_bundle(ctx, study_id)
    if not can_access_study_chat(study, ctx.current_user):
        ctx.flash("승인된 참여자만 채팅방에 입장할 수 있습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))

    if ctx.request.method == "POST":
        is_json = "application/json" in (ctx.request.headers.get("Content-Type") or "")
        await validate_csrf(ctx)
        payload = await ctx.get_json() if is_json else await ctx.get_form()
        content = normalize_text(payload.get("content"))
        if not content:
            if is_json:
                return ctx.json({"ok": False, "message": "메시지를 입력해주세요."}, status=400)
            ctx.flash("메시지를 입력해주세요.", "error")
            return ctx.redirect(url_for("study_chat", study_id=study_id))
        if len(content) > 300:
            if is_json:
                return ctx.json({"ok": False, "message": "메시지는 300자 이내로 입력해주세요."}, status=400)
            ctx.flash("메시지는 300자 이내로 입력해주세요.", "error")
            return ctx.redirect(url_for("study_chat", study_id=study_id))

        message_id = await d1_execute(
            ctx.env,
            "INSERT INTO chat_message (content, date, study_id, user_id) VALUES (?, ?, ?, ?) RETURNING id",
            [content, now_iso(), study_id, ctx.current_user["id"]],
        )
        message = {
            "id": message_id,
            "content": content,
            "date": parse_db_datetime(now_iso()),
            "study_id": study_id,
            "user_id": ctx.current_user["id"],
            "user": ctx.current_user,
        }
        payload = serialize_chat_message(message)
        if is_json:
            return ctx.json({"ok": True, "message": payload})
        return ctx.redirect(url_for("study_chat", study_id=study_id))

    messages = await fetch_chat_messages(ctx.env, study_id, limit=80)
    return ctx.render(
        "study_chat.html",
        study=study,
        messages=messages,
        user=ctx.current_user,
        is_owner=is_study_owner(study, ctx.current_user),
        chat_stream_url="",
        chat_poll_url=url_for("study_chat_messages", study_id=study_id),
    )


async def handle_study_chat_messages(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await load_study_bundle(ctx, study_id)
    if not can_access_study_chat(study, ctx.current_user):
        raise HTTPError(403, "접근 권한이 없습니다.")
    after_id = ctx.query.get("after_id")
    after_value = int(after_id) if after_id and after_id.isdigit() else None
    messages = await fetch_chat_messages(ctx.env, study_id, limit=50, after_id=after_value)
    return ctx.json({"ok": True, "messages": [serialize_chat_message(message) for message in messages]})


async def handle_update_profile(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    bio = normalize_optional_text(form.get("bio"))
    if bio and len(bio) > 50:
        ctx.flash("한줄 소개는 50자 이내로 입력해주세요.", "error")
        return ctx.redirect(url_for("mypage"))
    await d1_execute(ctx.env, "UPDATE user SET bio = ? WHERE id = ?", [bio, ctx.current_user["id"]])
    ctx.flash("한줄 소개가 업데이트되었습니다.", "success")
    return ctx.redirect(url_for("mypage"))


async def handle_profile(ctx):
    nickname = ctx.route_params["nickname"]
    target_user = await fetch_user_by_nickname(ctx.env, nickname)
    if not target_user:
        raise HTTPError(404, "사용자를 찾을 수 없습니다.")
    rows = await d1_rows(
        ctx.env,
        "SELECT * FROM study WHERE author_id = ? ORDER BY date DESC, id DESC",
        [target_user["id"]],
    )
    studies = [build_study(row) for row in rows]
    return ctx.render("profile.html", target_user=target_user, studies=studies)


async def handle_enrollment_action(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    enrollment_id = ensure_path_int(ctx.route_params, "enrollment_id")
    action = ctx.route_params["action"]
    row = await d1_first(
        ctx.env,
        "SELECT id, user_id, study_id, status, date FROM enrollment WHERE id = ?",
        [enrollment_id],
    )
    if not row:
        raise HTTPError(404, "신청 정보를 찾을 수 없습니다.")
    enrollment = build_enrollment(row)
    study = await load_study_bundle(ctx, enrollment["study_id"])
    if not is_study_owner(study, ctx.current_user):
        ctx.flash("처리 권한이 없습니다.", "error")
        return ctx.redirect(url_for("mypage"))
    if enrollment["status"] != 0:
        ctx.flash("이미 처리된 신청입니다.", "error")
        return ctx.redirect(url_for("mypage"))

    if action == "accept":
        if approved_member_count(study) >= study["member_count"]:
            await d1_execute(ctx.env, "UPDATE study SET is_closed = 1 WHERE id = ?", [study["id"]])
            ctx.flash("정원이 가득 차 더 이상 승인할 수 없습니다.", "error")
            return ctx.redirect(url_for("mypage"))
        await d1_execute(ctx.env, "UPDATE enrollment SET status = 1 WHERE id = ?", [enrollment_id])
        await sync_closed_state(ctx.env, study["id"])
        ctx.flash("신청자를 승인했습니다.", "success")
    else:
        await d1_execute(ctx.env, "UPDATE enrollment SET status = 2 WHERE id = ?", [enrollment_id])
        ctx.flash("신청을 거절했습니다.", "success")
    return ctx.redirect(url_for("mypage"))


async def handle_study_toggle_close(ctx):
    redirect_response = ctx.require_login()
    if redirect_response:
        return redirect_response
    form = await ctx.get_form()
    await validate_csrf(ctx, form)
    study_id = ensure_path_int(ctx.route_params, "study_id")
    study = await fetch_study_by_id(ctx.env, study_id)
    if not study:
        raise HTTPError(404, "스터디를 찾을 수 없습니다.")
    if not is_study_owner(study, ctx.current_user):
        ctx.flash("권한이 없습니다.", "error")
        return ctx.redirect(url_for("study_detail", study_id=study_id))
    await d1_execute(ctx.env, "UPDATE study SET is_closed = ? WHERE id = ?", [0 if study["is_closed"] else 1, study_id])
    ctx.flash("모집 상태가 변경되었습니다.", "success")
    return ctx.redirect(url_for("study_detail", study_id=study_id))


HANDLERS = {
    "home": handle_home,
    "index": handle_index,
    "login": handle_login,
    "logout": handle_logout,
    "check_userid": handle_check_userid,
    "signup": handle_signup,
    "study": handle_study,
    "studywrite": handle_studywrite,
    "study_detail": handle_study_detail,
    "study_delete": handle_study_delete,
    "study_edit": handle_study_edit,
    "my_posts": handle_my_posts,
    "comment_write": handle_comment_write,
    "comment_delete": handle_comment_delete,
    "comment_like": handle_comment_like,
    "study_apply": handle_study_apply,
    "mypage": handle_mypage,
    "chats": handle_chats,
    "study_chat": handle_study_chat,
    "study_chat_messages": handle_study_chat_messages,
    "update_profile": handle_update_profile,
    "profile": handle_profile,
    "enrollment_action": handle_enrollment_action,
    "study_toggle_close": handle_study_toggle_close,
}


async def serve_static(env, request, path):
    target = URL.new(request.url)
    target.pathname = path[len("/static") :] or "/"
    return await env.ASSETS.fetch(JsRequest.new(target.toString(), request))


def match_route(path, method):
    for endpoint, methods, pattern in ROUTE_PATTERNS:
        if method not in methods:
            continue
        matched = pattern.match(path)
        if matched:
            return endpoint, matched.groupdict()
    return None, None


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if path.startswith("/static/"):
            return await serve_static(self.env, request, path)
        if path == "/favicon.ico":
            return Response("", status=204)

        endpoint, route_params = match_route(path, request.method)
        if endpoint is None:
            return Response("Not Found", status=404)

        ctx = RequestContext(self.env, request, endpoint, route_params)
        await ctx.load_user()
        try:
            return await HANDLERS[endpoint](ctx)
        except HTTPError as error:
            return ctx.text(error.message, status=error.status)
        except Exception:
            return ctx.text("서버 오류가 발생했습니다.", status=500)