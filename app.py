from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
# [중요] models에서 Comment가 꼭 추가되어 있어야 합니다!
from models import db, User, Study, Comment
from sqlalchemy.sql.expression import func
import os

app = Flask(__name__)

# 세션용 시크릿 키 (로그인 정보를 안전하게 유지하기 위한 암호)
app.secret_key = 'secret-key-1234'

# DB 설정 (instance/database.db 파일 사용)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DB 연결 초기화
db.init_app(app)

# 1. 메인 페이지 (랜덤 스터디 3개 추천)
@app.route('/')
def home():
    # func.random()을 사용해서 스터디 중 3개를 무작위로 뽑아옵니다.
    random_studies = Study.query.order_by(func.random()).limit(3).all()

    return render_template(
        'index.html',
        user_nickname=session.get('user_nickname'), # 로그인한 사람 닉네임
        random_studies=random_studies
    )

@app.route('/index.html')
def index():
    return redirect(url_for('home'))

# 2. 로그인 기능
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # HTML 폼에서 보낸 아이디와 비번을 받습니다.
        userid = request.form['userid']
        password = request.form['password']

        # DB에서 해당 아이디를 가진 유저를 찾습니다.
        user = User.query.filter_by(userid=userid).first()

        # 유저가 있고, 비밀번호가 맞다면? (check_password_hash로 암호화된 비번 확인)
        if user and check_password_hash(user.password, password):
            # 세션에 정보를 저장해서 로그인 상태를 유지합니다.
            session['user_id'] = user.userid
            session['user_nickname'] = user.nickname
            return redirect(url_for('home'))
        else:
            return "아이디 또는 비밀번호가 틀렸습니다!"

    return render_template('login.html')

# 3. 로그아웃 기능
@app.route('/logout')
def logout():
    session.clear() # 세션 정보를 싹 비워서 로그아웃 처리
    return redirect(url_for('home'))

# 4. 아이디 중복 확인 (회원가입 시 사용)
@app.route('/check-userid')
def check_userid():
    userid = request.args.get('userid') # URL 뒤에 붙은 ?userid=... 값을 가져옴

    if not userid:
        return jsonify({'available': False, 'message': '아이디를 입력하세요.'})

    user = User.query.filter_by(userid=userid).first()

    if user:
        return jsonify({'available': False, 'message': '이미 사용 중인 아이디입니다.'})
    else:
        return jsonify({'available': True, 'message': '사용 가능한 아이디입니다!'})

# 5. 회원가입 기능
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']
        password_confirm = request.form['password_confirm']
        nickname = request.form['nickname']
        email = request.form['email']

        # 비밀번호 확인 검사
        if password != password_confirm:
            return "비밀번호가 서로 다릅니다!"

        # 아이디 중복 검사 (한 번 더 안전하게)
        if User.query.filter_by(userid=userid).first():
            return "이미 존재하는 아이디입니다!"
        
        # 이메일 중복 검사
        if User.query.filter_by(email=email).first():
            return "이미 가입된 이메일입니다!"

        # 비밀번호 암호화 (보안을 위해 필수!)
        hashed_password = generate_password_hash(password)
        
        # 새 유저 만들기
        new_user = User(
            userid=userid,
            password=hashed_password,
            nickname=nickname,
            email=email
        )

        db.session.add(new_user) # DB에 추가
        db.session.commit()      # 저장 확정

        return redirect(url_for('login'))

    return render_template('signup.html')

# 6. 스터디 목록 (검색 기능 포함)
@app.route('/study')
def study():
    page = request.args.get('page', 1, type=int) # 페이지 번호 (기본 1)
    keyword = request.args.get('keyword', type=str, default='') # 검색어 가져오기

    # 기본적으로는 날짜 최신순으로 정렬
    query = Study.query.order_by(Study.date.desc())

    # 만약 검색어(keyword)가 있다면? 제목에 포함된 것만 필터링
    if keyword:
        query = query.filter(Study.title.contains(keyword))

    # 페이지네이션 적용 (한 페이지에 9개씩)
    pagination = query.paginate(page=page, per_page=9)

    return render_template(
        'study.html',
        pagination=pagination,
        user_nickname=session.get('user_nickname'),
        keyword=keyword  # 검색어도 같이 템플릿으로 보내줍니다 (검색창 유지용)
    )

# 7. 스터디 글쓰기 (모집하기)
@app.route('/study/write', methods=['GET', 'POST'])
def studywrite():
    # 로그인 안 했으면 로그인 페이지로 보냄
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_study = Study(
            title=request.form['title'],
            category=request.form['category'],
            member_count=request.form['member_count'],
            content=request.form['content'],
            writer=session.get('user_nickname') # 현재 로그인한 사람 닉네임
        )

        db.session.add(new_study)
        db.session.commit()

        return redirect(url_for('study'))

    return render_template(
        'studywrite.html',
        user_nickname=session.get('user_nickname')
    )

