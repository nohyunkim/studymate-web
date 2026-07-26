import importlib
import os
import tempfile
import unittest


class StudyMatePublicPagesTestCase(unittest.TestCase):
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

    def test_public_information_pages_render(self):
        for path in ["/about", "/guide", "/faq", "/privacy", "/terms", "/contact"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("StudyMate", response.get_data(as_text=True))

    def test_editing_study_reopens_when_capacity_increases(self):
        with self.app.app_context():
            category = self.app_module.STUDY_CATEGORIES[0][1][0]
            owner = self.create_user("owner", "owner-nickname", "owner@example.com")
            guest = self.create_user("guest", "guest-nickname", "guest@example.com")
            study = self.Study(
                title="reopen-test",
                category=category,
                member_count=1,
                content="initial content",
                writer=owner["nickname"],
                author_id=owner["id"],
                is_closed=True,
            )
            self.db.session.add(study)
            self.db.session.commit()
            self.db.session.add(
                self.Enrollment(user_id=guest["id"], study_id=study.id, status=1)
            )
            self.db.session.commit()
            study_id = study.id

        self.login_as(owner)
        response = self.client.post(
            f"/study/{study_id}/edit",
            data={
                "_csrf_token": "test-token",
                "title": "reopen-test-updated",
                "category": category,
                "member_count": "2",
                "content": "updated content",
                "chat_link": "",
            },
            follow_redirects=True,
        )

        with self.app.app_context():
            study = self.db.session.get(self.Study, study_id)
            self.assertEqual(study.member_count, 2)
            self.assertFalse(study.is_closed)

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
