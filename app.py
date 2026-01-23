from flask import Flask, render_template #도구상자 꺼내기

app = Flask(__name__) #Flask 서버 객체를 만드는 과정

# 1. 메인 페이지 (http://127.0.0.1:5000/)
@app.route('/')
def home():
    return render_template('index.html')

# 2. 링크들이 작동하도록 경로 설정
@app.route('/index.html')
def index():
    return render_template('index.html')

@app.route('/login.html')
def login():
    return render_template('login.html')

@app.route('/signup.html')
def signup():
    return render_template('signup.html')

@app.route('/study.html')
def study():
    return render_template('study.html')

@app.route('/studywrite.html')
def studywrite():
    return render_template('studywrite.html')

# 서버 켜기 (debug=True는 코드를 고치면 자동으로 재시작해주는 기능)
if __name__ == '__main__':
    app.run(debug=True)