# 8. 스터디 상세 페이지
@app.route('/study/<int:study_id>')
def study_detail(study_id):
    # 해당 번호의 스터디를 가져오고, 없으면 404 에러
    study = Study.query.get_or_404(study_id)
    
    # 댓글 좋아요 여부를 확인하기 위해 '현재 로그인한 유저 정보(객체)'가 필요함
    current_user = None
    if 'user_id' in session:
        current_user = User.query.filter_by(userid=session['user_id']).first()

    return render_template(
        'study_detail.html',
        study=study,
        user_nickname=session.get('user_nickname'),
        current_user=current_user # 이걸 HTML로 넘겨줘야 좋아요 눌렀는지 확인 가능!
    )

# 9. 스터디 삭제 기능
@app.route('/study/<int:study_id>/delete')
def study_delete(study_id):
    study = Study.query.get_or_404(study_id)

    # 본인이 쓴 글인지 확인
    if session.get('user_nickname') != study.writer:
        return "삭제 권한이 없습니다."

    db.session.delete(study)
    db.session.commit()

    return redirect(url_for('study'))

# 10. 스터디 수정 기능
@app.route('/study/<int:study_id>/edit', methods=['GET', 'POST'])
def study_edit(study_id):
    study = Study.query.get_or_404(study_id)

    # 본인이 쓴 글인지 확인
    if session.get('user_nickname') != study.writer:
        return "수정 권한이 없습니다."

    if request.method == 'POST':
        # 수정된 내용으로 덮어쓰기
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

# 11. 내가 쓴 글 보기
@app.route('/myposts')
def my_posts():
    if 'user_nickname' not in session:
        return redirect(url_for('login')) # 로그인 안했으면 쫓아냄

    nickname = session['user_nickname']
    
    # 작성자(writer)가 '나'인 글만 찾아서 가져옴 (최신순)
    my_studies = Study.query.filter_by(writer=nickname).order_by(Study.date.desc()).all()

    return render_template(
        'myposts.html', # myposts.html 파일이 있어야 함
        studies=my_studies,
        user_nickname=nickname
    )

# 12. 댓글 작성 (대댓글 포함)
@app.route('/comment/write/<int:study_id>', methods=['POST'])
def comment_write(study_id):
    if 'user_nickname' not in session:
        return "로그인이 필요합니다."

    content = request.form['content']
    parent_id = request.form.get('parent_id') # 대댓글인 경우 부모 댓글 번호가 옴
    
    # parent_id가 빈 문자열이면 None으로 변환 (그냥 댓글이라는 뜻)
    if not parent_id: 
        parent_id = None
    else:
        parent_id = int(parent_id)

    new_comment = Comment(
        content=content,
        writer=session['user_nickname'],
        study_id=study_id,
        parent_id=parent_id
    )

    db.session.add(new_comment)
    db.session.commit()

    return redirect(url_for('study_detail', study_id=study_id))

# 13. 댓글 삭제 (cascade로 대댓글도 자동 삭제됨)
@app.route('/comment/delete/<int:comment_id>')
def comment_delete(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    study_id = comment.study_id # 삭제하고 돌아갈 페이지 번호 저장

    # 본인 댓글인지 확인
    if session.get('user_nickname') != comment.writer:
        return "삭제 권한이 없습니다."

    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('study_detail', study_id=study_id))

# 14. [변경됨] 댓글 좋아요 토글 기능
@app.route('/comment/like/<int:comment_id>')
def comment_like(comment_id):
    # 로그인 체크
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 해당 댓글 찾기
    comment = Comment.query.get_or_404(comment_id)
    
    # 현재 로그인한 사람 정보 가져오기
    current_user = User.query.filter_by(userid=session['user_id']).first()

    # 이미 좋아요 리스트에 내가 있다면? -> 삭제 (취소)
    if current_user in comment.likers:
        comment.likers.remove(current_user)
    # 없다면? -> 추가 (좋아요)
    else:
        comment.likers.append(current_user)

    db.session.commit()

    # 댓글이 달린 스터디 페이지로 다시 돌아감
    return redirect(url_for('study_detail', study_id=comment.study_id))

# 서버 실행
if __name__ == '__main__':
    with app.app_context():
        # models.py에 정의된 테이블들이 없으면 자동 생성
        db.create_all()
    app.run(debug=True)