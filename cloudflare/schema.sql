PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    nickname TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    bio TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS study (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    member_count INTEGER NOT NULL,
    content TEXT NOT NULL,
    date TEXT NOT NULL,
    writer TEXT NOT NULL,
    author_id INTEGER,
    chat_link TEXT,
    is_closed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (author_id) REFERENCES user(id) ON DELETE SET NULL
) STRICT;

CREATE TABLE IF NOT EXISTS enrollment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    study_id INTEGER NOT NULL,
    status INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL,
    UNIQUE (user_id, study_id),
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (study_id) REFERENCES study(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS comment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    date TEXT NOT NULL,
    writer TEXT NOT NULL,
    author_id INTEGER,
    study_id INTEGER NOT NULL,
    parent_id INTEGER,
    FOREIGN KEY (author_id) REFERENCES user(id) ON DELETE SET NULL,
    FOREIGN KEY (study_id) REFERENCES study(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES comment(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS comment_likes (
    user_id INTEGER NOT NULL,
    comment_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, comment_id),
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comment(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    date TEXT NOT NULL,
    study_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    FOREIGN KEY (study_id) REFERENCES study(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS ix_study_author_id ON study(author_id);
CREATE INDEX IF NOT EXISTS ix_study_date ON study(date DESC);
CREATE INDEX IF NOT EXISTS ix_enrollment_study_status ON enrollment(study_id, status);
CREATE INDEX IF NOT EXISTS ix_enrollment_user_date ON enrollment(user_id, date DESC);
CREATE INDEX IF NOT EXISTS ix_comment_study_parent ON comment(study_id, parent_id, date ASC);
CREATE INDEX IF NOT EXISTS ix_chat_message_study_date ON chat_message(study_id, date ASC, id ASC);