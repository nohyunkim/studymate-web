from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
# 👇 [수정 1] Study 장부를 추가로 가져와야 함!
from models import db, User, Study 
import os

app = Flask(__name__)

# 🔑 보안을 위해 필요한 비밀키 (로그인 유지용)
app.secret_key = 'secret-key-1234' 

# DB 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DB 연결
db.init_app(app)

# 1. 메인 페이지
@app.route('/')
def home():
    # 로그인 여부에 따라 닉네임을 가져옴
    user_nickname = session.get('user_nickname')
    return render_template('index.html', user_nickname=user_nickname)

@app.route('/index.html')
def index():
    return home()

# 2. 로그인 기능
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
            return "아이디 또는 비밀번호가 틀렸습니다! (뒤로가기 눌러주세요)"

    return render_template('login.html')

# 3. 로그아웃 기능
@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('home'))

# 4. 회원가입 기능
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']
        password_confirm = request.form['password_confirm']
        nickname = request.form['nickname']
        email = request.form['email']

        if password != password_confirm:
            return "비밀번호가 서로 다릅니다! (뒤로가기 눌러서 다시 입력해주세요)"

        if User.query.filter_by(userid=userid).first():
            return "이미 존재하는 아이디입니다! (뒤로가기 눌러주세요)"
        
        if User.query.filter_by(email=email).first():
            return "이미 가입된 이메일입니다! (뒤로가기 눌러주세요)"

        hashed_password = generate_password_hash(password)
        new_user = User(userid=userid, password=hashed_password, nickname=nickname, email=email)
        
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('signup.html')

# 👇 [수정 2] 스터디 목록 기능 (9개씩 끊어서 보여주기)
@app.route('/study.html')
def study():
    # 1. 페이지 번호 가져오기 (기본값 1)
    page = request.args.get('page', 1, type=int)

    # 2. DB에서 최신순으로 9개씩 끊어서 가져오기 (paginate 기능)
    pagination = Study.query.order_by(Study.date.desc()).paginate(page=page, per_page=9)
    
    # 3. html로 데이터 전달
    return render_template('study.html', pagination=pagination)

# 👇 [수정 3] 스터디 글쓰기 기능 (DB에 저장)
@app.route('/studywrite.html', methods=['GET', 'POST'])
def studywrite():
    # 로그인 안 한 사람은 로그인 페이지로 쫓아내기
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # form에서 데이터 가져오기 (HTML name 속성과 일치해야 함)
        title = request.form['title']
        category = request.form['category']
        member_count = request.form['member_count']
        content = request.form['content']
        writer = session.get('user_nickname', '익명') # 작성자 닉네임

        # DB에 저장
        new_study = Study(title=title, category=category, member_count=member_count, content=content, writer=writer)
        db.session.add(new_study)
        db.session.commit()

        # 다 쓰면 목록으로 이동
        return redirect(url_for('study'))

    return render_template('studywrite.html')

# 5. 서버 실행
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)