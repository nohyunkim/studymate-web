from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Study
from sqlalchemy.sql.expression import func
import os

app = Flask(__name__)

# 세션용 시크릿 키
app.secret_key = 'secret-key-1234'

# DB 설정 (instance/database.db 사용)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DB 연결
db.init_app(app)

# 1. 메인 페이지 (랜덤 3개 스터디)
@app.route('/')
def home():
    random_studies = Study.query.order_by(func.random()).limit(3).all()

    return render_template(
        'index.html',
        user_nickname=session.get('user_nickname'),
        random_studies=random_studies
    )

@app.route('/index.html')
def index():
    return redirect(url_for('home'))

# 2. 로그인
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']

        user = User.query.filter_by(userid=userid).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.userid
            session['user_nickname'] = user.nickname
            return redirect(url_for('home'))
        else:
            return "아이디 또는 비밀번호가 틀렸습니다!"

    return render_template('login.html')

# 3. 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# 4. 아이디 중복 확인 (AJAX)
@app.route('/check-userid')
def check_userid():
    userid = request.args.get('userid')

    if not userid:
        return jsonify({
            'available': False,
            'message': '아이디를 입력하세요.'
        })

    user = User.query.filter_by(userid=userid).first()

    if user:
        return jsonify({
            'available': False,
            'message': '이미 사용 중인 아이디입니다.'
        })
    else:
        return jsonify({
            'available': True,
            'message': '사용 가능한 아이디입니다!'
        })

# 5. 회원가입
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']
        password_confirm = request.form['password_confirm']
        nickname = request.form['nickname']
        email = request.form['email']

        if password != password_confirm:
            return "비밀번호가 서로 다릅니다!"

        if User.query.filter_by(userid=userid).first():
            return "이미 존재하는 아이디입니다!"

        if User.query.filter_by(email=email).first():
            return "이미 가입된 이메일입니다!"

        hashed_password = generate_password_hash(password)
        new_user = User(
            userid=userid,
            password=hashed_password,
            nickname=nickname,
            email=email
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('signup.html')

# 6. 스터디 목록
@app.route('/study')
def study():
    page = request.args.get('page', 1, type=int)

    pagination = Study.query.order_by(
        Study.date.desc()
    ).paginate(page=page, per_page=9)

    return render_template(
        'study.html',
        pagination=pagination,
        user_nickname=session.get('user_nickname')
    )

# 7. 스터디 글쓰기
@app.route('/study/write', methods=['GET', 'POST'])
def studywrite():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_study = Study(
            title=request.form['title'],
            category=request.form['category'],
            member_count=request.form['member_count'],
            content=request.form['content'],
            writer=session.get('user_nickname')
        )

        db.session.add(new_study)
        db.session.commit()

        return redirect(url_for('study'))

    return render_template(
        'studywrite.html',
        user_nickname=session.get('user_nickname')
    )

# 8. 스터디 상세
@app.route('/study/<int:study_id>')
def study_detail(study_id):
    study = Study.query.get_or_404(study_id)

    return render_template(
        'study_detail.html',
        study=study,
        user_nickname=session.get('user_nickname')
    )

# 9. 스터디 삭제
@app.route('/study/<int:study_id>/delete')
def study_delete(study_id):
    study = Study.query.get_or_404(study_id)

    if session.get('user_nickname') != study.writer:
        return "삭제 권한이 없습니다."

    db.session.delete(study)
    db.session.commit()

    return redirect(url_for('study'))

# 10. 스터디 수정
@app.route('/study/<int:study_id>/edit', methods=['GET', 'POST'])
def study_edit(study_id):
    study = Study.query.get_or_404(study_id)

    if session.get('user_nickname') != study.writer:
        return "수정 권한이 없습니다."

    if request.method == 'POST':
        study.title = request.form['title']
        study.category = request.form['category']
        study.member_count = request.form['member_count']
        study.content = request.form['content']

        db.session.commit()
        return redirect(url_for('study_detail', study_id=study.id))

    return render_template(
        'study_edit.html',
        study=study,
        user_nickname=session.get('user_nickname')
    )

# 서버 실행
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)