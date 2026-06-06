from app import app
from models import db

with app.app_context():
    print("URI:", app.config["SQLALCHEMY_DATABASE_URI"])
    db.create_all()
    print("Tablas creadas correctamente")