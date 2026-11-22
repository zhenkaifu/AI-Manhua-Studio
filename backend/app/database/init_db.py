from app.database.connection import Base, engine
from app.database import models  # noqa: F401  确保所有表被注册


def init_database():
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


if __name__ == "__main__":
    init_database()
