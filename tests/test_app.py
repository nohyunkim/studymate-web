import importlib
import json
import os
import tempfile
import unittest


class StudyMateAppTestCase(unittest.TestCase):
    def setUp(self):
        instance_dir = os.path.join(os.getcwd(), "instance")
        os.makedirs(instance_dir, exist_ok=True)
        fd, self.db_path = tempfile.mkstemp(prefix="test_", suffix=".db", dir=instance_dir)
        os.close(fd)

        self.original_db_uri = os.environ.get("STUDYMATE_DB_URI")
        self.original_secret = os.environ.get("SECRET_KEY")
        os.environ["STUDYMATE_DB_URI"] = "sqlite:///" + self.db_path.replace("\\", "/")
        os.environ["SECRET_KEY"] = "test-secret-key"

        import app as app_module

        self.app_module = importlib.reload(app_module)
        self.app = self.app_module.app
        self.db = self.app_module.db
        self.User = self.app_module.User
        self.Study = self.app_module.Study
        self.Comment = self.app_module.Comment
        self.ChatMessage = self.app_module.ChatMessage
        self.Enrollment = self.app_module.Enrollment
        self.client = self.app.test_client()

        with self.app.app_context():
            self.db.drop_all()
            self.db.create_all()
            self.app_module.run_schema_migrations()

    def tearDown(self):
        with self.app.app_context():
            self.db.session.remove()
            self.db.drop_all()
            self.db.engine.dispose()

        if self.original_db_uri is None:
            os.environ.pop("STUDYMATE_DB_URI", None)
        else:
            os.environ["STUDYMATE_DB_URI"] = self.original_db_uri

        if self.original_secret is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = self.original_secret

        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def create_user(self, userid, nickname, email):
        user = self.User(
            userid=userid,
            nickname=nickname,
            email=email,
            password=self.app_module.generate_password_hash("password123"),
        )
        self.db.session.add(user)
        self.db.session.commit()
        return {"id": user.id, "userid": user.userid, "nickname": user.nickname}

    def login_as(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user["userid"]
            session["user_nickname"] = user["nickname"]
            session["_csrf_token"] = "test-token"

    def test_category_filter_applies(self):
        with self.app.app_context():
            owner = self.create_user("owner", "개발왕", "owner@example.com")
            self.db.session.add(
                self.Study(
                    title="웹 개발 스터디",
                    category="웹 개발",
                    member_count=4,
                    content="프론트엔드와 백엔드 같이 공부합니다.",
                    writer=owner["nickname"],
                    author_id=owner["id"],
                )
            )
            self.db.session.add(
                self.Study(
                    title="토익 스터디",
                    category="토익 / 토플",
                    member_count=4,
                    content="매일 LC RC 문제 풀이",
                    writer=owner["nickname"],
                    author_id=owner["id"],
                )
            )
            self.db.session.commit()

        response = self.client.get("/study?category=웹 개발")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("웹 개발 스터디", html)
        self.assertNotIn("토익 스터디", html)

    def test_closed_study_blocks_application(self):
        with self.app.app_context():
            owner = self.create_user("owner", "방장", "owner@example.com")
            applicant = self.create_user("guest", "지원자", "guest@example.com")
            study = self.Study(
                title="마감된 스터디",
                category="웹 개발",
                member_count=2,
                content="이미 마감된 모집",
                writer=owner["nickname"],
                author_id=owner["id"],
                is_closed=True,
            )
            self.db.session.add(study)
            self.db.session.commit()
            study_id = study.id
            applicant_id = applicant["id"]

        self.login_as(applicant)
        response = self.client.post(
            f"/study/apply/{study_id}",
            data={"_csrf_token": "test-token"},
            follow_redirects=True,
        )

        with self.app.app_context():
            count = self.Enrollment.query.filter_by(user_id=applicant_id, study_id=study_id).count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(count, 0)
        self.assertIn("이미 모집이 마감된 스터디입니다.", response.get_data(as_text=True))

    def test_deleting_study_removes_comments_and_enrollments(self):
        with self.app.app_context():
            owner = self.create_user("owner", "운영자", "owner@example.com")
            guest = self.create_user("guest", "참여자", "guest@example.com")
            study = self.Study(
                title="삭제 테스트",
                category="웹 개발",
                member_count=3,
                content="삭제 시 연관 데이터도 함께 정리되어야 합니다.",
                writer=owner["nickname"],
                author_id=owner["id"],
            )
            self.db.session.add(study)
            self.db.session.commit()

            self.db.session.add(
                self.Comment(
                    content="댓글",
                    writer=guest["nickname"],
                    author_id=guest["id"],
                    study_id=study.id,
                )
            )
            self.db.session.add(self.Enrollment(user_id=guest["id"], study_id=study.id))
            self.db.session.commit()
            study_id = study.id

        self.login_as(owner)
        response = self.client.post(
            f"/study/{study_id}/delete",
            data={"_csrf_token": "test-token"},
            follow_redirects=True,
        )

        with self.app.app_context():
            self.assertEqual(self.Study.query.count(), 0)
            self.assertEqual(self.Comment.query.count(), 0)
            self.assertEqual(self.Enrollment.query.count(), 0)

        self.assertEqual(response.status_code, 200)

    def test_rejected_application_state_is_rendered(self):
        with self.app.app_context():
            owner = self.create_user("owner", "스터디장", "owner@example.com")
            guest = self.create_user("guest", "지원자", "guest@example.com")
            study = self.Study(
                title="거절 상태 테스트",
                category="웹 개발",
                member_count=4,
                content="상세 페이지에서 거절 상태를 보여줘야 합니다.",
                writer=owner["nickname"],
                author_id=owner["id"],
            )
            self.db.session.add(study)
            self.db.session.commit()

            self.db.session.add(
                self.Enrollment(user_id=guest["id"], study_id=study.id, status=2)
            )
            self.db.session.commit()
            study_id = study.id

        self.login_as(guest)
        response = self.client.get(f"/study/{study_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("신청이 거절된 스터디입니다.", response.get_data(as_text=True))

    def test_approved_member_can_access_study_chat_and_post_message(self):
        with self.app.app_context():
            owner = self.create_user("owner", "방장", "owner@example.com")
            guest = self.create_user("guest", "합격자", "guest@example.com")
            study = self.Study(
                title="채팅 테스트",
                category="웹 개발",
                member_count=4,
                content="승인된 멤버는 채팅에 들어갈 수 있어야 합니다.",
                writer=owner["nickname"],
                author_id=owner["id"],
            )
            self.db.session.add(study)
            self.db.session.commit()
            self.db.session.add(
                self.Enrollment(user_id=guest["id"], study_id=study.id, status=1)
            )
            self.db.session.commit()
            study_id = study.id

        self.login_as(guest)
        response = self.client.post(
            f"/study/{study_id}/chat",
            json={"content": "안녕하세요 반갑습니다"},
            headers={"X-CSRFToken": "test-token"},
        )

        with self.app.app_context():
            messages = self.ChatMessage.query.filter_by(study_id=study_id).all()

        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(messages), 1)
        self.assertEqual(payload["message"]["content"], "안녕하세요 반갑습니다")

    def test_pending_member_cannot_access_study_chat(self):
        with self.app.app_context():
            owner = self.create_user("owner", "방장", "owner@example.com")
            guest = self.create_user("guest", "대기자", "guest@example.com")
            study = self.Study(
                title="채팅 차단 테스트",
                category="웹 개발",
                member_count=4,
                content="승인 전에는 채팅 접근이 막혀야 합니다.",
                writer=owner["nickname"],
                author_id=owner["id"],
            )
            self.db.session.add(study)
            self.db.session.commit()
            self.db.session.add(
                self.Enrollment(user_id=guest["id"], study_id=study.id, status=0)
            )
            self.db.session.commit()
            study_id = study.id

        self.login_as(guest)
        response = self.client.get(f"/study/{study_id}/chat", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("승인된 참여자만 채팅방에 입장할 수 있습니다.", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
